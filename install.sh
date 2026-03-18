#!/usr/bin/env bash
set -euo pipefail
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENCLAW_DIR="${OPENCLAW_HOME:-$HOME/.openclaw}"
INSTALL_TARGET="$OPENCLAW_DIR/extensions/superpowers"
STATE_DIR="$OPENCLAW_DIR/skill-state"

echo "Installing openclaw-superpowers..."

if [ ! -d "$OPENCLAW_DIR" ]; then
  echo "OpenClaw not found at $OPENCLAW_DIR"
  exit 1
fi

# --- Symlink ---
mkdir -p "$OPENCLAW_DIR/extensions"
if [ -e "$INSTALL_TARGET" ] && [ ! -L "$INSTALL_TARGET" ]; then
  echo "Refusing to replace non-symlink path at $INSTALL_TARGET"
  if [ "$REPO_DIR" = "$INSTALL_TARGET" ]; then
    echo "This repository is checked out inside the extensions directory."
    echo "Clone it somewhere else (for example: $OPENCLAW_DIR/src/openclaw-superpowers) and rerun ./install.sh."
  else
    echo "Remove or move the existing directory manually, then rerun ./install.sh."
  fi
  exit 1
fi
rm -f "$INSTALL_TARGET"
ln -s "$REPO_DIR/skills" "$INSTALL_TARGET"

if ! python3 -c "import yaml" >/dev/null 2>&1; then
  echo "WARN: PyYAML is not installed. Stateful Python helpers can read less and may not persist updates correctly."
  echo "      Install it with: python3 -m pip install PyYAML"
fi

# --- Helper: register a stateful skill (create state dir + empty stub) ---
register_stateful_skill() {
  local skill_name="$1"
  local state_skill_dir="$STATE_DIR/$skill_name"
  mkdir -p "$state_skill_dir"
  if [ ! -f "$state_skill_dir/state.yaml" ]; then
    echo "# Runtime state for $skill_name — managed by openclaw-superpowers" > "$state_skill_dir/state.yaml"
    echo "  + state dir: $skill_name"
  else
    echo "  ~ state dir already exists, preserving: $skill_name"
  fi
}

# --- Helper: register a cron job (idempotent: remove then add) ---
register_cron_skill() {
  local skill_name="$1"
  local cron_expr="$2"
  openclaw cron remove "$skill_name" 2>/dev/null || true
  openclaw cron add "$skill_name" "$cron_expr" \
    || echo "  WARN: 'openclaw cron add' failed for $skill_name (is OpenClaw running?)"
  echo "  + cron: $skill_name ($cron_expr)"
}

# --- Scan openclaw-native skills for stateful/cron fields ---
mkdir -p "$STATE_DIR"
STATEFUL_COUNT=0
CRON_COUNT=0

for skill_file in "$REPO_DIR/skills/openclaw-native"/*/SKILL.md; do
  [ -f "$skill_file" ] || continue
  skill_name="$(basename "$(dirname "$skill_file")")"

  fm_stateful="$(sed -n '2,/^---$/p' "$skill_file" | grep '^stateful:' | sed 's/^stateful: *//' | tr -d '[:space:]')"
  fm_cron="$(sed -n '2,/^---$/p' "$skill_file" | grep '^cron:' | sed 's/^cron: *//' | tr -d '"'"'")"

  if [ "$fm_stateful" = "true" ]; then
    register_stateful_skill "$skill_name"
    STATEFUL_COUNT=$((STATEFUL_COUNT + 1))
  fi

  if [ -n "$fm_cron" ]; then
    register_cron_skill "$skill_name" "$fm_cron"
    CRON_COUNT=$((CRON_COUNT + 1))
  fi
done

echo ""
echo "openclaw-superpowers installed."
echo "  Skills symlinked to: $INSTALL_TARGET"
echo "  State directories:   $STATEFUL_COUNT created/preserved at $STATE_DIR"
echo "  Cron jobs registered: $CRON_COUNT"
echo ""
echo "Restart OpenClaw to activate."
