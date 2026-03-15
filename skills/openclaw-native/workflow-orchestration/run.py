#!/usr/bin/env python3
"""
Workflow Orchestration state manager for OpenClaw.

Manages YAML-backed workflow state: step advancement, failure handling,
status reporting, and resume support. Designed to be called by the agent
at each step transition.

Usage:
    python3 run.py --status                          # Show current workflow state
    python3 run.py --start <name> <steps-file>       # Start a new workflow
    python3 run.py --step-done                        # Advance to next step
    python3 run.py --step-failed "<reason>"           # Mark step failed (+ optional fallback)
    python3 run.py --complete                         # Mark workflow complete
    python3 run.py --reset                            # Clear workflow state

State file: ~/.openclaw/skill-state/workflow-orchestration/state.yaml

Steps file format (YAML):
    steps:
      - skill: skill-name
        instruction: "Brief instruction for this step"
        on_failure: fallback-skill-name   # optional
      - skill: another-skill
        instruction: "Next step"
"""

import argparse
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
STATE_FILE = OPENCLAW_DIR / "skill-state" / "workflow-orchestration" / "state.yaml"


# ── Minimal YAML helpers ─────────────────────────────────────────────────────

def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        text = STATE_FILE.read_text()
        if HAS_YAML:
            return yaml.safe_load(text) or {}
        # Fallback: very limited — recommend installing PyYAML
        return {}
    except Exception:
        return {}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if HAS_YAML:
        with open(STATE_FILE, "w") as f:
            yaml.dump(state, f, default_flow_style=False, allow_unicode=True)
    else:
        # Best-effort flat dump
        with open(STATE_FILE, "w") as f:
            for k, v in state.items():
                f.write(f"{k}: {v!r}\n")


# ── Commands ─────────────────────────────────────────────────────────────────

def cmd_status(state: dict) -> None:
    if not state:
        print("No active workflow.")
        return

    name = state.get("workflow_name", "unnamed")
    status = state.get("status", "idle")
    current = state.get("current_step", 1)
    total = state.get("total_steps", 0)
    steps = state.get("steps", [])
    last = state.get("last_updated", "")

    print(f"\nWorkflow: {name}")
    print(f"Status:   {status}")
    print(f"Progress: step {current}/{total}")
    if last:
        print(f"Updated:  {last}")

    if status == "blocked":
        print(f"Blocked:  {state.get('blocked_reason', '(no reason)')}")

    if steps:
        print("\nSteps:")
        for i, step in enumerate(steps, start=1):
            marker = "→" if i == current else " "
            step_status = step.get("status", "pending")
            icon = {"complete": "✓", "failed": "✗", "skipped": "⊘"}.get(step_status, "○")
            skill = step.get("skill", "?")
            instr = step.get("instruction", "")
            print(f"  {marker} {icon} [{i}] {skill}: {instr}")
    print()


def cmd_start(state: dict, name: str, steps_file: str) -> dict:
    if state.get("status") in ("in_progress",):
        existing = state.get("workflow_name", "unknown")
        print(f"ERROR: Workflow '{existing}' is already in progress. Use --reset first.")
        sys.exit(1)

    if not HAS_YAML:
        print("ERROR: PyYAML is required to load steps files. Install with: pip install pyyaml")
        sys.exit(1)

    steps_path = Path(steps_file)
    if not steps_path.exists():
        print(f"ERROR: Steps file not found: {steps_file}")
        sys.exit(1)

    with open(steps_path) as f:
        steps_def = yaml.safe_load(f) or {}

    raw_steps = steps_def.get("steps", [])
    if not raw_steps:
        print("ERROR: Steps file must contain a 'steps' list.")
        sys.exit(1)

    steps = []
    for i, raw in enumerate(raw_steps, start=1):
        steps.append(
            {
                "index": i,
                "skill": raw.get("skill", f"step-{i}"),
                "instruction": raw.get("instruction", ""),
                "on_failure": raw.get("on_failure", ""),
                "status": "pending",
            }
        )

    new_state = {
        "workflow_name": name,
        "status": "in_progress",
        "current_step": 1,
        "total_steps": len(steps),
        "steps": steps,
        "blocked_reason": "",
        "started_at": datetime.now().isoformat(),
        "last_updated": datetime.now().isoformat(),
    }
    return new_state


def cmd_step_done(state: dict) -> dict:
    if not state:
        print("ERROR: No active workflow.")
        sys.exit(1)

    current = state.get("current_step", 1)
    total = state.get("total_steps", 0)
    steps = state.get("steps", [])

    # Mark current step complete
    if steps and len(steps) >= current:
        steps[current - 1]["status"] = "complete"

    if current >= total:
        state["status"] = "complete"
        state["current_step"] = total
        print(f"✓ Workflow '{state.get('workflow_name')}' complete.")
    else:
        state["current_step"] = current + 1
        next_step = steps[current] if len(steps) > current else None
        if next_step:
            print(
                f"→ Step {current} done. Next: [{current + 1}] {next_step['skill']}: {next_step['instruction']}"
            )

    state["steps"] = steps
    state["last_updated"] = datetime.now().isoformat()
    return state


def cmd_step_failed(state: dict, reason: str) -> dict:
    if not state:
        print("ERROR: No active workflow.")
        sys.exit(1)

    current = state.get("current_step", 1)
    steps = state.get("steps", [])

    if steps and len(steps) >= current:
        step = steps[current - 1]
        step["status"] = "failed"
        fallback = step.get("on_failure", "")

        if fallback:
            print(f"⚠ Step {current} failed. on_failure skill: '{fallback}' — invoke it, then call --step-done.")
            # Treat as recoverable; don't block
        else:
            state["status"] = "blocked"
            state["blocked_reason"] = reason
            print(f"✗ Step {current} failed: {reason}")
            print(f"  No on_failure fallback. Workflow blocked.")
            print(f"  Fix the issue and run --step-done to continue, or --reset to restart.")

    state["steps"] = steps
    state["last_updated"] = datetime.now().isoformat()
    return state


def cmd_complete(state: dict) -> dict:
    state["status"] = "complete"
    state["last_updated"] = datetime.now().isoformat()
    print(f"✓ Workflow '{state.get('workflow_name')}' marked complete.")
    return state


def cmd_reset() -> dict:
    print("Workflow state cleared.")
    return {}


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Workflow orchestration state manager")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--status", action="store_true", help="Show current workflow")
    group.add_argument("--start", nargs=2, metavar=("NAME", "STEPS_FILE"), help="Start a workflow")
    group.add_argument("--step-done", action="store_true", help="Mark current step complete")
    group.add_argument("--step-failed", metavar="REASON", help="Mark current step failed")
    group.add_argument("--complete", action="store_true", help="Mark workflow complete")
    group.add_argument("--reset", action="store_true", help="Clear workflow state")
    args = parser.parse_args()

    state = load_state()

    if args.status:
        cmd_status(state)
        return

    if args.start:
        state = cmd_start(state, args.start[0], args.start[1])

    elif args.step_done:
        state = cmd_step_done(state)

    elif args.step_failed:
        state = cmd_step_failed(state, args.step_failed)

    elif args.complete:
        state = cmd_complete(state)

    elif args.reset:
        state = cmd_reset()

    save_state(state)


if __name__ == "__main__":
    main()
