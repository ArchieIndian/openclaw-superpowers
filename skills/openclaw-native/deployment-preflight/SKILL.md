---
name: deployment-preflight
version: "1.0"
category: openclaw-native
description: Validates OpenClaw deployment safety before install, upgrade, or unattended use — checks workspace visibility, persistent mounts, gateway exposure, and critical runtime paths.
stateful: true
---

# Deployment Preflight

## What it does

OpenClaw often fails in boring ways before the agent does anything wrong: the workspace is not mounted, `.openclaw` is ephemeral, the gateway is publicly exposed, or the extension install path points somewhere unexpected.

Deployment Preflight checks the environment before you trust it with unattended work.

## When to invoke

- Before first-time OpenClaw setup
- Before or after container / compose changes
- Before enabling cron-heavy autonomous workflows
- After upgrades, migrations, or moving the runtime to a new machine

## What it checks

| Check | Why it matters |
|---|---|
| OpenClaw home | Missing or unwritable runtime directories break stateful skills immediately |
| Workspace bootstrap | If `AGENTS.md`, `SOUL.md`, or `MEMORY.md` are absent, the agent starts half-configured |
| Superpowers install path | Detects missing or non-standard extension wiring before skills silently disappear |
| Compose / Docker persistence | Flags deployments that do not persist `.openclaw` or workspace data |
| Gateway exposure | Warns when common OpenClaw ports are published publicly or `network_mode: host` is used |
| Tooling readiness | Confirms `openclaw`, `docker`, and `PyYAML` are present when the deployment depends on them |

## How to use

```bash
python3 check.py --check
python3 check.py --check --path /srv/openclaw
python3 check.py --status
python3 check.py --findings
python3 check.py --format json
```

## Procedure

1. Point the checker at the deployment root if your compose files live outside the current directory.
2. Run `python3 check.py --check`.
3. Fix all FAIL items before deploying.
4. Review WARN items before enabling unattended cron jobs.
5. Save the last known-good output in state so later drift is obvious.

## Output levels

- **PASS** — the preflight area looks healthy
- **WARN** — the deployment may work, but there is drift or risk
- **FAIL** — fix this before trusting the runtime

## Scope

This skill is for deployment wiring, not live runtime behaviour.

- Use `runtime-verification-dashboard` after install to verify cron registration, stale state, and live runtime health.
- Use `deployment-preflight` before install or after infrastructure changes to catch environment mistakes early.

## State

State file: `~/.openclaw/skill-state/deployment-preflight/state.yaml`

Fields: `last_check_at`, `deployment_root`, `deployment_mode`, `environment`, `findings`, `check_history`.
