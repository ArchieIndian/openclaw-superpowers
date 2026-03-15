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

---

## Skills Included

### Core (15 skills)

Methodology skills that work in any runtime. Adapted from [obra/superpowers](https://github.com/obra/superpowers) plus OpenClaw-specific additions.

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
| `project-onboarding` | Crawls a new codebase to generate a `PROJECT.md` context file | `onboard.py` |
| `fact-check-before-trust` | Secondary verification pass for factual claims before acting on them | — |
| `skill-trigger-tester` | Scores a skill's description against sample prompts to predict trigger reliability | `test.py` |
| `skill-conflict-detector` | Detects name shadowing and description-overlap conflicts between installed skills | `detect.py` |
| `skill-portability-checker` | Validates OS/binary dependencies in companion scripts; catches non-portable calls | `check.py` |

### OpenClaw-Native (28 skills)

Skills that require OpenClaw's persistent runtime — cron scheduling, session state, or long-running execution. Not useful in session-based tools.

| Skill | Purpose | Cron | Stateful | Script |
|---|---|---|---|---|
| `long-running-task-management` | Breaks multi-hour tasks into checkpointed stages with resume | every 15 min | ✓ | — |
| `persistent-memory-hygiene` | Keeps OpenClaw's memory store clean and useful over time | daily 11pm | ✓ | — |
| `task-handoff` | Gracefully hands off incomplete tasks across agent restarts | — | ✓ | — |
| `agent-self-recovery` | Detects when the agent is stuck in a loop and escapes | — | ✓ | — |
| `context-window-management` | Prevents context overflow on long-running sessions | — | ✓ | — |
| `daily-review` | End-of-day structured summary and next-session prep | weekdays 6pm | ✓ | — |
| `morning-briefing` | Daily briefing: priorities, active tasks, pending handoffs | weekdays 7am | ✓ | `run.py` |
| `secrets-hygiene` | Audits installed skills for stale credentials and orphaned secrets | Mondays 9am | ✓ | `audit.py` |
| `workflow-orchestration` | Chains skills into resumable named workflows with on-failure conditions | — | ✓ | `run.py` |
| `context-budget-guard` | Estimates context usage and triggers compaction before overflow | — | ✓ | `check.py` |
| `prompt-injection-guard` | Detects injection attempts in external content before the agent acts | — | ✓ | `guard.py` |
| `spend-circuit-breaker` | Tracks API spend against a monthly budget; pauses crons at 100% | every 4h | ✓ | `check.py` |
| `dangerous-action-guard` | Requires explicit user confirmation before irreversible actions | — | ✓ | `audit.py` |
| `loop-circuit-breaker` | Detects infinite retry loops from deterministic errors and breaks them | — | ✓ | `check.py` |
| `workspace-integrity-guardian` | Detects drift or tampering in SOUL.md, AGENTS.md, MEMORY.md | Sundays 3am | ✓ | `guard.py` |
| `multi-agent-coordinator` | Manages parallel agent fleets: health checks, consistency, handoffs | — | ✓ | `run.py` |
| `cron-hygiene` | Audits cron skills for session mode waste and token efficiency | Mondays 9am | ✓ | `audit.py` |
| `channel-context-bridge` | Writes a resumé card at session end for seamless channel switching | — | ✓ | `bridge.py` |
| `skill-doctor` | Diagnoses silent skill discovery failures — YAML errors, path violations, schema mismatches | — | ✓ | `doctor.py` |
| `installed-skill-auditor` | Weekly post-install audit of all skills for injection, credentials, and drift | Mondays 9am | ✓ | `audit.py` |
| `skill-loadout-manager` | Named skill profiles to manage active skill sets and prevent system prompt bloat | — | ✓ | `loadout.py` |
| `skill-compatibility-checker` | Checks installed skills against the current OpenClaw version for feature compatibility | — | ✓ | `check.py` |
| `heartbeat-governor` | Enforces per-skill execution budgets for cron skills; auto-pauses runaway skills | every hour | ✓ | `governor.py` |
| `community-skill-radar` | Scans Reddit for OpenClaw pain points and feature requests; writes prioritized PROPOSALS.md | every 3 days | ✓ | `radar.py` |
| `memory-graph-builder` | Parses MEMORY.md into a knowledge graph; detects duplicates, contradictions, and stale entries; generates compressed digest | daily 10pm | ✓ | `graph.py` |
| `config-encryption-auditor` | Scans config directories for plaintext API keys, tokens, and world-readable permissions | Sundays 9am | ✓ | `audit.py` |
| `tool-description-optimizer` | Scores skill descriptions for trigger quality — clarity, specificity, keyword density — and suggests rewrites | — | ✓ | `optimize.py` |
| `mcp-health-checker` | Monitors MCP server connections for health, latency, and availability; detects stale connections | every 6h | ✓ | `check.py` |

### Community (1 skill)

Skills written by agents and contributors. Lives in `skills/community/`. Any agent can add a community skill via `create-skill`. Community skills default to stateless but may use `STATE_SCHEMA.yaml` when persistence is genuinely needed.

| Skill | Purpose | Cron | Stateful | Script |
|---|---|---|---|---|
| `obsidian-sync` | Syncs OpenClaw memory to an Obsidian vault nightly | daily 10pm | ✓ | `sync.py` |

---

## How State Works

Stateful skills commit a `STATE_SCHEMA.yaml` defining the shape of their runtime data. At install time, `install.sh` creates `~/.openclaw/skill-state/<skill-name>/state.yaml` on your local machine. The agent reads and writes this file during execution — enabling reliable resume, handoff, and cron-based wakeups without relying on prose instructions. The schema is portable and versioned; the runtime state is local-only and never committed.

## Companion Scripts

Skills marked with a script in the table above ship a small executable alongside their `SKILL.md`:

- **Python scripts** (`run.py`, `audit.py`, `check.py`, `guard.py`, `bridge.py`, `onboard.py`, `sync.py`, `doctor.py`, `loadout.py`, `governor.py`, `detect.py`, `test.py`, `radar.py`, `graph.py`, `optimize.py`) — run directly to manipulate state, generate reports, or trigger actions. No extra dependencies required; `pyyaml` is optional but recommended.
- **`vet.sh`** — Pure bash scanner; runs on any system with grep.
- Each script supports `--help` and prints a human-readable summary. JSON output available where useful (`--format json`). Dry-run mode available on scripts that make changes.
- See the `example-state.yaml` in each skill directory for sample state and a commented walkthrough of the skill's cron behaviour.

---

## Security skills at a glance

Six skills address the documented top security risks for OpenClaw agents:

| Threat | Skill | How |
|---|---|---|
| Malicious skill install (36% of ClawHub skills contain injection payloads) | `skill-vetting` | Scans before install — 6 security flags, SAFE / CAUTION / DO NOT INSTALL |
| Runtime injection from emails, web pages, scraped data | `prompt-injection-guard` | Detects 6 signal types at runtime; blocks on 2+ signals |
| Agent takes destructive action without confirmation | `dangerous-action-guard` | Pre-execution gate with 5-min expiry window and full audit trail |
| Post-install skill tampering or credential injection | `installed-skill-auditor` | Weekly content-hash drift detection; INJECTION / CREDENTIAL / EXFILTRATION checks |
| Silent skill loading failures hiding broken skills | `skill-doctor` | 6 diagnostic checks per skill; surfaces every load-time failure before it disappears |
| Plaintext API keys and tokens in config files | `config-encryption-auditor` | Scans for 8 API key patterns + 3 token patterns; auto-fixes permissions; suggests env var migration |

---

## Why OpenClaw-specific?

obra/superpowers was built for session-based tools (Claude Code, Cursor, Codex). OpenClaw is different:

- Runs **24/7**, not just per-session
- Handles tasks that take **hours, not minutes**
- Has **native cron scheduling** — skills wake up automatically on a schedule
- Needs skills around **handoff, memory persistence, and self-recovery** that session tools don't require

The OpenClaw-native skills in this repo exist because of that difference. And with `community-skill-radar`, the library discovers what to build next by scanning Reddit communities automatically.

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
