---
name: tool-description-optimizer
version: "1.0"
category: openclaw-native
description: Analyzes skill descriptions for trigger quality — scores clarity, keyword density, and specificity, then suggests rewrites that improve discovery accuracy.
stateful: true
---

# Tool Description Optimizer

## What it does

A skill's description is its only discovery mechanism. If the description is vague, overlapping, or keyword-poor, the agent won't trigger it — or worse, will trigger the wrong skill. Tool Description Optimizer analyzes every installed skill's description for trigger quality and suggests concrete rewrites.

Inspired by OpenLobster's tool-description scoring layer, which penalizes vague descriptions and rewards keyword-rich, action-specific ones.

## When to invoke

- After installing new skills — check if descriptions are trigger-ready
- When a skill isn't firing when expected — diagnose whether the description is the problem
- Periodically to audit all descriptions for quality drift
- Before publishing a skill — polish the description for discoverability

## How it works

### Scoring dimensions (5 metrics, 0–10 each)

| Metric | What it measures | Weight |
|---|---|---|
| Clarity | Single clear purpose, no ambiguity | 2x |
| Specificity | Action verbs, concrete nouns vs. vague terms | 2x |
| Keyword density | Trigger-relevant keywords per sentence | 1.5x |
| Uniqueness | Low overlap with other installed skill descriptions | 1.5x |
| Length | Optimal range (15–40 words) — too short = vague, too long = diluted | 1x |

### Quality grades

| Grade | Score range | Meaning |
|---|---|---|
| A | 8.0–10.0 | Excellent — high trigger accuracy expected |
| B | 6.0–7.9 | Good — minor improvements possible |
| C | 4.0–5.9 | Fair — likely to miss triggers or overlap |
| D | 2.0–3.9 | Poor — needs rewrite |
| F | 0.0–1.9 | Failing — will not trigger reliably |

## How to use

```bash
python3 optimize.py --scan                    # Score all installed skills
python3 optimize.py --scan --grade C          # Only show skills graded C or below
python3 optimize.py --skill <name>            # Deep analysis of a single skill
python3 optimize.py --suggest <name>          # Generate rewrite suggestions
python3 optimize.py --compare "desc A" "desc B"  # Compare two descriptions
python3 optimize.py --status                  # Last scan summary
python3 optimize.py --format json             # Machine-readable output
```

## Procedure

**Step 1 — Run a full scan**

```bash
python3 optimize.py --scan
```

Review the scorecard. Focus on skills graded C or below — these are the ones most likely to cause trigger failures.

**Step 2 — Get rewrite suggestions for low-scoring skills**

```bash
python3 optimize.py --suggest <skill-name>
```

The optimizer generates 2–3 alternative descriptions with predicted score improvements.

**Step 3 — Compare alternatives**

```bash
python3 optimize.py --compare "original description" "suggested rewrite"
```

Side-by-side scoring shows exactly which metrics improved.

**Step 4 — Apply the best rewrite**

Edit the skill's `SKILL.md` frontmatter `description:` field with the chosen rewrite.

## Vague word penalties

These words score 0 on specificity — they say nothing actionable:

`helps`, `manages`, `handles`, `deals with`, `works with`, `does stuff`, `various`, `things`, `general`, `misc`, `utility`, `tool for`, `assistant for`

## Strong trigger keywords (examples)

`scans`, `detects`, `validates`, `generates`, `audits`, `monitors`, `checks`, `reports`, `fixes`, `migrates`, `syncs`, `schedules`, `blocks`, `scores`, `diagnoses`

## State

Scan results and per-skill scores stored in `~/.openclaw/skill-state/tool-description-optimizer/state.yaml`.

Fields: `last_scan_at`, `skill_scores` list, `scan_history`.

## Notes

- Does not modify any skill files — analysis and suggestions only
- Uniqueness scoring uses Jaccard similarity against all other installed descriptions
- Length scoring uses a bell curve centered at 25 words (optimal)
- Rewrite suggestions are heuristic-based, not LLM-generated — deterministic and fast
