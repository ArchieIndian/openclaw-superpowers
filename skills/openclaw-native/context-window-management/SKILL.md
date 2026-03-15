---
name: context-window-management
description: Prevents context overflow on long-running OpenClaw sessions. Use when approaching context limits.
stateful: true
---

# Context Window Management

State file: `~/.openclaw/skill-state/context-window-management/state.yaml`

## Warning Signs

- Session running for many hours
- Responses getting slower or less coherent
- Carrying context about completed tasks no longer relevant
- Large code blocks in context not being actively used
- Check `last_compacted_at` in state — if compacted recently this session, prefer a lighter strategy

## Reduction Strategies

### Summarize Completed Work
Replace detailed context about finished tasks with short summaries.
After: write state `strategy_used: summarize`, `current_task`, `last_compacted_at`.

### Externalize Reference Material
Move large docs/schemas to files. Reference them by filename rather than including in context.
After: write state `strategy_used: externalize`, `current_task`, `last_compacted_at`.

### Clean Session Restart
Write comprehensive handoff document, start fresh session, load only what's needed.
After: write state `strategy_used: clean_restart`, `handoff_path`, `current_task`, `last_compacted_at`.

## What to Keep in Context

- Current task objective
- Current step being executed
- Relevant code being modified (just the parts in scope)
- Recent error messages if debugging

## What to Offload

- Completed task details (summarize to memory)
- Full file contents of files not currently being edited
- Conversation history from different topics hours ago
- Reference docs that can be re-read on demand
