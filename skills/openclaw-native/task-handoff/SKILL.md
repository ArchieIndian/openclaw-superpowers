---
name: task-handoff
description: Gracefully hands off incomplete tasks across agent restarts. Use when work must be paused mid-task.
stateful: true
---

# Task Handoff

State file: `~/.openclaw/skill-state/task-handoff/state.yaml`

## Pre-Handoff Checklist

- [ ] Current state is stable (no half-written files, no broken tests)
- [ ] All changed files are saved
- [ ] Tests have been run
- [ ] Handoff document is written
- [ ] State file is updated
- [ ] Memory is updated

## Writing a Handoff

Save to tasks/handoff-[task-name]-[timestamp].md:

```
# Handoff: [task name]
Written: YYYY-MM-DD HH:MM
Reason: [why stopping]

## Current State
[1-3 sentences: exactly where things are]

## What's Done
- [step] done

## What's Next
- [next step] - specific instructions

## Important Context
- [anything non-obvious from the code]
- [decisions made and why]

## Files Modified
- path/to/file - [what changed]

## Tests
- Last run: YYYY-MM-DD HH:MM
- Status: PASSING / FAILING

## Blockers
- [anything blocking]
```

Then update state: `active_handoff_path` (full path to the file), `task_name`, `reason`, `status: written`, `written_at`, `files_modified`.

## Picking Up a Handoff

1. Read state file to get `active_handoff_path`
2. Read the handoff document completely before touching any code
3. Run the tests to confirm current state
4. Start from 'What's Next' — do not redo completed steps
5. When complete: delete handoff file, update state `status: picked_up`, clear `active_handoff_path`
