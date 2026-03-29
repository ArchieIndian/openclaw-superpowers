---
name: upgrade-rollback-manager
version: "1.0"
category: openclaw-native
description: Snapshots OpenClaw config and state before upgrades, records version fingerprints, and writes rollback instructions so runtime updates stop being one-way bets.
stateful: true
---

# Upgrade Rollback Manager

## What it does

OpenClaw upgrades can change config shape, break skill assumptions, or leave the runtime in a half-working state. Upgrade Rollback Manager takes a snapshot before the change, records what version and config you upgraded from, and writes a rollback brief you can use if the new runtime goes sideways.

## When to invoke

- Immediately before upgrading OpenClaw
- Before changing runtime config in a way that is hard to reverse
- After an upgrade, to compare the current runtime against the last known-good snapshot
- When users report "it worked before the update" and you need a rollback path

## What it records

- Detected OpenClaw version
- Timestamped snapshot directory
- Checksums of important config files
- A list of preserved paths
- Human-readable rollback instructions

## How to use

```bash
python3 manage.py --snapshot
python3 manage.py --snapshot --label before-1-5-upgrade
python3 manage.py --status
python3 manage.py --list
python3 manage.py --rollback-plan before-1-5-upgrade
python3 manage.py --format json
```

## Safety model

This skill does not automatically downgrade or overwrite the runtime. It prepares a rollback kit:

- snapshot files
- version/config metadata
- exact restore steps

The operator still chooses when to execute the rollback.

## Difference from deployment-preflight

`deployment-preflight` tells you whether a deployment is wired safely.

`upgrade-rollback-manager` preserves a way back before you change that deployment.

## State

State file: `~/.openclaw/skill-state/upgrade-rollback-manager/state.yaml`

Fields: `last_snapshot_at`, `latest_snapshot`, `snapshots`, `rollback_history`.
