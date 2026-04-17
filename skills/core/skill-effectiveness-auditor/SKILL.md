---
name: skill-effectiveness-auditor
description: Reviews whether a skill will trigger reliably, guide useful behavior, avoid overlap, and produce testable outcomes.
---

# Skill Effectiveness Auditor

Structural validation proves a skill can load. Effectiveness review asks whether the agent will use it well. Use this skill when reviewing a new skill, improving an existing skill, or deciding whether a proposed skill belongs in the library.

## When to Use

- A skill passes format checks but may still be vague or redundant
- A contributor proposes a new skill
- A skill is not triggering when expected
- A skill seems too broad, too long, or hard to verify

## Audit Process

1. State the intended behavior.
   - Write one sentence describing what the skill should make the agent do.
   - List 3 user prompts that should trigger it.
   - List 2 prompts that should not trigger it.

2. Check trigger clarity.
   - The frontmatter description should name the task and the trigger.
   - Avoid generic descriptions such as "helps with quality" or "improves workflow".
   - Prefer concrete verbs: reviews, validates, scans, plans, records, summarizes.

3. Simulate agent use.
   - Walk through the skill as if responding to a real prompt.
   - Note any step where the agent must guess policy, inputs, output format, or stopping conditions.
   - Flag steps that say "think about" without telling the agent what to produce.

4. Check overlap.
   - Compare with nearby skills before approving a new one.
   - If overlap is mostly structural, merge or reference the existing skill.
   - If the new skill owns a distinct trigger, state that difference clearly.

5. Check testability.
   - The output should show whether the skill was followed.
   - Add verification criteria for high-risk workflows.
   - For stateful skills, require `STATE_SCHEMA.yaml` rather than prose-only memory.

## Verdicts

Use one verdict:

- `keep` - clear trigger, useful behavior, low overlap
- `revise` - useful idea with fixable trigger or process gaps
- `split` - too broad for one skill
- `remove` - duplicated, vague, or not a skill-level behavior

## Output

Return:

- Verdict
- Trigger assessment
- Actionability issues
- Overlap risks
- Suggested frontmatter rewrite
- Required edits before merge
