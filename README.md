# openclaw-superpowers

**59 ready-to-use skills that make your AI agent autonomous, self-healing, and self-improving.**

[![Skills](https://img.shields.io/badge/skills-59-blue)](#skills-included)
[![Security](https://img.shields.io/badge/security_skills-6-green)](#security--guardrails)
[![Cron](https://img.shields.io/badge/cron_scheduled-22-orange)](#openclaw-native-43-skills)
[![Scripts](https://img.shields.io/badge/companion_scripts-43-purple)](#companion-scripts)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

A plug-and-play skill library for [OpenClaw](https://github.com/openclaw/openclaw) — the open-source AI agent runtime. Gives your agent structured thinking, security guardrails, persistent memory, cron scheduling, deployment preflight, runtime verification, self-recovery, and the ability to write its own new skills during conversation.

Built for developers who want their AI agent to run autonomously 24/7, not just respond to prompts in a chat window.

> Inspired by [obra/superpowers](https://github.com/obra/superpowers). Extended for agents that never sleep.

---

## Why this exists

Most AI agent frameworks give you a chatbot that forgets everything between sessions. OpenClaw is different — it runs persistently, handles multi-hour tasks, and has native cron scheduling. But out of the box, it doesn't know *how* to use those capabilities well.

**openclaw-superpowers bridges that gap.** Install 59 skills in one command, and your agent immediately knows how to:

- **Think before it acts** — brainstorming, planning, and systematic debugging skills prevent the "dive in and break things" failure mode
- **Protect itself** — 6 security skills detect prompt injection, block dangerous actions, audit installed code, and scan for leaked credentials
- **Run unattended** — 22 cron-scheduled skills handle memory cleanup, health checks, budget tracking, and community monitoring while you sleep
- **Prove delivery** — cron execution proofs distinguish "the job fired" from "the user actually got the output"
- **Scale delegation safely** — subagent capability auditing catches missing spawn tools, unsafe depth settings, and bloated fleet definitions before they burn time and tokens
- **Rollback cleanly** — upgrade rollback snapshots preserve configs and restore instructions before runtime changes become irreversible
- **Deploy safely** — deployment preflight catches missing mounts, missing bootstrap files, and public gateway exposure before the runtime starts drifting
- **Verify itself** — runtime verification catches missing cron registrations, stale state, dependency drift, and install layout mistakes before they silently break automation
- **Recover from failures** — self-recovery, loop-breaking, task handoff, and reset recovery keep long-running work alive across crashes and routine session resets
- **Never forget** — DAG-based memory compaction, integrity checking, context scoring, and SQLite session persistence ensure the agent preserves critical information even in month-long conversations
- **Improve itself** — the agent can write new skills during normal conversation using `create-skill`, encoding your preferences as permanent behaviors

---

## The self-modifying agent

This is what makes openclaw-superpowers different from every other plugin library:

> *"Every time I do a code review, check for security issues first."*

Your agent invokes `create-skill`, writes a new `SKILL.md`, and that behavior is live — immediately, permanently, no restart needed. The agent encodes your preferences as durable skills. You describe what you want. It teaches itself.

The `community-skill-radar` skill takes this further: it scans Reddit every 3 days for pain points and feature requests from the OpenClaw community, scores them by signal strength, and writes a prioritized `PROPOSALS.md` — so the agent (or you) always knows what to build next.

---

## Quickstart

```bash
git clone https://github.com/ArchieIndian/openclaw-superpowers ~/.openclaw/src/openclaw-superpowers
cd ~/.openclaw/src/openclaw-superpowers && ./install.sh
openclaw gateway restart
```

`install.sh` symlinks the repo's `skills/` directory into `~/.openclaw/extensions/superpowers`, creates state directories for stateful skills, and registers cron jobs. Clone the repo outside `~/.openclaw/extensions` so the installer never has to replace your checkout.

Install `PyYAML` before using the stateful Python helpers: `python3 -m pip install PyYAML`.

---

## Skills included

### Core (15 skills)

Methodology skills that work in any AI agent runtime. Adapted from [obra/superpowers](https://github.com/obra/superpowers) plus new additions for skill quality assurance.

| Skill | What it does | Script |
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

### OpenClaw-Native (43 skills)

Skills that require OpenClaw's persistent runtime — cron scheduling, session state, or long-running execution. These are the skills that make a 24/7 autonomous agent actually work reliably.

| Skill | What it does | Cron | Script |
|---|---|---|---|
| `long-running-task-management` | Breaks multi-hour tasks into checkpointed stages with resume | every 15 min | — |
| `persistent-memory-hygiene` | Keeps the agent's memory store clean and useful over time | daily 11pm | — |
| `task-handoff` | Gracefully hands off incomplete tasks across agent restarts | — | — |
| `agent-self-recovery` | Detects when the agent is stuck in a loop and escapes | — | — |
| `context-window-management` | Prevents context overflow on long-running sessions | — | — |
| `daily-review` | End-of-day structured summary and next-session prep | weekdays 6pm | — |
| `morning-briefing` | Daily briefing: priorities, active tasks, pending handoffs | weekdays 7am | `run.py` |
| `secrets-hygiene` | Audits installed skills for stale credentials and orphaned secrets | Mondays 9am | `audit.py` |
| `workflow-orchestration` | Chains skills into resumable named workflows with on-failure conditions | — | `run.py` |
| `context-budget-guard` | Estimates context usage and triggers compaction before overflow | — | `check.py` |
| `prompt-injection-guard` | Detects injection attempts in external content before the agent acts | — | `guard.py` |
| `spend-circuit-breaker` | Tracks API spend against a monthly budget; pauses crons at 100% | every 4h | `check.py` |
| `dangerous-action-guard` | Requires explicit user confirmation before irreversible actions | — | `audit.py` |
| `loop-circuit-breaker` | Detects infinite retry loops from deterministic errors and breaks them | — | `check.py` |
| `workspace-integrity-guardian` | Detects drift or tampering in SOUL.md, AGENTS.md, MEMORY.md | Sundays 3am | `guard.py` |
| `multi-agent-coordinator` | Manages parallel agent fleets: health checks, consistency, handoffs | — | `run.py` |
| `cron-hygiene` | Audits cron skills for session mode waste and token efficiency | Mondays 9am | `audit.py` |
| `channel-context-bridge` | Writes a context card at session end for seamless channel switching | — | `bridge.py` |
| `skill-doctor` | Diagnoses silent skill discovery failures — YAML errors, path violations, schema mismatches | — | `doctor.py` |
| `installed-skill-auditor` | Weekly post-install audit of all skills for injection, credentials, and drift | Mondays 9am | `audit.py` |
| `deployment-preflight` | Validates deployment safety before install, upgrade, or unattended use — workspace visibility, persistent mounts, gateway exposure, and runtime paths | — | `check.py` |
| `session-reset-recovery` | Checkpoints active work before the overnight reset window and restores a concise resume brief after restart | daily 3:45am | `recover.py` |
| `cron-execution-prover` | Wraps scheduled workflows with proof records — start, finish, evidence, and stale-run detection | — | `prove.py` |
| `message-delivery-verifier` | Tracks outbound notification delivery across channels so sent, acknowledged, failed, and stale messages are explicit | every 15 min | `verify.py` |
| `subagent-capability-auditor` | Audits subagent configuration for spawn depth, tool exposure, and fleet shape before multi-agent work begins | — | `audit.py` |
| `upgrade-rollback-manager` | Snapshots config and state before upgrades and writes rollback instructions tied to the previous runtime version | — | `manage.py` |
| `skill-loadout-manager` | Named skill profiles to manage active skill sets and prevent system prompt bloat | — | `loadout.py` |
| `skill-compatibility-checker` | Checks installed skills against the current OpenClaw version for feature compatibility | — | `check.py` |
| `runtime-verification-dashboard` | Verifies cron registration, state freshness, install layout, and dependency readiness across the live runtime; can dry-run or apply safe remediations | every 6h | `check.py` |
| `heartbeat-governor` | Enforces per-skill execution budgets for cron skills; auto-pauses runaway skills | every hour | `governor.py` |
| `community-skill-radar` | Scans Reddit for OpenClaw pain points and feature requests; writes prioritized PROPOSALS.md | every 3 days | `radar.py` |
| `memory-graph-builder` | Parses MEMORY.md into a knowledge graph; detects duplicates, contradictions, stale entries | daily 10pm | `graph.py` |
| `config-encryption-auditor` | Scans config directories for plaintext API keys, tokens, and world-readable permissions | Sundays 9am | `audit.py` |
| `tool-description-optimizer` | Scores skill descriptions for trigger quality — clarity, specificity, keyword density — and suggests rewrites | — | `optimize.py` |
| `mcp-health-checker` | Monitors MCP server connections for health, latency, and availability; detects stale connections | every 6h | `check.py` |
| `memory-dag-compactor` | Builds hierarchical summary DAGs from MEMORY.md with depth-aware prompts (d0 leaf → d3+ durable) | daily 11pm | `compact.py` |
| `large-file-interceptor` | Detects oversized files, generates structural exploration summaries, stores compact references | — | `intercept.py` |
| `context-assembly-scorer` | Scores how well current context represents full conversation; detects blind spots | every 4h | `score.py` |
| `compaction-resilience-guard` | Monitors compaction for failures; enforces normal → aggressive → deterministic fallback chain | — | `guard.py` |
| `memory-integrity-checker` | Validates summary DAGs for orphans, circular refs, token inflation, broken lineage | Sundays 3am | `integrity.py` |
| `session-persistence` | Imports session transcripts into SQLite with FTS5 full-text search; queryable message history | every 15 min | `persist.py` |
| `dag-recall` | Walks the memory DAG to recall detailed context on demand — query, expand, and assemble cited answers | — | `recall.py` |
| `expansion-grant-guard` | YAML-based delegation grant ledger — scoped permission grants with token budgets and auto-expiry | — | `guard.py` |

### Community (1 skill)

Skills written by agents and contributors. Any agent can add a community skill via `create-skill`.

| Skill | What it does | Cron | Script |
|---|---|---|---|
| `obsidian-sync` | Syncs OpenClaw memory to an Obsidian vault nightly | daily 10pm | `sync.py` |

---

## Security & guardrails

Six skills form a defense-in-depth security layer for autonomous agents:

| Threat | Skill | How it works |
|---|---|---|
| Malicious skill installs | `skill-vetting` | Pre-install scanner with 6 security flags — rates SAFE / CAUTION / DO NOT INSTALL |
| Prompt injection from external content | `prompt-injection-guard` | Detects 6 injection signal types at runtime; blocks on 2+ signals |
| Agent takes destructive action without asking | `dangerous-action-guard` | Pre-execution confirmation gate with 5-min expiry and full audit trail |
| Post-install tampering or credential injection | `installed-skill-auditor` | Weekly SHA-256 drift detection; checks for INJECTION / CREDENTIAL / EXFILTRATION |
| Silent skill loading failures | `skill-doctor` | 6 diagnostic checks per skill; surfaces every load-time failure |
| Plaintext secrets in config files | `config-encryption-auditor` | Scans for 8 API key patterns + 3 token patterns; auto-fixes permissions |

---

## How it compares

| Feature | openclaw-superpowers | obra/superpowers | Custom prompts |
|---|---|---|---|
| Skills included | **59** | 8 | 0 |
| Self-modifying (agent writes new skills) | Yes | No | No |
| Cron scheduling | **22 scheduled skills** | No | No |
| Persistent state across sessions | **YAML state schemas** | No | No |
| Security guardrails | **6 defense-in-depth skills** | No | No |
| Companion scripts with CLI | **43 scripts** | No | No |
| Upgrade rollback planning | Yes | No | No |
| Deployment preflight / Docker safety | Yes | No | No |
| Memory graph / knowledge graph | Yes | No | No |
| SQLite session persistence + FTS5 search | Yes | No | No |
| Sub-agent recall with token-budgeted grants | Yes | No | No |
| MCP server health monitoring | Yes | No | No |
| Runtime verification / observability | Yes | No | No |
| API spend tracking & budget enforcement | Yes | No | No |
| Community feature radar (Reddit scanning) | Yes | No | No |
| Multi-agent coordination | Yes | No | No |
| Works with 24/7 persistent agents | **Built for it** | Session-only | Session-only |

---

## Architecture

```
~/.openclaw/extensions/superpowers/
├── skills/
│   ├── core/                    # 15 methodology skills (any runtime)
│   │   ├── brainstorming/
│   │   │   └── SKILL.md
│   │   ├── create-skill/
│   │   │   ├── SKILL.md
│   │   │   └── TEMPLATE.md
│   │   └── ...
│   ├── openclaw-native/         # 43 persistent-runtime skills
│   │   ├── memory-graph-builder/
│   │   │   ├── SKILL.md             # Skill definition + YAML frontmatter
│   │   │   ├── STATE_SCHEMA.yaml    # State shape (committed, versioned)
│   │   │   ├── graph.py             # Companion script
│   │   │   └── example-state.yaml   # Annotated example
│   │   └── ...
│   └── community/               # Agent-written and contributed skills
├── scripts/
│   └── validate-skills.sh       # CI validation
├── tests/
│   └── test-runner.sh
└── install.sh                   # One-command setup
```

**State model:** Each stateful skill commits a `STATE_SCHEMA.yaml` defining the shape of its runtime data. At install time, `install.sh` creates `~/.openclaw/skill-state/<skill-name>/state.yaml` on your machine. The schema is portable and versioned; the runtime state is local-only and never committed.

---

## Companion scripts

Skills marked with a script ship a small executable alongside their `SKILL.md`:

- **42 Python scripts** (`run.py`, `audit.py`, `check.py`, `guard.py`, `bridge.py`, `onboard.py`, `sync.py`, `doctor.py`, `loadout.py`, `governor.py`, `detect.py`, `test.py`, `radar.py`, `graph.py`, `optimize.py`, `compact.py`, `intercept.py`, `score.py`, `integrity.py`, `persist.py`, `recall.py`) — run directly to manipulate state, generate reports, or trigger actions. Install `PyYAML` for any helper that reads or writes skill state.
- **`vet.sh`** — Pure bash scanner; runs on any system with grep.
- Every script supports `--help` and `--format json`. Dry-run mode available on scripts that make changes.
- See the `example-state.yaml` in each skill directory for sample state and a commented walkthrough of cron behaviour.

---

## Use cases

**Solo developer with a persistent AI agent**
> Install superpowers, and your agent handles memory cleanup, security audits, and daily briefings on autopilot. You focus on building; the agent maintains itself.

**Anyone bitten by the overnight reset**
> Use `session-reset-recovery` to checkpoint active work before the routine reset window and recover with a concise "here is what changed, here is what to do next" brief after restart.

**Teams depending on scheduled delivery**
> Use `cron-execution-prover` around cron workflows that write files or send notifications, so "started" and "delivered" are no longer treated as the same thing.

**Anyone shipping notifications to real humans**
> Use `message-delivery-verifier` for the last mile. It tells you whether a Telegram or Slack-style notification was only queued, actually sent, acknowledged, failed, or left stale.

**Anyone moving from one agent to a fleet**
> Run `subagent-capability-auditor` before trusting subagents in production. It catches missing spawn capability, risky delegation depth, and flat fleets that will be painful to operate.

**Anyone upgrading frequently**
> Use `upgrade-rollback-manager` before changing the runtime version so you have preserved config, a version fingerprint, and a rollback plan if the new release behaves badly.

**Team running multiple OpenClaw agents**
> Use `multi-agent-coordinator` for fleet health checks, `skill-loadout-manager` to keep system prompts lean per agent role, and `heartbeat-governor` to prevent runaway cron costs.

**Self-hosted or Docker deployment**
> Run `deployment-preflight` before the first rollout or after compose changes to catch missing mounts, missing bootstrap files, and public gateway exposure. Follow it with `runtime-verification-dashboard` once the runtime is live.

**Open-source maintainer**
> `community-skill-radar` scans Reddit for pain points automatically. `skill-vetting` catches malicious community contributions before they're installed. `installed-skill-auditor` detects post-install tampering.

**Security-conscious deployment**
> Six defense-in-depth skills: pre-install vetting, runtime injection detection, destructive action gates, post-install drift detection, credential scanning, and silent failure diagnosis.

---

## Contributing

1. Open a Skill Proposal issue — or just ask your agent to write one using `create-skill`
2. Run `./scripts/validate-skills.sh`
3. Submit a PR — CI validates automatically
4. Community skills may be promoted to core over time

---

## Credits

- **[openclaw/openclaw](https://github.com/openclaw/openclaw)** — the open-source AI agent runtime
- **[obra/superpowers](https://github.com/obra/superpowers)** — Jesse Vincent's skills framework; core skills adapted under MIT license
- **[OpenLobster](https://github.com/Neirth/OpenLobster)** — inspiration for memory graph, config encryption auditing, tool-description scoring, and MCP health monitoring
- **[lossless-claw](https://github.com/Martian-Engineering/lossless-claw)** — inspiration for DAG-based memory compaction, session persistence, sub-agent recall, and delegation grants
