#!/usr/bin/env bash
set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENCLAW_DIR="${OPENCLAW_HOME:-$HOME/.openclaw}"
INSTALL_TARGET="$OPENCLAW_DIR/extensions/superpowers"
STATE_DIR="$OPENCLAW_DIR/skill-state"

# --- Deregister cron jobs BEFORE removing the symlink ---
CRON_COUNT=0
for skill_file in "$REPO_DIR/skills/openclaw-native"/*/SKILL.md; do
  [ -f "$skill_file" ] || continue
  skill_name="$(basename "$(dirname "$skill_file")")"
  fm_cron="$(sed -n '2,/^---$/p' "$skill_file" | grep '^cron:' | sed 's/^cron: *//' | tr -d '"'"'")"
  if [ -n "$fm_cron" ]; then
    openclaw cron remove "$skill_name" 2>/dev/null || true
    echo "  - cron removed: $skill_name"
    CRON_COUNT=$((CRON_COUNT + 1))
  fi
done

# --- Remove symlink ---
if [ -L "$INSTALL_TARGET" ] || [ -d "$INSTALL_TARGET" ]; then
  rm -rf "$INSTALL_TARGET"
  echo "openclaw-superpowers removed."
else
  echo "Nothing to uninstall."
fi

echo ""
echo "  Cron jobs deregistered: $CRON_COUNT"
echo "  Runtime state preserved at: $STATE_DIR"
echo "  (Remove manually if no longer needed)"
