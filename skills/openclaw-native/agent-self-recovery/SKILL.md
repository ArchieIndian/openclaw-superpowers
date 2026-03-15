---
name: agent-self-recovery
description: Detects when the agent is stuck in a loop and escapes systematically. Use when you notice repeated failures or loss of direction.
stateful: true
---

# Agent Self-Recovery

State file: `~/.openclaw/skill-state/agent-self-recovery/state.yaml`

## Signs You're Stuck

- Tried the same approach 3+ times with the same result
- Making changes that feel random rather than targeted
- Lost track of the original goal
- Taking longer than expected on a 'simple' step

## Recovery Protocol

### Step 1: Stop
Stop making changes. No more quick tries.

### Step 2: Write State
Write to the state file:
- `what_trying`: what were you trying to do?
- `what_tried`: append this latest approach to the list
- `loop_type`: name the pattern (see Step 3)
- `attempts`: increment by 1
- `status: recovering`
- `started_at`: current timestamp (first time only)

### Step 3: Name the Loop
Pick the `loop_type`:
- `same-fix-variations` — trying the same fix with minor changes
- `cascading-dependencies` — each fix reveals a new dependency
- `unclear-error` — unclear what the actual error is
- `lost-goal` — lost track of original requirement

### Step 4: Break the Loop

If `loop_type: unclear-error` → use systematic-debugging first.
If `loop_type: lost-goal` → re-read the original requirement.
If genuinely blocked → document clearly, ask the user. Update state `status: escalated`.
If context too large → use context-window-management.
If truly lost → use task-handoff, ask user to redirect. Update state `status: escalated`.

### Step 5: Resume with a New Approach
Choose a genuinely different approach. Update state `last_approach`, append to `what_tried`.
On success: update state `status: recovered`.
