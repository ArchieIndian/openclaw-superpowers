# Operational Playbooks

This repo has enough always-on skills now that the useful question is no longer "which skills exist?" but "which ones should I turn on together?"

Use these playbooks as a rollout order.

## 1. First deployment

Use this when bringing up OpenClaw on a laptop, server, or Docker host for the first time.

1. Run `deployment-preflight` before install or after any compose change.
2. Install `openclaw-superpowers`.
3. Run `runtime-verification-dashboard` once the runtime is live.
4. Fix any missing mounts, missing bootstrap files, missing cron registrations, or state path issues before enabling unattended workflows.

Why this order:
- `deployment-preflight` catches layout and exposure mistakes before the runtime starts.
- `runtime-verification-dashboard` catches post-install drift inside the live runtime.

## 2. Scheduled workflow with proof

Use this when a cron workflow writes files, posts a report, or notifies a human.

1. Wrap the workflow in `cron-execution-prover`.
2. Track the last-mile notification in `message-delivery-verifier`.
3. Review stale executions and stale deliveries before trusting the automation.

Why this order:
- `cron-execution-prover` proves the job started and finished.
- `message-delivery-verifier` proves the output was actually sent and acknowledged.

## 3. Overnight continuity

Use this when long-running work regularly crosses the session reset window.

1. Enable `session-reset-recovery`.
2. Pair it with `task-handoff` for tasks that may span multiple sessions or agents.
3. Review `resume_brief` output after restart before resuming work.

Why this order:
- `session-reset-recovery` preserves the active checkpoint.
- `task-handoff` keeps the next operator or session from restarting blind.

## 4. Safer upgrades

Use this before changing OpenClaw versions, config structure, or deployment layout.

1. Run `upgrade-rollback-manager --snapshot`.
2. Apply the upgrade.
3. Re-run `deployment-preflight`.
4. Re-run `runtime-verification-dashboard`.
5. If something regresses, generate rollback instructions with `upgrade-rollback-manager --rollback-plan <label>`.

Why this order:
- Snapshot first.
- Then verify both the deployment surface and the live runtime after the change.

## 5. MCP-dependent automation

Use this when OpenClaw depends on GitHub, Linear, filesystem, browser, or other MCP servers.

1. Use `mcp-health-checker` to verify transport reachability.
2. Use `mcp-auth-lifecycle-manager` to verify token expiry, env vars, and refresh readiness.
3. Avoid unattended dependency on MCP servers that still require interactive re-authentication.

Why this order:
- Reachability and auth are different failure modes.
- A healthy server can still be unusable if the auth path is broken.
