#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
README="$REPO_DIR/README.md"

SKILL_COUNT="$(git -C "$REPO_DIR" ls-files 'skills/*/*/SKILL.md' | wc -l | tr -d '[:space:]')"
CRON_COUNT="$(git -C "$REPO_DIR" grep -l '^cron:' -- 'skills/*/*/SKILL.md' | wc -l | tr -d '[:space:]')"
PYTHON_SCRIPT_COUNT="$(git -C "$REPO_DIR" ls-files 'skills/**/*.py' | wc -l | tr -d '[:space:]')"
COMPANION_SCRIPT_COUNT=$((PYTHON_SCRIPT_COUNT + 1))

assert_contains() {
  local pattern="$1"
  local message="$2"
  if ! grep -Fq -- "$pattern" "$README"; then
    echo "FAIL: $message"
    echo "  Expected to find: $pattern"
    exit 1
  fi
}

assert_contains "[![Skills](https://img.shields.io/badge/skills-$SKILL_COUNT-blue)]" "README skills badge is stale"
assert_contains "[![Cron](https://img.shields.io/badge/cron_scheduled-$CRON_COUNT-orange)]" "README cron badge is stale"
assert_contains "[![Scripts](https://img.shields.io/badge/companion_scripts-$COMPANION_SCRIPT_COUNT-purple)]" "README script badge is stale"
assert_contains "Install $SKILL_COUNT skills in one command" "README install summary count is stale"
assert_contains "**Run unattended** — $CRON_COUNT cron-scheduled skills" "README unattended count is stale"
assert_contains "| Cron scheduling | **$CRON_COUNT scheduled skills** | No | No |" "README comparison table cron count is stale"
assert_contains "| Companion scripts with CLI | **$COMPANION_SCRIPT_COUNT scripts** | No | No |" "README comparison table script count is stale"
assert_contains "- **$PYTHON_SCRIPT_COUNT Python scripts**" "README companion script count is stale"

echo "README metrics are in sync."
