---
name: spend-circuit-breaker
version: "1.0"
category: openclaw-native
description: Tracks cumulative API spend against a monthly budget and pauses non-essential automations when thresholds are crossed
stateful: true
cron: "0 */4 * * *"
---

# spend-circuit-breaker

OpenClaw has no built-in hard spending cap. This skill monitors session logs to estimate cumulative API cost, alerts at configurable thresholds, and automatically pauses non-essential cron automations when the monthly budget ceiling is hit.

## Setup (first run)

Before the skill is useful, record your monthly budget in state:

```
python3 check.py --set-budget 50        # $50/month hard cap
python3 check.py --set-alert 0.5 0.75   # Alert at 50% and 75%
```

## Cron Wakeup Behaviour

Runs every 4 hours (`cron: "0 */4 * * *"`). On each wakeup:

1. Read `~/.openclaw/skill-state/spend-circuit-breaker/state.yaml` — load `monthly_budget_usd` and `spend_this_month_usd`
2. Parse OpenClaw session logs from `~/.openclaw/sessions/` to estimate new spend since `last_checked_at` (model × token counts × price table)
3. Update `spend_this_month_usd` and `last_checked_at` in state
4. Apply threshold logic (see below)
5. Reset spend to 0 on the 1st of each month

## Threshold logic

| Spend % | Action |
|---|---|
| < 50% | Log silently — nothing to surface |
| ≥ 50% | Notify user: "You've used ~50% of your $X budget this month" |
| ≥ 75% | Notify user + suggest which cron skills to pause |
| ≥ 100% | Notify user + automatically pause all `cron`-scheduled skills except `daily-review`, `morning-briefing`, and `spend-circuit-breaker` itself |

At 100%, write `circuit_open: true` to state. `install.sh` checks this flag before registering new cron jobs — new installs are allowed, new cron triggers are not.

## Circuit reset

To restore automations after a budget reset or manual override:

```
python3 check.py --reset-circuit
```

This sets `circuit_open: false` and re-registers all paused cron jobs.

## Model price table

The script ships with a price table for common models (claude-3-5-sonnet, gpt-4o, etc.). To add a custom model:

```
python3 check.py --add-model my-model-name --input-cost 3.00 --output-cost 15.00
```

Prices are per million tokens.
