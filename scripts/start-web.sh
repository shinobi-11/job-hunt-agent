#!/usr/bin/env bash
# Launch the FastAPI web frontend.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -f ".env" ]; then
    echo "❌ .env missing — run: cp .env.example .env and set GEMINI_API_KEY"
    exit 1
fi

if [ ! -d "venv" ]; then
    echo "⚠️  venv missing — creating"
    python3.12 -m venv venv
fi

source venv/bin/activate

if ! python -c "import fastapi" 2>/dev/null; then
    pip install -q -r requirements.txt
fi

PORT="${PORT:-8000}"
echo "🚀 Web frontend running at http://localhost:$PORT"
exec uvicorn web.app:app --host 0.0.0.0 --port "$PORT" --reload
