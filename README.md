# openclaw-superpowers

Give your OpenClaw agents superpowers.

A plug-and-play skill library built specifically for OpenClaw, inspired by [obra/superpowers](https://github.com/obra/superpowers).

## What is this?

[OpenClaw](https://github.com/openclaw/openclaw) is the fastest-growing personal AI agent runtime — 122K stars and counting. It runs 24/7 on any OS and is the backbone for thousands of personal and professional agent workflows.

[obra/superpowers](https://github.com/obra/superpowers) introduced a brilliant idea: composable skill files — markdown documents that tell your agent exactly how to behave for specific tasks. No more repeating yourself. No more agents that fail the same way twice.

This repo bridges both. It gives OpenClaw users a ready-made, tested, always-growing library of skills — tuned specifically to how OpenClaw's runtime works.

## Why OpenClaw-specific?

Superpowers was built primarily for Claude Code, Cursor, and Codex. OpenClaw has a different runtime model:

- It runs **persistently (24/7)**, not just per-session
- It handles **long-running tasks** across hours, not minutes
- It has its own tool naming conventions
- It benefits from skills around **task handoff, memory persistence, and agent recovery** that session-based tools don't need

This repo handles those differences so you don't have to.

## Quickstart

```bash
git clone https://github.com/ArchieIndian/openclaw-superpowers ~/.openclaw/extensions/superpowers
cd ~/.openclaw/extensions/superpowers && ./install.sh
openclaw gateway restart
```

That's it. Your agent now has superpowers.

## Skills Included

### Core (Ported & Adapted from obra/superpowers)

| Skill | Purpose |
|---|---|
| `using-superpowers` | Bootstrap — teaches the agent how to find and invoke skills |
| `brainstorming` | Structured ideation before any implementation |
| `writing-plans` | Creates clear, reviewable implementation plans |
| `executing-plans` | Executes plans task-by-task with verification |
| `systematic-debugging` | 4-phase root cause process before any fix |
| `verification-before-completion` | Ensures tasks are actually done, not just attempted |
| `test-driven-development` | Red-green-refactor discipline |
| `subagent-driven-development` | Parallel subagent execution for complex tasks |
| `create-skill` | Scaffolds and validates new skills — the easiest way to contribute |

### OpenClaw-Native (New Skills, Not in Superpowers)

| Skill | Purpose |
|---|---|
| `long-running-task-management` | Breaks multi-hour tasks into checkpointed stages with resume capability |
| `persistent-memory-hygiene` | Keeps OpenClaw's memory store clean, structured, and useful over time |
| `task-handoff` | Gracefully hands off incomplete tasks across agent restarts |
| `agent-self-recovery` | Detects when the agent is stuck in a loop and escapes systematically |
| `context-window-management` | Prevents context overflow on long-running OpenClaw sessions |
| `daily-review` | End-of-day structured summary and next-session prep |

### Community

Community-contributed skills live in `skills/community/`. Want to add one? See [CONTRIBUTING.md](CONTRIBUTING.md) or use the `create-skill` superpower.

## Contributing

We welcome community skills! The process:

1. **Propose** — [Open a Skill Proposal issue](../../issues/new?template=skill-proposal.yml) to get feedback before writing
2. **Create** — Use the `create-skill` superpower or follow the [template](skills/core/create-skill/TEMPLATE.md)
3. **Validate** — Run `./scripts/validate-skills.sh` locally to check your skill
4. **Submit** — Open a PR (CI will validate automatically)

See [CONTRIBUTING.md](CONTRIBUTING.md) for full details.

## Credits

This project stands on the shoulders of two incredible communities:

- **[openclaw/openclaw](https://github.com/openclaw/openclaw)** — the personal AI agent runtime that makes all of this possible.
- **[obra/superpowers](https://github.com/obra/superpowers)** — Jesse Vincent's brilliant skills framework. The core skills in this repo are adapted from Superpowers (MIT license).
