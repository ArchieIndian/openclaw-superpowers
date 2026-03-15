#!/usr/bin/env python3
"""
Installed Skill Auditor for openclaw-superpowers.

Weekly audit of all installed skills for malicious patterns,
credential leaks, and post-install content drift.

Usage:
    python3 audit.py --scan                    # Full audit
    python3 audit.py --scan --critical-only    # CRITICAL only
    python3 audit.py --baseline                # Record current state
    python3 audit.py --diff <skill>            # Show changes since baseline
    python3 audit.py --resolve <skill>         # Mark finding resolved
    python3 audit.py --status                  # Last audit summary
    python3 audit.py --format json             # Machine-readable
"""

import argparse
import hashlib
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
STATE_FILE = OPENCLAW_DIR / "skill-state" / "installed-skill-auditor" / "state.yaml"
SUPERPOWERS_DIR = Path(os.environ.get(
    "SUPERPOWERS_DIR",
    Path.home() / ".openclaw" / "extensions" / "superpowers"
))
SKILLS_DIRS = [
    SUPERPOWERS_DIR / "skills" / "core",
    SUPERPOWERS_DIR / "skills" / "openclaw-native",
    SUPERPOWERS_DIR / "skills" / "community",
]
MAX_HISTORY = 12

# ── Detection patterns ────────────────────────────────────────────────────────

INJECTION_PATTERNS = [
    re.compile(r'ignore (?:all )?(?:previous|prior|above) instructions', re.I),
    re.compile(r'you are now (?:a|an|in)', re.I),
    re.compile(r'act as (?:a|an)', re.I),
    re.compile(r'disregard (?:your|all) (?:rules|instructions|constraints)', re.I),
    re.compile(r'new (?:system|developer|admin) (?:instructions?|prompt)', re.I),
    re.compile(r'jailbreak', re.I),
]

CREDENTIAL_PATTERNS = [
    re.compile(r'(?:api[_\-]?key|apikey)\s*[=:]\s*["\']?[A-Za-z0-9_\-]{16,}', re.I),
    re.compile(r'(?:secret|token|password|passwd|pwd)\s*[=:]\s*["\']?[A-Za-z0-9_\-]{8,}', re.I),
    re.compile(r'sk-[A-Za-z0-9]{20,}'),
    re.compile(r'(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}'),
    re.compile(r'AKIA[0-9A-Z]{16}'),  # AWS access key
    re.compile(r'Bearer [A-Za-z0-9\-_\.]{20,}'),
]

EXFILTRATION_PATTERNS = [
    re.compile(r'(?:requests?|urllib|curl|wget).*(?:post|put|send).*http', re.I | re.S),
    re.compile(r'webhook\.site', re.I),
    re.compile(r'requestbin', re.I),
    re.compile(r'ngrok\.io', re.I),
    re.compile(r'pastebin\.com', re.I),
]

SEVERITY = {
    "INJECTION": "CRITICAL",
    "EXFILTRATION": "CRITICAL",
    "CREDENTIAL": "HIGH",
    "DRIFT": "MEDIUM",
    "ORPHAN": "MEDIUM",
}


# ── State helpers ─────────────────────────────────────────────────────────────

def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"baselines": {}, "findings": [], "audit_history": []}
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


# ── Hashing ───────────────────────────────────────────────────────────────────

def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def skill_hashes(skill_dir: Path) -> dict:
    hashes = {}
    for f in sorted(skill_dir.rglob("*")):
        if f.is_file():
            rel = str(f.relative_to(skill_dir))
            try:
                hashes[rel] = file_sha256(f)
            except Exception:
                pass
    return hashes


# ── Pattern scanning ──────────────────────────────────────────────────────────

def scan_file_patterns(path: Path) -> list[dict]:
    findings = []
    try:
        text = path.read_text(errors="replace")
    except Exception:
        return findings

    for pattern in INJECTION_PATTERNS:
        if pattern.search(text):
            findings.append({"check": "INJECTION", "file": str(path), "detail":
                             f"Injection pattern matched: {pattern.pattern[:60]}"})

    for pattern in CREDENTIAL_PATTERNS:
        if pattern.search(text):
            findings.append({"check": "CREDENTIAL", "file": str(path), "detail":
                             f"Credential pattern matched: {pattern.pattern[:60]}"})

    for pattern in EXFILTRATION_PATTERNS:
        if pattern.search(text):
            findings.append({"check": "EXFILTRATION", "file": str(path), "detail":
                             f"Exfiltration pattern matched: {pattern.pattern[:60]}"})

    return findings


# ── Audit core ────────────────────────────────────────────────────────────────

def audit_skill(skill_dir: Path, baselines: dict) -> list[dict]:
    skill_name = skill_dir.name
    now = datetime.now().isoformat()
    findings = []

    def finding(check, file_path, detail):
        return {
            "skill_name": skill_name,
            "check": check,
            "severity": SEVERITY[check],
            "file_path": str(file_path),
            "detail": detail,
            "detected_at": now,
            "resolved": False,
        }

    # Pattern scans on all files
    for f in sorted(skill_dir.rglob("*")):
        if f.is_file() and f.suffix in (".md", ".py", ".sh", ".yaml", ".yml", ".txt"):
            for hit in scan_file_patterns(f):
                findings.append(finding(hit["check"], hit["file"], hit["detail"]))

    # Drift detection
    bl = baselines.get(skill_name, {}).get("hashes", {})
    if bl:
        current = skill_hashes(skill_dir)
        for rel_path, old_hash in bl.items():
            new_hash = current.get(rel_path)
            if new_hash is None:
                findings.append(finding("DRIFT", skill_dir / rel_path,
                                        f"File deleted since baseline: {rel_path}"))
            elif new_hash != old_hash:
                findings.append(finding("DRIFT", skill_dir / rel_path,
                                        f"Content changed since baseline ({rel_path})"))
        for rel_path in current:
            if rel_path not in bl:
                findings.append(finding("DRIFT", skill_dir / rel_path,
                                        f"New file added since baseline: {rel_path}"))

    return findings


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_scan(state: dict, critical_only: bool, fmt: str) -> None:
    baselines = state.get("baselines") or {}
    all_findings = []
    skills_audited = 0

    for skills_root in SKILLS_DIRS:
        if not skills_root.exists():
            continue
        for skill_dir in sorted(skills_root.iterdir()):
            if not skill_dir.is_dir():
                continue
            findings = audit_skill(skill_dir, baselines)
            all_findings.extend(findings)
            skills_audited += 1

    if critical_only:
        all_findings = [f for f in all_findings if f["severity"] == "CRITICAL"]

    critical = sum(1 for f in all_findings if f["severity"] == "CRITICAL")
    high = sum(1 for f in all_findings if f["severity"] == "HIGH")
    medium = sum(1 for f in all_findings if f["severity"] == "MEDIUM")
    now = datetime.now().isoformat()

    if fmt == "json":
        print(json.dumps({
            "audited_at": now,
            "skills_audited": skills_audited,
            "critical_count": critical,
            "high_count": high,
            "medium_count": medium,
            "findings": all_findings,
        }, indent=2))
    else:
        print(f"\nInstalled Skill Audit — {datetime.now().strftime('%Y-%m-%d')}")
        print("─" * 48)
        print(f"  {skills_audited} skills audited | "
              f"{critical} CRITICAL | {high} HIGH | {medium} MEDIUM")
        print()
        if not all_findings:
            print("  ✓ No issues detected.")
        else:
            by_skill: dict = {}
            for f in all_findings:
                by_skill.setdefault(f["skill_name"], []).append(f)
            for sname, flist in sorted(by_skill.items()):
                for f in flist:
                    print(f"  {f['severity']:8s} {sname} — {f['check']}")
                    print(f"           {f['detail']}")
        print()

    history = state.get("audit_history") or []
    history.insert(0, {
        "audited_at": now,
        "skills_audited": skills_audited,
        "critical_count": critical,
        "high_count": high,
        "medium_count": medium,
    })
    state["audit_history"] = history[:MAX_HISTORY]
    state["last_audit_at"] = now
    state["findings"] = all_findings
    save_state(state)

    sys.exit(1 if critical > 0 else 0)


def cmd_baseline(state: dict) -> None:
    baselines = state.get("baselines") or {}
    now = datetime.now().isoformat()
    count = 0
    for skills_root in SKILLS_DIRS:
        if not skills_root.exists():
            continue
        for skill_dir in sorted(skills_root.iterdir()):
            if not skill_dir.is_dir():
                continue
            baselines[skill_dir.name] = {
                "hashes": skill_hashes(skill_dir),
                "recorded_at": now,
            }
            count += 1
    state["baselines"] = baselines
    save_state(state)
    print(f"✓ Baseline recorded for {count} skills at {now[:19]}")


def cmd_diff(state: dict, skill_name: str) -> None:
    baselines = state.get("baselines") or {}
    bl = baselines.get(skill_name, {}).get("hashes", {})
    if not bl:
        print(f"No baseline recorded for '{skill_name}'. Run --baseline first.")
        return

    skill_dir = None
    for skills_root in SKILLS_DIRS:
        candidate = skills_root / skill_name
        if candidate.exists():
            skill_dir = candidate
            break

    if skill_dir is None:
        print(f"Skill '{skill_name}' not found in skills directories.")
        return

    current = skill_hashes(skill_dir)
    changed = [(p, "CHANGED") for p, h in bl.items() if current.get(p) != h]
    added = [(p, "ADDED") for p in current if p not in bl]
    deleted = [(p, "DELETED") for p in bl if p not in current]
    all_diffs = changed + added + deleted

    if not all_diffs:
        print(f"✓ {skill_name}: no drift detected from baseline.")
        return

    print(f"\nDrift for: {skill_name}")
    print("─" * 40)
    for path, status in sorted(all_diffs):
        print(f"  {status:8s} {path}")
    print()


def cmd_resolve(state: dict, skill_name: str) -> None:
    findings = state.get("findings") or []
    count = 0
    for f in findings:
        if f.get("skill_name") == skill_name and not f.get("resolved"):
            f["resolved"] = True
            count += 1
    save_state(state)
    print(f"✓ Resolved {count} finding(s) for '{skill_name}'.")


def cmd_status(state: dict) -> None:
    last = state.get("last_audit_at", "never")
    print(f"\nInstalled Skill Auditor — Last run: {last}")
    history = state.get("audit_history") or []
    if history:
        latest = history[0]
        print(f"  {latest.get('skills_audited',0)} skills | "
              f"{latest.get('critical_count',0)} CRITICAL | "
              f"{latest.get('high_count',0)} HIGH | "
              f"{latest.get('medium_count',0)} MEDIUM")
    active = [f for f in (state.get("findings") or []) if not f.get("resolved")]
    if active:
        print(f"\n  Unresolved findings ({len(active)}):")
        for f in active[:5]:
            print(f"    [{f['severity']}] {f['skill_name']}: {f['check']}")
    print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Installed Skill Auditor")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--scan", action="store_true")
    group.add_argument("--baseline", action="store_true")
    group.add_argument("--diff", metavar="SKILL")
    group.add_argument("--resolve", metavar="SKILL")
    group.add_argument("--status", action="store_true")
    parser.add_argument("--critical-only", action="store_true")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    state = load_state()

    if args.status:
        cmd_status(state)
    elif args.baseline:
        cmd_baseline(state)
    elif args.diff:
        cmd_diff(state, args.diff)
    elif args.resolve:
        cmd_resolve(state, args.resolve)
    elif args.scan:
        cmd_scan(state, critical_only=args.critical_only, fmt=args.format)


if __name__ == "__main__":
    main()
