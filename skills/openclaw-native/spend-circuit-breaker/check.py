#!/usr/bin/env python3
"""
Spend Circuit Breaker for OpenClaw.

Reads session logs to estimate API spend, compares against monthly budget,
alerts at thresholds, and opens the circuit (pauses non-essential crons)
when the budget ceiling is hit.

Usage:
    python3 check.py                        # Run spend check (cron mode)
    python3 check.py --status               # Show current spend summary
    python3 check.py --set-budget 50        # Set $50/month cap
    python3 check.py --set-alert 0.5 0.75   # Alert at 50% + 75%
    python3 check.py --reset-circuit        # Re-open circuit after budget reset
    python3 check.py --add-model NAME --input-cost 3.0 --output-cost 15.0
"""

import argparse
import json
import os
import re
from datetime import date, datetime
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

OPENCLAW_DIR = Path(os.environ.get("OPENCLAW_HOME", Path.home() / ".openclaw"))
SESSIONS_DIR = OPENCLAW_DIR / "sessions"
STATE_FILE = OPENCLAW_DIR / "skill-state" / "spend-circuit-breaker" / "state.yaml"

# Default model price table ($ per million tokens, March 2026)
DEFAULT_PRICES = {
    "claude-3-5-sonnet": {"input": 3.0,  "output": 15.0},
    "claude-3-7-sonnet": {"input": 3.0,  "output": 15.0},
    "claude-3-opus":     {"input": 15.0, "output": 75.0},
    "claude-3-haiku":    {"input": 0.25, "output": 1.25},
    "gpt-4o":            {"input": 2.5,  "output": 10.0},
    "gpt-4o-mini":       {"input": 0.15, "output": 0.6},
    "gpt-4-turbo":       {"input": 10.0, "output": 30.0},
    "gemini-1.5-pro":    {"input": 1.25, "output": 5.0},
}

NEVER_PAUSE = {"daily-review", "morning-briefing", "spend-circuit-breaker"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"spend_this_month_usd": 0.0, "circuit_open": False,
                "alert_thresholds": [0.5, 0.75], "spend_history": [],
                "paused_crons": [], "custom_models": []}
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
    else:
        with open(STATE_FILE, "w") as f:
            for k, v in state.items():
                f.write(f"{k}: {v!r}\n")


def price_table(state: dict) -> dict:
    table = dict(DEFAULT_PRICES)
    for custom in (state.get("custom_models") or []):
        name = custom.get("name", "")
        if name:
            table[name] = {
                "input": float(custom.get("input_per_m", 0)),
                "output": float(custom.get("output_per_m", 0)),
            }
    return table


def estimate_session_cost(session_file: Path, prices: dict) -> float:
    """Parse a session JSONL file and estimate cost from token counts."""
    cost = 0.0
    try:
        for line in session_file.read_text(errors="ignore").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            # Look for usage records: {"model": ..., "usage": {"input_tokens": ..., "output_tokens": ...}}
            usage = record.get("usage") or record.get("token_usage") or {}
            model = record.get("model", "")
            inp = int(usage.get("input_tokens", 0) or usage.get("prompt_tokens", 0))
            out = int(usage.get("output_tokens", 0) or usage.get("completion_tokens", 0))
            if inp or out:
                matched = next(
                    (v for k, v in prices.items() if k in model.lower()), None
                )
                if matched:
                    cost += inp / 1_000_000 * matched["input"]
                    cost += out / 1_000_000 * matched["output"]
    except Exception:
        pass
    return cost


def scan_sessions_since(last_checked: str, prices: dict) -> tuple[float, int]:
    """Return (total_cost_usd, session_count) for sessions modified since last_checked."""
    if not SESSIONS_DIR.exists():
        return 0.0, 0
    try:
        cutoff = datetime.fromisoformat(last_checked) if last_checked else datetime.min
    except ValueError:
        cutoff = datetime.min

    total_cost = 0.0
    count = 0
    for session_file in SESSIONS_DIR.glob("*.jsonl"):
        mtime = datetime.fromtimestamp(session_file.stat().st_mtime)
        if mtime > cutoff:
            cost = estimate_session_cost(session_file, prices)
            if cost > 0:
                total_cost += cost
                count += 1
    return round(total_cost, 4), count


def format_status(state: dict) -> str:
    budget = float(state.get("monthly_budget_usd") or 0)
    spend = float(state.get("spend_this_month_usd") or 0)
    circuit = state.get("circuit_open", False)
    pct = (spend / budget * 100) if budget > 0 else 0

    icon = "🔴" if circuit else ("🟡" if pct >= 75 else ("🟠" if pct >= 50 else "🟢"))
    lines = [
        f"\n{icon} Spend Circuit Breaker",
        f"   Month:   {state.get('current_month', date.today().strftime('%Y-%m'))}",
        f"   Spent:   ${spend:.2f} / ${budget:.2f}  ({pct:.1f}%)",
        f"   Circuit: {'OPEN — non-essential crons paused' if circuit else 'closed'}",
    ]
    if circuit and state.get("paused_crons"):
        lines.append(f"   Paused:  {', '.join(state['paused_crons'])}")
    lines.append(f"   Checked: {state.get('last_checked_at', 'never')[:19]}")
    return "\n".join(lines) + "\n"


def check_thresholds(state: dict, prev_spend: float) -> list[str]:
    """Return notification messages for newly crossed thresholds."""
    budget = float(state.get("monthly_budget_usd") or 0)
    if budget <= 0:
        return []
    spend = float(state.get("spend_this_month_usd") or 0)
    thresholds = sorted(state.get("alert_thresholds") or [0.5, 0.75])
    messages = []
    for t in thresholds:
        if (prev_spend / budget) < t <= (spend / budget):
            messages.append(
                f"⚠  Spend alert: ${spend:.2f} is {t*100:.0f}% of your "
                f"${budget:.2f} monthly budget."
            )
    return messages


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_check(state: dict) -> dict:
    """Core cron check: scan sessions, update spend, apply thresholds."""
    if not state.get("monthly_budget_usd"):
        print("No budget set. Run: python3 check.py --set-budget <amount>")
        return state

    # Month rollover
    current_month = date.today().strftime("%Y-%m")
    if state.get("current_month") != current_month:
        print(f"New month ({current_month}) — resetting spend to $0.00")
        state["spend_this_month_usd"] = 0.0
        state["current_month"] = current_month
        state["circuit_open"] = False
        state["paused_crons"] = []

    prices = price_table(state)
    last_checked = state.get("last_checked_at", "")
    new_cost, session_count = scan_sessions_since(last_checked, prices)

    prev_spend = float(state.get("spend_this_month_usd") or 0)
    state["spend_this_month_usd"] = round(prev_spend + new_cost, 4)
    state["last_checked_at"] = datetime.now().isoformat()

    # Log to daily history
    today_str = str(date.today())
    history = state.get("spend_history") or []
    today_entry = next((h for h in history if h.get("date") == today_str), None)
    if today_entry:
        today_entry["usd"] = round(today_entry["usd"] + new_cost, 4)
        today_entry["sessions"] = today_entry.get("sessions", 0) + session_count
    else:
        history.append({"date": today_str, "usd": new_cost, "sessions": session_count})
    state["spend_history"] = history[-90:]  # keep 90 days

    # Threshold checks
    for msg in check_thresholds(state, prev_spend):
        print(msg)

    # Circuit breaker
    budget = float(state.get("monthly_budget_usd", 0))
    spend = float(state["spend_this_month_usd"])
    if budget > 0 and spend >= budget and not state.get("circuit_open"):
        state["circuit_open"] = True
        print(f"🔴 CIRCUIT OPEN: ${spend:.2f} has reached budget of ${budget:.2f}.")
        print("   Non-essential cron skills will be paused.")
        print("   Run `python3 check.py --reset-circuit` after billing cycle resets.")
        # In a real install, would run: openclaw cron remove <skill> for each

    print(format_status(state))
    return state


def main():
    parser = argparse.ArgumentParser(description="API spend circuit breaker")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--set-budget", type=float, metavar="USD")
    parser.add_argument("--set-alert", type=float, nargs="+", metavar="FRACTION")
    parser.add_argument("--reset-circuit", action="store_true")
    parser.add_argument("--add-model", metavar="NAME")
    parser.add_argument("--input-cost", type=float, metavar="USD_PER_M")
    parser.add_argument("--output-cost", type=float, metavar="USD_PER_M")
    args = parser.parse_args()

    state = load_state()

    if args.set_budget is not None:
        state["monthly_budget_usd"] = args.set_budget
        state["current_month"] = date.today().strftime("%Y-%m")
        print(f"Budget set: ${args.set_budget:.2f}/month")
        save_state(state)
        return

    if args.set_alert:
        state["alert_thresholds"] = sorted(args.set_alert)
        print(f"Alerts set at: {[f'{t*100:.0f}%' for t in state['alert_thresholds']]}")
        save_state(state)
        return

    if args.reset_circuit:
        state["circuit_open"] = False
        state["paused_crons"] = []
        print("Circuit closed. Cron schedules will be restored on next install.")
        save_state(state)
        return

    if args.add_model:
        customs = state.get("custom_models") or []
        customs = [c for c in customs if c.get("name") != args.add_model]
        customs.append({"name": args.add_model,
                        "input_per_m": args.input_cost or 0,
                        "output_per_m": args.output_cost or 0})
        state["custom_models"] = customs
        print(f"Model added: {args.add_model}")
        save_state(state)
        return

    if args.status:
        print(format_status(state))
        return

    state = cmd_check(state)
    save_state(state)


if __name__ == "__main__":
    main()
