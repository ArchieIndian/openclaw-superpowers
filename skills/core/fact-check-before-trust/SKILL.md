---
name: fact-check-before-trust
version: "1.0"
category: core
description: Triggers a secondary verification pass for any agent output containing factual claims, numbers, dates, or named entities before the output is acted on
---

# fact-check-before-trust

`verification-before-completion` checks that a task was *done*. This skill checks that the *facts are correct*. An agent confidently reporting a £716 visa fee as £70,000 will pass completion verification — this skill catches it.

## When to invoke

Invoke this skill before treating any agent output as authoritative when the output contains:
- **Numbers or money** (prices, quantities, measurements, statistics)
- **Dates and deadlines** (filing deadlines, release dates, expiry dates)
- **Named entities** (people, organisations, laws, product names)
- **Causal claims** ("X causes Y", "because of Z")
- **Superlatives** ("the largest", "the only", "the most recent")

Skip for: code output, file system operations, and clearly self-contained tasks (renaming a variable, formatting a document).

## Verification protocol

**Step 1 — Extract claims**
Identify every verifiable claim in the output. List them explicitly:
```
Claim 1: UK visa fee is £716
Claim 2: Processing time is 3 weeks
Claim 3: Applies to Tier 2 (Skilled Worker) visa category
```

**Step 2 — Score each claim**
For each claim, assign a confidence level:
- **High** — Agent has direct evidence in its context (read a document, fetched a URL)
- **Medium** — Agent inferred from training data (check recency)
- **Low** — Agent stated without citing a source

**Step 3 — Verify low/medium claims**
For each Low or Medium claim:
1. Search or re-fetch the source if possible
2. If source found: update confidence to High or mark **Contradicted**
3. If no source available: mark **Unverifiable**

**Step 4 — Classify output**
| Result | Meaning |
|---|---|
| ✓ Verified | All claims High confidence |
| ⚠ Uncertain | 1+ Unverifiable claims |
| ✗ Contradicted | 1+ claims conflict with found evidence |

**Step 5 — Surface to user**
- **Verified**: proceed
- **Uncertain**: surface unverifiable claims with a note
- **Contradicted**: stop, show the contradiction, do not use the output until resolved

## Difference from verification-before-completion

`verification-before-completion` checks: "Did the agent do the task?" (task completion)
`fact-check-before-trust` checks: "Is what the agent said true?" (output accuracy)

Both should be used for research, financial, legal, and compliance workflows.
