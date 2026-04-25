#!/usr/bin/env bash
# Launch the Django admin UI.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -f ".env" ]; then
    echo "❌ .env missing"
    exit 1
fi

if [ ! -d "venv" ]; then
    python3.12 -m venv venv
fi

source venv/bin/activate

if ! python -c "import django" 2>/dev/null; then
    pip install -q -r requirements.txt
fi

mkdir -p data

# One-time: create Django meta tables (auth, sessions) in a separate DB file.
if [ ! -f "data/django_admin.db" ]; then
    echo "🗄  First run — creating Django meta tables..."
    python admin_site/manage.py migrate --database=django_meta --noinput
fi

# Ensure superuser exists
ADMIN_USER="${ADMIN_USER:-admin}"
ADMIN_PASS="${ADMIN_PASS:-changeme123}"
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@example.com}"

python admin_site/manage.py shell --database=django_meta <<EOF 2>/dev/null
from django.contrib.auth import get_user_model
U = get_user_model()
if not U.objects.filter(username="$ADMIN_USER").exists():
    U.objects.create_superuser(username="$ADMIN_USER", email="$ADMIN_EMAIL", password="$ADMIN_PASS")
    print("✅ Superuser '$ADMIN_USER' created (password: $ADMIN_PASS)")
else:
    print("ℹ  Superuser '$ADMIN_USER' already exists")
EOF

PORT="${PORT:-8001}"
echo
echo "🛡  Django admin running at http://localhost:$PORT/admin/"
echo "   Login: $ADMIN_USER / $ADMIN_PASS (override via ADMIN_USER, ADMIN_PASS env vars)"
echo
exec python admin_site/manage.py runserver "0.0.0.0:$PORT"
