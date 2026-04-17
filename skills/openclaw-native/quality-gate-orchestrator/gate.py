#!/usr/bin/env python3
"""
Stateful quality gate tracker for OpenClaw tasks.

Records validation gates and reports whether required gates have passed or
been waived. Writes only its own state file under OPENCLAW_HOME.
"""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path


OPENCLAW_HOME = Path(os.environ.get("OPENCLAW_HOME", Path.home() / ".openclaw"))
STATE_FILE = OPENCLAW_HOME / "skill-state" / "quality-gate-orchestrator" / "state.yaml"
PASSING = {"pass", "waived"}


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def default_state() -> dict:
    return {"gates": [], "ready": True, "last_ready_at": "", "gate_history": []}


def load_state() -> dict:
    if not STATE_FILE.exists():
        return default_state()
    try:
        data = json.loads(STATE_FILE.read_text())
        if isinstance(data, dict):
            return {**default_state(), **data}
    except Exception:
        pass
    return default_state()


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def find_gate(state: dict, name: str):
    for gate in state.get("gates", []):
        if gate.get("name") == name:
            return gate
    return None


def append_history(state: dict, event: dict) -> None:
    history = state.get("gate_history") or []
    history.append(event)
    state["gate_history"] = history[-25:]


def compute_ready(state: dict) -> dict:
    blockers = []
    for gate in state.get("gates", []):
        if gate.get("required", True) and gate.get("last_status", "pending") not in PASSING:
            blockers.append({
                "name": gate.get("name", ""),
                "status": gate.get("last_status", "pending"),
                "command": gate.get("command", ""),
            })
    ready = not blockers
    state["ready"] = ready
    state["last_ready_at"] = now()
    return {"ready": ready, "blockers": blockers, "gates": state.get("gates", [])}


def add_gate(args: argparse.Namespace) -> dict:
    state = load_state()
    stamp = now()
    gate = find_gate(state, args.name)
    if gate is None:
        gate = {
            "name": args.name,
            "command": args.command or "",
            "required": not args.optional,
            "last_status": "pending",
            "note": args.note or "",
            "updated_at": stamp,
        }
        state["gates"].append(gate)
    else:
        gate["command"] = args.command or gate.get("command", "")
        gate["required"] = not args.optional
        gate["note"] = args.note or gate.get("note", "")
        gate["updated_at"] = stamp
    append_history(state, {"event": "add", "name": args.name, "at": stamp})
    compute_ready(state)
    save_state(state)
    return {"action": "add", "gate": gate, "ready": state["ready"]}


def record_gate(args: argparse.Namespace) -> tuple[dict, int]:
    state = load_state()
    gate = find_gate(state, args.name)
    if gate is None:
        return {"error": f"Unknown gate: {args.name}", "known_gates": state.get("gates", [])}, 1
    if args.status == "waived" and not args.note:
        return {"error": "Waived gates require --note."}, 1
    stamp = now()
    gate["last_status"] = args.status
    gate["note"] = args.note or gate.get("note", "")
    gate["updated_at"] = stamp
    append_history(state, {"event": "record", "name": args.name, "status": args.status, "at": stamp})
    readiness = compute_ready(state)
    save_state(state)
    return {"action": "record", "gate": gate, **readiness}, 0


def status_payload() -> dict:
    state = load_state()
    readiness = compute_ready(state)
    return {**state, "blockers": readiness["blockers"]}


def ready_payload() -> dict:
    state = load_state()
    readiness = compute_ready(state)
    append_history(state, {"event": "ready", "ready": readiness["ready"], "at": state["last_ready_at"]})
    save_state(state)
    return readiness


def print_text(payload: dict) -> None:
    if "error" in payload:
        print(f"ERROR: {payload['error']}")
        return
    gates = payload.get("gates", [])
    ready = payload.get("ready", False)
    print("Quality Gate Orchestrator")
    print(f"Ready: {str(ready).lower()}")
    if not gates:
        print("No gates recorded.")
        return
    for gate in gates:
        required = "required" if gate.get("required", True) else "optional"
        print(f"- {gate.get('name')}: {gate.get('last_status', 'pending')} ({required})")


def main() -> int:
    parser = argparse.ArgumentParser(description="Track task validation gates.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--status", action="store_true", help="Show gate state.")
    mode.add_argument("--add", action="store_true", help="Add or update a gate.")
    mode.add_argument("--record", action="store_true", help="Record a gate result.")
    mode.add_argument("--ready", action="store_true", help="Report completion readiness.")
    parser.add_argument("--name", help="Gate name.")
    parser.add_argument("--command", default="", help="Command associated with a gate.")
    parser.add_argument("--status-value", dest="status_alias", choices=["pass", "fail", "waived", "pending"], help=argparse.SUPPRESS)
    parser.add_argument("--status-result", dest="status_result", choices=["pass", "fail", "waived", "pending"], help=argparse.SUPPRESS)
    parser.add_argument("--result", choices=["pass", "fail", "waived", "pending"], help=argparse.SUPPRESS)
    parser.add_argument("--optional", action="store_true", help="Mark gate optional.")
    parser.add_argument("--note", default="", help="Result note or waiver reason.")
    parser.add_argument("--format", dest="output_format", choices=["text", "json"], default="text")
    parser.add_argument("legacy_status", nargs="?", choices=["pass", "fail", "waived", "pending"], help=argparse.SUPPRESS)

    # argparse cannot reuse --status as both a mode and a result option. Accept
    # the requested interface by pre-processing "--record ... --status pass".
    import sys
    argv = sys.argv[1:]
    normalized = []
    record_mode = "--record" in argv
    i = 0
    while i < len(argv):
        if record_mode and argv[i] == "--status" and i + 1 < len(argv) and argv[i + 1] in {"pass", "fail", "waived", "pending"}:
            normalized.extend(["--status-result", argv[i + 1]])
            i += 2
            continue
        normalized.append(argv[i])
        i += 1

    args = parser.parse_args(normalized)
    result_status = args.status_result or args.status_alias or args.result or args.legacy_status

    exit_code = 0
    if args.add:
        if not args.name:
            payload, exit_code = {"error": "--add requires --name."}, 1
        else:
            payload = add_gate(args)
    elif args.record:
        if not args.name or not result_status:
            payload, exit_code = {"error": "--record requires --name and --status pass|fail|waived|pending."}, 1
        else:
            args.status = result_status
            payload, exit_code = record_gate(args)
    elif args.ready:
        payload = ready_payload()
    else:
        payload = status_payload()

    if args.output_format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print_text(payload)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
