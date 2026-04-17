---
name: quality-gate-orchestrator
version: "1.0"
category: openclaw-native
description: Tracks required validation gates, records pass/fail/waived results, and reports readiness before task completion.
stateful: true
---

# Quality Gate Orchestrator

Agents often remember to run checks at the end, when it is easiest to miss a failed or skipped gate. Use this skill to track required validation throughout the task.

## When to Invoke

- A task has multiple test, lint, build, review, or migration checks
- The user asks for tests-first, verification-first, or completion gates
- Work spans sessions and validation state must survive handoff
- The agent is about to declare completion

## Gate Model

Each gate has:

- `name` - stable identifier such as `lint`, `unit-tests`, or `migration-dry-run`
- `command` - command to run, if applicable
- `required` - required gates must pass or be waived before completion
- `last_status` - `pending`, `pass`, `fail`, or `waived`
- `note` - short reason, error summary, or waiver explanation

## How to Use

```bash
python3 gate.py --status
python3 gate.py --add --name lint --command "npm run lint"
python3 gate.py --add --name smoke --command "npm test" --optional
python3 gate.py --record --name lint --status pass
python3 gate.py --record --name smoke --status waived --note "Not relevant for docs-only change"
python3 gate.py --ready --format json
```

## Procedure

1. At the start of risky work, add the expected gates.
2. After each check, record `pass`, `fail`, or `waived`.
3. If a required gate fails, fix the issue and record a new result.
4. Before completion, run `python3 gate.py --ready`.
5. Do not claim completion unless readiness is true or the user accepts the remaining risk.

## State

Gate state is stored in `~/.openclaw/skill-state/quality-gate-orchestrator/state.yaml`.

Fields: `gates`, `last_ready_at`, `ready`, and `gate_history`.

## Guardrails

- Recording a gate result does not run the command for you.
- Waivers need a note.
- Required gates default to pending until recorded.
