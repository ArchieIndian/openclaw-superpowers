# Repo-Fit Skill Pack Spec

## Goal

Add four skills that fit the current `openclaw-superpowers` library and improve day-to-day agent reliability:

- PR feedback handling
- Semantic skill quality review
- OpenClaw configuration diagnosis
- Task completion gates

These additions should extend the repo's existing autonomy, validation, and OpenClaw-native state patterns without introducing external marketplace structure or branding.

## Skills

### `pull-request-feedback-loop`

Core skill for handling PR review feedback. It uses `gh` to fetch review comments, groups related comments by issue, fixes one group at a time, runs targeted verification, and prepares concise replies only after the fix is confirmed.

### `skill-effectiveness-auditor`

Core skill for semantic skill review. It checks whether a skill will trigger reliably, guide useful agent behavior, avoid overlap with existing skills, and produce testable outcomes. It complements structural tools such as `skill-doctor`, `skill-trigger-tester`, `skill-conflict-detector`, and `tool-description-optimizer`.

### `openclaw-config-advisor`

OpenClaw-native stateful skill for read-only config diagnosis. It scans likely OpenClaw config files, reports provider, fallback, channel, MCP, and gateway health hints, and stores scan summaries in its own state file.

### `quality-gate-orchestrator`

OpenClaw-native stateful skill for task completion gates. It tracks required and optional validation gates, commands, last results, waivers, and readiness so agents do not declare completion before required checks pass or are explicitly waived.

## Non-Goals

- Do not copy external plugin or marketplace structure.
- Do not require network access for normal behavior.
- Do not modify untracked `.claude/` or `CLAUDE.md`.
- Do not perform destructive Git or filesystem actions.
- Do not write state outside `$OPENCLAW_HOME/skill-state/<skill-name>/state.yaml`.

## Acceptance Criteria

- All four skills validate with the existing repo scripts.
- New OpenClaw-native scripts are standard-library only.
- Missing local OpenClaw config produces useful warnings, not crashes.
- README skill counts and tables match the filesystem.
- Validation passes through `scripts/validate-skills.sh`, `tests/test-runner.sh`, `tests/test-repo-fit-skill-pack.sh`, and `git diff --check`.
