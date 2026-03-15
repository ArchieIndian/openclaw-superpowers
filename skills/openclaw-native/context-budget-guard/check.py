#!/usr/bin/env python3
"""
Context Budget Guard for OpenClaw.

Estimates how much of the current context window has been consumed,
based on session start time and activity rate heuristics. Outputs a
LOW / MEDIUM / HIGH risk level and actionable recommendation.

Usage:
    python3 check.py                    # Check current context usage
    python3 check.py --session-start    # Mark now as session start in state
    python3 check.py --threshold N      # Custom HIGH threshold % (default: 70)
    python3 check.py --format json      # Output JSON instead of human-readable

State file: ~/.openclaw/skill-state/context-budget-guard/state.yaml
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

OPENCLAW_DIR = Path(os.environ.get("OPENCLAW_HOME", Path.home() / ".openclaw"))
STATE_FILE = OPENCLAW_DIR / "skill-state" / "context-budget-guard" / "state.yaml"

# Heuristic: average % of context window consumed per minute of active session.
# Based on ~200k token window, ~1600 tokens/min for mixed reading+writing.
FILL_RATE_PCT_PER_MIN = 0.8

THRESHOLDS = {
    "LOW": 50,
    "MEDIUM": 70,
}

RECOMMENDATIONS = {
    "LOW": "Context healthy. Continue working normally.",
    "MEDIUM": (
        "Context at medium capacity. Consider summarizing completed work "
        "and cleaning up scratch notes before the window fills."
    ),
    "HIGH": (
        "Context budget near limit. Trigger compaction now via "
        "`context-window-management` before productivity degrades."
    ),
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        text = STATE_FILE.read_text()
        if HAS_YAML:
            return yaml.safe_load(text) or {}
        result = {}
        for line in text.splitlines():
            line = line.strip()
            if line and ":" in line and not line.startswith("#"):
                k, _, v = line.partition(":")
                result[k.strip()] = v.strip()
        return result
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
                f.write(f"{k}: {v}\n")


def level_for(pct: float, high_threshold: int) -> str:
    if pct >= high_threshold:
        return "HIGH"
    elif pct >= THRESHOLDS["MEDIUM"]:
        return "MEDIUM"
    return "LOW"


# ── Core ──────────────────────────────────────────────────────────────────────

def estimate_usage(state: dict) -> tuple[float, float]:
    """Return (estimated_pct, elapsed_minutes)."""
    session_start_raw = state.get("session_start") or state.get("started_at", "")
    if not session_start_raw:
        return 0.0, 0.0
    try:
        if isinstance(session_start_raw, datetime):
            session_start = session_start_raw
        else:
            session_start = datetime.fromisoformat(str(session_start_raw))
        elapsed = (datetime.now() - session_start).total_seconds() / 60
        pct = min(elapsed * FILL_RATE_PCT_PER_MIN, 99.0)
        return round(pct, 1), round(elapsed, 1)
    except (ValueError, TypeError):
        return 0.0, 0.0


def build_result(state: dict, high_threshold: int) -> dict:
    pct, elapsed_min = estimate_usage(state)
    level = level_for(pct, high_threshold)
    task = state.get("current_task", "") or state.get("what_trying", "")
    last_compacted = state.get("last_compacted_at", "")

    return {
        "level": level,
        "estimated_pct": pct,
        "elapsed_minutes": elapsed_min,
        "current_task": task,
        "last_compacted_at": last_compacted,
        "recommendation": RECOMMENDATIONS[level],
        "timestamp": datetime.now().isoformat(),
    }


def print_human(result: dict) -> None:
    level = result["level"]
    pct = result["estimated_pct"]
    elapsed = result["elapsed_minutes"]
    task = result["current_task"]
    last_compacted = result["last_compacted_at"]

    level_icons = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🔴"}
    icon = level_icons.get(level, "⚪")

    print(f"\n{icon} Context Budget: {level}  (~{pct}% used)")
    print(f"   Session age:     {elapsed:.0f} min")
    if task:
        print(f"   Current task:   {task}")
    if last_compacted:
        print(f"   Last compacted: {last_compacted}")
    print(f"\n   → {result['recommendation']}\n")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Context budget estimator")
    parser.add_argument(
        "--session-start",
        action="store_true",
        help="Record now as session start in state",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=THRESHOLDS["MEDIUM"],
        help=f"HIGH threshold %% (default: {THRESHOLDS['MEDIUM']})",
    )
    parser.add_argument(
        "--format",
        choices=["human", "json"],
        default="human",
        help="Output format (default: human)",
    )
    parser.add_argument(
        "--task",
        metavar="DESCRIPTION",
        help="Record current task description in state",
    )
    args = parser.parse_args()

    state = load_state()

    if args.session_start:
        state["session_start"] = datetime.now().isoformat()
        save_state(state)
        print(f"Session start recorded: {state['session_start']}")
        sys.exit(0)

    if args.task:
        state["current_task"] = args.task
        save_state(state)
        print(f"Task recorded: {args.task}")

    if not state.get("session_start"):
        # Auto-seed if no session start recorded
        print("(No session_start in state — recording now as baseline)")
        state["session_start"] = datetime.now().isoformat()
        save_state(state)

    result = build_result(state, args.threshold)

    if args.format == "json":
        print(json.dumps(result, indent=2))
    else:
        print_human(result)

    # Update last_checked
    state["last_checked_at"] = result["timestamp"]
    save_state(state)

    # Exit with machine-readable code
    exit_codes = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
    sys.exit(exit_codes.get(result["level"], 0))


if __name__ == "__main__":
    main()
