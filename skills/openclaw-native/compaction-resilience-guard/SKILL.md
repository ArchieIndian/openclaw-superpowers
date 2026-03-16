---
name: compaction-resilience-guard
version: "1.0"
category: openclaw-native
description: Monitors memory compaction for failures and enforces a three-level fallback chain — normal, aggressive, deterministic truncation — ensuring compaction always makes forward progress.
stateful: true
---

# Compaction Resilience Guard

## What it does

Memory compaction can fail silently: the LLM produces empty output, summaries that are *larger* than their input, or garbled text. When this happens, compaction stalls and context overflows.

Compaction Resilience Guard enforces a three-level escalation chain inspired by [lossless-claw](https://github.com/Martian-Engineering/lossless-claw):

| Level | Strategy | When used |
|---|---|---|
| L1 — Normal | Standard summarization prompt | First attempt |
| L2 — Aggressive | Low temperature, reduced reasoning, shorter output target | After L1 failure |
| L3 — Deterministic | Pure truncation: keep first N + last N lines, drop middle | After L2 failure |

This ensures compaction **always makes progress** — even if the LLM is broken.

## When to invoke

- After any compaction event — validate the output
- When context usage approaches 90% — compaction may be failing
- When summaries seem unusually long or empty — detect inflation
- As a pre-check before memory-dag-compactor runs

## How to use

```bash
python3 guard.py --check                       # Validate recent compaction outputs
python3 guard.py --check --file <summary.yaml> # Check a specific summary file
python3 guard.py --simulate <text>             # Run the 3-level chain on sample text
python3 guard.py --report                      # Show failure/escalation history
python3 guard.py --status                      # Last check summary
python3 guard.py --format json                 # Machine-readable output
```

## Failure detection

The guard detects these compaction failures:

| Failure | How detected | Action |
|---|---|---|
| Empty output | Summary length < 10 chars | Escalate to next level |
| Inflation | Summary tokens > input tokens | Escalate to next level |
| Garbled text | Entropy score > 5.0 (random chars) | Escalate to next level |
| Repetition | Same 20+ char phrase repeated 3+ times | Escalate to next level |
| Truncation marker | Contains `[FALLBACK]` or `[TRUNCATED]` | Record as L3 usage |
| Stale | Summary unchanged from previous run | Flag for review |

## Procedure

**Step 1 — Check recent compaction outputs**

```bash
python3 guard.py --check
```

Validates all summary nodes in memory-dag-compactor state. Reports failures by level and whether escalation was needed.

**Step 2 — Simulate the fallback chain**

```bash
python3 guard.py --simulate "$(cat long-text.txt)"
```

Runs the 3-level chain on sample text to test that each level produces valid output.

**Step 3 — Review escalation history**

```bash
python3 guard.py --report
```

Shows how often each level was used. High L2/L3 usage indicates the primary summarization prompt needs improvement.

## State

Failure counts, escalation history, and per-summary validation results stored in `~/.openclaw/skill-state/compaction-resilience-guard/state.yaml`.

Fields: `last_check_at`, `level_usage`, `failures`, `check_history`.

## Notes

- Read-only monitoring — does not perform compaction itself
- Works alongside memory-dag-compactor as a quality gate
- Deterministic truncation (L3) preserves first 30% and last 20% of input, drops middle
- Entropy is measured using Shannon entropy on character distribution
- High L3 usage (>10% of compactions) suggests a systemic LLM issue
