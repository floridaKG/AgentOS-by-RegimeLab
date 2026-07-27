#!/usr/bin/env bash
# Source this to load role models as env vars.
# Usage: eval $(~/.config/agent-workflows/load-roles.sh)

ROLES_FILE="$HOME/.config/agent-workflows/roles.toml"

_role_model() {
    local role="$1"
    awk -F'"' "/^\[${role}\]/{found=1} found && /^model/{print \$2; exit}" "$ROLES_FILE"
}

_role_provider() {
    local role="$1"
    awk -F'"' "/^\[${role}\]/{found=1} found && /^provider/{print \$2; exit}" "$ROLES_FILE"
}

echo "export ROLE_EXPLORER=$(_role_model explorer)"
echo "export ROLE_ARCHITECT=$(_role_model architect)"
echo "export ROLE_EXECUTOR=$(_role_model executor)"
echo "export ROLE_REVIEWER=$(_role_model reviewer)"
echo "export ROLE_CODE_REVIEWER=$(_role_model code_reviewer)"
echo "export ROLE_ESCALATION=$(_role_model escalation)"
echo "export PROVIDER_ESCALATION=$(_role_provider escalation)"
