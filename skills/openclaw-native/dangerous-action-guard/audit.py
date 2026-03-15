#!/usr/bin/env python3
"""
Dangerous Action Guard — audit trail manager for OpenClaw.

Records pending confirmations, executions, rejections, and expirations.
Called by the agent before and after any dangerous action.

Usage:
    python3 audit.py --pending "rm -rf /tmp/old" --category file_destruction --scope "/tmp/old (312 files)"
    python3 audit.py --confirm "rm -rf /tmp/old" --phrase "yes go ahead"
    python3 audit.py --reject "rm -rf /tmp/old"
    python3 audit.py --expire-stale       # Mark expired pending actions
    python3 audit.py --history            # Show full audit trail
    python3 audit.py --history --last 20  # Last 20 entries
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

OPENCLAW_DIR = Path(os.environ.get("OPENCLAW_HOME", Path.home() / ".openclaw"))
STATE_FILE = OPENCLAW_DIR / "skill-state" / "dangerous-action-guard" / "state.yaml"
APPROVAL_WINDOW_MINUTES = 5


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"audit_trail": [], "total_executed": 0,
                "total_rejected": 0, "total_expired": 0}
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


def cmd_pending(state: dict, command: str, category: str, scope: str,
                reversible: bool) -> dict:
    now = datetime.now()
    state["pending_action"] = {
        "description": command,
        "category": category,
        "command": command,
        "scope": scope,
        "reversible": reversible,
        "requested_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=APPROVAL_WINDOW_MINUTES)).isoformat(),
    }
    print(f"⏳ Pending confirmation: {command}")
    print(f"   Category:   {category}")
    print(f"   Scope:      {scope}")
    print(f"   Reversible: {'yes' if reversible else 'NO'}")
    print(f"   Expires:    {APPROVAL_WINDOW_MINUTES} minutes from now")
    return state


def cmd_confirm(state: dict, command: str, phrase: str) -> dict:
    pending = state.get("pending_action") or {}
    if not pending:
        print("ERROR: No pending action found.")
        sys.exit(1)

    # Expiry check
    expires_at = pending.get("expires_at", "")
    if expires_at:
        try:
            if datetime.now() > datetime.fromisoformat(expires_at):
                print(f"ERROR: Approval window expired at {expires_at[:19]}. Re-confirm with user.")
                sys.exit(1)
        except ValueError:
            pass

    entry = dict(pending)
    entry["outcome"] = "executed"
    entry["confirmed_at"] = datetime.now().isoformat()
    entry["confirmation"] = phrase

    trail = state.get("audit_trail") or []
    trail.append(entry)
    state["audit_trail"] = trail
    state["pending_action"] = None
    state["total_executed"] = (state.get("total_executed") or 0) + 1

    print(f"✓ Action confirmed and logged: {command}")
    return state


def cmd_reject(state: dict, command: str) -> dict:
    pending = state.get("pending_action") or {}
    entry = dict(pending) if pending else {"description": command, "command": command}
    entry["outcome"] = "rejected"
    entry["rejected_at"] = datetime.now().isoformat()

    trail = state.get("audit_trail") or []
    trail.append(entry)
    state["audit_trail"] = trail
    state["pending_action"] = None
    state["total_rejected"] = (state.get("total_rejected") or 0) + 1

    print(f"✗ Action rejected and logged: {command}")
    return state


def cmd_expire_stale(state: dict) -> dict:
    pending = state.get("pending_action") or {}
    if not pending:
        return state
    expires_at = pending.get("expires_at", "")
    if not expires_at:
        return state
    try:
        if datetime.now() > datetime.fromisoformat(expires_at):
            entry = dict(pending)
            entry["outcome"] = "expired"
            trail = state.get("audit_trail") or []
            trail.append(entry)
            state["audit_trail"] = trail
            state["pending_action"] = None
            state["total_expired"] = (state.get("total_expired") or 0) + 1
            print(f"⏰ Expired pending action: {pending.get('command', '(unknown)')}")
    except ValueError:
        pass
    return state


def cmd_history(state: dict, last: int) -> None:
    trail = state.get("audit_trail") or []
    if last:
        trail = trail[-last:]
    total_e = state.get("total_executed", 0)
    total_r = state.get("total_rejected", 0)
    total_x = state.get("total_expired", 0)

    print(f"\nDangerous Action Audit Trail")
    print(f"{'─' * 40}")
    print(f"Executed: {total_e}  Rejected: {total_r}  Expired: {total_x}")
    print()

    if not trail:
        print("(no records yet)")
        return

    icons = {"executed": "✓", "rejected": "✗", "expired": "⏰"}
    for entry in reversed(trail):
        outcome = entry.get("outcome", "?")
        icon = icons.get(outcome, "?")
        ts = (entry.get("confirmed_at") or entry.get("rejected_at")
              or entry.get("requested_at") or "")[:19]
        print(f"  {icon} [{ts}] {entry.get('command', entry.get('description', '?'))}")
        print(f"       Category: {entry.get('category', '?')}  |  "
              f"Reversible: {'yes' if entry.get('reversible') else 'no'}")
        if outcome == "executed":
            print(f"       Confirmed with: \"{entry.get('confirmation', '')}\"")
        print()


def main():
    parser = argparse.ArgumentParser(description="Dangerous action audit trail")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--pending", metavar="COMMAND", help="Register a pending action")
    group.add_argument("--confirm", metavar="COMMAND", help="Mark action as confirmed")
    group.add_argument("--reject", metavar="COMMAND", help="Mark action as rejected")
    group.add_argument("--expire-stale", action="store_true")
    group.add_argument("--history", action="store_true")
    parser.add_argument("--category", default="other")
    parser.add_argument("--scope", default="unknown")
    parser.add_argument("--reversible", action="store_true", default=False)
    parser.add_argument("--phrase", default="confirmed", help="User confirmation phrase")
    parser.add_argument("--last", type=int, default=0, help="Show last N entries")
    args = parser.parse_args()

    state = load_state()

    if args.history:
        cmd_history(state, args.last)
        return

    if args.expire_stale:
        state = cmd_expire_stale(state)
    elif args.pending:
        state = cmd_pending(state, args.pending, args.category, args.scope, args.reversible)
    elif args.confirm:
        state = cmd_confirm(state, args.confirm, args.phrase)
    elif args.reject:
        state = cmd_reject(state, args.reject)

    save_state(state)


if __name__ == "__main__":
    main()
