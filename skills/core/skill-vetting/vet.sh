#!/usr/bin/env bash
# skill-vetting/vet.sh
# Security scanner for OpenClaw skills downloaded from ClawHub.
#
# Usage:
#   ./vet.sh <path-to-skill-dir>       # Vet a single skill directory
#   ./vet.sh --all <skills-root>        # Vet all skills under a directory
#
# Exit codes:
#   0  SAFE (0 flags)
#   1  CAUTION (1-2 flags)
#   2  DO NOT INSTALL (3+ flags)
#   3  Usage error

set -euo pipefail

# ── Helpers ──────────────────────────────────────────────────────────────────

RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BOLD='\033[1m'
RESET='\033[0m'

usage() {
    echo "Usage: $0 <skill-dir>"
    echo "       $0 --all <skills-root-dir>"
    exit 3
}

# ── Flag definitions ──────────────────────────────────────────────────────────
# Each flag: NAME | PATTERN | DESCRIPTION
# Patterns are extended regex applied to all text files in the skill dir.

declare -a FLAG_NAMES=(
    "OUTBOUND_NETWORK"
    "CREDENTIAL_HARVEST"
    "FILESYSTEM_WRITE"
    "OBFUSCATED_CODE"
    "PRIVILEGE_ESCALATION"
    "UNTRUSTED_INPUT_EXEC"
)

declare -a FLAG_PATTERNS=(
    'curl|wget|fetch\(|http\.get|requests\.get|urllib|axios'
    'API_KEY|SECRET|TOKEN|PASSWORD|CREDENTIAL|keychain|vault'
    'rm -rf|shutil\.rmtree|os\.remove|unlink|truncate|> /'
    'base64 -d|eval\(|exec\(|__import__|pickle\.loads|marshal'
    'sudo|chmod 777|chown root|setuid|su -'
    'subprocess\.call|os\.system|shell=True|eval.*input|exec.*input'
)

declare -a FLAG_DESCRIPTIONS=(
    "Makes outbound network requests (data exfiltration risk)"
    "References credentials or secret stores"
    "Performs destructive filesystem operations"
    "Contains obfuscated or dynamically evaluated code"
    "Attempts privilege escalation"
    "Executes user input or external data as code (injection risk)"
)

# ── Core vet function ─────────────────────────────────────────────────────────

vet_skill() {
    local skill_dir="$1"
    local skill_name
    skill_name="$(basename "$skill_dir")"

    if [ ! -f "$skill_dir/SKILL.md" ]; then
        echo "ERROR: $skill_dir does not contain SKILL.md — not a skill directory"
        return 3
    fi

    echo ""
    echo "${BOLD}Vetting: $skill_name${RESET}"
    echo "Path: $skill_dir"
    echo "──────────────────────────────────────────"

    local flags=0
    local flag_details=()

    for i in "${!FLAG_NAMES[@]}"; do
        local name="${FLAG_NAMES[$i]}"
        local pattern="${FLAG_PATTERNS[$i]}"
        local description="${FLAG_DESCRIPTIONS[$i]}"

        # Search all text files in the skill directory
        local matches
        matches="$(grep -rEl "$pattern" "$skill_dir" 2>/dev/null || true)"

        if [ -n "$matches" ]; then
            flags=$((flags + 1))
            flag_details+=("  ⚑ ${YELLOW}${name}${RESET}: $description")
            while IFS= read -r match_file; do
                local rel_file="${match_file#$skill_dir/}"
                flag_details+=("      File: $rel_file")
            done <<< "$matches"
        fi
    done

    # Verdict
    if [ "$flags" -eq 0 ]; then
        echo -e "  ${GREEN}✓ SAFE${RESET} — No flags raised"
        verdict_code=0
    elif [ "$flags" -le 2 ]; then
        echo -e "  ${YELLOW}⚠ CAUTION${RESET} — $flags flag(s) raised"
        verdict_code=1
    else
        echo -e "  ${RED}✗ DO NOT INSTALL${RESET} — $flags flag(s) raised"
        verdict_code=2
    fi

    if [ "${#flag_details[@]}" -gt 0 ]; then
        echo ""
        echo "Flags:"
        for line in "${flag_details[@]}"; do
            echo -e "$line"
        done
    fi

    echo ""
    echo "Manual review checklist:"
    echo "  [ ] Does the skill description match what the code does?"
    echo "  [ ] Are network calls documented in SKILL.md?"
    echo "  [ ] Is the author/source trusted?"
    echo "  [ ] Does STATE_SCHEMA.yaml scope match the skill?"
    echo ""

    return "$verdict_code"
}

# ── Entry point ───────────────────────────────────────────────────────────────

if [ "$#" -eq 0 ]; then
    usage
fi

if [ "$1" = "--all" ]; then
    if [ "$#" -lt 2 ]; then usage; fi
    root_dir="$2"
    if [ ! -d "$root_dir" ]; then
        echo "ERROR: $root_dir is not a directory"
        exit 3
    fi

    total=0
    safe=0
    caution=0
    danger=0

    echo "${BOLD}=== Batch Vetting: $root_dir ===${RESET}"

    for skill_dir in "$root_dir"/*/; do
        [ -d "$skill_dir" ] || continue
        [ -f "$skill_dir/SKILL.md" ] || continue
        total=$((total + 1))

        verdict_code=0
        vet_skill "$skill_dir" || verdict_code=$?

        case "$verdict_code" in
            0) safe=$((safe + 1)) ;;
            1) caution=$((caution + 1)) ;;
            2) danger=$((danger + 1)) ;;
        esac
    done

    echo "──────────────────────────────────────────"
    echo "${BOLD}Summary: $total skills scanned${RESET}"
    echo -e "  ${GREEN}Safe:         $safe${RESET}"
    echo -e "  ${YELLOW}Caution:      $caution${RESET}"
    echo -e "  ${RED}Do Not Install: $danger${RESET}"

    if [ "$danger" -gt 0 ]; then
        exit 2
    elif [ "$caution" -gt 0 ]; then
        exit 1
    else
        exit 0
    fi
else
    verdict_code=0
    vet_skill "$1" || verdict_code=$?
    exit "$verdict_code"
fi
