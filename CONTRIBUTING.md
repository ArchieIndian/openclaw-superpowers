# Contributing

We'd love your skills! Here's how to contribute.

## Quick Start

1. **Propose your idea** — [Open a Skill Proposal issue](../../issues/new?template=skill-proposal.yml) to get feedback
2. **Create the skill** — Use the `create-skill` superpower or copy the [template](skills/core/create-skill/TEMPLATE.md)
3. **Validate locally** — Run `./scripts/validate-skills.sh` to catch issues
4. **Submit a PR** — CI validates automatically on any PR that touches `skills/`

## Where to Put Your Skill

| Directory | For | Examples |
|---|---|---|
| `skills/core/` | General agent methodology — works in any runtime | brainstorming, debugging, TDD |
| `skills/openclaw-native/` | Requires persistence, memory, or long sessions | task-handoff, self-recovery |
| `skills/community/` | Community contributions — any category | your skill goes here! |

New contributors should use `skills/community/`. Proven community skills may be promoted to core or openclaw-native over time.

## Conventions

- Directory names use **kebab-case**: `my-new-skill`
- Each skill is one directory with one `SKILL.md` file
- Keep skills under 80 lines — if it's longer, consider splitting
- Frontmatter `name` must match the directory name
- Include clear "When to Use" triggers so the agent knows when to invoke it

## Validation

Run the validation script before submitting:

```bash
./scripts/validate-skills.sh
```

It checks: frontmatter format, naming conventions, file structure, and line count.

## Pull Requests

- One skill per PR
- Include a short description of why this skill is needed
- If it overlaps with an existing skill, explain the difference
- Link to the Skill Proposal issue if one exists
