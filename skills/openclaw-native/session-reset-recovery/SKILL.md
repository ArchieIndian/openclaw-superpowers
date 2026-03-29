---
name: session-reset-recovery
version: "1.0"
category: openclaw-native
description: Checkpoints active work before the overnight session reset window and restores a concise resume brief after restart so long tasks survive routine session loss.
stateful: true
cron: "45 3 * * *"
---

# Session Reset Recovery

## What it does

Some OpenClaw users lose active context during routine overnight session resets. Work is not always gone, but the active thread of thought is. Session Reset Recovery writes a compact checkpoint before the risky window and turns it into a resume brief after restart.

## When to invoke

- Automatically at 03:45 local time before the common overnight reset window
- Manually before stopping a long-running session
- Immediately after a reset when the user says "pick up where we left off"

## What to capture

- Current task name
- Current status
- The last stable checkpoint
- The next concrete action
- Files in play
- Risks or blockers
- Whether the checkpoint was created automatically or manually

## How to use

```bash
python3 recover.py --checkpoint --task "ship deployment-preflight" --next "run tests and open PR"
python3 recover.py --checkpoint --task "ship deployment-preflight" --checkpoint-text "deployment-preflight skill implemented"
python3 recover.py --resume
python3 recover.py --status
python3 recover.py --clear
python3 recover.py --format json
```

## Reset-window behaviour

At 03:45:

1. Read the current checkpoint state
2. If a task is in progress, write a fresh recovery checkpoint
3. Mark it as `pending_resume: true`
4. Save a short resume brief that can be injected after restart

If no task is active, skip.

## Recovery protocol

After a reset:

1. Run `python3 recover.py --resume`
2. Read the latest recovery brief
3. Confirm the last stable checkpoint and next step
4. Continue from the recorded next action instead of reconstructing context from memory

## Difference from task-handoff

`task-handoff` is a deliberate pause between agents or sessions.

`session-reset-recovery` is for routine or accidental session loss where the user wants the same agent to recover quickly with minimal friction.

## State

State file: `~/.openclaw/skill-state/session-reset-recovery/state.yaml`

Fields: `active_task`, `latest_checkpoint`, `resume_brief`, `pending_resume`, `checkpoint_history`.
