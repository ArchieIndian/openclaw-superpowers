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
- If your skill persists state between sessions, set `stateful: true` in frontmatter and include `STATE_SCHEMA.yaml` in the skill directory
- If your skill should run on a schedule, set `cron: "<expression>"` in frontmatter — `install.sh` handles registration automatically

## Stateful Skills

Use `stateful: true` when your skill needs to remember data between separate invocations (e.g. tracking progress across a multi-session task, recording last-run timestamps to prevent duplicate runs).

- **`STATE_SCHEMA.yaml`** is committed alongside `SKILL.md` — it documents the shape of runtime state and is portable across machines
- **Runtime state** lives at `~/.openclaw/skill-state/<skill-name>/state.yaml` on each local machine — never committed, created automatically by `install.sh`
- Schema format: start with `version: "1.0"` and a `fields:` block. See any existing `skills/openclaw-native/*/STATE_SCHEMA.yaml` for examples.
- Community skills should default to **stateless** unless state is genuinely required — don't add `stateful: true` for simple methodology skills

## Validation

Run the validation script before submitting:

```bash
./scripts/validate-skills.sh
```

It checks: frontmatter format, naming conventions, file structure, line count, stateful skill coherence (`STATE_SCHEMA.yaml` present when `stateful: true`), and cron expression format.

## Pull Requests

- One skill per PR
- Include a short description of why this skill is needed
- If it overlaps with an existing skill, explain the difference
- Link to the Skill Proposal issue if one exists
