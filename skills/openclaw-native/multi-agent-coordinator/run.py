#!/usr/bin/env python3
"""
Multi-Agent Coordinator for OpenClaw.

Manages a fleet of parallel agents: registration, heartbeats,
health checks, output consistency, and structured handoffs.

Usage:
    python3 run.py --register agent-id=coder role=code_impl channel=C001
    python3 run.py --heartbeat agent-id=coder task="Writing auth module"
    python3 run.py --health-check
    python3 run.py --record-output --agent coder --key api_design --value "POST /users"
    python3 run.py --consistency-check --key api_design
    python3 run.py --handoff --from coder --to reviewer --task "Review PR #42" --context "Added JWT auth"
    python3 run.py --status
    python3 run.py --deregister agent-id=coder
"""

import argparse
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
STATE_FILE = OPENCLAW_DIR / "skill-state" / "multi-agent-coordinator" / "state.yaml"


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"agents": [], "timeout_minutes": 30, "outputs": [],
                "contradictions": [], "handoffs": []}
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


def parse_kv_args(args_list: list) -> dict:
    """Parse ['key=value', 'key2=value2'] into a dict."""
    result = {}
    for item in args_list:
        if "=" in item:
            k, _, v = item.partition("=")
            result[k.strip()] = v.strip()
    return result


def find_agent(state: dict, agent_id: str) -> dict | None:
    return next((a for a in (state.get("agents") or []) if a["agent_id"] == agent_id), None)


def cmd_register(state: dict, kv: dict) -> dict:
    agent_id = kv.get("agent-id") or kv.get("agent_id", "")
    if not agent_id:
        print("ERROR: agent-id is required")
        sys.exit(1)
    agents = state.get("agents") or []
    existing = find_agent(state, agent_id)
    if existing:
        print(f"Agent already registered: {agent_id}")
        return state
    now = datetime.now().isoformat()
    agents.append({
        "agent_id": agent_id,
        "role": kv.get("role", "general"),
        "channel": kv.get("channel", ""),
        "status": "active",
        "current_task": kv.get("task", ""),
        "last_seen": now,
        "registered_at": now,
        "output_keys": [],
    })
    state["agents"] = agents
    print(f"✓ Registered: {agent_id} ({kv.get('role', 'general')})")
    return state


def cmd_heartbeat(state: dict, kv: dict) -> dict:
    agent_id = kv.get("agent-id") or kv.get("agent_id", "")
    agent = find_agent(state, agent_id)
    if not agent:
        print(f"ERROR: Agent not found: {agent_id}. Register first.")
        sys.exit(1)
    agent["last_seen"] = datetime.now().isoformat()
    agent["status"] = "active"
    if kv.get("task"):
        agent["current_task"] = kv["task"]
    print(f"♡ Heartbeat: {agent_id}")
    return state


def cmd_health_check(state: dict) -> dict:
    agents = state.get("agents") or []
    timeout = int(state.get("timeout_minutes") or 30)
    cutoff = datetime.now() - timedelta(minutes=timeout)
    timed_out = []
    now = datetime.now().isoformat()

    print(f"\nAgent Health Check (timeout: {timeout}min)")
    print(f"{'─' * 40}")

    for agent in agents:
        if agent.get("status") == "completed":
            print(f"  ✓ {agent['agent_id']} — completed")
            continue
        last_seen_raw = agent.get("last_seen", "")
        try:
            last_seen = datetime.fromisoformat(last_seen_raw)
            age_min = (datetime.now() - last_seen).total_seconds() / 60
            if last_seen < cutoff:
                agent["status"] = "timed_out"
                timed_out.append(agent["agent_id"])
                print(f"  ✗ {agent['agent_id']} — TIMED OUT ({age_min:.0f}min ago)")
            else:
                print(f"  ✓ {agent['agent_id']} — active ({age_min:.0f}min ago) — {agent.get('current_task', '')}")
        except ValueError:
            print(f"  ? {agent['agent_id']} — unknown last_seen")

    if timed_out:
        print(f"\n⚠ {len(timed_out)} agent(s) timed out: {', '.join(timed_out)}")
        print("  → Reassign tasks or increase --timeout-minutes")
    else:
        print(f"\n✓ All {len(agents)} agent(s) healthy")
    print()
    return state


def cmd_record_output(state: dict, agent_id: str, key: str, value: str) -> dict:
    outputs = state.get("outputs") or []
    outputs.append({
        "key": key,
        "agent_id": agent_id,
        "value": value,
        "recorded_at": datetime.now().isoformat(),
    })
    state["outputs"] = outputs
    # Update agent's output_keys
    agent = find_agent(state, agent_id)
    if agent:
        keys = agent.get("output_keys") or []
        if key not in keys:
            keys.append(key)
        agent["output_keys"] = keys
    print(f"✓ Output recorded: {agent_id} → {key}")
    return state


def cmd_consistency_check(state: dict, key: str) -> dict:
    outputs = [o for o in (state.get("outputs") or []) if o.get("key") == key]
    if len(outputs) < 2:
        print(f"Only {len(outputs)} output(s) for key '{key}' — nothing to compare")
        return state

    values = {o["agent_id"]: o["value"] for o in outputs}
    unique_values = set(values.values())

    print(f"\nConsistency Check: '{key}'")
    for agent_id, value in values.items():
        print(f"  {agent_id}: {value[:80]}")

    if len(unique_values) == 1:
        print(f"\n✓ All agents agree on '{key}'")
    else:
        print(f"\n⚠ Contradiction detected: {len(unique_values)} different values")
        contradiction = {
            "key": key,
            "agents": list(values.keys()),
            "values": list(values.values()),
            "detected_at": datetime.now().isoformat(),
            "resolved": False,
            "resolution": "",
        }
        contradictions = state.get("contradictions") or []
        contradictions.append(contradiction)
        state["contradictions"] = contradictions
        print("  → Resolve before merging outputs")
        sys.exit(1)
    return state


def cmd_handoff(state: dict, from_agent: str, to_agent: str,
                task: str, context: str) -> dict:
    handoffs = state.get("handoffs") or []
    handoffs.append({
        "from_agent": from_agent,
        "to_agent": to_agent,
        "task": task,
        "context": context,
        "handed_at": datetime.now().isoformat(),
        "accepted_at": "",
    })
    state["handoffs"] = handoffs
    # Update agent statuses
    from_a = find_agent(state, from_agent)
    if from_a:
        from_a["status"] = "idle"
    to_a = find_agent(state, to_agent)
    if to_a:
        to_a["status"] = "active"
        to_a["current_task"] = task
    print(f"✓ Handoff: {from_agent} → {to_agent}: {task}")
    return state


def cmd_status(state: dict) -> None:
    agents = state.get("agents") or []
    contradictions = [c for c in (state.get("contradictions") or []) if not c.get("resolved")]
    handoffs = state.get("handoffs") or []

    print(f"\nMulti-Agent Coordinator Status")
    print(f"{'─' * 40}")
    print(f"Agents:         {len(agents)}")
    print(f"Contradictions: {len(contradictions)} unresolved")
    print(f"Handoffs:       {len(handoffs)}")
    print()
    status_icons = {"active": "▶", "idle": "⏸", "timed_out": "✗",
                    "completed": "✓", "failed": "✗"}
    for agent in agents:
        icon = status_icons.get(agent.get("status"), "?")
        print(f"  {icon} {agent['agent_id']} [{agent.get('role','')}]  "
              f"— {agent.get('current_task', 'no task')}")
    if contradictions:
        print(f"\nUnresolved contradictions:")
        for c in contradictions:
            print(f"  ⚠ '{c['key']}': {c['agents']}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Multi-agent coordinator")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--register", nargs="+", metavar="KEY=VAL")
    group.add_argument("--heartbeat", nargs="+", metavar="KEY=VAL")
    group.add_argument("--health-check", action="store_true")
    group.add_argument("--record-output", action="store_true")
    group.add_argument("--consistency-check", action="store_true")
    group.add_argument("--handoff", action="store_true")
    group.add_argument("--status", action="store_true")
    group.add_argument("--deregister", nargs="+", metavar="KEY=VAL")
    parser.add_argument("--agent", default="")
    parser.add_argument("--key", default="")
    parser.add_argument("--value", default="")
    parser.add_argument("--from", dest="from_agent", default="")
    parser.add_argument("--to", dest="to_agent", default="")
    parser.add_argument("--task", default="")
    parser.add_argument("--context", default="")
    parser.add_argument("--timeout-minutes", type=int, default=0)
    args = parser.parse_args()

    state = load_state()
    if args.timeout_minutes:
        state["timeout_minutes"] = args.timeout_minutes

    if args.register:
        state = cmd_register(state, parse_kv_args(args.register))
    elif args.heartbeat:
        state = cmd_heartbeat(state, parse_kv_args(args.heartbeat))
    elif args.health_check:
        state = cmd_health_check(state)
    elif args.record_output:
        state = cmd_record_output(state, args.agent, args.key, args.value)
    elif args.consistency_check:
        state = cmd_consistency_check(state, args.key)
    elif args.handoff:
        state = cmd_handoff(state, args.from_agent, args.to_agent,
                           args.task, args.context)
    elif args.deregister:
        kv = parse_kv_args(args.deregister)
        aid = kv.get("agent-id", "")
        state["agents"] = [a for a in (state.get("agents") or [])
                          if a["agent_id"] != aid]
        print(f"Deregistered: {aid}")
    elif args.status:
        cmd_status(state)
        return

    save_state(state)


if __name__ == "__main__":
    main()
