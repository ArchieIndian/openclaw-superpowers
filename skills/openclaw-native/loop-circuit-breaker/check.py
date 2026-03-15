#!/usr/bin/env python3
"""
Loop Circuit Breaker for OpenClaw.

Tracks tool call failures per session and trips when the same
(tool, args, error) signature fails N times in a row.

Usage:
    # Record a tool call failure — returns "trip" if circuit should open
    python3 check.py --record --tool read --args '{"path": ""}' --error "missing required parameter: path"

    # Mark a tripped loop as resolved
    python3 check.py --resolve "read" --resolution "User provided correct path"

    # Show current session state
    python3 check.py --status

    # Reset session (new session start)
    python3 check.py --new-session SESSION_ID

    # Set trip threshold
    python3 check.py --set-threshold 3
"""

import argparse
import hashlib
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
STATE_FILE = OPENCLAW_DIR / "skill-state" / "loop-circuit-breaker" / "state.yaml"
HISTORY_TTL_HOURS = 2

TRANSIENT_ERRORS = {
    "rate_limit", "timeout", "network_error", "connection_error",
    "429", "503", "502",
}


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"trip_threshold": 2, "call_history": [],
                "tripped_loops": [], "total_loops_detected": 0}
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


def make_signature(tool: str, args: str, error: str) -> str:
    """Create a normalized hash for deduplication."""
    # Normalise args: sort keys, strip whitespace values
    try:
        args_dict = json.loads(args) if args else {}
        normalised = json.dumps(args_dict, sort_keys=True)
    except (json.JSONDecodeError, TypeError):
        normalised = str(args)[:100]

    # Normalise error type (strip specific values like path names)
    error_type = error.split(":")[0].strip().lower() if error else "unknown"

    key = f"{tool.lower()}|{normalised}|{error_type}"
    return hashlib.md5(key.encode()).hexdigest()[:12]


def is_transient(error: str) -> bool:
    e = error.lower()
    return any(t in e for t in TRANSIENT_ERRORS)


def prune_old(history: list) -> list:
    cutoff = datetime.now() - timedelta(hours=HISTORY_TTL_HOURS)
    return [
        h for h in history
        if datetime.fromisoformat(h.get("last_seen", datetime.now().isoformat())) > cutoff
    ]


def cmd_record(state: dict, tool: str, args: str, error: str) -> tuple[dict, bool]:
    """
    Record a failure. Returns (updated_state, should_trip).
    Prints "trip" to stdout if circuit should open — agent checks this.
    """
    threshold = int(state.get("trip_threshold") or 2)

    # Transient errors get more slack
    if is_transient(error):
        transient_threshold = max(threshold, 3)
        threshold = transient_threshold

    sig = make_signature(tool, args, error)
    history = prune_old(state.get("call_history") or [])

    existing = next((h for h in history if h["signature"] == sig), None)
    now = datetime.now().isoformat()

    if existing:
        existing["fail_count"] += 1
        existing["last_seen"] = now
        fail_count = existing["fail_count"]
    else:
        error_type = error.split(":")[0].strip().lower() if error else "unknown"
        entry = {
            "signature": sig,
            "tool_name": tool,
            "args_summary": args[:100] if args else "",
            "error_type": error_type,
            "error_msg": error[:200] if error else "",
            "fail_count": 1,
            "first_seen": now,
            "last_seen": now,
            "tripped": False,
        }
        history.append(entry)
        existing = entry
        fail_count = 1

    state["call_history"] = history
    should_trip = (fail_count >= threshold) and not existing.get("tripped", False)

    if should_trip:
        existing["tripped"] = True
        tripped = state.get("tripped_loops") or []
        tripped.append({
            "tool_name": tool,
            "args_summary": args[:100] if args else "",
            "error_msg": error[:200] if error else "",
            "fail_count": fail_count,
            "tripped_at": now,
            "resolved": False,
            "resolution": "",
        })
        state["tripped_loops"] = tripped
        state["total_loops_detected"] = (state.get("total_loops_detected") or 0) + 1
        print(f"TRIP: Loop detected on {tool}() — {fail_count} identical failures. "
              f"Error: {error[:80]}")
    else:
        print(f"ok: {tool}() fail #{fail_count}/{threshold}")

    return state, should_trip


def cmd_resolve(state: dict, tool: str, resolution: str) -> dict:
    tripped = state.get("tripped_loops") or []
    for loop in tripped:
        if loop.get("tool_name") == tool and not loop.get("resolved"):
            loop["resolved"] = True
            loop["resolution"] = resolution
            print(f"✓ Loop resolved: {tool}() — {resolution}")
            break
    state["tripped_loops"] = tripped
    return state


def cmd_status(state: dict) -> None:
    threshold = state.get("trip_threshold", 2)
    history = prune_old(state.get("call_history") or [])
    tripped = [l for l in (state.get("tripped_loops") or []) if not l.get("resolved")]

    print(f"\nLoop Circuit Breaker — Session Status")
    print(f"{'─' * 40}")
    print(f"Trip threshold: {threshold} identical failures")
    print(f"Active failures tracked: {len(history)}")
    print(f"Open circuits: {len(tripped)}")
    print(f"Total detected (all time): {state.get('total_loops_detected', 0)}")

    if tripped:
        print(f"\nOpen loops (awaiting resolution):")
        for loop in tripped:
            print(f"  ✗ {loop['tool_name']}(): {loop['fail_count']} failures")
            print(f"    Error: {loop['error_msg'][:80]}")
            print(f"    Since: {loop.get('tripped_at','')[:19]}")

    if history:
        print(f"\nRecent failures (last {min(5, len(history))}):")
        for h in history[-5:]:
            status = "TRIPPED" if h.get("tripped") else f"{h['fail_count']}x"
            print(f"  {status}  {h['tool_name']}() — {h['error_type']}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Loop circuit breaker")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--record", action="store_true")
    group.add_argument("--resolve", metavar="TOOL")
    group.add_argument("--status", action="store_true")
    group.add_argument("--new-session", metavar="SESSION_ID")
    group.add_argument("--set-threshold", type=int, metavar="N")
    parser.add_argument("--tool", default="")
    parser.add_argument("--args", default="{}")
    parser.add_argument("--error", default="")
    parser.add_argument("--resolution", default="manually resolved")
    args = parser.parse_args()

    state = load_state()

    if args.set_threshold:
        state["trip_threshold"] = args.set_threshold
        print(f"Threshold set: {args.set_threshold}")
        save_state(state)
        return

    if args.new_session:
        state["session_id"] = args.new_session
        state["call_history"] = []
        state["tripped_loops"] = []
        print(f"New session: {args.new_session}")
        save_state(state)
        return

    if args.status:
        cmd_status(state)
        return

    if args.resolve:
        state = cmd_resolve(state, args.resolve, args.resolution)
        save_state(state)
        return

    if args.record:
        if not args.tool:
            print("ERROR: --tool is required with --record")
            sys.exit(1)
        state, tripped = cmd_record(state, args.tool, args.args, args.error)
        save_state(state)
        sys.exit(2 if tripped else 0)


if __name__ == "__main__":
    main()
