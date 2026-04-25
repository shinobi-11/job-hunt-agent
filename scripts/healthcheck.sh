#!/usr/bin/env bash
# Verify the agent's operational dependencies are healthy.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

COLOR_GREEN='\033[0;32m'
COLOR_RED='\033[0;31m'
COLOR_YELLOW='\033[1;33m'
COLOR_RESET='\033[0m'

ok()   { printf "${COLOR_GREEN}  ✅ %s${COLOR_RESET}\n" "$*"; }
fail() { printf "${COLOR_RED}  ❌ %s${COLOR_RESET}\n" "$*"; }
warn() { printf "${COLOR_YELLOW}  ⚠️  %s${COLOR_RESET}\n" "$*"; }

EXIT_CODE=0

echo "Job Hunt Agent — Health Check"
echo

echo "1. Configuration"
if [ -f ".env" ]; then
    ok ".env file exists"
else
    fail ".env file missing"
    EXIT_CODE=1
fi

if grep -q "^GEMINI_API_KEY=.\{30,\}" .env 2>/dev/null; then
    ok "GEMINI_API_KEY configured"
else
    fail "GEMINI_API_KEY missing or too short"
    EXIT_CODE=1
fi
echo

echo "2. Storage"
if [ -d "data" ]; then
    ok "data/ directory exists"
else
    warn "data/ directory missing (will be created on first run)"
fi

if [ -f "data/jobs.db" ]; then
    ok "SQLite database present"
    if command -v sqlite3 >/dev/null 2>&1; then
        JOBS_COUNT=$(sqlite3 data/jobs.db "SELECT COUNT(*) FROM jobs" 2>/dev/null || echo "0")
        APPS_COUNT=$(sqlite3 data/jobs.db "SELECT COUNT(*) FROM applications" 2>/dev/null || echo "0")
        ok "Database integrity: $JOBS_COUNT jobs, $APPS_COUNT applications"
    fi
else
    warn "No database yet (first run will create one)"
fi
echo

echo "3. Dependencies"
if [ -d "venv" ]; then
    ok "Virtual environment exists"
    if venv/bin/python -c "import google.generativeai, rich, pydantic" 2>/dev/null; then
        ok "Core dependencies importable"
    else
        fail "Some dependencies missing — run: pip install -r requirements.txt"
        EXIT_CODE=1
    fi
else
    warn "venv/ missing — run: ./scripts/start.sh"
fi
echo

echo "4. Gemini API"
if [ -f "venv/bin/python" ] && [ -f ".env" ]; then
    if venv/bin/python -c "
import warnings
warnings.filterwarnings('ignore')
from dotenv import load_dotenv
load_dotenv()
import os
import google.generativeai as genai
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
model = genai.GenerativeModel('gemini-2.5-flash')
model.generate_content('ping', generation_config={'max_output_tokens': 5})
" 2>/dev/null; then
        ok "Gemini API reachable"
    else
        warn "Gemini API call failed (quota/network) — agent will use fallback scores"
    fi
fi
echo

echo "5. Agent Process"
if pgrep -f "python agent.py" >/dev/null 2>&1; then
    PID=$(pgrep -f "python agent.py" | head -1)
    ok "Agent running (PID $PID)"
else
    warn "Agent not currently running"
fi
echo

if [ $EXIT_CODE -eq 0 ]; then
    printf "${COLOR_GREEN}✅ System healthy${COLOR_RESET}\n"
else
    printf "${COLOR_RED}❌ Issues found — see above${COLOR_RESET}\n"
fi

exit $EXIT_CODE
