---
name: skill-conflict-detector
version: "1.0"
category: core
description: Detects skill name shadowing and description-overlap conflicts that cause OpenClaw to trigger the wrong skill or silently ignore one when two skills compete for the same intent.
---

# Skill Conflict Detector

## What it does

Two types of conflict cause skills to misbehave silently:

**1. Name shadowing** — Two installed skills have the same `name:` field. OpenClaw loads the last one lexicographically; the other silently disappears. No warning.

**2. Description overlap** — Two skills' descriptions are so semantically similar that OpenClaw can't reliably distinguish them. The wrong skill fires. You think one skill is broken; actually the other is intercepting it.

Skill Conflict Detector scans all installed skills for both types and reports them with overlap scores and resolution suggestions.

## When to invoke

- After installing a new skill from ClawHub
- When a skill fires inconsistently or triggers on unexpected prompts
- Before publishing a new skill (ensure it doesn't shadow an existing one)
- As part of `install.sh` post-install validation

## Conflict types

| Type | Severity | Effect |
|---|---|---|
| NAME_SHADOW | CRITICAL | One skill completely hidden |
| EXACT_DUPLICATE | CRITICAL | Identical description — both fire or neither does |
| HIGH_OVERLAP | HIGH | >75% semantic similarity — unreliable trigger routing |
| MEDIUM_OVERLAP | MEDIUM | 50–75% similarity — possible confusion |

## Output

```
Skill Conflict Report — 32 skills
────────────────────────────────────────────────
0 CRITICAL | 1 HIGH | 0 MEDIUM

HIGH  skill-vetting ↔ installed-skill-auditor  overlap: 0.81
      Both describe "scanning skills for security issues"
      Suggestion: Differentiate — skill-vetting is pre-install,
      installed-skill-auditor is post-install ongoing audit.
```

## How to use

```bash
python3 detect.py --scan                   # Full conflict scan
python3 detect.py --scan --skill my-skill  # Check one skill vs all others
python3 detect.py --scan --threshold 0.6   # Custom similarity threshold
python3 detect.py --names                  # Check name shadowing only
python3 detect.py --format json
```

## Procedure

**Step 1 — Run the scan**

```bash
python3 detect.py --scan
```

**Step 2 — Resolve CRITICAL conflicts first**

NAME_SHADOW: Rename one skill's `name:` field and its directory. Run `bash scripts/validate-skills.sh` to confirm.

EXACT_DUPLICATE: One skill is redundant. Remove or differentiate it.

**Step 3 — Assess HIGH_OVERLAP pairs**

Read both descriptions. Ask: could a user's natural-language request unambiguously route to one and not the other? If no, differentiate. Common fix: add the scope or timing to the description (e.g., "before install" vs. "after install").

**Step 4 — Accept or suppress MEDIUM_OVERLAP**

Medium overlaps are informational. If the two skills serve genuinely different contexts and users would naturally phrase requests differently, they can coexist. Document why in the skill's SKILL.md if it's non-obvious.

## Similarity model

Token-overlap Jaccard similarity between description strings after stop-word removal. Fast and deterministic — no external dependencies.

Threshold defaults: HIGH ≥ 0.75, MEDIUM ≥ 0.50.
