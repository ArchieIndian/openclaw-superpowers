#!/usr/bin/env python3
"""
Skill Compatibility Checker for openclaw-superpowers.

Checks installed skills against the current OpenClaw version for
version constraints and feature availability.

Usage:
    python3 check.py --check
    python3 check.py --check --skill channel-context-bridge
    python3 check.py --openclaw-version 1.5.0  # override detected version
    python3 check.py --features                 # list feature registry
    python3 check.py --status                   # last check summary
    python3 check.py --format json
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

OPENCLAW_DIR = Path(os.environ.get("OPENCLAW_HOME", Path.home() / ".openclaw"))
STATE_FILE = OPENCLAW_DIR / "skill-state" / "skill-compatibility-checker" / "state.yaml"
SUPERPOWERS_DIR = Path(os.environ.get(
    "SUPERPOWERS_DIR",
    Path.home() / ".openclaw" / "extensions" / "superpowers"
))
SKILLS_DIRS = [
    SUPERPOWERS_DIR / "skills" / "core",
    SUPERPOWERS_DIR / "skills" / "openclaw-native",
    SUPERPOWERS_DIR / "skills" / "community",
]
MAX_HISTORY = 10

# Feature availability: feature_name -> introduced_in (as tuple)
FEATURE_REGISTRY = {
    "cron":               (1, 0, 0),
    "state_storage":      (1, 0, 0),
    "session_isolation":  (1, 2, 0),
    "context_compaction": (1, 3, 0),
    "sessions_send":      (1, 4, 0),
}


# ── Version helpers ───────────────────────────────────────────────────────────

def parse_version(v: str) -> tuple[int, ...]:
    """Parse '1.2.3' → (1, 2, 3). Returns (0,) on failure."""
    try:
        return tuple(int(x) for x in re.findall(r'\d+', str(v)))
    except Exception:
        return (0,)


def version_str(t: tuple) -> str:
    return ".".join(str(x) for x in t)


def satisfies_constraint(version: tuple, constraint: str) -> tuple[bool, str]:
    """
    Check semver constraint like '>=1.2.0', '==1.3.0', '>1.0'.
    Returns (ok, explanation).
    """
    constraint = constraint.strip()
    m = re.match(r'^(>=|<=|==|!=|>|<)\s*(.+)$', constraint)
    if not m:
        return True, ""  # can't parse → assume compatible

    op, ver_str = m.group(1), m.group(2).strip()
    required = parse_version(ver_str)

    ops = {
        ">=": lambda a, b: a >= b,
        "<=": lambda a, b: a <= b,
        "==": lambda a, b: a == b,
        "!=": lambda a, b: a != b,
        ">":  lambda a, b: a > b,
        "<":  lambda a, b: a < b,
    }
    ok = ops[op](version, required)
    explanation = f"{op}{ver_str}"
    return ok, explanation


def detect_openclaw_version() -> tuple[int, ...]:
    """Try to detect OpenClaw version from CLI or version file."""
    # Try CLI
    try:
        result = subprocess.run(
            ["openclaw", "--version"],
            capture_output=True, text=True, timeout=5
        )
        output = result.stdout.strip() or result.stderr.strip()
        m = re.search(r'(\d+\.\d+(?:\.\d+)?)', output)
        if m:
            return parse_version(m.group(1))
    except Exception:
        pass

    # Try version file
    for candidate in [
        OPENCLAW_DIR / "VERSION",
        OPENCLAW_DIR / "version.txt",
        Path("/usr/local/lib/openclaw/VERSION"),
    ]:
        if candidate.exists():
            try:
                return parse_version(candidate.read_text().strip())
            except Exception:
                pass

    return (1, 0, 0)  # safe fallback


# ── Frontmatter parser ────────────────────────────────────────────────────────

def parse_frontmatter(skill_md: Path) -> dict:
    try:
        text = skill_md.read_text()
        lines = text.splitlines()
        if not lines or lines[0].strip() != "---":
            return {}
        end = None
        for i, line in enumerate(lines[1:], 1):
            if line.strip() == "---":
                end = i
                break
        if end is None:
            return {}
        fm_text = "\n".join(lines[1:end])
        if HAS_YAML:
            return yaml.safe_load(fm_text) or {}
        # Minimal fallback
        fields = {}
        for line in fm_text.splitlines():
            if ":" in line and not line.startswith(" "):
                k, _, v = line.partition(":")
                fields[k.strip()] = v.strip().strip('"').strip("'")
        return fields
    except Exception:
        return {}


# ── State helpers ─────────────────────────────────────────────────────────────

def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"incompatibilities": [], "check_history": []}
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


# ── Check logic ───────────────────────────────────────────────────────────────

def check_skill(skill_dir: Path, oc_version: tuple) -> list[dict]:
    skill_name = skill_dir.name
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return []

    fm = parse_frontmatter(skill_md)
    now = datetime.now().isoformat()
    issues = []

    def issue(level, constraint, feature, detail):
        return {
            "skill_name": skill_name,
            "level": level,
            "constraint": constraint,
            "feature": feature,
            "detail": detail,
            "detected_at": now,
        }

    # Check requires_openclaw version constraint
    req_ver = fm.get("requires_openclaw", "")
    if req_ver:
        ok, explanation = satisfies_constraint(oc_version, str(req_ver))
        if not ok:
            issues.append(issue(
                "FAIL",
                str(req_ver),
                "openclaw_version",
                f"Requires OpenClaw {explanation}, have {version_str(oc_version)}"
            ))

    # Check requires_features list
    req_features = fm.get("requires_features") or []
    if isinstance(req_features, str):
        req_features = [req_features]

    for feature in req_features:
        feature = str(feature).strip()
        if feature not in FEATURE_REGISTRY:
            issues.append(issue(
                "WARN",
                "",
                feature,
                f"Unknown feature '{feature}' — not in feature registry"
            ))
            continue
        introduced = FEATURE_REGISTRY[feature]
        if oc_version < introduced:
            level = "FAIL" if oc_version < introduced else "WARN"
            issues.append(issue(
                level,
                f">={version_str(introduced)}",
                feature,
                f"Requires feature '{feature}' (≥{version_str(introduced)}), "
                f"have {version_str(oc_version)}"
            ))

    return issues


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_check(state: dict, oc_version: tuple, single_skill: str,
              fmt: str) -> None:
    all_issues = []
    skills_checked = 0

    for skills_root in SKILLS_DIRS:
        if not skills_root.exists():
            continue
        for skill_dir in sorted(skills_root.iterdir()):
            if not skill_dir.is_dir():
                continue
            if single_skill and skill_dir.name != single_skill:
                continue
            issues = check_skill(skill_dir, oc_version)
            all_issues.extend(issues)
            skills_checked += 1

    fails = sum(1 for i in all_issues if i["level"] == "FAIL")
    warns = sum(1 for i in all_issues if i["level"] == "WARN")
    now = datetime.now().isoformat()

    if fmt == "json":
        print(json.dumps({
            "checked_at": now,
            "openclaw_version": version_str(oc_version),
            "skills_checked": skills_checked,
            "fail_count": fails,
            "warn_count": warns,
            "incompatibilities": all_issues,
        }, indent=2))
    else:
        print(f"\nSkill Compatibility Check — OpenClaw {version_str(oc_version)}")
        print("─" * 50)
        print(f"  {skills_checked} skills checked | "
              f"{fails} incompatible | {warns} warnings")
        print()
        if not all_issues:
            print("  ✓ All skills compatible.")
        else:
            for issue in all_issues:
                icon = "✗" if issue["level"] == "FAIL" else "⚠"
                print(f"  {icon} {issue['level']:4s}  {issue['skill_name']}: "
                      f"{issue['detail']}")
        print()

    # Persist
    history = state.get("check_history") or []
    history.insert(0, {
        "checked_at": now,
        "openclaw_version": version_str(oc_version),
        "skills_checked": skills_checked,
        "fail_count": fails,
        "warn_count": warns,
    })
    state["check_history"] = history[:MAX_HISTORY]
    state["last_check_at"] = now
    state["openclaw_version"] = version_str(oc_version)
    state["incompatibilities"] = all_issues
    save_state(state)

    sys.exit(1 if fails > 0 else 0)


def cmd_features(fmt: str) -> None:
    if fmt == "json":
        print(json.dumps({k: version_str(v) for k, v in FEATURE_REGISTRY.items()},
                         indent=2))
        return
    print("\nOpenClaw Feature Registry")
    print("─" * 40)
    for feature, introduced in sorted(FEATURE_REGISTRY.items(),
                                      key=lambda x: x[1]):
        print(f"  {feature:25s}  introduced in {version_str(introduced)}")
    print()


def cmd_status(state: dict) -> None:
    last = state.get("last_check_at", "never")
    ver = state.get("openclaw_version", "unknown")
    history = state.get("check_history") or []
    print(f"\nSkill Compatibility Checker — Last run: {last} (OpenClaw {ver})")
    if history:
        h = history[0]
        print(f"  {h['skills_checked']} checked | "
              f"{h['fail_count']} incompatible | {h['warn_count']} warnings")
    active = state.get("incompatibilities") or []
    if active:
        print(f"\n  Active incompatibilities ({len(active)}):")
        for i in active[:5]:
            print(f"    [{i['level']}] {i['skill_name']}: {i['detail'][:60]}")
    print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Skill Compatibility Checker")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--features", action="store_true")
    group.add_argument("--status", action="store_true")
    parser.add_argument("--skill", metavar="NAME")
    parser.add_argument("--openclaw-version", metavar="VER",
                        help="Override detected OpenClaw version")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    state = load_state()

    if args.features:
        cmd_features(args.format)
        return

    if args.status:
        cmd_status(state)
        return

    oc_version = (parse_version(args.openclaw_version)
                  if args.openclaw_version
                  else detect_openclaw_version())

    cmd_check(state, oc_version, single_skill=args.skill, fmt=args.format)


if __name__ == "__main__":
    main()
