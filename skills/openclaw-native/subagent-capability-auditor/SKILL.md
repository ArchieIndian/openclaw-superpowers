---
name: subagent-capability-auditor
version: "1.0"
category: openclaw-native
description: Audits subagent configuration for spawn depth, tool exposure, and fleet shape so multi-agent setups fail early instead of becoming expensive mystery states.
stateful: true
---

# Subagent Capability Auditor

## What it does

Subagent failures are often configuration failures hiding behind runtime symptoms: no spawn tool, unsafe `maxSpawnDepth`, too many loosely defined agents, or configs spread across files with no obvious ownership.

Subagent Capability Auditor inspects the available configuration and records the issues before the orchestrator tries to use them.

## When to invoke

- Before enabling subagents in a new environment
- After changing agent profiles or tool exposure
- When subagents fail to spawn or produce inconsistent fleet behaviour
- Before trusting large multi-agent workflows

## What it checks

| Check | Why it matters |
|---|---|
| Subagent config discovery | You cannot audit what the runtime cannot see |
| `maxSpawnDepth` | Too low blocks useful delegation; too high creates runaway trees |
| Spawn tool exposure | Missing `sessions_spawn` / equivalent makes subagents impossible |
| Fleet size | Large flat fleets without strong roles are hard to reason about |
| Role metadata | Agents without clear roles increase overlap and wasted token usage |

## How to use

```bash
python3 audit.py --audit
python3 audit.py --audit --path ~/.openclaw
python3 audit.py --status
python3 audit.py --findings
python3 audit.py --format json
```

## Output levels

- **PASS** — no configuration concerns found
- **WARN** — something is likely to work poorly or expensively
- **FAIL** — a required subagent capability appears to be missing

## Difference from multi-agent-coordinator

`multi-agent-coordinator` manages an active fleet.

`subagent-capability-auditor` validates whether the fleet is configured sanely enough to exist in the first place.

## State

State file: `~/.openclaw/skill-state/subagent-capability-auditor/state.yaml`

Fields: `last_audit_at`, `config_files`, `findings`, `audit_history`.
