#!/usr/bin/env python3
"""
Secrets Hygiene auditor for OpenClaw.

Scans installed skill directories for references to credentials (env vars,
config files, keychain entries). Flags stale or orphaned secrets and reports.
Updates own state.yaml after each run.

Usage:
    python3 audit.py                    # Run audit
    python3 audit.py --report-only      # Print last saved audit report
    python3 audit.py --dry-run          # Audit without updating state
    python3 audit.py --max-age-days N   # Custom staleness threshold (default: 90)
"""

import argparse
import os
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

OPENCLAW_DIR = Path(os.environ.get("OPENCLAW_HOME", Path.home() / ".openclaw"))
SKILL_STATE_DIR = OPENCLAW_DIR / "skill-state"
OWN_STATE_FILE = SKILL_STATE_DIR / "secrets-hygiene" / "state.yaml"

# Typical locations for OpenClaw skill installations
SKILL_SEARCH_PATHS = [
    OPENCLAW_DIR / "extensions",
    Path.home() / ".openclaw" / "skills",
]

# Credential pattern: variable names that indicate secrets
CREDENTIAL_PATTERNS = [
    r"\b([A-Z_]*(?:API_KEY|SECRET|TOKEN|PASSWORD|CREDENTIAL|PRIVATE_KEY|AUTH_KEY|ACCESS_KEY)[A-Z_]*)\b",
    r"keychain\s+['\"]([^'\"]+)['\"]",
    r"vault\s+['\"]([^'\"]+)['\"]",
    r"os\.environ(?:\.get)?\(['\"]([^'\"]*(?:KEY|SECRET|TOKEN|PASSWORD)[^'\"]*)['\"]",
    r"\$\{?([A-Z_]*(?:API_KEY|SECRET|TOKEN|PASSWORD)[A-Z_]*)\}?",
]

MAX_AGE_DAYS_DEFAULT = 90


def load_yaml_simple(path: Path) -> dict:
    """Minimal YAML loader for flat key: value state files."""
    if not path.exists():
        return {}
    try:
        text = path.read_text()
        if HAS_YAML:
            return yaml.safe_load(text) or {}
        result = {}
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                k, _, v = line.partition(":")
                result[k.strip()] = v.strip()
        return result
    except Exception:
        return {}


def dump_state(state: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if HAS_YAML:
        with open(path, "w") as f:
            yaml.dump(state, f, default_flow_style=False, allow_unicode=True)
    else:
        with open(path, "w") as f:
            for k, v in state.items():
                f.write(f"{k}: {v}\n")


def find_skill_dirs() -> list[Path]:
    """Locate all installed skill directories (containing SKILL.md)."""
    found = []
    for base in SKILL_SEARCH_PATHS:
        if not base.exists():
            continue
        for skill_md in base.rglob("SKILL.md"):
            found.append(skill_md.parent)
    return found


def scan_skill_for_credentials(skill_dir: Path) -> list[str]:
    """Return list of credential names referenced in this skill."""
    found = set()
    for filepath in skill_dir.rglob("*"):
        if not filepath.is_file():
            continue
        # Skip binary files and images
        suffix = filepath.suffix.lower()
        if suffix in (".png", ".jpg", ".jpeg", ".gif", ".ico", ".bin", ".pyc"):
            continue
        try:
            text = filepath.read_text(errors="ignore")
        except Exception:
            continue
        for pattern in CREDENTIAL_PATTERNS:
            for match in re.finditer(pattern, text):
                name = match.group(1) if match.lastindex else match.group(0)
                found.add(name.strip())
    return sorted(found)


def check_staleness(secret_name: str, tracked: dict, max_age_days: int) -> bool:
    """Return True if the secret should be flagged as stale."""
    last_rotated = tracked.get("last_rotated", "unknown")
    if last_rotated == "unknown" or not last_rotated:
        return True
    try:
        rotated_date = date.fromisoformat(last_rotated)
        age = (date.today() - rotated_date).days
        return age > max_age_days
    except ValueError:
        return True


def run_audit(max_age_days: int) -> dict:
    """Run the full audit and return results dict."""
    skill_dirs = find_skill_dirs()

    # Build map: secret_name -> list of skill names that use it
    secret_to_skills: dict[str, list[str]] = {}
    for skill_dir in skill_dirs:
        skill_name = skill_dir.name
        creds = scan_skill_for_credentials(skill_dir)
        for cred in creds:
            secret_to_skills.setdefault(cred, []).append(skill_name)

    # Load previous state to get rotation dates
    prev_state = load_yaml_simple(OWN_STATE_FILE)
    prev_tracked: list = prev_state.get("tracked_secrets", []) or []
    prev_map = {}
    if isinstance(prev_tracked, list):
        for entry in prev_tracked:
            if isinstance(entry, dict):
                prev_map[entry.get("name", "")] = entry

    # Build new tracked list
    tracked_secrets = []
    flagged = []
    orphaned = []
    installed_skill_names = {d.name for d in skill_dirs}

    for secret_name, using_skills in sorted(secret_to_skills.items()):
        prev = prev_map.get(secret_name, {})
        last_rotated = prev.get("last_rotated", "unknown")
        is_flagged = check_staleness(secret_name, prev, max_age_days)
        active_skills = [s for s in using_skills if s in installed_skill_names]
        is_orphaned = len(active_skills) == 0

        entry = {
            "name": secret_name,
            "skills_with_access": using_skills,
            "last_rotated": last_rotated,
            "flagged": is_flagged or is_orphaned,
        }
        tracked_secrets.append(entry)

        if is_flagged:
            flagged.append(secret_name)
        if is_orphaned:
            orphaned.append(secret_name)

    return {
        "tracked_secrets": tracked_secrets,
        "flagged": flagged,
        "orphaned": orphaned,
        "skill_dirs_scanned": len(skill_dirs),
    }


def print_report(results: dict, audit_date: str) -> None:
    tracked = results["tracked_secrets"]
    flagged = results["flagged"]
    orphaned = results["orphaned"]

    print(f"\nSecrets Audit — {audit_date}")
    print(f"{'─' * 40}")
    print(f"{len(tracked)} secrets tracked")
    print(f"{len(flagged)} flagged for rotation: {', '.join(flagged) or 'none'}")
    print(f"{len(orphaned)} orphaned (skill removed): {', '.join(orphaned) or 'none'}")
    print(f"Action needed: {'yes' if flagged or orphaned else 'no'}")
    print()
    if tracked:
        print("Details:")
        for entry in tracked:
            status_marker = "⚑" if entry.get("flagged") else "✓"
            print(f"  {status_marker}  {entry['name']}")
            print(f"       Skills: {', '.join(entry['skills_with_access'])}")
            print(f"       Last rotated: {entry['last_rotated']}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Secrets hygiene audit")
    parser.add_argument("--report-only", action="store_true", help="Print last saved report")
    parser.add_argument("--dry-run", action="store_true", help="Audit without updating state")
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=MAX_AGE_DAYS_DEFAULT,
        help=f"Days before a secret is considered stale (default: {MAX_AGE_DAYS_DEFAULT})",
    )
    args = parser.parse_args()

    if args.report_only:
        state = load_yaml_simple(OWN_STATE_FILE)
        if not state:
            print("No previous audit found. Run without --report-only first.")
            sys.exit(1)
        print(f"\nLast audit: {state.get('last_audit_at', 'unknown')}")
        print(f"Flagged: {state.get('flagged_count', 0)}, Orphaned: {state.get('orphaned_count', 0)}")
        sys.exit(0)

    today = date.today()
    print(f"Running secrets audit (max age: {args.max_age_days} days)...")
    results = run_audit(args.max_age_days)
    print_report(results, str(today))

    if not args.dry_run:
        state = {
            "last_audit_at": datetime.now().isoformat(),
            "flagged_count": len(results["flagged"]),
            "orphaned_count": len(results["orphaned"]),
            "status": "done",
            "tracked_secrets": results["tracked_secrets"],
        }
        dump_state(state, OWN_STATE_FILE)
        print(f"State updated: {OWN_STATE_FILE}")


if __name__ == "__main__":
    main()
