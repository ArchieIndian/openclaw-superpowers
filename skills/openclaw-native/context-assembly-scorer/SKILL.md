---
name: context-assembly-scorer
version: "1.0"
category: openclaw-native
description: Scores how well the current context represents the full conversation — detects information blind spots, stale summaries, and coverage gaps that cause the agent to forget critical details.
stateful: true
cron: "0 */4 * * *"
---

# Context Assembly Scorer

## What it does

When an agent compacts context, it loses information. But how much? And which information? Context Assembly Scorer answers these questions by measuring **coverage** — the ratio of important topics in the full conversation history that are represented in the current assembled context.

Inspired by [lossless-claw](https://github.com/Martian-Engineering/lossless-claw)'s context assembly system, which carefully selects which summaries to include in each turn's context to maximize information coverage.

## When to invoke

- Automatically every 4 hours (cron) — silent coverage check
- Before starting a task that depends on prior context — verify nothing critical is missing
- After compaction — measure information loss
- When the agent says "I don't remember" — diagnose why

## Coverage dimensions

| Dimension | What it measures | Weight |
|---|---|---|
| Topic coverage | % of conversation topics present in current context | 2x |
| Recency bias | Whether recent context is over-represented vs. older important context | 1.5x |
| Entity continuity | Named entities (files, people, APIs) mentioned in history that are missing from context | 2x |
| Decision retention | Architectural decisions and user preferences still accessible | 2x |
| Task continuity | Active/pending tasks that might be lost after compaction | 1.5x |

## How to use

```bash
python3 score.py --score                      # Score current context assembly
python3 score.py --score --verbose             # Detailed per-dimension breakdown
python3 score.py --blind-spots                 # List topics missing from context
python3 score.py --drift                       # Compare current vs. previous scores
python3 score.py --status                      # Last score summary
python3 score.py --format json                 # Machine-readable output
```

## Procedure

**Step 1 — Score context coverage**

```bash
python3 score.py --score
```

The scorer reads MEMORY.md (full history) and compares it against what's currently accessible. Outputs a coverage score from 0–100% with a letter grade.

**Step 2 — Find blind spots**

```bash
python3 score.py --blind-spots
```

Lists specific topics, entities, and decisions that exist in full history but are missing from current context — these are what the agent has effectively "forgotten."

**Step 3 — Track drift over time**

```bash
python3 score.py --drift
```

Shows how coverage has changed across the last 20 scores. Identify if compaction is progressively losing more information.

## Grading

| Grade | Coverage | Meaning |
|---|---|---|
| A | 90–100% | Excellent — minimal information loss |
| B | 75–89% | Good — minor gaps, unlikely to cause issues |
| C | 60–74% | Fair — some important context missing |
| D | 40–59% | Poor — significant blind spots |
| F | 0–39% | Critical — agent is operating with major gaps |

## State

Coverage scores and blind spot history stored in `~/.openclaw/skill-state/context-assembly-scorer/state.yaml`.

Fields: `last_score_at`, `current_score`, `blind_spots`, `score_history`.

## Notes

- Read-only — does not modify context or memory
- Topic extraction uses keyword clustering, not LLM calls
- Entity detection uses regex patterns for file paths, URLs, class names, API endpoints
- Decision detection looks for markers: "decided", "chose", "prefer", "always", "never"
- Recency bias is measured as the ratio of recent-vs-old entry representation
