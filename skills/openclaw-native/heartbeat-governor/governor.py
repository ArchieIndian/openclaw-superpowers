#!/usr/bin/env python3
"""
Heartbeat Governor for openclaw-superpowers.

Enforces per-skill execution budgets for cron skills.
Pauses runaway skills before they drain your monthly API allowance.

Usage:
    python3 governor.py --check                           # Hourly cron check
    python3 governor.py --status                          # Current utilisation
    python3 governor.py --record <skill> --usd 0.12 --minutes 4
    python3 governor.py --pause <skill>                   # Manual pause
    python3 governor.py --resume <skill>                  # Resume after review
    python3 governor.py --set-budget <skill> --monthly 10.00 [--per-run 1.00]
    python3 governor.py --report                          # Monthly spend report
    python3 governor.py --format json
"""

import argparse
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

OPENCLAW_DIR = Path(os.environ.get("OPENCLAW_HOME", Path.home() / ".openclaw"))
STATE_FILE = OPENCLAW_DIR / "skill-state" / "heartbeat-governor" / "state.yaml"

DEFAULT_BUDGET = {
    "max_usd_monthly": 5.0,
    "max_usd_per_run": 0.50,
    "max_wall_minutes": 30,
    "max_runs_daily": 48,
}
ROLLING_DAYS = 30
MAX_BREACH_LOG = 200


# ── State helpers ─────────────────────────────────────────────────────────────

def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"skill_ledgers": {}, "breach_log": [], "monthly_summary": {}}
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


# ── Ledger helpers ────────────────────────────────────────────────────────────

def get_ledger(state: dict, skill_name: str) -> dict:
    ledgers = state.setdefault("skill_ledgers", {})
    if skill_name not in ledgers:
        ledgers[skill_name] = {
            "budget": dict(DEFAULT_BUDGET),
            "paused": False,
            "pause_reason": None,
            "paused_at": None,
            "runs": [],
        }
    return ledgers[skill_name]


def prune_old_runs(runs: list) -> list:
    cutoff = datetime.now() - timedelta(days=ROLLING_DAYS)
    return [r for r in runs if _parse_dt(r.get("ran_at", "")) >= cutoff]


def _parse_dt(s: str) -> datetime:
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return datetime.min


def rolling_usd(runs: list) -> float:
    return sum(r.get("usd_spent", 0) for r in runs)


def runs_today(runs: list) -> int:
    today = datetime.now().date()
    return sum(1 for r in runs if _parse_dt(r.get("ran_at", "")).date() == today)


def add_breach(state: dict, skill_name: str, breach_type: str,
               value: float, limit: float) -> None:
    breach_log = state.setdefault("breach_log", [])
    breach_log.append({
        "skill_name": skill_name,
        "breach_type": breach_type,
        "value": round(value, 4),
        "limit": round(limit, 4),
        "breached_at": datetime.now().isoformat(),
        "resolved": False,
    })
    state["breach_log"] = breach_log[-MAX_BREACH_LOG:]


def pause_skill(state: dict, skill_name: str, reason: str) -> None:
    ledger = get_ledger(state, skill_name)
    ledger["paused"] = True
    ledger["pause_reason"] = reason
    ledger["paused_at"] = datetime.now().isoformat()
    print(f"  ⏸ PAUSED: {skill_name} — {reason}")


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_record(state: dict, skill_name: str, usd: float, minutes: float) -> None:
    ledger = get_ledger(state, skill_name)
    ledger["runs"] = prune_old_runs(ledger.get("runs") or [])

    now = datetime.now().isoformat()
    run = {"ran_at": now, "usd_spent": usd, "wall_minutes": minutes}

    # Per-run checks
    budget = ledger.get("budget") or DEFAULT_BUDGET
    per_run_limit = budget.get("max_usd_per_run", DEFAULT_BUDGET["max_usd_per_run"])
    wall_limit = budget.get("max_wall_minutes", DEFAULT_BUDGET["max_wall_minutes"])

    if usd > per_run_limit:
        add_breach(state, skill_name, "per_run_usd", usd, per_run_limit)
        print(f"⚠ {skill_name}: per-run spend ${usd:.2f} exceeds limit ${per_run_limit:.2f}")

    if minutes > wall_limit:
        add_breach(state, skill_name, "wall_clock", minutes, wall_limit)
        print(f"⚠ {skill_name}: wall-clock {minutes:.1f}m exceeds limit {wall_limit}m")

    ledger["runs"].append(run)
    save_state(state)
    print(f"✓ Recorded run for '{skill_name}': ${usd:.4f} in {minutes:.1f}m")


def cmd_check(state: dict, fmt: str) -> None:
    """Hourly cron check — evaluate all skill budgets."""
    ledgers = state.get("skill_ledgers") or {}
    paused_now = []
    alerts = []

    for skill_name, ledger in ledgers.items():
        if ledger.get("paused"):
            continue

        budget = ledger.get("budget") or DEFAULT_BUDGET
        ledger["runs"] = prune_old_runs(ledger.get("runs") or [])

        # Monthly budget check
        monthly_limit = budget.get("max_usd_monthly", DEFAULT_BUDGET["max_usd_monthly"])
        total = rolling_usd(ledger["runs"])
        if total >= monthly_limit:
            reason = f"30-day spend ${total:.2f} reached monthly limit ${monthly_limit:.2f}"
            pause_skill(state, skill_name, reason)
            add_breach(state, skill_name, "monthly_usd", total, monthly_limit)
            paused_now.append(skill_name)
            alerts.append({"skill": skill_name, "breach": "monthly_usd",
                           "value": total, "limit": monthly_limit})
            continue

        # Daily runs check
        daily_limit = budget.get("max_runs_daily", DEFAULT_BUDGET["max_runs_daily"])
        today_runs = runs_today(ledger["runs"])
        if today_runs >= daily_limit:
            alerts.append({"skill": skill_name, "breach": "daily_runs",
                           "value": today_runs, "limit": daily_limit})

    now = datetime.now().isoformat()
    if fmt == "json":
        print(json.dumps({
            "checked_at": now,
            "paused_this_run": paused_now,
            "alerts": alerts,
        }, indent=2))
    else:
        print(f"\nHeartbeat Governor — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("─" * 48)
        if paused_now:
            for name in paused_now:
                print(f"  ⏸ Paused: {name}")
        if not paused_now and not alerts:
            print("  ✓ All skills within budget.")
        for a in alerts:
            if a["breach"] == "daily_runs":
                print(f"  ⚠ {a['skill']}: {int(a['value'])} runs today "
                      f"(limit {int(a['limit'])})")
        print()

    save_state(state)


def cmd_status(state: dict, fmt: str) -> None:
    ledgers = state.get("skill_ledgers") or {}
    rows = []
    for skill_name, ledger in sorted(ledgers.items()):
        budget = ledger.get("budget") or DEFAULT_BUDGET
        ledger["runs"] = prune_old_runs(ledger.get("runs") or [])
        total = rolling_usd(ledger["runs"])
        monthly_limit = budget.get("max_usd_monthly", DEFAULT_BUDGET["max_usd_monthly"])
        pct = int(100 * total / monthly_limit) if monthly_limit else 0
        rows.append({
            "skill": skill_name,
            "paused": ledger.get("paused", False),
            "monthly_usd": round(total, 4),
            "monthly_limit": monthly_limit,
            "pct": pct,
        })

    if fmt == "json":
        print(json.dumps(rows, indent=2))
        return

    print(f"\nHeartbeat Governor — Skill Budget Status")
    print("─" * 55)
    print(f"  {'Skill':30s}  {'Spend':>7s}  {'Budget':>7s}  {'%':>4s}  Status")
    for r in rows:
        status = "⏸ PAUSED" if r["paused"] else ("⚠" if r["pct"] >= 80 else "✓")
        print(f"  {r['skill']:30s}  ${r['monthly_usd']:>6.2f}  "
              f"${r['monthly_limit']:>6.2f}  {r['pct']:>3d}%  {status}")
    print()


def cmd_pause(state: dict, skill_name: str) -> None:
    pause_skill(state, skill_name, "Manual pause")
    save_state(state)


def cmd_resume(state: dict, skill_name: str) -> None:
    ledger = get_ledger(state, skill_name)
    ledger["paused"] = False
    ledger["pause_reason"] = None
    ledger["paused_at"] = None
    save_state(state)
    print(f"✓ Resumed '{skill_name}'. Will fire on next scheduled run.")


def cmd_set_budget(state: dict, skill_name: str, monthly: float,
                   per_run: float, wall_minutes: int, daily_runs: int) -> None:
    ledger = get_ledger(state, skill_name)
    budget = ledger.setdefault("budget", dict(DEFAULT_BUDGET))
    if monthly is not None:
        budget["max_usd_monthly"] = monthly
    if per_run is not None:
        budget["max_usd_per_run"] = per_run
    if wall_minutes is not None:
        budget["max_wall_minutes"] = wall_minutes
    if daily_runs is not None:
        budget["max_runs_daily"] = daily_runs
    save_state(state)
    print(f"✓ Budget updated for '{skill_name}': {budget}")


def cmd_report(state: dict, fmt: str) -> None:
    ledgers = state.get("skill_ledgers") or {}
    month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0)
    rows = []
    for skill_name, ledger in sorted(ledgers.items()):
        runs = [r for r in (ledger.get("runs") or [])
                if _parse_dt(r.get("ran_at", "")) >= month_start]
        total = sum(r.get("usd_spent", 0) for r in runs)
        rows.append({"skill": skill_name, "runs": len(runs),
                     "total_usd": round(total, 4)})

    grand_total = sum(r["total_usd"] for r in rows)

    if fmt == "json":
        print(json.dumps({"rows": rows, "grand_total_usd": round(grand_total, 4)},
                         indent=2))
        return

    print(f"\nMonthly Spend Report — {datetime.now().strftime('%B %Y')}")
    print("─" * 48)
    for r in rows:
        print(f"  {r['skill']:35s}  {r['runs']:3d} runs  ${r['total_usd']:.4f}")
    print(f"  {'TOTAL':35s}           ${grand_total:.4f}")
    print()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Heartbeat Governor")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true",
                       help="Hourly budget check (cron entry point)")
    group.add_argument("--status", action="store_true")
    group.add_argument("--record", metavar="SKILL")
    group.add_argument("--pause", metavar="SKILL")
    group.add_argument("--resume", metavar="SKILL")
    group.add_argument("--set-budget", metavar="SKILL")
    group.add_argument("--report", action="store_true")
    parser.add_argument("--usd", type=float, default=0.0)
    parser.add_argument("--minutes", type=float, default=0.0)
    parser.add_argument("--monthly", type=float)
    parser.add_argument("--per-run", type=float)
    parser.add_argument("--wall-minutes", type=int)
    parser.add_argument("--daily-runs", type=int)
    parser.add_argument("--format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    state = load_state()

    if args.check:
        cmd_check(state, args.format)
    elif args.status:
        cmd_status(state, args.format)
    elif args.record:
        cmd_record(state, args.record, args.usd, args.minutes)
    elif args.pause:
        cmd_pause(state, args.pause)
    elif args.resume:
        cmd_resume(state, args.resume)
    elif args.set_budget:
        cmd_set_budget(state, args.set_budget, args.monthly, args.per_run,
                       args.wall_minutes, args.daily_runs)
    elif args.report:
        cmd_report(state, args.format)


if __name__ == "__main__":
    main()
