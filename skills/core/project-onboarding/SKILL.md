---
name: project-onboarding
version: "1.0"
category: core
description: Crawls a new codebase to infer stack, conventions, and key invariants, then generates a PROJECT.md context file for the agent
stateful: true
---

# project-onboarding

When starting work on a new codebase, the agent has zero context. This leads to hallucinated conventions, ignored project patterns, and wasted turns re-explaining the stack. This skill crawls a target directory, infers everything it can automatically, and generates a structured `PROJECT.md` that the agent loads for all future work on that project.

## When to invoke

Invoke this skill when:
- Starting work on a codebase for the first time
- The agent begins making assumption errors about the project structure
- A new team member (agent) is added to an existing project

## Onboarding protocol

**Step 1 — Crawl the directory**
Scan the project root for:
- `package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, `pom.xml`, etc. → infer tech stack
- `Makefile`, `justfile`, `scripts/` → infer build/test commands
- `.github/workflows/` → CI commands and quality gates
- Test file patterns (`__tests__/`, `spec/`, `*_test.go`) → testing conventions
- `CONTRIBUTING.md`, `DEVELOPMENT.md`, `docs/` → explicit conventions
- `src/`, `lib/`, `app/`, `internal/` → project structure

**Step 2 — Infer key invariants**
Ask: what would break the project if violated? Examples:
- "All API responses must include a `requestId` field"
- "Never commit secrets — use `.env.example`"
- "All new routes must have a corresponding integration test"

Read existing test names, CI checks, and lint config to infer these.

**Step 3 — Generate PROJECT.md**
Write `PROJECT.md` to the project root (or `~/.openclaw/workspace/<project-slug>.md`):

```markdown
# Project: <name>
## Stack
## Build & Test Commands
## Project Structure
## Key Conventions
## Things the Agent Must Never Do Here
## Known Gotchas
```

**Step 4 — User validation**
Show the generated file and ask: "Does this look right? Anything missing or wrong?"
Revise based on feedback.

**Step 5 — Register in state**
Record the project path, PROJECT.md location, and onboarded date in state so the agent auto-loads context on future sessions.

## Auto-load on session start

When working in a directory that matches a registered project, the agent should:
1. Read PROJECT.md into context before any work
2. Skip Step 1–4 (already onboarded)
3. Run `python3 onboard.py --refresh` monthly to catch drift

## Companion script

`python3 onboard.py --scan <path>` performs Step 1 and outputs a structured JSON summary of detected stack/conventions — the agent uses this to populate Step 3.
