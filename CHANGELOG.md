# Changelog

## [0.2.0] - 2026-03-29

### Added
- Runtime reliability skills: `runtime-verification-dashboard`, `deployment-preflight`, `session-reset-recovery`, `cron-execution-prover`, `message-delivery-verifier`, `subagent-capability-auditor`, `upgrade-rollback-manager`, and `mcp-auth-lifecycle-manager`
- Operational playbooks in `docs/OPERATIONS.md`

### Changed
- README and contributor guidance now reflect the expanded operational skill set and validation workflow
- New shared `scripts/state_helpers.py` reduces repeated state loading and saving code across recent Python helpers

## [0.1.0] - 2026-03-15

### Added
- 8 core skills adapted from obra/superpowers for OpenClaw
- 6 OpenClaw-native skills for persistent agent workflows
- install.sh / uninstall.sh
