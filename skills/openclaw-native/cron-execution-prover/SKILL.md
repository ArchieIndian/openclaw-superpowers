---
name: cron-execution-prover
version: "1.0"
category: openclaw-native
description: Wraps scheduled workflows with proof records — start, finish, evidence, and stale-run detection — so cron jobs can be trusted instead of merely assumed.
stateful: true
---

# Cron Execution Prover

## What it does

Cron jobs often "kind of run": the task starts, some work happens, but the final side effect never lands. Cron Execution Prover gives scheduled workflows a durable proof trail so you can tell the difference between a completed run and an abandoned one.

## When to invoke

- Around any cron-driven workflow that writes files, sends messages, or produces deliverables
- When scheduled jobs seem to run but users still do not receive the expected output
- When debugging stuck or half-finished cron chains

## Proof model

Every cron run gets a ledger entry:

- `expected_at`
- `started_at`
- `finished_at`
- `status`
- `evidence`
- `notes`

If a run never finishes, the prover can surface it as stale.

## How to use

```bash
python3 prove.py --expect morning-briefing --expected-at "2026-03-30T07:00:00"
python3 prove.py --start morning-briefing --run-id mb-20260330-0700
python3 prove.py --finish morning-briefing --run-id mb-20260330-0700 --evidence "telegram:msg-8812"
python3 prove.py --fail morning-briefing --run-id mb-20260330-0700 --notes "Telegram send timed out"
python3 prove.py --stale
python3 prove.py --report
python3 prove.py --format json
```

## Operating rule

For important cron workflows:

1. Create or infer an expected run record
2. Mark the run started
3. Record proof of side effects on completion
4. Mark failures explicitly
5. Review stale runs before assuming the schedule is healthy

## Difference from runtime-verification-dashboard

`runtime-verification-dashboard` verifies whether cron skills are registered and whether state is fresh.

`cron-execution-prover` verifies whether specific scheduled runs actually produced the expected outcome.

## State

State file: `~/.openclaw/skill-state/cron-execution-prover/state.yaml`

Fields: `runs`, `stale_runs`, `last_report_at`, `report_history`.
