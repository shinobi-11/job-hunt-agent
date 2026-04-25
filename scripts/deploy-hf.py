#!/usr/bin/env python3
"""Deploy the project to a Hugging Face Space (Docker SDK).

Reads HF_USERNAME, HF_TOKEN, and Supabase/Sentry secrets from .env,
creates the Space if missing, sets repository secrets, then uploads
the source tree (skipping local-only files).

Run from project root:
    python scripts/deploy-hf.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Load .env
for line in (ROOT / ".env").read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

from huggingface_hub import HfApi, create_repo, upload_folder, add_space_secret  # noqa: E402

SPACE_NAME = "job-hunt-agent"
HF_USERNAME = os.environ.get("HF_USERNAME") or "job-hunt"
HF_TOKEN = os.environ.get("HF_TOKEN")
REPO_ID = f"{HF_USERNAME}/{SPACE_NAME}"


def main():
    if not HF_TOKEN:
        print("❌ HF_TOKEN not set in .env")
        sys.exit(1)

    print(f"==> Target Space: {REPO_ID}")
    api = HfApi(token=HF_TOKEN)

    print("==> Whoami check...")
    try:
        whoami = api.whoami()
        print(f"   logged in as: {whoami.get('name')}")
    except Exception as e:
        print(f"   ❌ token invalid: {e}")
        sys.exit(1)

    print("==> Ensuring Space exists...")
    try:
        create_repo(
            repo_id=REPO_ID,
            repo_type="space",
            space_sdk="docker",
            token=HF_TOKEN,
            private=False,
            exist_ok=True,
        )
        print("   ✅ Space ready")
    except Exception as e:
        print(f"   ❌ create_repo failed: {e}")
        sys.exit(1)

    print("==> Setting Space secrets...")
    secrets = {
        "DATABASE_URL": os.environ.get("DATABASE_URL"),
        "SUPABASE_URL": os.environ.get("SUPABASE_URL"),
        "SUPABASE_SERVICE_KEY": os.environ.get("SUPABASE_SERVICE_KEY"),
        "SESSION_SECRET": os.environ.get("SESSION_SECRET"),
        "SENTRY_DSN": os.environ.get("SENTRY_DSN"),
        "ADMIN_USER": "admin",
        "ADMIN_PASS": "JobHunt2026!",
        "ADMIN_EMAIL": "admin@job-hunt.local",
        "ADMIN_SECRET_KEY": os.environ.get("SESSION_SECRET", "fallback-secret"),
        "ENVIRONMENT": "production",
        # Firebase web config (public, safe to expose)
        "FIREBASE_API_KEY": os.environ.get("FIREBASE_API_KEY"),
        "FIREBASE_AUTH_DOMAIN": os.environ.get("FIREBASE_AUTH_DOMAIN"),
        "FIREBASE_PROJECT_ID": os.environ.get("FIREBASE_PROJECT_ID"),
        "FIREBASE_STORAGE_BUCKET": os.environ.get("FIREBASE_STORAGE_BUCKET"),
        "FIREBASE_MESSAGING_SENDER_ID": os.environ.get("FIREBASE_MESSAGING_SENDER_ID"),
        "FIREBASE_APP_ID": os.environ.get("FIREBASE_APP_ID"),
        "FIREBASE_MEASUREMENT_ID": os.environ.get("FIREBASE_MEASUREMENT_ID"),
    }

    # Firebase service account is sensitive — load from local JSON file
    sa_path = ROOT / "data" / "firebase-admin.json"
    if sa_path.exists():
        secrets["FIREBASE_SERVICE_ACCOUNT_JSON"] = sa_path.read_text()
        print(f"   Including FIREBASE_SERVICE_ACCOUNT_JSON ({sa_path.stat().st_size} bytes)")
    for name, value in secrets.items():
        if not value:
            print(f"   ⚠️  {name} not set, skipping")
            continue
        try:
            add_space_secret(repo_id=REPO_ID, key=name, value=value, token=HF_TOKEN)
            print(f"   ✅ {name}")
        except Exception as e:
            print(f"   ⚠️  {name} failed: {e}")

    print("==> Uploading source...")
    ignore = [
        "venv/*", ".venv/*", "__pycache__/*", "*.pyc",
        "data/*", "backups/*", "htmlcov/*", ".coverage",
        ".pytest_cache/*", ".mypy_cache/*", ".ruff_cache/*",
        ".env", "*.bak", ".git/*", ".github/*",
        "tests/*",
        "Dockerfile", "docker-compose.yml",  # local-only Docker
        "scripts/*",
        "CODE_GRAPH.md", "ISSUE_REGISTRY.md", ".shinobi_mem",
        "admin_site/staticfiles/*",  # collected at runtime
        "admin_site/manage.py",
    ]

    # HF expects a Dockerfile at the root + README.md with the YAML frontmatter
    # We use Dockerfile.hf and HF_README.md, so symlink them temporarily by uploading
    # with rename via path_in_repo:
    upload_folder(
        repo_id=REPO_ID,
        repo_type="space",
        folder_path=str(ROOT),
        token=HF_TOKEN,
        ignore_patterns=ignore,
        commit_message="Deploy: Liquid Glass + multi-LLM + multi-source search",
    )
    print("   ✅ Source uploaded")

    # Now overwrite README.md and Dockerfile with the HF variants (they're not in repo as those names)
    print("==> Setting HF-specific README and Dockerfile...")
    api.upload_file(
        path_or_fileobj=str(ROOT / "HF_README.md"),
        path_in_repo="README.md",
        repo_id=REPO_ID,
        repo_type="space",
        token=HF_TOKEN,
        commit_message="Set HF Space README with frontmatter",
    )
    api.upload_file(
        path_or_fileobj=str(ROOT / "Dockerfile.hf"),
        path_in_repo="Dockerfile",
        repo_id=REPO_ID,
        repo_type="space",
        token=HF_TOKEN,
        commit_message="Set HF Dockerfile (port 7860)",
    )
    print("   ✅ README + Dockerfile set")

    print()
    print(f"🚀 Live at: https://huggingface.co/spaces/{REPO_ID}")
    print(f"🌐 App URL: https://{HF_USERNAME.replace('_','-')}-{SPACE_NAME}.hf.space")
    print()
    print("Watch the build at:")
    print(f"  https://huggingface.co/spaces/{REPO_ID}?logs=container")


if __name__ == "__main__":
    main()
