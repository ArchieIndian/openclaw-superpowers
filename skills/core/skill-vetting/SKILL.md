---
name: skill-vetting
description: Reviews a ClawHub skill's source code for security risks before installation. Use before installing any new skill.
---

# Skill Vetting

~17% of ClawHub skills are malicious. Read before you install.

## When to Use

- Before installing any skill from ClawHub or an external source
- When a skill requests unusual permissions or credentials

## The Process

### Step 1: Read the Source
Locate and read the skill's full `SKILL.md` and any scripts it references. Never install from a description alone.

### Step 2: Check for Red Flags

Scan for each of these — flag any that are present:

- [ ] **Unknown network calls** — does it POST to a non-obvious domain? (`curl`, `fetch`, `requests.post`)
- [ ] **Credential harvesting** — does it read `~/.ssh`, `~/.env`, API key env vars, or keychain?
- [ ] **Filesystem writes outside expected paths** — anything writing outside `~/.openclaw/` or the project dir?
- [ ] **Obfuscated code** — base64-encoded payloads, eval of dynamic strings, minified one-liners
- [ ] **Excessive permissions** — requesting tool access it doesn't need for its stated purpose
- [ ] **Unverifiable author** — new account, no history, no linked repo

### Step 3: Verdict

- **0 flags** → safe to install
- **1–2 flags** → install with caution; note which flags and monitor
- **3+ flags** → do not install; tell the user why

### Step 4: Report
State your verdict clearly before any install proceeds:
> "Vetted `[skill-name]`: [0/1/2/3] flags. [Safe to install / Install with caution / Do not install]. Flags: [list]."

## Key Principles

- Never skip vetting because a skill is popular or highly downloaded
- A skill that "just reads" can still exfiltrate data via network calls
- If source code is unavailable or obfuscated, that itself is a flag
