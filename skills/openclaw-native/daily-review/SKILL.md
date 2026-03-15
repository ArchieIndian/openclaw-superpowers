---
name: daily-review
description: End-of-day structured summary and next-session prep. Use at the end of each working day or significant work block.
cron: "0 18 * * 1-5"
stateful: true
---

# Daily Review

State file: `~/.openclaw/skill-state/daily-review/state.yaml`

## The Review

### 1. What Was Accomplished
List everything completed. Be specific.

### 2. What's In Progress
For each: current status, next concrete step, blockers.

### 3. What Was Decided
Capture decisions and reasoning.

### 4. What Was Learned
Technical discoveries, user preferences, gotchas.

### 5. Tomorrow's Priorities
Top 3 things to do next session, in order.

## Format

```
## Daily Review - YYYY-MM-DD

### Accomplished
- [item]

### In Progress
- [item]: status / next step / blockers

### Decisions
- [decision]: reason

### Learned
- [learning]

### Tomorrow
1. [priority 1]
2. [priority 2]
3. [priority 3]
```

## After the Review

- Update memory/YYYY-MM-DD.md with full review
- Update MEMORY.md with any durable learnings
- Update open task files with current progress
- Update state: `last_review_date` (today's date), `priorities` (Tomorrow list), `status: done`, `last_review_at`

## Cron Wakeup Behavior

On 6pm weekday wakeup:
- Read state file
- If `last_review_date` is today: skip (already ran)
- Otherwise: run the review and update state
