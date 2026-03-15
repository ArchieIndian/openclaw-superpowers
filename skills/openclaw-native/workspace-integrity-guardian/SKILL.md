---
name: workspace-integrity-guardian
version: "1.0"
category: openclaw-native
description: Detects drift or tampering in SOUL.md, AGENTS.md, MEMORY.md, and other critical workspace files and prompts recovery
stateful: true
cron: "0 3 * * 0"
---

# workspace-integrity-guardian

`SOUL.md`, `AGENTS.md`, `MEMORY.md`, and `IDENTITY.md` define the agent's persistent identity. These files can be accidentally overwritten by the agent itself, corrupted during a failed skill execution, or modified by a malicious installed skill. The SOUL.md documentation warns: *"A compromised SOUL.md means a permanently hijacked agent that survives restarts."*

This skill hashes all critical workspace files on first run, then checks for drift on a weekly schedule and on demand.

## Protected files

By default, the following files are monitored:

- `~/.openclaw/workspace/SOUL.md`
- `~/.openclaw/workspace/AGENTS.md`
- `~/.openclaw/workspace/MEMORY.md`
- `~/.openclaw/workspace/IDENTITY.md`

Add custom files:
```
python3 guard.py --add-file ~/.openclaw/workspace/MY_RULES.md
```

## Cron Wakeup Behaviour

Runs weekly on Sunday at 03:00 (`cron: "0 3 * * 0"`). On each wakeup:

1. Read stored baseline hashes from state
2. Re-hash all monitored files
3. Compare — if any hash changed, classify the change
4. Surface drift to user; ask whether to accept or restore

## Drift classification

| Change type | Indicator | Action |
|---|---|---|
| Append-only | File grew, existing content intact | Review + accept |
| Truncation | File shrank significantly | High-priority alert |
| Full replacement | Hash completely different | Critical alert |
| Deletion | File missing | Attempt restore from baseline |

## Recovery protocol

When drift is detected:

1. Show a diff summary: what changed, how much, when (file mtime)
2. Ask user: "Accept this change?" or "Restore from baseline?"
3. If restore: write the baseline content back to the file
4. If accept: update the stored baseline hash to the new hash
5. Log the decision to state

## Difference from persistent-memory-hygiene

`persistent-memory-hygiene` enforces formatting and structure discipline in memory files (keeping them clean and useful). This skill is purely about **integrity**: detecting unauthorised or accidental changes to the agent's identity and configuration files.
