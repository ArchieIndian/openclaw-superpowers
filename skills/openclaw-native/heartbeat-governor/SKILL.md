---
name: heartbeat-governor
version: "1.0"
category: openclaw-native
description: Enforces per-skill execution budgets for scheduled cron skills — pauses runaway skills that exceed their token or wall-clock budget before they drain your monthly API allowance.
stateful: true
cron: "0 * * * *"
---

# Heartbeat Governor

## What it does

Cron skills run autonomously. A skill with a bug — an infinite retry, an unexpectedly large context, a model call inside a loop — can silently consume hundreds of dollars before you notice.

Heartbeat Governor tracks cumulative execution cost and wall-clock time per scheduled skill on a rolling 30-day basis. When a skill exceeds its budget, the governor pauses it and sends an alert. The skill won't fire again until you explicitly review and resume it.

It runs every hour to catch budget overruns within one cron cycle.

## When to invoke

- Automatically, every hour (cron)
- Manually after noticing an unexpected API bill spike
- When a cron skill has been running unusually long

## Budget types

| Budget type | Default | Configurable |
|---|---|---|
| `max_usd_monthly` | $5.00 | Yes, per skill |
| `max_usd_per_run` | $0.50 | Yes, per skill |
| `max_wall_minutes` | 30 | Yes, per skill |
| `max_runs_daily` | 48 | Yes, per skill |

## Actions on budget breach

| Breach type | Action |
|---|---|
| `monthly_usd` exceeded | Pause skill, log breach, alert |
| `per_run_usd` exceeded | Abort current run, log breach |
| `wall_clock` exceeded | Abort current run, log breach |
| `daily_runs` exceeded | Skip remaining runs today, log |

## How to use

```bash
python3 governor.py --status               # Show all skills and budget utilisation
python3 governor.py --record <skill> --usd 0.12 --minutes 4   # Record a run
python3 governor.py --pause <skill>        # Manually pause a skill
python3 governor.py --resume <skill>       # Resume a paused skill after review
python3 governor.py --set-budget <skill> --monthly 10.00       # Override budget
python3 governor.py --check                # Run hourly check (called by cron)
python3 governor.py --report               # Full monthly spend report
python3 governor.py --format json
```

## Cron wakeup behaviour

Every hour the governor runs `--check`:

1. Load all skill ledgers from state
2. For each skill with `paused: false`:
   - If 30-day rolling spend exceeds `max_usd_monthly` → `paused: true`, log
   - If runs today exceed `max_runs_daily` → skip, log
3. Print summary of paused skills and budget utilisation
4. Save updated state

## Procedure

**Step 1 — Set sensible budgets**

After installing any new cron skill, set its monthly budget:

```bash
python3 governor.py --set-budget daily-review --monthly 2.00
python3 governor.py --set-budget morning-briefing --monthly 3.00
```

Defaults are conservative ($5/month) but explicit is better.

**Step 2 — Monitor utilisation**

```bash
python3 governor.py --status
```

Review the utilisation column. Any skill above 80% monthly budget warrants investigation.

**Step 3 — Respond to pause alerts**

When the governor pauses a skill, investigate why it's over budget:
- Was there a one-time expensive run (large context)?
- Is there a bug causing repeated expensive calls?
- Does the budget simply need to be raised?

Resume after investigating:
```bash
python3 governor.py --resume <skill>
```

## State

Per-skill ledgers and pause flags stored in `~/.openclaw/skill-state/heartbeat-governor/state.yaml`.

Fields: `skill_ledgers` map, `paused_skills` list, `breach_log`, `monthly_summary`.
