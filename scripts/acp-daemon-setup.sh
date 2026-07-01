#!/usr/bin/env bash
# acp-daemon-setup.sh — Install ACP daemon auto-start
#
# Tries systemd user service first, falls back to crontab @reboot.
# Usage:
#   scripts/acp-daemon-setup.sh            # Install (default)
#   scripts/acp-daemon-setup.sh --remove   # Remove auto-start
#   scripts/acp-daemon-setup.sh --status   # Check current setup

set -euo pipefail

AGENT_OS_HOME="${AGENT_OS_HOME:-}"
if [[ -z "$AGENT_OS_HOME" ]]; then
    SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
    if [[ -f "$SCRIPT_DIR/../AGENTS.md" ]]; then
        AGENT_OS_HOME="$(cd "$SCRIPT_DIR/.." && pwd)"
    else
        AGENT_OS_HOME="$HOME/agent-os"
    fi
fi

DAEMON_BIN="$AGENT_OS_HOME/bin/acp-daemon"
SERVICE_NAME="agent-os-acp"
SERVICE_FILE="${HOME}/.config/systemd/user/${SERVICE_NAME}.service"
CRON_MARKER="# agent-os-acp-daemon"

info()  { printf "\033[36m[INFO]\033[0m  %s\n" "$*"; }
ok()    { printf "\033[32m[OK]\033[0m    %s\n" "$*"; }
warn()  { printf "\033[33m[WARN]\033[0m  %s\n" "$*" >&2; }
err()   { printf "\033[31m[ERROR]\033[0m %s\n" "$*" >&2; }
die()   { err "$*"; exit 1; }

check_daemon()   { [[ -x "$DAEMON_BIN" ]] || die "Daemon not found: $DAEMON_BIN"; }
has_systemd()    { command -v systemctl &>/dev/null && systemctl --user list-units &>/dev/null 2>&1; }

do_install() {
    check_daemon
    info "Installing ACP daemon auto-start for $AGENT_OS_HOME"
    if has_systemd; then
        info "Installing systemd user service"
        mkdir -p "$(dirname "$SERVICE_FILE")"
        cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Agent OS ACP Daemon
After=network.target

[Service]
ExecStart=${DAEMON_BIN}
Restart=on-failure
RestartSec=10
Environment=AGENT_OS_HOME=${AGENT_OS_HOME}

[Install]
WantedBy=default.target
EOF
        systemctl --user daemon-reload
        systemctl --user enable --now "$SERVICE_NAME"
        ok "systemd service installed and started: $SERVICE_NAME"
    else
        warn "systemd unavailable — falling back to crontab"
        if crontab -l 2>/dev/null | grep -qF "$CRON_MARKER"; then
            ok "Crontab entry already exists"
        else
            (crontab -l 2>/dev/null || true; echo "@reboot sleep 10 && $DAEMON_BIN >/dev/null 2>&1 & $CRON_MARKER") | crontab -
            ok "Crontab entry added (@reboot)"
        fi
    fi
}

do_remove() {
    info "Removing ACP daemon auto-start"
    if has_systemd && [[ -f "$SERVICE_FILE" ]]; then
        systemctl --user stop "$SERVICE_NAME" 2>/dev/null || true
        systemctl --user disable "$SERVICE_NAME" 2>/dev/null || true
        rm -f "$SERVICE_FILE"
        systemctl --user daemon-reload 2>/dev/null || true
        ok "systemd service removed: $SERVICE_NAME"
    fi
    if crontab -l 2>/dev/null | grep -qF "$CRON_MARKER"; then
        crontab -l 2>/dev/null | grep -vF "$CRON_MARKER" | crontab -
        ok "Crontab entry removed"
    fi
    if ! has_systemd && [[ ! -f "$SERVICE_FILE" ]]; then
        ok "No auto-start found — nothing to remove"
    fi
}

do_status() {
    info "ACP daemon auto-start status for $AGENT_OS_HOME"
    if has_systemd && [[ -f "$SERVICE_FILE" ]]; then
        echo "  Method:    systemd user service"
        echo "  Unit:      $SERVICE_NAME"
        if systemctl --user is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
            ok "Service is active"
        else
            warn "Service is inactive"
        fi
        echo "  Enabled:   $(systemctl --user is-enabled "$SERVICE_NAME" 2>/dev/null || echo 'unknown')"
    elif crontab -l 2>/dev/null | grep -qF "$CRON_MARKER"; then
        echo "  Method:    crontab (@reboot)"
        ok "Crontab entry present"
    else
        warn "No auto-start configured"
        echo "  To install, run: $0"
        exit 1
    fi
    [[ -x "$DAEMON_BIN" ]] && echo "  Daemon:    $DAEMON_BIN" || warn "Daemon binary missing: $DAEMON_BIN"
    ok "Status check complete"
}

case "${1:-}" in
    --install|"")     do_install ;;
    --remove)         do_remove ;;
    --status)         do_status ;;
    --help|-h)
        sed -n '3,10p' "$0"
        echo "  --install   Install auto-start (default)"
        echo "  --remove    Remove auto-start"
        echo "  --status    Check current setup"
        echo "  --help      Show this help"
        ;;
    *)                echo "Usage: $0 [--install|--remove|--status|--help]"; exit 2 ;;
esac
