#!/usr/bin/env python3
from __future__ import annotations

"""
Runtime Verification Dashboard for openclaw-superpowers.

Audits the live runtime: install layout, cron registration, state freshness,
dependency readiness, and per-skill PASS/WARN/FAIL status.

Usage:
    python3 check.py --scan
    python3 check.py --scan --failures
    python3 check.py --scan --skill morning-briefing
    python3 check.py --status
    python3 check.py --findings
    python3 check.py --format json
"""

import argparse
import json
import os
import re
import shutil
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
STATE_FILE = OPENCLAW_DIR / "skill-state" / "runtime-verification-dashboard" / "state.yaml"
SUPERPOWERS_DIR = Path(os.environ.get("SUPERPOWERS_DIR", OPENCLAW_DIR / "extensions" / "superpowers"))
CATEGORIES = ["core", "openclaw-native", "community"]
CRON_RE = re.compile(
    r'^[0-9*/,\-]+\s+'
    r'[0-9*/,\-]+\s+'
    r'[0-9*/,\-]+\s+'
    r'[0-9*/,\-]+\s+'
    r'[0-9*/,\-]+$'
)
MAX_HISTORY = 20


def default_state() -> dict:
    return {
        "last_scan_at": "",
        "summary": {},
        "environment": {},
        "global_findings": [],
        "skills": [],
        "scan_history": [],
    }


def load_state() -> dict:
    if not STATE_FILE.exists():
        return default_state()
    try:
        text = STATE_FILE.read_text()
        if HAS_YAML:
            return yaml.safe_load(text) or default_state()
        return json.loads(text)
    except Exception:
        return default_state()


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if HAS_YAML:
        with open(STATE_FILE, "w") as handle:
            yaml.dump(state, handle, default_flow_style=False, allow_unicode=True, sort_keys=False)
    else:
        STATE_FILE.write_text(json.dumps(state, indent=2))


def resolve_skills_root(base_dir: Path) -> Path:
    for candidate in (base_dir / "skills", base_dir):
        if all((candidate / category).exists() for category in CATEGORIES):
            return candidate
    return base_dir / "skills"


def parse_frontmatter(skill_md: Path) -> tuple[dict, str]:
    try:
        text = skill_md.read_text()
    except Exception as exc:
        return {}, f"Cannot read SKILL.md: {exc}"

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, "No frontmatter block found"

    end = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end = index
            break

    if end is None:
        return {}, "Frontmatter block is not closed"

    block = "\n".join(lines[1:end])
    if HAS_YAML:
        try:
            return yaml.safe_load(block) or {}, ""
        except Exception as exc:
            return {}, f"Unparseable frontmatter: {exc}"

    fields = {}
    for line in block.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip().strip('"').strip("'")
    return fields, ""


def find_companion_scripts(skill_dir: Path) -> list[str]:
    ignored = {"SKILL.md", "STATE_SCHEMA.yaml", "example-state.yaml"}
    scripts = []
    for path in sorted(skill_dir.iterdir()):
        if not path.is_file() or path.name in ignored:
            continue
        if path.suffix in {".py", ".sh"}:
            scripts.append(path.name)
    return scripts


def get_registered_crons() -> tuple[list[str] | None, str]:
    if shutil.which("openclaw") is None:
        return None, "openclaw CLI not found"

    try:
        proc = subprocess.run(
            ["openclaw", "cron", "list"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception as exc:
        return None, f"openclaw cron list failed: {exc}"

    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip() or "unknown error"
        return None, f"openclaw cron list failed: {detail}"

    return [line.strip() for line in proc.stdout.splitlines() if line.strip()], ""


def interval_minutes(cron_expr: str) -> int:
    minute, hour, day, month, weekday = cron_expr.split()

    if minute.startswith("*/") and hour == day == month == weekday == "*":
        return max(1, int(minute[2:]))

    if hour.startswith("*/") and day == month == weekday == "*":
        return max(1, int(hour[2:])) * 60

    if day != "*" or weekday != "*":
        return 24 * 60

    if hour != "*" or minute != "*":
        return 24 * 60

    return 60


def make_finding(level: str, check: str, detail: str, recommendation: str) -> dict:
    return {
        "level": level,
        "check": check,
        "detail": detail,
        "recommendation": recommendation,
    }


def status_for(findings: list[dict]) -> str:
    if any(item["level"] == "FAIL" for item in findings):
        return "FAIL"
    if findings:
        return "WARN"
    return "PASS"


def scan(single_skill: str | None = None) -> dict:
    scanned_at = datetime.now().isoformat()
    skills_root = resolve_skills_root(SUPERPOWERS_DIR)
    cron_lines, cron_error = get_registered_crons()
    global_findings = []

    if not skills_root.exists():
        global_findings.append(
            make_finding(
                "FAIL",
                "SKILLS_ROOT_MISSING",
                f"Cannot find skills root at {skills_root}",
                "Check OPENCLAW_HOME / SUPERPOWERS_DIR and reinstall the extension.",
            )
        )

    if skills_root == SUPERPOWERS_DIR:
        global_findings.append(
            make_finding(
                "WARN",
                "INSTALL_LAYOUT",
                "Detected installed-extension layout where `superpowers` points directly at the skills root.",
                "Use path resolution that accepts both repo-root and installed-extension layouts.",
            )
        )

    if not HAS_YAML:
        global_findings.append(
            make_finding(
                "WARN",
                "PYYAML_MISSING",
                "PyYAML is unavailable; stateful helpers may read less and persist less reliably.",
                "Install PyYAML with `python3 -m pip install PyYAML`.",
            )
        )

    if cron_lines is None:
        global_findings.append(
            make_finding(
                "WARN",
                "CRON_REGISTRY_UNAVAILABLE",
                cron_error,
                "Install the OpenClaw CLI or run the checker where `openclaw cron list` is available.",
            )
        )

    skills = []
    total_skills = 0
    stateful_count = 0
    scheduled_count = 0
    companion_script_count = 0

    for category in CATEGORIES:
        category_dir = skills_root / category
        if not category_dir.exists():
            continue
        for skill_dir in sorted(category_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            if single_skill and skill_dir.name != single_skill:
                continue

            total_skills += 1
            skill_md = skill_dir / "SKILL.md"
            frontmatter, parse_error = parse_frontmatter(skill_md)
            findings = []

            if parse_error:
                findings.append(
                    make_finding(
                        "FAIL",
                        "FRONTMATTER",
                        parse_error,
                        "Fix the YAML frontmatter at the top of SKILL.md.",
                    )
                )

            is_stateful = str(frontmatter.get("stateful", "")).lower() == "true"
            cron_expr = str(frontmatter.get("cron", "")).strip()
            companion_scripts = find_companion_scripts(skill_dir)
            companion_script_count += len(companion_scripts)

            if is_stateful:
                stateful_count += 1
            if cron_expr:
                scheduled_count += 1
                if not CRON_RE.match(cron_expr):
                    findings.append(
                        make_finding(
                            "FAIL",
                            "CRON_FORMAT",
                            f"Invalid cron expression in frontmatter: {cron_expr}",
                            "Use a valid 5-field cron expression.",
                        )
                    )

            state_file = OPENCLAW_DIR / "skill-state" / skill_dir.name / "state.yaml"
            if is_stateful and not state_file.exists():
                findings.append(
                    make_finding(
                        "WARN",
                        "STATE_MISSING",
                        f"Expected state file is missing: {state_file}",
                        "Run ./install.sh or execute the skill once to create its state directory.",
                    )
                )
            elif is_stateful and cron_expr:
                age_minutes = (datetime.now().timestamp() - state_file.stat().st_mtime) / 60
                freshness_budget = interval_minutes(cron_expr) * 3
                if age_minutes > freshness_budget:
                    findings.append(
                        make_finding(
                            "WARN",
                            "STATE_STALE",
                            f"State file is {int(age_minutes)} minutes old, above the {freshness_budget}-minute freshness budget.",
                            "Inspect the cron logs and rerun the companion script manually.",
                        )
                    )

            if cron_expr and cron_lines is not None:
                if not any(skill_dir.name in line for line in cron_lines):
                    findings.append(
                        make_finding(
                            "FAIL",
                            "CRON_NOT_REGISTERED",
                            "Skill is scheduled in frontmatter but was not found in `openclaw cron list`.",
                            "Re-run ./install.sh or register the cron entry manually.",
                        )
                    )

            skills.append(
                {
                    "name": skill_dir.name,
                    "category": category,
                    "status": status_for(findings),
                    "stateful": is_stateful,
                    "cron": cron_expr,
                    "state_file": str(state_file),
                    "companion_scripts": companion_scripts,
                    "findings": findings,
                }
            )

    pass_count = sum(1 for item in skills if item["status"] == "PASS")
    warn_count = sum(1 for item in skills if item["status"] == "WARN")
    fail_count = sum(1 for item in skills if item["status"] == "FAIL")

    summary = {
        "total_skills": total_skills,
        "pass_count": pass_count,
        "warn_count": warn_count,
        "fail_count": fail_count,
        "stateful_count": stateful_count,
        "scheduled_count": scheduled_count,
        "companion_script_count": companion_script_count,
    }
    environment = {
        "openclaw_home": str(OPENCLAW_DIR),
        "superpowers_dir": str(SUPERPOWERS_DIR),
        "skills_root": str(skills_root),
        "openclaw_cli_found": shutil.which("openclaw") is not None,
        "pyyaml_found": HAS_YAML,
        "cron_registry_ok": cron_lines is not None,
    }
    return {
        "last_scan_at": scanned_at,
        "summary": summary,
        "environment": environment,
        "global_findings": global_findings,
        "skills": skills,
    }


def update_state(report: dict) -> dict:
    state = load_state()
    history = state.get("scan_history") or []
    history.insert(
        0,
        {
            "scanned_at": report["last_scan_at"],
            "total_skills": report["summary"]["total_skills"],
            "pass_count": report["summary"]["pass_count"],
            "warn_count": report["summary"]["warn_count"],
            "fail_count": report["summary"]["fail_count"],
            "global_finding_count": len(report["global_findings"]),
        },
    )
    report["scan_history"] = history[:MAX_HISTORY]
    save_state(report)
    return report


def filter_report(report: dict, skill_name: str | None, failures_only: bool) -> dict:
    filtered = {
        "last_scan_at": report.get("last_scan_at"),
        "summary": report.get("summary", {}),
        "environment": report.get("environment", {}),
        "global_findings": report.get("global_findings", []),
        "skills": report.get("skills", []),
        "scan_history": report.get("scan_history", []),
    }
    if skill_name:
        filtered["skills"] = [item for item in filtered["skills"] if item["name"] == skill_name]
    if failures_only:
        filtered["global_findings"] = [
            item for item in filtered["global_findings"] if item["level"] in {"WARN", "FAIL"}
        ]
        filtered["skills"] = [item for item in filtered["skills"] if item["status"] != "PASS"]
    return filtered


def print_summary(report: dict) -> None:
    summary = report.get("summary", {})
    environment = report.get("environment", {})
    print("\nRuntime Verification Dashboard")
    print("───────────────────────────────────────────────────────")
    print(
        f"  Skills: {summary.get('total_skills', 0)} total | "
        f"{summary.get('pass_count', 0)} PASS | "
        f"{summary.get('warn_count', 0)} WARN | "
        f"{summary.get('fail_count', 0)} FAIL"
    )
    print(
        f"  Stateful: {summary.get('stateful_count', 0)} | "
        f"Scheduled: {summary.get('scheduled_count', 0)} | "
        f"Companion scripts: {summary.get('companion_script_count', 0)}"
    )
    print(f"  Skills root: {environment.get('skills_root', 'unknown')}")
    print(f"  Last scan:   {report.get('last_scan_at', 'never')}")


def print_findings(report: dict, skill_name: str | None = None) -> None:
    global_findings = report.get("global_findings", [])
    if global_findings:
        print("\nGlobal findings")
        print("───────────────────────────────────────────────────────")
        for item in global_findings:
            print(f"  {item['level']:4} {item['check']}")
            print(f"       {item['detail']}")

    skills = report.get("skills", [])
    if skill_name and not skills:
        print(f"\nNo data recorded for skill '{skill_name}'.")
        return

    issue_skills = [item for item in skills if item["status"] != "PASS"]
    if not issue_skills and not global_findings:
        print("\nAll monitored skills look healthy.")
        return

    if issue_skills:
        print("\nSkill findings")
        print("───────────────────────────────────────────────────────")
        for item in issue_skills:
            print(f"  {item['status']:4} {item['name']} ({item['category']})")
            for finding in item["findings"]:
                print(f"       {finding['check']}: {finding['detail']}")


def print_status(report: dict) -> None:
    print_summary(report)
    history = report.get("scan_history", [])
    if history:
        print("\nRecent scans")
        print("───────────────────────────────────────────────────────")
        for entry in history[:5]:
            print(
                f"  {entry['scanned_at'][:19]}  "
                f"P:{entry['pass_count']} W:{entry['warn_count']} F:{entry['fail_count']}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Runtime verification and observability for skills")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--scan", action="store_true", help="Run a live runtime scan")
    group.add_argument("--status", action="store_true", help="Show summary from the last scan")
    group.add_argument("--findings", action="store_true", help="Show findings from the last scan")
    parser.add_argument("--skill", metavar="NAME", help="Limit output to a single skill")
    parser.add_argument("--failures", action="store_true", help="Only show WARN / FAIL items")
    parser.add_argument("--format", choices=["human", "json"], default="human")
    args = parser.parse_args()

    if args.scan:
        report = update_state(scan(args.skill))
    else:
        report = load_state()

    report = filter_report(report, args.skill, args.failures)

    if args.format == "json":
        print(json.dumps(report, indent=2))
        return

    if args.status:
        print_status(report)
        return

    print_summary(report)
    print_findings(report, args.skill)


if __name__ == "__main__":
    main()
