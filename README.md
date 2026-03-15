# openclaw-superpowers

Give your OpenClaw agent superpowers — and let it teach itself new ones.

A plug-and-play skill library for [OpenClaw](https://github.com/openclaw/openclaw), inspired by [obra/superpowers](https://github.com/obra/superpowers).

---

## The idea that makes this different

Most AI tools require a developer to add new behaviors. You file an issue, wait for a release, update your config.

**openclaw-superpowers makes your agent self-modifying.**

> *"Every time I ask for a code review, always check for security issues first."*

Your agent invokes `create-skill`, writes a new `SKILL.md`, and that behavior is live — immediately, permanently, no restart needed.

The agent can encode your preferences as durable skills during normal conversation. You describe what you want. It teaches itself.

- It runs **persistently (24/7)**, not just per-session
- It handles **long-running tasks** across hours, not minutes
- It has **native cron scheduling** — skills can wake up automatically on a schedule
- It has its own tool naming conventions
- It benefits from skills around **task handoff, memory persistence, and agent recovery** that session-based tools don't need

---

## Quickstart

```bash
git clone https://github.com/ArchieIndian/openclaw-superpowers ~/.openclaw/extensions/superpowers
cd ~/.openclaw/extensions/superpowers && ./install.sh
openclaw gateway restart
```

`install.sh` symlinks skills, creates state directories for stateful skills, and registers cron jobs — everything in one step.

That's it. Your agent now has superpowers.

## Skills Included

### Core (10 skills — adapted from obra/superpowers)

| Skill | Purpose | Script |
|---|---|---|
| `using-superpowers` | Bootstrap — teaches the agent how to find and invoke skills | — |
| `brainstorming` | Structured ideation before any implementation | — |
| `writing-plans` | Clear, reviewable implementation plans | — |
| `executing-plans` | Executes plans step-by-step with verification | — |
| `systematic-debugging` | 4-phase root cause process before any fix | — |
| `verification-before-completion` | Ensures tasks are done, not just attempted | — |
| `test-driven-development` | Red-green-refactor discipline | — |
| `subagent-driven-development` | Parallel subagent execution for complex tasks | — |
| `create-skill` | **Writes new skills during conversation** | — |
| `skill-vetting` | Security scanner for ClawHub skills before installing | `vet.sh` |

### OpenClaw-Native (10 skills — new, not in superpowers)

| Skill | Purpose | Cron | Stateful | Script |
|---|---|---|---|---|
| `long-running-task-management` | Breaks multi-hour tasks into checkpointed stages with resume | every 15 min | ✓ | — |
| `persistent-memory-hygiene` | Keeps OpenClaw's memory store clean and useful over time | daily 11pm | ✓ | — |
| `task-handoff` | Gracefully hands off incomplete tasks across agent restarts | — | ✓ | — |
| `agent-self-recovery` | Detects when the agent is stuck in a loop and escapes | — | ✓ | — |
| `context-window-management` | Prevents context overflow on long-running sessions | — | ✓ | — |
| `daily-review` | End-of-day structured summary and next-session prep | weekdays 6pm | ✓ | — |
| `morning-briefing` | Daily briefing: priorities, active tasks, pending handoffs | weekdays 7am | ✓ | `run.py` |
| `secrets-hygiene` | Audits skills for stale credentials and flags orphaned secrets | Mondays 9am | ✓ | `audit.py` |
| `workflow-orchestration` | Chains skills into resumable named workflows with conditions | — | ✓ | `run.py` |
| `context-budget-guard` | Proactively estimates context usage and triggers compaction | — | ✓ | `check.py` |

### Community (1 skill)

| Skill | Purpose | Cron | Stateful | Script |
|---|---|---|---|---|
| `obsidian-sync` | Syncs OpenClaw memory to an Obsidian vault nightly | daily 10pm | ✓ | `sync.py` |

### How State Works

Stateful skills commit a `STATE_SCHEMA.yaml` defining the shape of their runtime data. At install time, `install.sh` creates `~/.openclaw/skill-state/<skill-name>/state.yaml` on your local machine. The agent reads and writes this file during execution — enabling reliable resume, handoff, and cron-based wakeups without relying on prose instructions. The schema is portable and versioned; the runtime state is local-only and never committed.

### Companion Scripts

Skills marked with a script in the table above ship a small executable alongside their `SKILL.md`:

- **`run.py` / `audit.py` / `check.py` / `sync.py`** — Python 3 scripts the agent (or you) can run directly to manipulate state, generate reports, or trigger sync. No extra dependencies required; `pyyaml` is optional but recommended.
- **`vet.sh`** — Pure bash scanner; runs on any system with grep.
- Each script supports `--dry-run`, `--help`, and prints a human-readable summary. JSON output available where useful (`--format json`).
- See the `example-state.yaml` in each skill directory for sample state and a commented walkthrough.

---

## Why OpenClaw-specific?

obra/superpowers was built for session-based tools (Claude Code, Cursor, Codex). OpenClaw is different:

- Runs **24/7**, not just per-session
- Handles tasks that take **hours, not minutes**
- Needs skills around **handoff, memory persistence, and self-recovery** that session tools don't require

The OpenClaw-native skills in this repo exist because of that difference.

---

## Contributing

1. Open a Skill Proposal issue — or just ask your agent to write one using `create-skill`
2. Run `./scripts/validate-skills.sh`
3. Submit a PR — CI validates automatically
4. Community skills may be promoted to core over time

---

## Credits

- **[openclaw/openclaw](https://github.com/openclaw/openclaw)** — the personal AI runtime that makes this possible
- **[obra/superpowers](https://github.com/obra/superpowers)** — Jesse Vincent's skills framework; core skills adapted here under MIT license
