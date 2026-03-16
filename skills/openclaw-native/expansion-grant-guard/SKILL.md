---
name: expansion-grant-guard
version: "1.0"
category: openclaw-native
description: YAML-based delegation grant ledger — issues, validates, and tracks scoped permission grants for sub-agent expansions with token budgets and auto-expiry.
stateful: true
---

# Expansion Grant Guard

## What it does

When an agent delegates work to a sub-agent (or expands context via DAG recall), it needs a controlled way to grant scoped permissions. Expansion Grant Guard maintains a YAML-based grant ledger that issues time-limited, token-budgeted grants — ensuring sub-agent operations stay within defined boundaries.

Inspired by [lossless-claw](https://github.com/Martian-Engineering/lossless-claw)'s delegation grant system, where a parent agent issues a signed grant specifying what a sub-agent can access, how many tokens it may consume, and when the grant expires.

## When to invoke

- Before any sub-agent expansion or delegation — issue a grant first
- When a sub-agent requests resources — validate the grant before proceeding
- When checking token budgets — verify remaining budget in the grant
- Periodically to clean up expired grants — auto-expiry sweep

## How to use

```bash
python3 guard.py --issue --scope "dag-recall" --budget 4000 --ttl 30   # Issue a grant
python3 guard.py --validate <grant-id>                                  # Check if grant is valid
python3 guard.py --consume <grant-id> --tokens 500                     # Record token usage
python3 guard.py --revoke <grant-id>                                    # Revoke a grant early
python3 guard.py --list                                                 # List all active grants
python3 guard.py --sweep                                                # Clean up expired grants
python3 guard.py --audit                                                # Full audit log
python3 guard.py --stats                                                # Grant statistics
python3 guard.py --status                                               # Current status summary
python3 guard.py --format json                                          # Machine-readable output
```

## Grant structure

Each grant is a YAML entry in the ledger:

```yaml
grant_id: "g-20260316-001"
scope: "dag-recall"           # What the grant allows
issued_at: "2026-03-16T10:00:00Z"
expires_at: "2026-03-16T10:30:00Z"
token_budget: 4000            # Max tokens allowed
tokens_consumed: 1250         # Tokens used so far
status: active                # active | expired | revoked | exhausted
issuer: "parent-session"
metadata:
  query: "auth migration"
  reason: "Recalling auth decisions for new implementation"
```

## Grant lifecycle

```
Issue → Active → { Consumed | Expired | Revoked | Exhausted }
  │                    │
  │                    ├─ tokens_consumed < budget → still active
  │                    ├─ tokens_consumed >= budget → exhausted
  │                    ├─ now > expires_at → expired
  │                    └─ explicit revoke → revoked
  │
  └─ Validation checks: status=active AND not expired AND budget remaining
```

## Procedure

**Step 1 — Issue a grant before expansion**

```bash
python3 guard.py --issue --scope "dag-recall" --budget 4000 --ttl 30
```

Output:
```
Grant Issued
─────────────────────────────────────────────
  Grant ID:     g-20260316-001
  Scope:        dag-recall
  Token budget: 4,000
  Expires:      2026-03-16T10:30:00Z (in 30 min)
  Status:       active
```

**Step 2 — Validate before consuming resources**

```bash
python3 guard.py --validate g-20260316-001
```

Returns status, remaining budget, and time until expiry. Non-zero exit code if invalid.

**Step 3 — Record token consumption**

```bash
python3 guard.py --consume g-20260316-001 --tokens 1250
```

Deducts from the grant's remaining budget. Fails if exceeding budget.

**Step 4 — Sweep expired grants**

```bash
python3 guard.py --sweep
```

Marks all expired grants and cleans up the active list.

## Scope types

- `dag-recall` — Permission to walk DAG nodes and assemble answers
- `session-search` — Permission to search session persistence database
- `file-access` — Permission to read externalized large files
- `context-expand` — Permission to expand context window with external data
- `tool-invoke` — Permission to invoke external tools/MCP servers
- Custom scopes accepted — any string is valid

## Integration with other skills

- **dag-recall**: Should issue a grant before expanding DAG nodes; checks budget during expansion
- **session-persistence**: Grant-gated search — validate grant before querying message database
- **large-file-interceptor**: Grant-gated file restore — validate before loading large files back
- **context-assembly-scorer**: Token budget tracking feeds into assembly scoring

## State

Grant ledger and audit log stored in `~/.openclaw/skill-state/expansion-grant-guard/state.yaml`.

Fields: `active_grants`, `total_issued`, `total_expired`, `total_revoked`, `total_exhausted`, `total_tokens_granted`, `total_tokens_consumed`, `grant_history`.

## Notes

- Uses Python's built-in modules only — no external dependencies
- Grant IDs are timestamped and sequential within a day
- Ledger file is append-friendly YAML — safe for concurrent reads
- Expired grants kept in history for audit; active list stays clean after sweep
- Default TTL is 30 minutes; max TTL is 24 hours
- Token budget is advisory — enforcement depends on consuming skill cooperation
