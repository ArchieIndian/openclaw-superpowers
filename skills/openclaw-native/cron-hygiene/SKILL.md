---
name: cron-hygiene
version: "1.0"
category: openclaw-native
description: Audits cron-scheduled skills for session mode, token waste, and cost efficiency — and enforces concise-reply constraints on cron contexts
stateful: true
cron: "0 9 * * 1"
---

# cron-hygiene

Cron jobs running in `main` session mode inherit the full conversation history — re-sending thousands of tokens of context on every invocation. A cron running every 5 minutes in main session mode can turn a $10/month setup into $80+ (issue #20092). This skill audits all configured cron skills weekly and enforces hygiene standards.

## Difference from context-budget-guard

`context-budget-guard` monitors live session token usage in real-time. `cron-hygiene` is about the structural problem: cron jobs that are *architecturally wasteful* because they're configured in the wrong session mode.

## Cron Wakeup Behaviour

Runs every Monday at 09:00 (`cron: "0 9 * * 1"`). On each wakeup:

1. Read the list of registered cron skills from OpenClaw config
2. For each skill, check its session mode (`main` vs `isolated`)
3. Estimate cost impact: crons in `main` mode × frequency × estimated context size
4. Flag violations and surface recommendations

## Hygiene rules

| Rule | Check | Severity |
|---|---|---|
| Session isolation | Cron skills should use `isolated` session mode | High |
| Reply conciseness | Cron output should be < 500 tokens | Medium |
| Frequency sanity | Crons running < 10min apart need justification | Medium |
| Dead crons | Cron skills with no state update in 7+ days | Low |
| Overlapping crons | Two skills scheduled at the same time | Low |

## Weekly report format

```
Cron Hygiene Report — 2026-03-16
────────────────────────────────
5 crons audited | 2 violations | Est. monthly waste: $12.40

HIGH:   persistent-memory-hygiene — runs in main session mode
        Fix: add sessionMode: isolated to skill config
        Est. savings: ~$8.20/month

MEDIUM: long-running-task-management — fires every 15min
        Output not constrained (last run: 1,240 tokens)
        Recommendation: add reply_token_limit: 200 to skill config
```

## Remediation

To fix a main-session cron manually:
```
python3 audit.py --fix-session <skill-name>
```

This writes `sessionMode: isolated` to the skill's OpenClaw config entry.
