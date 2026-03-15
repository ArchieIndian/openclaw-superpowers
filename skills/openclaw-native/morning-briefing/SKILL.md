---
name: morning-briefing
description: Compiles a daily morning briefing from active tasks, priorities, and pending items. Use at the start of each working day.
cron: "0 7 * * 1-5"
stateful: true
---

# Morning Briefing

State file: `~/.openclaw/skill-state/morning-briefing/state.yaml`

Start every working day knowing exactly what matters — one message, no tab-switching.

## When to Use

- On 7am weekday cron wakeup
- When the user asks for a morning update or daily kickoff

## The Briefing

Compile from these sources, in order:

1. **Today's priorities** — read `priorities` from `daily-review` state file (`~/.openclaw/skill-state/daily-review/state.yaml`)
2. **Active tasks** — read any task with `status: in_progress` from `long-running-task-management` state file
3. **Pending handoffs** — check `task-handoff` state; if `status: written`, flag it
4. **Date and day** — include today's date and day of week at the top

## Output Format

```
Good morning. Here's your [Day], [Date] briefing.

PRIORITIES
1. [priority from daily-review]
2. ...

IN PROGRESS
- [task_id]: [checkpoint] → next: [next_action]

NEEDS ATTENTION
- [handoff task_name] waiting to be picked up
```

Send via the user's active messaging channel (Telegram, Slack, etc.).

## After Delivery

Update state: `last_briefing_date` (today), `delivered_at`, `items_count` (total items in briefing).

## Cron Wakeup Behavior

On 7am weekday wakeup:
- Read state; if `last_briefing_date` is today, skip (already delivered)
- Otherwise compile and deliver briefing, then update state
