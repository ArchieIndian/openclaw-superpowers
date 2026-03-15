#!/usr/bin/env python3
"""
Skill Conflict Detector for openclaw-superpowers.

Detects name shadowing and description-overlap conflicts between
installed skills that cause silent trigger routing failures.

Usage:
    python3 detect.py --scan
    python3 detect.py --scan --skill my-skill
    python3 detect.py --scan --threshold 0.6
    python3 detect.py --names              # Name shadowing only
    python3 detect.py --format json
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

SUPERPOWERS_DIR = Path(os.environ.get(
    "SUPERPOWERS_DIR",
    Path.home() / ".openclaw" / "extensions" / "superpowers"
))
SKILLS_DIRS = [
    SUPERPOWERS_DIR / "skills" / "core",
    SUPERPOWERS_DIR / "skills" / "openclaw-native",
    SUPERPOWERS_DIR / "skills" / "community",
]

DEFAULT_HIGH_THRESHOLD = 0.75
DEFAULT_MEDIUM_THRESHOLD = 0.50

_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "it", "its", "this", "that", "so", "not", "no", "all", "any", "each",
    "more", "most", "has", "have", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "can", "which", "when", "where",
    "how", "what", "who", "i", "you", "we", "they", "he", "she",
}


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
        fields = {}
        for line in fm_text.splitlines():
            if ":" in line and not line.startswith(" "):
                k, _, v = line.partition(":")
                fields[k.strip()] = v.strip().strip('"').strip("'")
        return fields
    except Exception:
        return {}


# ── Tokeniser + similarity ────────────────────────────────────────────────────

def tokenise(text: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return {t for t in tokens if t not in _STOPWORDS and len(t) > 2}


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union > 0 else 0.0


# ── Skill loader ──────────────────────────────────────────────────────────────

def load_all_skills() -> list[dict]:
    skills = []
    for skills_root in SKILLS_DIRS:
        if not skills_root.exists():
            continue
        for skill_dir in sorted(skills_root.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue
            fm = parse_frontmatter(skill_md)
            skills.append({
                "dir_name": skill_dir.name,
                "name": fm.get("name", skill_dir.name),
                "description": fm.get("description", ""),
                "path": str(skill_md),
            })
    return skills


# ── Conflict detection ────────────────────────────────────────────────────────

def detect_conflicts(skills: list[dict], high_threshold: float,
                     medium_threshold: float,
                     single_skill: str = None) -> list[dict]:
    conflicts = []

    # Name shadowing: same name field, different directories
    by_name: dict = {}
    for s in skills:
        by_name.setdefault(s["name"], []).append(s)

    for name, group in by_name.items():
        if len(group) > 1:
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    a, b = group[i], group[j]
                    if single_skill and single_skill not in (a["dir_name"], b["dir_name"]):
                        continue
                    conflicts.append({
                        "type": "NAME_SHADOW",
                        "severity": "CRITICAL",
                        "skill_a": a["dir_name"],
                        "skill_b": b["dir_name"],
                        "overlap_score": 1.0,
                        "detail": f"Both have `name: {name}` — one will be hidden",
                        "suggestion": f"Rename one skill's `name:` field and its directory.",
                    })

    # Description overlap
    for i in range(len(skills)):
        for j in range(i + 1, len(skills)):
            a, b = skills[i], skills[j]
            if single_skill and single_skill not in (a["dir_name"], b["dir_name"]):
                continue

            ta = tokenise(a["description"])
            tb = tokenise(b["description"])

            if not ta or not tb:
                continue

            score = jaccard(ta, tb)

            if score >= high_threshold:
                # Check for exact duplicate
                severity = "CRITICAL" if a["description"] == b["description"] else "HIGH"
                ctype = "EXACT_DUPLICATE" if severity == "CRITICAL" else "HIGH_OVERLAP"
                common = ta & tb
                conflicts.append({
                    "type": ctype,
                    "severity": severity,
                    "skill_a": a["dir_name"],
                    "skill_b": b["dir_name"],
                    "overlap_score": round(score, 3),
                    "detail": (
                        f"Descriptions share key terms: "
                        + ", ".join(f'"{t}"' for t in sorted(common)[:5])
                    ),
                    "suggestion": (
                        "Differentiate descriptions — add scope, timing, or "
                        "context that distinguishes when each skill fires."
                    ),
                })
            elif score >= medium_threshold:
                common = ta & tb
                conflicts.append({
                    "type": "MEDIUM_OVERLAP",
                    "severity": "MEDIUM",
                    "skill_a": a["dir_name"],
                    "skill_b": b["dir_name"],
                    "overlap_score": round(score, 3),
                    "detail": (
                        "Moderate description overlap — "
                        + ", ".join(f'"{t}"' for t in sorted(common)[:4])
                    ),
                    "suggestion": (
                        "Acceptable if use-cases are clearly distinct. "
                        "Consider adding differentiating context to each description."
                    ),
                })

    return conflicts


# ── Output ────────────────────────────────────────────────────────────────────

def print_report(conflicts: list, skills_count: int, fmt: str) -> None:
    criticals = [c for c in conflicts if c["severity"] == "CRITICAL"]
    highs = [c for c in conflicts if c["severity"] == "HIGH"]
    mediums = [c for c in conflicts if c["severity"] == "MEDIUM"]

    if fmt == "json":
        print(json.dumps({
            "skills_scanned": skills_count,
            "critical_count": len(criticals),
            "high_count": len(highs),
            "medium_count": len(mediums),
            "conflicts": conflicts,
        }, indent=2))
        return

    print(f"\nSkill Conflict Report — {skills_count} skills")
    print("─" * 50)
    print(f"  {len(criticals)} CRITICAL | {len(highs)} HIGH | {len(mediums)} MEDIUM")
    print()

    if not conflicts:
        print("  ✓ No conflicts detected.")
    else:
        for c in conflicts:
            icon = "✗" if c["severity"] in ("CRITICAL",) else (
                "!" if c["severity"] == "HIGH" else "⚠"
            )
            score_str = f"  overlap: {c['overlap_score']:.2f}" if c["type"] != "NAME_SHADOW" else ""
            print(f"  {icon} {c['severity']:8s}  {c['skill_a']} ↔ {c['skill_b']}"
                  f"{score_str}")
            print(f"           {c['detail']}")
            print(f"           → {c['suggestion']}")
            print()


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_scan(high_threshold: float, medium_threshold: float,
             single_skill: str, fmt: str) -> None:
    skills = load_all_skills()
    conflicts = detect_conflicts(skills, high_threshold, medium_threshold, single_skill)
    print_report(conflicts, len(skills), fmt)
    critical_count = sum(1 for c in conflicts if c["severity"] == "CRITICAL")
    sys.exit(1 if critical_count > 0 else 0)


def cmd_names(fmt: str) -> None:
    skills = load_all_skills()
    conflicts = detect_conflicts(skills, high_threshold=2.0, medium_threshold=2.0)
    name_conflicts = [c for c in conflicts if c["type"] == "NAME_SHADOW"]
    if fmt == "json":
        print(json.dumps(name_conflicts, indent=2))
    else:
        if not name_conflicts:
            print("✓ No name shadowing detected.")
        else:
            for c in name_conflicts:
                print(f"✗ SHADOW: {c['skill_a']} ↔ {c['skill_b']}  {c['detail']}")
    sys.exit(1 if name_conflicts else 0)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Skill Conflict Detector")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--scan", action="store_true")
    group.add_argument("--names", action="store_true",
                       help="Check name shadowing only")
    parser.add_argument("--skill", metavar="NAME",
                        help="Check one skill against all others")
    parser.add_argument("--threshold", type=float, default=DEFAULT_HIGH_THRESHOLD,
                        help=f"HIGH similarity threshold (default: {DEFAULT_HIGH_THRESHOLD})")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    if args.names:
        cmd_names(args.format)
    elif args.scan:
        cmd_scan(
            high_threshold=args.threshold,
            medium_threshold=DEFAULT_MEDIUM_THRESHOLD,
            single_skill=args.skill,
            fmt=args.format,
        )


if __name__ == "__main__":
    main()
