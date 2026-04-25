#!/usr/bin/env bash
# Gracefully stop a running Job Hunt Agent container or process.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

COLOR_CYAN='\033[0;36m'
COLOR_GREEN='\033[0;32m'
COLOR_YELLOW='\033[1;33m'
COLOR_RESET='\033[0m'

log_info()    { printf "${COLOR_CYAN}ℹ  %s${COLOR_RESET}\n" "$*"; }
log_success() { printf "${COLOR_GREEN}✅ %s${COLOR_RESET}\n" "$*"; }
log_warn()    { printf "${COLOR_YELLOW}⚠️  %s${COLOR_RESET}\n" "$*"; }

if command -v docker >/dev/null 2>&1 && docker ps --format '{{.Names}}' | grep -q '^job-hunt-agent$'; then
    log_info "Stopping Docker container..."
    docker compose down
    log_success "Docker container stopped"
fi

if pgrep -f "python agent.py" >/dev/null; then
    log_info "Sending SIGTERM to running agent (graceful shutdown)..."
    pkill -TERM -f "python agent.py" || true
    sleep 2
    if pgrep -f "python agent.py" >/dev/null; then
        log_warn "Process still running — sending SIGKILL"
        pkill -KILL -f "python agent.py" || true
    fi
    log_success "Agent process stopped"
else
    log_info "No running agent process found"
fi
