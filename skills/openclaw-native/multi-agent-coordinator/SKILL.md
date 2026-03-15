---
name: multi-agent-coordinator
version: "1.0"
category: openclaw-native
description: Orchestrates multiple parallel OpenClaw agents — tracks health, detects timeouts, reconciles conflicting outputs, and manages structured handoffs
stateful: true
---

# multi-agent-coordinator

When running 3+ OpenClaw agents in parallel, the flat `agents.list[]` config becomes unmanageable, channel "bleeding" occurs between agents, parallel agents can produce contradictory outputs, and there is no timeout detection for silent agent failures.

This skill lives in the **orchestrator agent** and provides: a shared agent registry, health-check heartbeats, output consistency checks, and structured inter-agent handoffs.

## Agent registry

Register each sub-agent when it starts:
```
python3 run.py --register agent-id=coder role=code_implementation channel=C001
python3 run.py --register agent-id=reviewer role=code_review channel=C002
```

The registry tracks: agent ID, role, channel, status, last-seen timestamp, and current task.

## Health checks

The orchestrator pings each registered agent's last-seen timestamp. An agent is considered **timed out** if it hasn't updated in longer than the configured timeout (default: 30 minutes).

Invoke periodically:
```
python3 run.py --health-check
```

On timeout detection: write `AGENT_TIMEOUT` to state, alert the orchestrator, and prompt: "Agent `coder` hasn't responded in 45 minutes. Reassign task or wait?"

## Output consistency checkpoint

Before merging parallel agent outputs:
```
python3 run.py --consistency-check --agents coder reviewer --key "api_design"
```

The orchestrator compares outputs for the same key and flags contradictions. Example: `coder` proposes `POST /users`, `reviewer` proposes `PUT /users/{id}` for the same operation — these are flagged as contradictions requiring human resolution before merge.

## Structured handoff

Pass context from one agent to another:
```
python3 run.py --handoff --from coder --to reviewer --task-file handoff.yaml
```

Handoff files capture: what was done, what wasn't, key decisions made, constraints discovered, and next recommended action. This extends `task-handoff` (which is single-agent) to the multi-agent case.

## Difference from workflow-orchestration

`workflow-orchestration` executes a linear sequence of steps in a single agent. `multi-agent-coordinator` manages a parallel fleet: independent agents with their own sessions, channels, and context windows.
