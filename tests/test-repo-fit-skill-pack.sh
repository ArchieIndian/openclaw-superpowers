#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

fail() {
  echo "FAIL: $1"
  exit 1
}

assert_file() {
  [ -f "$1" ] || fail "missing file: $1"
}

assert_dir() {
  [ -d "$1" ] || fail "missing directory: $1"
}

assert_json() {
  python3 -m json.tool >/dev/null || fail "$1 did not emit valid JSON"
}

assert_skill() {
  local category="$1"
  local name="$2"
  local dir="$REPO_DIR/skills/$category/$name"
  local skill="$dir/SKILL.md"

  assert_dir "$dir"
  assert_file "$skill"

  local first_line
  first_line="$(head -1 "$skill")"
  [ "$first_line" = "---" ] || fail "$name SKILL.md missing frontmatter"

  local fm_name
  fm_name="$(sed -n '2,/^---$/p' "$skill" | grep '^name:' | sed 's/^name: *//' | tr -d '[:space:]')"
  [ "$fm_name" = "$name" ] || fail "$name frontmatter name mismatch: $fm_name"
}

assert_stateful_skill() {
  local name="$1"
  local dir="$REPO_DIR/skills/openclaw-native/$name"

  assert_skill "openclaw-native" "$name"
  assert_file "$dir/STATE_SCHEMA.yaml"
  assert_file "$dir/example-state.yaml"
}

echo "Testing repo-fit skill pack..."

assert_skill "core" "pull-request-feedback-loop"
assert_skill "core" "skill-effectiveness-auditor"
assert_stateful_skill "openclaw-config-advisor"
assert_stateful_skill "quality-gate-orchestrator"

python3 "$REPO_DIR/skills/openclaw-native/openclaw-config-advisor/advise.py" --help >/dev/null
python3 "$REPO_DIR/skills/openclaw-native/quality-gate-orchestrator/gate.py" --help >/dev/null

export OPENCLAW_HOME="$TMP_DIR/openclaw-home"
MISSING_CONFIG="$TMP_DIR/missing-config"

python3 "$REPO_DIR/skills/openclaw-native/openclaw-config-advisor/advise.py" \
  --scan --config-dir "$MISSING_CONFIG" --format json | assert_json "openclaw-config-advisor scan"

python3 "$REPO_DIR/skills/openclaw-native/quality-gate-orchestrator/gate.py" \
  --status --format json | assert_json "quality-gate-orchestrator status"

python3 "$REPO_DIR/skills/openclaw-native/quality-gate-orchestrator/gate.py" \
  --add --name lint --command "npm test" --format json | assert_json "quality-gate-orchestrator add"

python3 "$REPO_DIR/skills/openclaw-native/quality-gate-orchestrator/gate.py" \
  --record --name lint --status pass --format json | assert_json "quality-gate-orchestrator record"

READY_JSON="$TMP_DIR/ready.json"
python3 "$REPO_DIR/skills/openclaw-native/quality-gate-orchestrator/gate.py" \
  --ready --format json > "$READY_JSON"
python3 -m json.tool "$READY_JSON" >/dev/null || fail "quality-gate-orchestrator ready did not emit valid JSON"
python3 - "$READY_JSON" <<'PY'
import json
import sys

with open(sys.argv[1]) as f:
    data = json.load(f)

if data.get("ready") is not True:
    raise SystemExit("FAIL: expected ready=true after required gate passed")
PY

echo "PASS: repo-fit skill pack"
