---
name: long-running-task-management
description: Breaks multi-hour tasks into checkpointed stages with resume capability. Use when a task is expected to take more than 30 minutes or multiple sessions.
cron: "*/15 * * * *"
stateful: true
---

# Long-Running Task Management

State file: `~/.openclaw/skill-state/long-running-task-management/state.yaml`

## When to Use

- Task estimated at more than 30 minutes
- Task will span multiple sessions
- Task modifies many files across multiple directories

## Starting a Task

1. Write initial state to the state file:
   - `task_id`: short kebab-case name
   - `status: in_progress`
   - `description`: one-sentence goal
   - `stages`: ordered list with `status: pending` for each
   - `started_at`: current timestamp
2. Begin the first stage

## At Each Checkpoint

1. Complete the stage
2. Run tests/verification
3. Update state file: mark stage `status: complete`, write `checkpoint` (what's stable now), write `next_action` (first thing to do on resume), update `last_updated`
4. Commit progress to git if applicable

## Resume After Interruption

1. Read the state file
2. Check `status` and `next_action`
3. Continue from the next `pending` stage — do NOT start over

## Completion

1. Update state: `status: complete`, final `checkpoint`
2. Run full verification

## Cron Wakeup Behavior

On each 15-minute wakeup:
- Read state file
- If `status: in_progress` and `last_updated` is stale (>30 min ago): log a checkpoint update to daily memory
- If `status: complete` or no active task: skip
