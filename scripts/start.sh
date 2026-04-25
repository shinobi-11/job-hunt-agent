#!/usr/bin/env bash
# Launch Job Hunt Agent locally — validates environment and picks the right runtime.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

COLOR_CYAN='\033[0;36m'
COLOR_GREEN='\033[0;32m'
COLOR_RED='\033[0;31m'
COLOR_YELLOW='\033[1;33m'
COLOR_RESET='\033[0m'

log_info()    { printf "${COLOR_CYAN}ℹ  %s${COLOR_RESET}\n" "$*"; }
log_success() { printf "${COLOR_GREEN}✅ %s${COLOR_RESET}\n" "$*"; }
log_warn()    { printf "${COLOR_YELLOW}⚠️  %s${COLOR_RESET}\n" "$*"; }
log_error()   { printf "${COLOR_RED}❌ %s${COLOR_RESET}\n" "$*"; }

log_info "Job Hunt Agent — Local Launcher"
echo

if [ ! -f ".env" ]; then
    log_error ".env file not found"
    log_info "Run: cp .env.example .env && edit .env to add GEMINI_API_KEY"
    exit 1
fi

if ! grep -q "^GEMINI_API_KEY=.\{30,\}" .env; then
    log_error "GEMINI_API_KEY not set (or too short) in .env"
    log_info "Get a key at: https://aistudio.google.com/app/apikey"
    exit 1
fi
log_success ".env validated"

mkdir -p data
log_success "data/ directory ready"

MODE="${1:-venv}"

case "$MODE" in
    venv)
        if [ ! -d "venv" ]; then
            log_warn "venv/ not found — creating one"
            if command -v python3.12 >/dev/null 2>&1; then
                python3.12 -m venv venv
            elif command -v python3.11 >/dev/null 2>&1; then
                python3.11 -m venv venv
            else
                python3 -m venv venv
            fi
            log_success "venv created"
        fi

        source venv/bin/activate

        if ! python -c "import google.generativeai" 2>/dev/null; then
            log_warn "Dependencies missing — installing"
            pip install --quiet -r requirements.txt
            log_success "Dependencies installed"
        fi

        log_info "Launching agent in venv..."
        echo
        exec python agent.py "${@:2}"
        ;;

    docker)
        if ! command -v docker >/dev/null 2>&1; then
            log_error "Docker not found — install Docker Desktop or use: ./scripts/start.sh venv"
            exit 1
        fi

        log_info "Building Docker image..."
        docker compose build
        log_success "Image built"

        log_info "Launching in Docker..."
        docker compose up
        ;;

    *)
        log_error "Unknown mode: $MODE"
        log_info "Usage: ./scripts/start.sh [venv|docker]  (default: venv)"
        exit 1
        ;;
esac
