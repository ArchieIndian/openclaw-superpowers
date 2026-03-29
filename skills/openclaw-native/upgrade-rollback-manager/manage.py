#!/usr/bin/env python3
from __future__ import annotations

"""
Upgrade Rollback Manager for openclaw-superpowers.

Creates pre-upgrade snapshots of important OpenClaw paths and prints rollback
instructions from recorded snapshots.
"""

import argparse
import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

OPENCLAW_DIR = Path(os.environ.get("OPENCLAW_HOME", Path.home() / ".openclaw"))
STATE_FILE = OPENCLAW_DIR / "skill-state" / "upgrade-rollback-manager" / "state.yaml"
SNAPSHOT_ROOT = OPENCLAW_DIR / "rollback-snapshots"
MAX_HISTORY = 12
PRESERVED_PATHS = [
    OPENCLAW_DIR / "openclaw.json",
    OPENCLAW_DIR / "config",
    OPENCLAW_DIR / "extensions",
    OPENCLAW_DIR / "workspace",
]


def default_state() -> dict:
    return {
        "last_snapshot_at": "",
        "latest_snapshot": {},
        "snapshots": [],
        "rollback_history": [],
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


def detect_openclaw_version() -> str:
    if shutil.which("openclaw") is None:
        return "unknown"
    try:
        proc = subprocess.run(
            ["openclaw", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception:
        return "unknown"
    if proc.returncode != 0:
        return "unknown"
    return proc.stdout.strip() or "unknown"


def snapshot(label: str | None) -> dict:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    label = label or "pre-upgrade"
    snapshot_dir = SNAPSHOT_ROOT / f"{timestamp}-{label}"
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    copied = []
    for path in PRESERVED_PATHS:
        if not path.exists():
            continue
        target = snapshot_dir / path.name
        if path.is_dir():
            shutil.copytree(path, target, dirs_exist_ok=True)
        else:
            shutil.copy2(path, target)
        copied.append(str(path))

    entry = {
        "label": label,
        "snapshot_dir": str(snapshot_dir),
        "openclaw_version": detect_openclaw_version(),
        "created_at": datetime.now().isoformat(),
        "files": copied,
    }

    state = load_state()
    snapshots = state.get("snapshots") or []
    snapshots.insert(0, entry)
    state["last_snapshot_at"] = entry["created_at"]
    state["latest_snapshot"] = entry
    state["snapshots"] = snapshots[:MAX_HISTORY]
    save_state(state)
    return state


def generate_plan(state: dict, label: str) -> dict:
    snapshots = state.get("snapshots") or []
    match = next((item for item in snapshots if item.get("label") == label), None)
    if not match:
        raise SystemExit(f"No snapshot found for label '{label}'")
    history = state.get("rollback_history") or []
    history.insert(
        0,
        {
            "generated_at": datetime.now().isoformat(),
            "label": match["label"],
            "snapshot_dir": match["snapshot_dir"],
        },
    )
    state["rollback_history"] = history[:MAX_HISTORY]
    save_state(state)
    return match


def print_status(state: dict) -> None:
    latest = state.get("latest_snapshot") or {}
    print("\nUpgrade Rollback Manager")
    print("───────────────────────────────────────────────────────")
    if not latest:
        print("  No snapshots recorded.")
        return
    print(f"  Latest: {latest.get('label', '')}")
    print(f"  Version: {latest.get('openclaw_version', '')}")
    print(f"  Snapshot dir: {latest.get('snapshot_dir', '')}")
    print(f"  Files preserved: {len(latest.get('files', []))}")


def print_list(state: dict) -> None:
    snapshots = state.get("snapshots") or []
    if not snapshots:
        print("No snapshots recorded.")
        return
    print("\nSnapshots")
    print("───────────────────────────────────────────────────────")
    for item in snapshots:
        print(f"  {item['label']}  {item['openclaw_version']}  {item['created_at'][:19]}")


def print_plan(snapshot_entry: dict) -> None:
    print(f"\nRollback plan for {snapshot_entry['label']}")
    print("───────────────────────────────────────────────────────")
    print("1. Stop the OpenClaw gateway and background workers.")
    print(f"2. Restore preserved files from {snapshot_entry['snapshot_dir']}.")
    print(f"3. Reinstall or restart the previous runtime version: {snapshot_entry['openclaw_version']}.")
    print("4. Re-run deployment-preflight and runtime-verification-dashboard before reopening automation.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create rollback snapshots before upgrades")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--snapshot", action="store_true", help="Create a rollback snapshot")
    group.add_argument("--status", action="store_true", help="Show the latest snapshot summary")
    group.add_argument("--list", action="store_true", help="List recent snapshots")
    group.add_argument("--rollback-plan", metavar="LABEL", help="Print rollback instructions for a snapshot label")
    parser.add_argument("--label", help="Optional snapshot label")
    parser.add_argument("--format", choices=["human", "json"], default="human")
    args = parser.parse_args()

    if args.snapshot:
        state = snapshot(args.label)
    else:
        state = load_state()

    if args.format == "json":
        if args.rollback_plan:
            print(json.dumps(generate_plan(state, args.rollback_plan), indent=2))
        else:
            print(json.dumps(state, indent=2))
        return

    if args.status or args.snapshot:
        print_status(state)
    elif args.list:
        print_list(state)
    elif args.rollback_plan:
        plan = generate_plan(state, args.rollback_plan)
        print_plan(plan)


if __name__ == "__main__":
    main()
