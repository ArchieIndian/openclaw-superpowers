# Contributing

The easiest way to create a new skill is to use the `create-skill` superpower — it walks you through the full process, from naming to validation.

If you prefer to do it manually:

1. Create a directory under `skills/core/` (general methodology) or `skills/openclaw-native/` (requires persistence/memory)
2. Add a `SKILL.md` with `name` and `description` frontmatter
3. Follow the template and conventions in `skills/core/create-skill/SKILL.md`
4. Run the validation checklist before submitting

## Conventions

- Directory names use **kebab-case**: `my-new-skill`
- Each skill is one directory with one `SKILL.md` file
- Keep skills under 80 lines — if it's longer, consider splitting
- Frontmatter `name` must match the directory name
- Include clear "When to Use" triggers so the agent knows when to invoke it

## Pull Requests

- One skill per PR
- Include a short description of why this skill is needed
- If it overlaps with an existing skill, explain the difference
