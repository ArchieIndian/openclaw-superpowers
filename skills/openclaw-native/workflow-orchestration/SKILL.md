---
name: workflow-orchestration
description: Chains multiple skills into a named multi-step workflow with conditions and state tracking. Use when a recurring task requires the same sequence of skills every time.
stateful: true
---

# Workflow Orchestration

State file: `~/.openclaw/skill-state/workflow-orchestration/state.yaml`

A workflow is a named sequence of skill invocations with optional conditions. Define it once, run it reliably every time.

## When to Use

- A recurring task always follows the same skill sequence (e.g. review → plan → execute → verify)
- A multi-step process needs to resume if interrupted
- You want conditional branching: "if step 2 fails, run skill X instead"

## Defining a Workflow

A workflow is defined inline as:
```
workflow: <name>
steps:
  1. <skill-name>: <brief instruction>
  2. <skill-name>: <brief instruction>
  [on_failure: <skill-name>]
  3. <skill-name>: <brief instruction>
```

## Running a Workflow

### Step 1: Load or Create
- If a workflow named `<name>` exists in state, load it and check `current_step`
- If new, write workflow definition to state with `status: in_progress`, `current_step: 1`

### Step 2: Execute Current Step
- Announce: "Workflow `<name>` — step [N]: invoking `<skill-name>`"
- Invoke the skill with its instruction
- If step succeeds: advance `current_step`, update `last_updated`
- If step fails and `on_failure` is set: invoke the fallback skill, then continue
- If step fails with no fallback: set `status: blocked`, write `blocked_reason`, stop and notify user

### Step 3: Repeat Until Done
Continue until all steps complete. Set `status: complete`.

## Key Principles

- One active workflow at a time per state file
- Always announce which step you're on so the user can follow along
- Never silently skip a step — blocked is better than wrong
