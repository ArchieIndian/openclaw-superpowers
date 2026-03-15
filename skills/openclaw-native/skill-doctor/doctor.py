#!/usr/bin/env python3
"""
Skill Doctor for openclaw-superpowers.

Diagnoses silent skill discovery failures: YAML parse errors, path
violations, schema mismatches, cron format problems. Reports every
issue that would cause a skill to silently disappear from the registry.

Usage:
    python3 doctor.py --scan                     # Full diagnostic pass
    python3 doctor.py --scan --only-failures     # FAILs only
    python3 doctor.py --scan --skill cron-hygiene  # Single skill
    python3 doctor.py --fix-hint cron-hygiene    # Actionable fix hint
    python3 doctor.py --status                   # Summary of last scan
    python3 doctor.py --format json              # Machine-readable output
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

OPENCLAW_DIR = Path(os.environ.get("OPENCLAW_HOME", Path.home() / ".openclaw"))
STATE_FILE = OPENCLAW_DIR / "skill-state" / "skill-doctor" / "state.yaml"
SUPERPOWERS_DIR = Path(os.environ.get(
    "SUPERPOWERS_DIR",
    Path.home() / ".openclaw" / "extensions" / "superpowers"
))
SKILLS_DIRS = [
    SUPERPOWERS_DIR / "skills" / "core",
    SUPERPOWERS_DIR / "skills" / "openclaw-native",
    SUPERPOWERS_DIR / "skills" / "community",
]
CRON_RE = re.compile(
    r'^(\*|[0-9,\-\/]+)\s+'
    r'(\*|[0-9,\-\/]+)\s+'
    r'(\*|[0-9,\-\/]+)\s+'
    r'(\*|[0-9,\-\/]+)\s+'
    r'(\*|[0-9,\-\/]+)$'
)
MAX_HISTORY = 10


# ── State helpers ─────────────────────────────────────────────────────────────

def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"violations": [], "scan_history": [], "skills_scanned": 0,
                "fail_count": 0, "warn_count": 0}
    try:
        text = STATE_FILE.read_text()
        return (yaml.safe_load(text) or {}) if HAS_YAML else {}
    except Exception:
        return {}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if HAS_YAML:
        with open(STATE_FILE, "w") as f:
            yaml.dump(state, f, default_flow_style=False, allow_unicode=True)


# ── Frontmatter parser ────────────────────────────────────────────────────────

def parse_frontmatter(skill_md: Path) -> tuple[dict, str]:
    """
    Returns (fields_dict, error_message).
    error_message is empty string on success.
    """
    try:
        text = skill_md.read_text()
    except Exception as e:
        return {}, f"Cannot read file: {e}"

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, "No frontmatter block found (file must start with ---)"

    end = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end = i
            break

    if end is None:
        return {}, "Frontmatter block not closed (missing closing ---)"

    fm_text = "\n".join(lines[1:end])
    if not HAS_YAML:
        # Minimal key:value parser
        fields = {}
        for line in fm_text.splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                fields[k.strip()] = v.strip().strip('"').strip("'")
        return fields, ""

    try:
        fields = yaml.safe_load(fm_text) or {}
        return fields, ""
    except Exception as e:
        return {}, f"YAML parse error: {e}"


# ── Per-skill diagnostic ──────────────────────────────────────────────────────

def diagnose_skill(skill_dir: Path) -> list[dict]:
    """Returns list of violation dicts (empty = all clear)."""
    violations = []
    skill_name = skill_dir.name
    skill_md = skill_dir / "SKILL.md"
    now = datetime.now().isoformat()

    def violation(level, check, message, fix_hint):
        return {
            "skill_name": skill_name,
            "level": level,
            "check": check,
            "message": message,
            "fix_hint": fix_hint,
            "detected_at": now,
            "resolved": False,
        }

    if not skill_md.exists():
        violations.append(violation(
            "FAIL", "SKILL_MD_MISSING",
            f"No SKILL.md in {skill_dir}",
            "Create SKILL.md with ---frontmatter--- block."
        ))
        return violations

    fm, parse_err = parse_frontmatter(skill_md)

    # Check 1: YAML parse
    if parse_err:
        violations.append(violation(
            "FAIL", "YAML_PARSE",
            f"Frontmatter unparseable: {parse_err}",
            "Fix YAML syntax in the --- block at the top of SKILL.md."
        ))
        return violations  # Can't continue without parseable frontmatter

    # Check 2: Required fields
    for field in ("name", "description"):
        if not fm.get(field):
            violations.append(violation(
                "FAIL", "REQUIRED_FIELD",
                f"Missing required frontmatter field: `{field}`",
                f"Add `{field}: <value>` to the frontmatter block."
            ))

    # Check 3: Path convention
    fm_name = fm.get("name", "")
    if fm_name and fm_name != skill_name:
        violations.append(violation(
            "FAIL", "PATH_MISMATCH",
            f"Directory name `{skill_name}` does not match `name: {fm_name}`",
            f"Rename directory to `{fm_name}` or update `name:` in frontmatter."
        ))

    # Check 4: Cron format
    cron_val = fm.get("cron", "")
    if cron_val:
        cron_str = str(cron_val).strip()
        if not CRON_RE.match(cron_str):
            violations.append(violation(
                "FAIL", "CRON_FORMAT",
                f"Invalid cron expression: `{cron_str}`",
                "Use a valid 5-field cron: `minute hour day month weekday` (e.g. `0 9 * * 1-5`)."
            ))

    # Check 5: Stateful coherence
    schema_file = skill_dir / "STATE_SCHEMA.yaml"
    is_stateful = str(fm.get("stateful", "")).lower() == "true"

    if is_stateful and not schema_file.exists():
        violations.append(violation(
            "FAIL", "STATEFUL_NO_SCHEMA",
            "`stateful: true` in frontmatter but STATE_SCHEMA.yaml is missing",
            "Create STATE_SCHEMA.yaml with `version:` and `fields:` keys."
        ))
    elif schema_file.exists() and not is_stateful:
        violations.append(violation(
            "WARN", "SCHEMA_NO_STATEFUL",
            "STATE_SCHEMA.yaml exists but `stateful: true` is absent from frontmatter",
            "Add `stateful: true` to the frontmatter block."
        ))

    # Check 6: Schema validity
    if schema_file.exists() and HAS_YAML:
        try:
            schema = yaml.safe_load(schema_file.read_text()) or {}
            if "version" not in schema:
                violations.append(violation(
                    "WARN", "SCHEMA_NO_VERSION",
                    "STATE_SCHEMA.yaml missing `version:` key",
                    "Add `version: \"1.0\"` to STATE_SCHEMA.yaml."
                ))
            if "fields" not in schema:
                violations.append(violation(
                    "WARN", "SCHEMA_NO_FIELDS",
                    "STATE_SCHEMA.yaml missing `fields:` key",
                    "Add a `fields:` block defining your state shape."
                ))
        except Exception as e:
            violations.append(violation(
                "FAIL", "SCHEMA_PARSE",
                f"STATE_SCHEMA.yaml unparseable: {e}",
                "Fix YAML syntax in STATE_SCHEMA.yaml."
            ))

    return violations


# ── Scan ──────────────────────────────────────────────────────────────────────

def scan(only_failures=False, single_skill=None) -> tuple[list, int, int, int]:
    """Returns (violations, skills_scanned, fail_count, warn_count)."""
    all_violations = []
    skills_scanned = 0

    for skills_root in SKILLS_DIRS:
        if not skills_root.exists():
            continue
        for skill_dir in sorted(skills_root.iterdir()):
            if not skill_dir.is_dir():
                continue
            if single_skill and skill_dir.name != single_skill:
                continue
            viols = diagnose_skill(skill_dir)
            skills_scanned += 1
            if only_failures:
                viols = [v for v in viols if v["level"] == "FAIL"]
            all_violations.extend(viols)

    fail_count = sum(1 for v in all_violations if v["level"] == "FAIL")
    warn_count = sum(1 for v in all_violations if v["level"] == "WARN")
    return all_violations, skills_scanned, fail_count, warn_count


# ── Fix hints ─────────────────────────────────────────────────────────────────

def print_fix_hints(skill_name: str, state: dict) -> None:
    violations = [v for v in (state.get("violations") or [])
                  if v.get("skill_name") == skill_name]
    if not violations:
        print(f"No recorded violations for '{skill_name}'. Run --scan first.")
        return
    print(f"\nFix hints for: {skill_name}")
    print("─" * 40)
    for v in violations:
        print(f"  [{v['level']}] {v['check']}")
        print(f"    Problem : {v['message']}")
        print(f"    Fix     : {v['fix_hint']}")
        print()


# ── Output formatting ─────────────────────────────────────────────────────────

def print_report(violations: list, skills_scanned: int,
                 fail_count: int, warn_count: int, fmt: str = "text") -> None:
    if fmt == "json":
        print(json.dumps({
            "skills_scanned": skills_scanned,
            "fail_count": fail_count,
            "warn_count": warn_count,
            "violations": violations,
        }, indent=2))
        return

    print(f"\nSkill Doctor Report — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("─" * 48)
    print(f"  Skills scanned : {skills_scanned}")
    print(f"  FAILs          : {fail_count}")
    print(f"  WARNs          : {warn_count}")
    print()

    if not violations:
        print("  ✓ All skills healthy — no issues detected.")
    else:
        # Group by skill
        by_skill: dict = {}
        for v in violations:
            by_skill.setdefault(v["skill_name"], []).append(v)
        for skill_name, viols in sorted(by_skill.items()):
            for v in viols:
                icon = "✗" if v["level"] == "FAIL" else "⚠"
                print(f"  {icon} [{v['level']:4s}] {skill_name}: {v['check']}")
                print(f"         {v['message']}")
    print()


# ── Status ────────────────────────────────────────────────────────────────────

def print_status(state: dict) -> None:
    last = state.get("last_scan_at", "never")
    scanned = state.get("skills_scanned", 0)
    fails = state.get("fail_count", 0)
    warns = state.get("warn_count", 0)
    print(f"\nSkill Doctor — Last scan: {last}")
    print(f"  {scanned} skills | {fails} FAILs | {warns} WARNs")
    active = [v for v in (state.get("violations") or []) if not v.get("resolved")]
    if active:
        print(f"\n  Active issues ({len(active)}):")
        for v in active:
            print(f"    [{v['level']}] {v['skill_name']}: {v['check']}")
    print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Skill Doctor — diagnose skill loading failures")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--scan", action="store_true", help="Run full diagnostic scan")
    group.add_argument("--fix-hint", metavar="SKILL", help="Print fix hint for a skill")
    group.add_argument("--status", action="store_true", help="Show last scan summary")
    parser.add_argument("--only-failures", action="store_true",
                        help="With --scan, show FAILs only")
    parser.add_argument("--skill", metavar="SKILL",
                        help="With --scan, scan a single skill only")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    state = load_state()

    if args.status:
        print_status(state)
        return

    if args.fix_hint:
        print_fix_hints(args.fix_hint, state)
        return

    if args.scan:
        violations, scanned, fails, warns = scan(
            only_failures=args.only_failures,
            single_skill=args.skill,
        )
        print_report(violations, scanned, fails, warns, fmt=args.format)

        # Persist
        now = datetime.now().isoformat()
        history = state.get("scan_history") or []
        history.insert(0, {
            "scanned_at": now,
            "skills_scanned": scanned,
            "fail_count": fails,
            "warn_count": warns,
        })
        state["scan_history"] = history[:MAX_HISTORY]
        state["last_scan_at"] = now
        state["skills_scanned"] = scanned
        state["fail_count"] = fails
        state["warn_count"] = warns
        state["violations"] = violations
        save_state(state)

        sys.exit(1 if fails > 0 else 0)


if __name__ == "__main__":
    main()
