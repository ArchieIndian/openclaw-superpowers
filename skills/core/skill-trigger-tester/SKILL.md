---
name: skill-trigger-tester
version: "1.0"
category: core
description: Scores a skill's description field against sample user prompts to predict whether OpenClaw will correctly trigger it — before you publish or install.
---

# Skill Trigger Tester

## What it does

OpenClaw maps user intent to skills by matching the user's message against each skill's `description:` field. A weak description means your skill silently never fires. A description that's too broad means it fires when it shouldn't.

Skill Trigger Tester helps you validate the trigger quality of a skill's description before publishing. You give it:
- The description string you're testing
- A set of "should fire" prompts (true positives)
- A set of "should not fire" prompts (true negatives)

It scores precision, recall, and gives an overall trigger quality grade (A–F) plus actionable suggestions.

## When to invoke

- Before publishing any new skill to ClawHub
- When a skill you expect to trigger isn't firing
- When a skill keeps firing on irrelevant prompts
- Inside `create-skill` workflow (Step 5: validation)

## Scoring model

The tool uses a keyword + semantic overlap heuristic against the description field:

| Metric | Meaning |
|---|---|
| **Recall** | % of "should fire" prompts that would match |
| **Precision** | % of matches that are actually "should fire" |
| **F1** | Harmonic mean of recall and precision |

Grade thresholds:

| Grade | F1 |
|---|---|
| A | ≥ 0.85 |
| B | ≥ 0.70 |
| C | ≥ 0.55 |
| D | ≥ 0.40 |
| F | < 0.40 |

## How to use

```bash
python3 test.py --description "Diagnoses skill discovery failures" \
  --should-fire "why isn't my skill loading" \
               "my skill disappeared from the registry" \
               "check if my skills are healthy" \
  --should-not-fire "write a skill" \
                    "install superpowers" \
                    "review my code"

python3 test.py --file skill-spec.yaml    # Load test cases from YAML file
python3 test.py --format json             # Machine-readable output
```

## Test spec file format

```yaml
description: "Diagnoses skill discovery failures — YAML parse errors, path violations"
should_fire:
  - "why isn't my skill loading"
  - "my skill disappeared"
  - "check skill health"
should_not_fire:
  - "write a new skill"
  - "install openclaw"
```

## Procedure

**Step 1 — Write your test cases**

For each skill you're testing, list 3–5 prompts that should trigger it and 3–5 that should not. Be honest about edge cases.

**Step 2 — Run the scorer**

```bash
python3 test.py --description "<your description>" \
  --should-fire "..." --should-not-fire "..."
```

**Step 3 — Interpret results**

- Grade A/B: description is well-calibrated. Publish.
- Grade C: borderline — add more specific keywords to the description, or narrow the wording.
- Grade D/F: description is too vague or uses jargon the user won't say. Rewrite and retest.

**Step 4 — Iterate**

Try alternative descriptions and compare scores side-by-side using `--compare`.

**Step 5 — Add test file to the skill directory**

Commit the `trigger-tests.yaml` spec alongside the skill. Future contributors can run it to verify trigger quality hasn't regressed.

## Common mistakes

- **Too generic**: `"Helps with skills"` — will either never fire or fire on everything
- **Technical jargon**: `"Validates SKILL.md frontmatter schema coherence"` — users don't say this
- **Action + object only**: `"Creates skills"` — add when/why context
- **Missing synonyms**: If users might say "check" or "verify" or "test", the description needs to capture the semantic range

## Output example

```
Skill Trigger Quality — skill-doctor
─────────────────────────────────────────────
Description: "Diagnoses silent skill discovery failures..."

Should fire (5 prompts):    4 / 5 matched   recall    = 0.80
Should not fire (5 prompts): 1 / 5 matched  precision = 0.80
F1 score: 0.80   Grade: B

⚠ 1 false negative: "check if skills are healthy"
   Suggestion: Add "healthy", "health", or "check" to the description.

⚠ 1 false positive: "check my code"
   Suggestion: Narrow description to avoid generic "check" overlap.
```
