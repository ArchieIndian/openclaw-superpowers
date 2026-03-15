#!/usr/bin/env python3
"""
Morning Briefing runner for OpenClaw.

Reads state from sibling skills (daily-review, long-running-task-management,
task-handoff) and composes a concise morning briefing. Updates own state to
prevent duplicate delivery on the same day.

Usage:
    python3 run.py              # Run briefing (skips if already delivered today)
    python3 run.py --force      # Re-deliver even if already done today
    python3 run.py --dry-run    # Print briefing without updating state
"""

import argparse
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    # Minimal YAML loader for simple key: value files (no lists/nested)
    class yaml:
        @staticmethod
        def safe_load(text):
            result = {}
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if ":" in line:
                    k, _, v = line.partition(":")
                    result[k.strip()] = v.strip()
            return result

        @staticmethod
        def dump(data, stream=None, default_flow_style=False, **kwargs):
            lines = []
            for k, v in data.items():
                lines.append(f"{k}: {v}")
            output = "\n".join(lines) + "\n"
            if stream:
                stream.write(output)
            return output


OPENCLAW_DIR = Path(os.environ.get("OPENCLAW_HOME", Path.home() / ".openclaw"))
STATE_BASE = OPENCLAW_DIR / "skill-state"
OWN_STATE = STATE_BASE / "morning-briefing" / "state.yaml"


def load_state(skill_name: str) -> dict:
    path = STATE_BASE / skill_name / "state.yaml"
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def save_own_state(state: dict) -> None:
    OWN_STATE.parent.mkdir(parents=True, exist_ok=True)
    with open(OWN_STATE, "w") as f:
        yaml.dump(state, f, default_flow_style=False)


def format_briefing(
    review: dict,
    tasks: dict,
    handoff: dict,
    today: date,
) -> str:
    lines = [
        f"# Morning Briefing — {today.strftime('%A, %B %-d')}",
        "",
    ]

    # --- Section: Daily priorities from daily-review ---
    priorities = review.get("priorities", [])
    if isinstance(priorities, str):
        # YAML loaded as string in fallback loader
        priorities = [p.strip("- ").strip() for p in priorities.split(",") if p.strip()]

    if priorities:
        lines.append("## Today's Priorities")
        for p in priorities:
            lines.append(f"  • {p}")
    else:
        lines.append("## Today's Priorities")
        lines.append("  (No priorities set — run `daily-review` to populate)")
    lines.append("")

    # --- Section: Active long-running task ---
    task_status = tasks.get("status", "")
    task_id = tasks.get("task_id", "")
    task_desc = tasks.get("description", "")
    next_action = tasks.get("next_action", "")

    lines.append("## Active Task")
    if task_status in ("in_progress", "paused") and task_id:
        lines.append(f"  Task:   {task_id}")
        if task_desc:
            lines.append(f"  Goal:   {task_desc}")
        lines.append(f"  Status: {task_status}")
        if next_action:
            lines.append(f"  Next:   {next_action}")
    else:
        lines.append("  No active long-running task")
    lines.append("")

    # --- Section: Pending handoff ---
    handoff_status = handoff.get("status", "none")
    handoff_path = handoff.get("active_handoff_path", "")
    task_name = handoff.get("task_name", "")
    reason = handoff.get("reason", "")

    lines.append("## Pending Handoff")
    if handoff_status == "written" and handoff_path:
        lines.append(f"  ⚠️  Handoff waiting at: {handoff_path}")
        if task_name:
            lines.append(f"  Task: {task_name}")
        if reason:
            lines.append(f"  Why:  {reason}")
        lines.append("  → Run `task-handoff` to pick it up")
    else:
        lines.append("  No pending handoff")
    lines.append("")

    lines.append("---")
    lines.append(f"Delivered at {datetime.now().strftime('%H:%M')}. Have a great day.")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Deliver morning briefing")
    parser.add_argument("--force", action="store_true", help="Re-deliver even if done today")
    parser.add_argument("--dry-run", action="store_true", help="Print without updating state")
    args = parser.parse_args()

    today = date.today()
    own_state = load_state("morning-briefing")

    # Idempotency check
    last_date = own_state.get("last_briefing_date", "")
    if last_date == str(today) and not args.force:
        print(f"Briefing already delivered today ({today}). Use --force to re-deliver.")
        sys.exit(0)

    # Load sibling skill states
    review = load_state("daily-review")
    tasks = load_state("long-running-task-management")
    handoff = load_state("task-handoff")

    briefing = format_briefing(review, tasks, handoff, today)
    print(briefing)

    if not args.dry_run:
        own_state.update(
            {
                "last_briefing_date": str(today),
                "delivered_at": datetime.now().isoformat(),
                "items_count": briefing.count("  •") + briefing.count("  Task:"),
                "status": "delivered",
            }
        )
        save_own_state(own_state)


if __name__ == "__main__":
    main()
