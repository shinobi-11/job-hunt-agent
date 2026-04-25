"""Minimal Django settings for admin UI over the shared SQLite DB."""
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent

load_dotenv(PROJECT_ROOT / ".env")

import os as __os

SECRET_KEY = __os.environ.get(
    "ADMIN_SECRET_KEY",
    "dev-only-not-for-production-change-via-env-ADMIN_SECRET_KEY",
)

DEBUG = __os.environ.get("DJANGO_DEBUG", "false").lower() == "true"
ALLOWED_HOSTS = ["*"]
CSRF_TRUSTED_ORIGINS = [
    "https://job-hunt-job-hunt-agent.hf.space",
    "https://*.hf.space",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:8001",
    "http://127.0.0.1:8001",
]
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
FORCE_SCRIPT_NAME = "/django"
STATIC_URL = "/django/static/"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "admin_site.app",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "admin_site.urls"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {
        "context_processors": [
            "django.template.context_processors.request",
            "django.contrib.auth.context_processors.auth",
            "django.contrib.messages.context_processors.messages",
        ],
    },
}]

WSGI_APPLICATION = "admin_site.wsgi.application"

import os as _os
import re as _re

_DB_URL = _os.environ.get("DATABASE_URL", "")

if _DB_URL.startswith(("postgres://", "postgresql://")):
    # Parse Supabase Postgres URL
    _m = _re.match(
        r"postgres(?:ql)?://([^:]+):([^@]+)@([^:/]+):?(\d+)?/(\w+)",
        _DB_URL,
    )
    if _m:
        _user, _pw, _host, _port, _name = _m.groups()
        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": _name,
                "USER": _user,
                "PASSWORD": _pw,
                "HOST": _host,
                "PORT": _port or "5432",
                "OPTIONS": {"sslmode": "require"},
            },
            "django_meta": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": _name,
                "USER": _user,
                "PASSWORD": _pw,
                "HOST": _host,
                "PORT": _port or "5432",
                "OPTIONS": {"sslmode": "require"},
            },
        }
    else:
        DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": PROJECT_ROOT / "data" / "jobs.db"}}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": PROJECT_ROOT / "data" / "jobs.db",
        },
        "django_meta": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": PROJECT_ROOT / "data" / "django_admin.db",
        },
    }

DATABASE_ROUTERS = ["admin_site.router.DjangoMetaRouter"]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_ROOT = PROJECT_ROOT / "admin_site" / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "/django/admin/login/"
