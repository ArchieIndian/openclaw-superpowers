---
name: context-budget-guard
description: Proactively monitors estimated token usage during long sessions and triggers context-window-management before overflow, not after. Use at the start of any session expected to last more than 30 minutes.
stateful: true
---

# Context Budget Guard

State file: `~/.openclaw/skill-state/context-budget-guard/state.yaml`

Don't wait for the model to go incoherent. Act at 70%, not 95%.

## When to Use

- At the start of any long-running session (>30 min expected)
- Before each major task step in a multi-hour workflow
- When `long-running-task-management` advances to a new stage

## The Process

### Step 1: Initialize (Session Start)
Write to state: `session_start` timestamp, `compaction_count: 0`, `status: monitoring`, `threshold_pct: 70`.

### Step 2: Check Budget (Before Each Major Step)
Estimate current context usage as a rough percentage:
- **Low (<50%)** — continue normally
- **Medium (50–70%)** — note in state, proceed with caution (avoid loading large files)
- **High (>70%)** — trigger `context-window-management` NOW, before continuing

To estimate: count approximate tokens from recent messages, loaded file contents, and active task context.

### Step 3: After Compaction
- Increment `compaction_count` in state
- Write `last_compacted_at`, `strategy_used` (passed from `context-window-management`)
- Reset mental estimate to ~20% (post-compaction baseline)

### Step 4: Session End
Update state: `status: idle`, `session_end` timestamp.

## Key Principles

- The 70% threshold is the trigger — earlier is always better than later
- Check budget BEFORE loading large files or running subagents, not after
- If in doubt: compact. A clean context costs less than a confused one.
- Works best paired with `long-running-task-management` — check budget at every checkpoint
