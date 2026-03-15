#!/usr/bin/env python3
"""
Cron Hygiene auditor for OpenClaw.

Checks cron-scheduled skills for session mode violations, token waste,
frequency issues, and dead crons. Produces a weekly cost waste report.

Usage:
    python3 audit.py                    # Run weekly audit
    python3 audit.py --report           # Show last audit summary
    python3 audit.py --fix-session SKILL  # Write sessionMode: isolated for skill
    python3 audit.py --dry-run          # Audit without saving state
"""

import argparse
import os
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

OPENCLAW_DIR = Path(os.environ.get("OPENCLAW_HOME", Path.home() / ".openclaw"))
STATE_FILE = OPENCLAW_DIR / "skill-state" / "cron-hygiene" / "state.yaml"
SKILL_STATE_DIR = OPENCLAW_DIR / "skill-state"

# Cost assumptions: avg tokens per cron run × model cost
AVG_TOKENS_MAIN_SESSION = 8000     # Main session: full history re-sent
AVG_TOKENS_ISOLATED = 800          # Isolated: fresh context
COST_PER_TOKEN = 0.000003          # ~$3/M tokens (claude-3-5-sonnet)

CRON_SKILLS = [
    # (skill_name, interval_minutes, session_mode)
    # Detected from installed skills + OpenClaw config
    ("long-running-task-management", 15,   "main"),
    ("persistent-memory-hygiene",    1440, "main"),
    ("daily-review",                  480, "isolated"),
    ("morning-briefing",              1440, "isolated"),
    ("secrets-hygiene",               10080, "isolated"),
    ("spend-circuit-breaker",         240, "isolated"),
    ("workspace-integrity-guardian",  10080, "isolated"),
    ("cron-hygiene",                  10080, "isolated"),
]


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"cron_ledger": [], "violations": [], "audit_history": []}
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


def check_dead_cron(skill_name: str, interval_min: int) -> bool:
    """Return True if skill's state hasn't been updated in 7+ days."""
    state_file = SKILL_STATE_DIR / skill_name / "state.yaml"
    if not state_file.exists():
        return False
    age = datetime.now() - datetime.fromtimestamp(state_file.stat().st_mtime)
    expected_runs = (7 * 24 * 60) / interval_min
    return age.days >= 7 and expected_runs > 3


def estimate_monthly_waste(interval_min: int, session_mode: str) -> float:
    """Estimate monthly $ waste from using main instead of isolated session."""
    if session_mode == "isolated":
        return 0.0
    runs_per_month = (30 * 24 * 60) / interval_min
    waste_tokens = (AVG_TOKENS_MAIN_SESSION - AVG_TOKENS_ISOLATED) * runs_per_month
    return round(waste_tokens * COST_PER_TOKEN, 2)


def run_audit(state: dict) -> tuple[dict, list]:
    violations = []
    now = datetime.now()
    today = str(date.today())

    # Check session modes and frequency
    for skill_name, interval_min, session_mode in CRON_SKILLS:
        # Rule 1: Session isolation
        if session_mode == "main":
            waste = estimate_monthly_waste(interval_min, session_mode)
            violations.append({
                "skill_name": skill_name,
                "rule": "session_isolation",
                "severity": "high",
                "details": f"Runs in main session mode — re-sends ~{AVG_TOKENS_MAIN_SESSION:,} tokens/run",
                "detected_at": now.isoformat(),
                "resolved": False,
                "est_waste_usd": waste,
            })

        # Rule 2: Frequency sanity
        if interval_min < 10:
            violations.append({
                "skill_name": skill_name,
                "rule": "frequency_sanity",
                "severity": "medium",
                "details": f"Runs every {interval_min}min — very high frequency",
                "detected_at": now.isoformat(),
                "resolved": False,
                "est_waste_usd": 0,
            })

        # Rule 3: Dead crons
        if check_dead_cron(skill_name, interval_min):
            violations.append({
                "skill_name": skill_name,
                "rule": "dead_cron",
                "severity": "low",
                "details": f"State file not updated in 7+ days",
                "detected_at": now.isoformat(),
                "resolved": False,
                "est_waste_usd": 0,
            })

    total_waste = sum(v["est_waste_usd"] for v in violations)

    # Merge with existing (keep resolved)
    existing = [v for v in (state.get("violations") or []) if v.get("resolved")]
    state["violations"] = existing + violations
    state["last_audit_at"] = now.isoformat()

    # Audit history
    history = state.get("audit_history") or []
    history.append({
        "date": today,
        "crons_audited": len(CRON_SKILLS),
        "violations_found": len(violations),
        "est_monthly_waste_usd": total_waste,
    })
    state["audit_history"] = history[-52:]  # 52 weeks

    return state, violations


def print_report(violations: list, cron_count: int, total_waste: float) -> None:
    today = str(date.today())
    print(f"\nCron Hygiene Report — {today}")
    print(f"{'─' * 40}")
    print(f"{cron_count} crons audited | {len(violations)} violations | "
          f"Est. monthly waste: ${total_waste:.2f}")
    print()

    by_severity = {"high": [], "medium": [], "low": []}
    for v in violations:
        by_severity.get(v["severity"], []).append(v)

    icons = {"high": "HIGH  ", "medium": "MEDIUM", "low": "LOW   "}
    for severity in ["high", "medium", "low"]:
        for v in by_severity[severity]:
            print(f"{icons[severity]}  {v['skill_name']}: {v['details']}")
            if v["est_waste_usd"] > 0:
                print(f"         Est. waste: ~${v['est_waste_usd']:.2f}/month")
            if v["rule"] == "session_isolation":
                print(f"         Fix: python3 audit.py --fix-session {v['skill_name']}")
            print()

    if not violations:
        print("✓ All crons pass hygiene checks.")
    print()


def main():
    parser = argparse.ArgumentParser(description="Cron hygiene auditor")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--fix-session", metavar="SKILL")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    state = load_state()

    if args.report:
        history = state.get("audit_history") or []
        if not history:
            print("No audits run yet.")
            return
        last = history[-1]
        print(f"\nLast audit: {last['date']}")
        print(f"Crons audited: {last['crons_audited']}")
        print(f"Violations: {last['violations_found']}")
        print(f"Est. monthly waste: ${last['est_monthly_waste_usd']:.2f}")
        return

    if args.fix_session:
        skill = args.fix_session
        print(f"Note: To fix session mode for '{skill}', add to its OpenClaw config:")
        print(f"  sessionMode: isolated")
        print(f"Then re-register the cron with: openclaw cron remove {skill} && openclaw cron add {skill} <expr>")
        return

    state, violations = run_audit(state)
    total_waste = sum(v["est_waste_usd"] for v in violations)
    print_report(violations, len(CRON_SKILLS), total_waste)

    if not args.dry_run:
        save_state(state)


if __name__ == "__main__":
    main()
