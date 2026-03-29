#!/usr/bin/env python3
"""
Session Reset Recovery for openclaw-superpowers.

Writes recovery checkpoints before the overnight reset window and prints a
resume brief after restart.
"""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

OPENCLAW_DIR = Path(os.environ.get("OPENCLAW_HOME", Path.home() / ".openclaw"))
STATE_FILE = OPENCLAW_DIR / "skill-state" / "session-reset-recovery" / "state.yaml"
MAX_HISTORY = 12


def default_state() -> dict:
    return {
        "active_task": "",
        "pending_resume": False,
        "latest_checkpoint": {},
        "resume_brief": "",
        "checkpoint_history": [],
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


def build_resume_brief(checkpoint: dict) -> str:
    task = checkpoint.get("task", "unknown-task")
    checkpoint_text = checkpoint.get("checkpoint_text", "No checkpoint recorded.")
    next_action = checkpoint.get("next_action", "No next action recorded.")
    return f"Resume `{task}`: {checkpoint_text} Next: {next_action}"


def write_checkpoint(state: dict, args: argparse.Namespace) -> dict:
    now = datetime.now().isoformat()
    latest = state.get("latest_checkpoint") or {}
    checkpoint = {
        "task": args.task or state.get("active_task") or latest.get("task", ""),
        "status": args.task_status or latest.get("status", "in_progress"),
        "checkpoint_text": args.checkpoint_text or latest.get("checkpoint_text", "Checkpoint recorded."),
        "next_action": args.next or latest.get("next_action", "Resume the active task."),
        "files_in_play": args.files or latest.get("files_in_play", []),
        "blockers": args.blockers or latest.get("blockers", []),
        "mode": "automatic" if args.automatic else "manual",
        "written_at": now,
    }
    state["active_task"] = checkpoint["task"]
    state["pending_resume"] = True
    state["latest_checkpoint"] = checkpoint
    state["resume_brief"] = build_resume_brief(checkpoint)
    history = state.get("checkpoint_history") or []
    history.insert(
        0,
        {
            "task": checkpoint["task"],
            "status": checkpoint["status"],
            "checkpoint_text": checkpoint["checkpoint_text"],
            "next_action": checkpoint["next_action"],
            "mode": checkpoint["mode"],
            "written_at": now,
        },
    )
    state["checkpoint_history"] = history[:MAX_HISTORY]
    save_state(state)
    return state


def clear_state(state: dict) -> dict:
    state["pending_resume"] = False
    state["resume_brief"] = ""
    state["active_task"] = ""
    state["latest_checkpoint"] = {}
    save_state(state)
    return state


def print_status(state: dict) -> None:
    checkpoint = state.get("latest_checkpoint") or {}
    print("\nSession Reset Recovery")
    print("───────────────────────────────────────────────────────")
    if not checkpoint:
        print("  No checkpoint recorded.")
        return
    print(f"  Task: {checkpoint.get('task', '')}")
    print(f"  Status: {checkpoint.get('status', '')}")
    print(f"  Pending resume: {state.get('pending_resume', False)}")
    print(f"  Written at: {checkpoint.get('written_at', '')}")
    print(f"  Next: {checkpoint.get('next_action', '')}")


def print_resume(state: dict) -> None:
    brief = state.get("resume_brief")
    if not brief:
        print("No recovery brief recorded.")
        return
    print(brief)


def main() -> None:
    parser = argparse.ArgumentParser(description="Recovery checkpoints for session resets")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--checkpoint", action="store_true", help="Write a recovery checkpoint")
    group.add_argument("--resume", action="store_true", help="Print the latest resume brief")
    group.add_argument("--status", action="store_true", help="Show current checkpoint status")
    group.add_argument("--clear", action="store_true", help="Clear the active recovery checkpoint")
    parser.add_argument("--automatic", action="store_true", help="Mark the checkpoint as cron-generated")
    parser.add_argument("--task", help="Active task name")
    parser.add_argument("--status-text", dest="task_status", help="Task status")
    parser.add_argument("--checkpoint-text", help="Last stable checkpoint summary")
    parser.add_argument("--next", help="Next concrete action")
    parser.add_argument("--files", nargs="*", default=[], help="Files in play")
    parser.add_argument("--blockers", nargs="*", default=[], help="Known blockers")
    parser.add_argument("--format", choices=["human", "json"], default="human")
    args = parser.parse_args()

    state = load_state()
    if args.checkpoint:
        state = write_checkpoint(state, args)
    elif args.clear:
        state = clear_state(state)

    if args.format == "json":
        if args.resume:
            print(json.dumps({"resume_brief": state.get("resume_brief", "")}, indent=2))
        else:
            print(json.dumps(state, indent=2))
        return

    if args.resume:
        print_resume(state)
    elif args.status or args.checkpoint or args.clear:
        print_status(state)


if __name__ == "__main__":
    main()
