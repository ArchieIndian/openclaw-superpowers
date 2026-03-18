---
name: runtime-verification-dashboard
version: "1.0"
category: openclaw-native
description: Verifies skill runtime health — cron registration, state freshness, dependency readiness, and install layout drift — so autonomous agents stay observable and trustworthy.
stateful: true
cron: "0 */6 * * *"
---

# Runtime Verification Dashboard

## What it does

A skill library is only useful if the skills actually trigger, write state, and stay registered after upgrades. Runtime Verification Dashboard audits the live OpenClaw install and writes a rolling health report you can inspect in one command.

It catches the gap between "the files exist" and "the runtime is healthy."

## When to invoke

- Automatically every 6 hours
- After installing or upgrading openclaw-superpowers
- When cron skills stop firing, state looks stale, or the runtime feels drifted
- Before trusting long-running automation in production

## What it checks

| Check | Why it matters |
|---|---|
| Install layout | Detects repo-root vs skills-root path drift before scripts look in the wrong place |
| Cron registration | Finds scheduled skills that exist on disk but are not registered with OpenClaw |
| State freshness | Flags stateful cron skills whose state has gone stale relative to their schedule |
| Dependency readiness | Warns when `PyYAML` or the `openclaw` CLI is unavailable |
| Skill inventory | Records PASS / WARN / FAIL status per skill in one ledger |

## How to use

```bash
python3 check.py --scan                 # Full live runtime audit
python3 check.py --scan --failures      # Show only WARN / FAIL items
python3 check.py --scan --skill morning-briefing
python3 check.py --status               # Summary from the last scan
python3 check.py --findings             # Findings from the last scan
python3 check.py --format json
```

## Cron wakeup behaviour

Every 6 hours:

1. Resolve the installed skill root
2. Inspect every skill's frontmatter and runtime state
3. Check cron visibility through `openclaw cron list` when available
4. Write a summary ledger and rolling history to state
5. Surface FAILs first, then WARNs

## Operating rule

Use this skill as the first stop when the agent's behaviour looks inconsistent with the skill files on disk. It tells you whether the problem is registration, state drift, dependency drift, or install layout drift.

## State

State file: `~/.openclaw/skill-state/runtime-verification-dashboard/state.yaml`

Fields: `last_scan_at`, `summary`, `environment`, `global_findings`, `skills`, `scan_history`.
