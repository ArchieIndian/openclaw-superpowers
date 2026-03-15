---
name: create-skill
description: Scaffolds and validates new superpowers skills. Use when creating a new skill for this repository.
---

# Create Skill

A meta-skill for onboarding new skills into openclaw-superpowers. Follow this process whenever you or a contributor wants to add a new skill.

## Step 1: Define the Skill

Answer these questions before writing anything:

1. **What does this skill do?** (one sentence)
2. **When should the agent use it?** (the trigger)
3. **Is it core or OpenClaw-native?**
   - **Core:** General agent methodology (brainstorming, debugging, planning). Works in any agent runtime.
   - **OpenClaw-native:** Requires persistence, long-running sessions, or memory. Specific to OpenClaw's always-on model.
4. **Does an existing skill already cover this?** If yes, extend it instead of creating a new one.
5. **Does this skill need to persist state between sessions or wakeups?** If yes → `stateful: true` + `STATE_SCHEMA.yaml`.

## Step 2: Choose a Name

- Use **kebab-case**: `my-new-skill`
- Name describes the **action**, not the category: `retry-with-backoff` not `error-handling-utils`
- Keep it short — 2-4 words max

## Step 3: Scaffold the Skill

Create the directory and files:

```
skills/<core|openclaw-native>/<skill-name>/
  ├── SKILL.md
  └── STATE_SCHEMA.yaml   # only if stateful: true
```

Use the frontmatter template for `SKILL.md` (optional fields shown as comments):

```markdown
---
name: <skill-name>
description: <One sentence — what it does and when to use it.>
# cron: "<5-field cron expression>"   # optional: if skill runs on a schedule
# stateful: true                       # optional: if skill persists state
---
```

See [TEMPLATE.md](TEMPLATE.md) for the full content structure.

## Step 4: Write the Content

Follow these conventions (learned from existing skills):

- **Be direct.** Open with the core principle, not a preamble. ("Plans prevent wasted work." not "This skill helps you write plans.")
- **Be prescriptive.** Tell the agent exactly what to do, step by step. Avoid vague guidance.
- **Be brief.** The best skills in this repo are under 50 lines. If it's longer, split into smaller skills.
- **Include decision criteria.** Tell the agent *when* to use it and *when not to*.
- **Use checklists** for verification steps (see `verification-before-completion`).
- **Add checkpoint guidance** if the skill applies to work spanning multiple sessions.
- **State in prose is a mistake.** If your skill describes saving progress to markdown or memory files, use `stateful: true` + `STATE_SCHEMA.yaml` instead.

## Step 5: Validate

Before committing, check:

- [ ] **Frontmatter is correct** — `name` matches directory name, `description` is one clear sentence
- [ ] **File is at the right path** — `skills/<core|openclaw-native>/<name>/SKILL.md`
- [ ] **No overlap** with existing skills — if there's overlap, merge or differentiate clearly
- [ ] **Follows the template** — has When to Use, The Process, and Key Principles sections
- [ ] **Under 80 lines** — if longer, consider splitting
- [ ] **Actionable** — every step tells the agent what to *do*, not what to *think about*
- [ ] **Testable** — you can tell whether the agent followed the skill correctly by looking at its output
- [ ] If `stateful: true` — `STATE_SCHEMA.yaml` exists with `version:` and `fields:` keys
- [ ] If `cron:` is set — expression is valid 5-field cron syntax

## Step 6: Register

No manual registration needed. OpenClaw auto-discovers skills from the extensions directory. Ensure:

1. The directory is under `skills/core/` or `skills/openclaw-native/`
2. The file is named exactly `SKILL.md`
3. The install symlink is in place (`install.sh` handles this)
4. For stateful skills, `install.sh` creates `~/.openclaw/skill-state/<skill-name>/` automatically
5. For skills with `cron:`, `install.sh` registers them with OpenClaw's cron on next run

## Common Mistakes

- **Too abstract.** "Think carefully about edge cases" is not a skill step. "List 3 edge cases and write a test for each" is.
- **Too broad.** If a skill covers more than one distinct workflow, split it.
- **Missing triggers.** Without clear "when to use" criteria, the agent won't know to invoke it.
- **Duplicating existing skills.** Check `brainstorming`, `writing-plans`, `systematic-debugging`, and `verification-before-completion` before creating something similar.
- **State in prose.** If your skill describes saving progress to markdown or memory files, use `stateful: true` with a `STATE_SCHEMA.yaml` instead — it's structured, machine-readable, and resumable.
