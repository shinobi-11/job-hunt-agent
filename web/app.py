"""FastAPI web frontend for Job Hunt Agent."""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from config import get_config
from database import JobDatabase
from llm_providers import PROVIDERS
from matcher import JobMatcher
from models import Application, ApplicationStatus, Job, MatchScore, UserProfile
from resume_parser import ResumeParser
from searcher import JobSearcher
from web.auth import (
    LoginPayload,
    SignupPayload,
    authenticate,
    clear_session,
    create_user,
    find_user_by_email,
    get_current_user,
    init_users_table,
    issue_session,
    require_user,
)

ROOT = Path(__file__).parent
STATIC_DIR = ROOT / "static"
TEMPLATES_DIR = ROOT / "templates"

STATIC_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

# Sentry instrumentation (optional — only init if DSN provided)
_SENTRY_DSN = os.environ.get("SENTRY_DSN")
if _SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        sentry_sdk.init(
            dsn=_SENTRY_DSN,
            integrations=[FastApiIntegration()],
            traces_sample_rate=0.1,
            environment=os.environ.get("ENVIRONMENT", "production"),
            release="job-hunt-agent@0.2.0",
        )
    except Exception as e:
        print(f"Sentry init failed (non-fatal): {e}")

app = FastAPI(title="Job Hunt Agent", version="0.2.0")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Django collected static files (mounted at startup if collectstatic ran)
DJANGO_STATIC = ROOT.parent / "admin_site" / "staticfiles"
if DJANGO_STATIC.exists():
    app.mount("/django/static", StaticFiles(directory=str(DJANGO_STATIC)), name="django-static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@app.on_event("startup")
def _on_startup() -> None:
    init_users_table()


# ─── Mount Django admin at /django ──────────────────────────────────
def _mount_django_admin() -> None:
    """Mount Django's admin app under /django so the same Space serves both."""
    try:
        import os as _os
        import sys as _sys
        from pathlib import Path as _Path

        _sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
        _os.environ.setdefault("DJANGO_SETTINGS_MODULE", "admin_site.settings")

        import django  # noqa: E402
        django.setup()

        # Auto-migrate Django meta tables (auth, sessions) on startup
        try:
            from django.core.management import call_command  # noqa: E402
            # On HF (Postgres), default and django_meta point at same DB; migrate both
            call_command("migrate", "--database=django_meta", "--noinput", verbosity=0)
            if _os.environ.get("DATABASE_URL", "").startswith(("postgres://", "postgresql://")):
                # On Postgres, default DB also needs the auth/sessions tables
                # because we route them via DjangoMetaRouter to django_meta which == default here.
                # Migration above handled it.
                pass
        except Exception as e:
            print(f"Django auto-migrate failed (non-fatal): {e}")

        # Collect static files so /django/static/* serves admin CSS/JS
        try:
            from django.core.management import call_command  # noqa: E402,F811
            call_command("collectstatic", "--noinput", verbosity=0)
        except Exception as e:
            print(f"Django collectstatic failed (non-fatal): {e}")

        # Re-mount static if collectstatic just produced the directory
        try:
            _DS = ROOT.parent / "admin_site" / "staticfiles"
            if _DS.exists() and not any(r.path == "/django/static" for r in app.routes):
                app.mount("/django/static", StaticFiles(directory=str(_DS)), name="django-static")
        except Exception as e:
            print(f"Django static re-mount failed (non-fatal): {e}")

        # Auto-create superuser if env vars provided
        try:
            from django.contrib.auth import get_user_model  # noqa: E402
            U = get_user_model()
            admin_user = _os.environ.get("ADMIN_USER", "admin")
            admin_pw = _os.environ.get("ADMIN_PASS", "changeme123")
            admin_email = _os.environ.get("ADMIN_EMAIL", "admin@example.com")
            if not U.objects.using("django_meta").filter(username=admin_user).exists():
                u = U(username=admin_user, email=admin_email, is_staff=True, is_superuser=True)
                u.set_password(admin_pw)
                u.save(using="django_meta")
                print(f"   Django superuser '{admin_user}' created")
        except Exception as e:
            print(f"Django superuser bootstrap failed (non-fatal): {e}")

        from django.core.wsgi import get_wsgi_application  # noqa: E402
        from starlette.middleware.wsgi import WSGIMiddleware  # noqa: E402

        django_app = get_wsgi_application()
        app.mount("/django", WSGIMiddleware(django_app))
        print("   ✅ Django admin mounted at /django")
    except Exception as e:
        print(f"Django mount failed (non-fatal): {e}")


_mount_django_admin()


# ─── Firebase Admin (optional — verifies Google/Phone ID tokens) ──────
_FIREBASE_INITIALIZED = False


def _init_firebase() -> None:
    """Initialize firebase_admin SDK from service-account JSON in env or local file."""
    global _FIREBASE_INITIALIZED
    if _FIREBASE_INITIALIZED:
        return
    try:
        import firebase_admin
        from firebase_admin import credentials

        sa_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
        if sa_json:
            sa_dict = json.loads(sa_json)
            cred = credentials.Certificate(sa_dict)
        else:
            local_path = ROOT.parent / "data" / "firebase-admin.json"
            if local_path.exists():
                cred = credentials.Certificate(str(local_path))
            else:
                print("Firebase: no service account configured — skipping init")
                return

        firebase_admin.initialize_app(cred)
        _FIREBASE_INITIALIZED = True
        print("   ✅ Firebase Admin initialized")
    except Exception as e:
        print(f"Firebase Admin init failed (non-fatal): {e}")


_init_firebase()


class SearchState:
    """Thread-shared runtime state for the search loop."""

    def __init__(self) -> None:
        self.running = False
        self.paused = False
        self.cycle = 0
        self.started_at: datetime | None = None
        self.events: list[dict] = []
        self.thread: threading.Thread | None = None
        self._last_seen = 0
        self.last_diagnostics: dict | None = None  # set after each cycle's _search_all

    def push(self, event: dict) -> None:
        event["ts"] = datetime.now().isoformat()
        self.events.append(event)
        if len(self.events) > 500:
            self.events = self.events[-500:]

    def unseen(self) -> list[dict]:
        new = self.events[self._last_seen:]
        self._last_seen = len(self.events)
        return new


STATE = SearchState()

_CFG = None
_DB_INSTANCE: JobDatabase | None = None
_DB_LOCK = threading.Lock()


def _cfg():
    global _CFG
    if _CFG is None:
        _CFG = get_config()
    return _CFG


def _db() -> JobDatabase:
    global _DB_INSTANCE
    if _DB_INSTANCE is None:
        with _DB_LOCK:
            if _DB_INSTANCE is None:
                _DB_INSTANCE = JobDatabase(db_path=_cfg().database_path)
    return _DB_INSTANCE


@app.get("/")
async def home(request: Request, user: dict | None = Depends(get_current_user)):
    if user:
        return RedirectResponse("/app", status_code=303)
    return templates.TemplateResponse(request, "home.html", {})


@app.get("/login")
async def login_page(request: Request, user: dict | None = Depends(get_current_user)):
    if user:
        return RedirectResponse("/app", status_code=303)
    return templates.TemplateResponse(request, "login.html", {})


@app.get("/signup")
async def signup_page(request: Request, user: dict | None = Depends(get_current_user)):
    if user:
        return RedirectResponse("/app", status_code=303)
    return templates.TemplateResponse(request, "signup.html", {})


@app.get("/app")
async def dashboard(request: Request, user: dict | None = Depends(get_current_user)):
    if not user:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request, "index.html", {"user": user})


@app.post("/api/auth/signup")
async def api_signup(payload: SignupPayload, response: Response):
    try:
        user = create_user(payload.email, payload.password, payload.name or "")
    except ValueError as e:
        raise HTTPException(400, str(e))
    issue_session(response, user["id"])
    return {"ok": True, "user": {"id": user["id"], "email": user["email"], "name": user["name"]}}


@app.post("/api/auth/login")
async def api_login(payload: LoginPayload, response: Response):
    user = authenticate(payload.email, payload.password)
    if not user:
        raise HTTPException(401, "Invalid email or password")
    issue_session(response, user["id"])
    return {"ok": True, "user": {"id": user["id"], "email": user["email"], "name": user["name"]}}


@app.post("/api/auth/logout")
async def api_logout(response: Response):
    clear_session(response)
    return {"ok": True}


class ContactPayload(BaseModel):
    name: str
    email: str
    phone: str | None = None
    message: str


@app.post("/api/contact")
async def submit_contact(payload: ContactPayload):
    """Public endpoint — saves contact-form submissions to the queries table."""
    import re
    import uuid

    name = (payload.name or "").strip()
    email = (payload.email or "").strip().lower()
    message = (payload.message or "").strip()

    if not name or len(name) > 200:
        raise HTTPException(400, "Name is required (max 200 chars)")
    if not re.match(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$", email):
        raise HTTPException(400, "Valid email is required")
    if not message or len(message) > 5000:
        raise HTTPException(400, "Message is required (max 5000 chars)")

    qid = f"q_{uuid.uuid4().hex[:16]}"
    db = _db()

    try:
        with db._connect() as conn:
            cur = conn.cursor()
            ph = "%s" if db.is_postgres else "?"
            cur.execute(
                f"INSERT INTO queries (id, name, email, phone, message, status) "
                f"VALUES ({ph},{ph},{ph},{ph},{ph},{ph})",
                (qid, name[:200], email[:200], (payload.phone or "")[:50], message[:5000], "new"),
            )
        return {"ok": True, "id": qid}
    except Exception as e:
        raise HTTPException(500, f"Could not save query: {str(e)[:120]}")


@app.get("/api/auth/me")
async def api_me(user: dict | None = Depends(get_current_user)):
    if not user:
        return {"user": None}
    return {"user": {"id": user["id"], "email": user["email"], "name": user.get("name")}}


@app.get("/api/auth/firebase-config")
async def firebase_config():
    """Public Firebase web SDK config."""
    return {
        "apiKey": os.environ.get("FIREBASE_API_KEY", ""),
        "authDomain": os.environ.get("FIREBASE_AUTH_DOMAIN", ""),
        "projectId": os.environ.get("FIREBASE_PROJECT_ID", ""),
        "storageBucket": os.environ.get("FIREBASE_STORAGE_BUCKET", ""),
        "messagingSenderId": os.environ.get("FIREBASE_MESSAGING_SENDER_ID", ""),
        "appId": os.environ.get("FIREBASE_APP_ID", ""),
        "measurementId": os.environ.get("FIREBASE_MEASUREMENT_ID", ""),
    }


class FirebaseLoginPayload(BaseModel):
    id_token: str


@app.post("/api/auth/firebase")
async def firebase_login(payload: FirebaseLoginPayload, response: Response):
    """Verify a Firebase ID token (Google sign-in or phone OTP) and create
    or link a local user, then issue a session cookie."""
    if not _FIREBASE_INITIALIZED:
        raise HTTPException(503, "Firebase auth not configured on this server")

    try:
        from firebase_admin import auth as fb_auth
        decoded = fb_auth.verify_id_token(payload.id_token)
    except Exception as e:
        raise HTTPException(401, f"Invalid Firebase token: {e}")

    email = decoded.get("email") or f"{decoded['uid']}@firebase.local"
    name = decoded.get("name", "") or decoded.get("phone_number", "")
    provider = decoded.get("firebase", {}).get("sign_in_provider", "firebase")

    existing = find_user_by_email(email)
    if existing:
        user_id = existing["id"]
    else:
        import uuid
        import bcrypt
        from web.auth import _connect, _placeholder
        user_id = f"u_{uuid.uuid4().hex[:16]}"
        # Random hash so this user can't log in via password flow until they reset
        pw_hash = bcrypt.hashpw(uuid.uuid4().hex.encode(), bcrypt.gensalt(12)).decode("utf-8")
        ph = _placeholder()
        conn = _connect()
        try:
            cur = conn.cursor()
            cur.execute(
                f"INSERT INTO users (id, email, password_hash, name) VALUES ({ph},{ph},{ph},{ph})",
                (user_id, email.lower(), pw_hash, name),
            )
            conn.commit()
        finally:
            conn.close()

    issue_session(response, user_id)
    return {"ok": True, "user": {"id": user_id, "email": email, "name": name, "provider": provider}}


@app.get("/api/profile")
async def get_profile(user: dict = Depends(require_user)):
    profile = _db().get_profile(user_id=user["id"])
    if not profile:
        return JSONResponse({"profile": None})
    return JSONResponse({"profile": _mask_key(profile.model_dump(mode="json"))})


class ProfilePayload(BaseModel):
    name: str
    email: str
    current_role: str | None = None
    years_experience: int = 0
    desired_roles: list[str] = []
    skills: list[str] = []
    preferred_locations: list[str] = []
    remote_preference: str = "any"
    current_salary: float | None = None
    hike_percent_min: float = 20.0
    hike_percent_max: float = 40.0
    salary_currency: str = "USD"
    willing_to_relocate: bool = False
    auto_apply_enabled: bool = True
    strict_salary_filter: bool = True
    llm_provider: str = "gemini"
    llm_api_key: str | None = None
    llm_model: str | None = None


class ListModelsPayload(BaseModel):
    provider: str
    api_key: str | None = None  # if not given, use the saved key


@app.post("/api/llm/models")
async def discover_models(payload: ListModelsPayload, user: dict = Depends(require_user)):
    """Given a provider + API key, list models the key can access."""
    from llm_providers import list_models_async, PROVIDERS

    if payload.provider not in PROVIDERS:
        raise HTTPException(400, f"Unknown provider: {payload.provider}")

    key = payload.api_key
    if not key:
        existing = _db().get_profile(user_id=user["id"])
        if existing and existing.llm_provider == payload.provider:
            key = existing.llm_api_key
    if not key:
        raise HTTPException(400, "Provide an API key (or save one to your profile first)")

    try:
        models = await list_models_async(payload.provider, key)
        return {"models": models, "default": PROVIDERS[payload.provider]["default_model"]}
    except Exception as e:
        msg = str(e)
        if "expired" in msg.lower() or "invalid" in msg.lower() or "API_KEY_INVALID" in msg:
            raise HTTPException(401, "API key expired or invalid. Please paste a fresh key.")
        if "quota" in msg.lower() or "429" in msg:
            raise HTTPException(429, "API quota exceeded for this key.")
        raise HTTPException(400, f"Could not list models: {msg[:200]}")


@app.get("/api/providers")
async def list_providers():
    """LLM providers available for user selection."""
    return {
        "providers": [
            {"id": pid, **meta}
            for pid, meta in PROVIDERS.items()
        ]
    }


@app.post("/api/profile")
async def save_profile(payload: ProfilePayload, user: dict = Depends(require_user)):
    # Preserve existing key if client sends a masked/empty value
    existing = _db().get_profile(user_id=user["id"])
    data = payload.model_dump()
    if existing and (not data.get("llm_api_key") or data["llm_api_key"] in ("●●●●●●●●", "")):
        data["llm_api_key"] = existing.llm_api_key

    profile = UserProfile(**data)
    profile.compute_expected_salary()
    _db().save_profile(profile, user_id=user["id"])
    return {"ok": True, "profile": _mask_key(profile.model_dump(mode="json"))}


def _mask_key(payload: dict) -> dict:
    """Never return the full API key to the client after it's saved."""
    if payload.get("llm_api_key"):
        k = payload["llm_api_key"]
        payload["llm_api_key"] = k[:6] + "..." + k[-4:] if len(k) > 12 else "●●●●●●●●"
    return payload


def _user_resume_path(user_id: str, suffix: str = ".pdf") -> Path:
    """Per-user resume file path. Suffix preserved from upload."""
    base = Path(_cfg().resume_path).parent
    return base / "resumes" / f"{user_id}{suffix}"


def _find_user_resume(user_id: str) -> Path | None:
    base = Path(_cfg().resume_path).parent / "resumes"
    if not base.exists():
        return None
    for sfx in (".pdf", ".docx", ".doc"):
        p = base / f"{user_id}{sfx}"
        if p.exists():
            return p
    return None


@app.post("/api/resume")
async def upload_resume(file: UploadFile = File(...), user: dict = Depends(require_user)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".pdf", ".docx", ".doc"}:
        raise HTTPException(400, "Only PDF or DOCX supported")

    # Remove any existing resume for this user (different format)
    old = _find_user_resume(user["id"])
    if old:
        old.unlink(missing_ok=True)

    dest = _user_resume_path(user["id"], suffix)
    dest.parent.mkdir(parents=True, exist_ok=True)
    contents = await file.read()
    if not contents:
        raise HTTPException(400, "Empty file received")
    dest.write_bytes(contents)

    try:
        text = ResumeParser.parse_resume(str(dest))
    except Exception as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, f"Parse failed: {e}")

    if not text or len(text.strip()) < 50:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, "Resume parsed but text content is too short — possibly an image-only PDF. Try a text-based PDF/DOCX.")

    # Try AI-powered profile autofill if user has an LLM key configured
    suggested = None
    autofill_status = "no_api_key"
    existing = _db().get_profile(user_id=user["id"])

    # Use the user's saved key. Don't fall back to env — that key is shared and
    # may be expired/quota-exhausted, masking the real "no key" state.
    api_key = existing.llm_api_key if existing else None
    provider = (existing.llm_provider if existing else None) or "gemini"
    model = existing.llm_model if existing else None

    if api_key and len(api_key) >= 20:
        try:
            import asyncio
            from profile_builder import ProfileBuilder

            def _build():
                builder = ProfileBuilder(api_key=api_key, provider=provider, model_name=model)
                return builder.build_from_resume(text)

            built = await asyncio.wait_for(asyncio.to_thread(_build), timeout=30.0)
            if built:
                suggested = {
                    "name": built.name,
                    "email": built.email if "@" in built.email and "firebase.local" not in built.email else (existing.email if existing else None),
                    "current_role": built.current_role,
                    "years_experience": built.years_experience,
                    "desired_roles": built.desired_roles,
                    "skills": built.skills,
                    "industries": built.industries,
                    "preferred_locations": built.preferred_locations,
                    "remote_preference": built.remote_preference,
                    "company_size_preference": built.company_size_preference,
                }
                autofill_status = "ok"
            else:
                autofill_status = "ai_returned_nothing"
        except asyncio.TimeoutError:
            autofill_status = "ai_timeout"
            print("AI autofill timed out after 30s")
        except Exception as e:
            autofill_status = f"ai_error: {str(e)[:100]}"
            print(f"AI autofill failed (non-fatal): {e}")

    return {
        "ok": True,
        "filename": file.filename,
        "size_bytes": len(contents),
        "chars": len(text),
        "suggested_profile": suggested,
        "autofill_status": autofill_status,
    }


@app.get("/api/resume")
async def get_resume_info(user: dict = Depends(require_user)):
    p = _find_user_resume(user["id"])
    if not p:
        return {"exists": False}
    return {
        "exists": True,
        "filename": p.name,
        "size_bytes": p.stat().st_size,
        "modified": datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
    }


@app.post("/api/resume/autofill")
async def resume_autofill(user: dict = Depends(require_user)):
    """Re-run AI autofill on the already-uploaded resume using the saved API key."""
    resume_path = _find_user_resume(user["id"])
    if not resume_path:
        raise HTTPException(400, "No resume uploaded yet — upload one first")

    profile = _db().get_profile(user_id=user["id"])
    api_key = profile.llm_api_key if profile else None
    if not api_key or len(api_key) < 20:
        raise HTTPException(400, "No API key saved — save your AI Provider settings first")

    try:
        text = ResumeParser.parse_resume(str(resume_path))
    except Exception as e:
        raise HTTPException(400, f"Resume parse failed: {e}")

    if not text or len(text.strip()) < 50:
        raise HTTPException(400, "Resume text too short — try re-uploading as a text-based PDF/DOCX")

    provider = (profile.llm_provider if profile else None) or "gemini"
    model = profile.llm_model if profile else None

    try:
        from profile_builder import ProfileBuilder
        built = await asyncio.wait_for(
            asyncio.to_thread(
                lambda: ProfileBuilder(api_key=api_key, provider=provider, model_name=model)
                        .build_from_resume(text)
            ),
            timeout=30.0,
        )
    except asyncio.TimeoutError:
        raise HTTPException(504, "AI autofill timed out — try again")
    except Exception as e:
        raise HTTPException(500, f"AI autofill failed: {str(e)[:120]}")

    if not built:
        raise HTTPException(422, "AI could not parse profile from resume — check the key is valid and the resume has enough text")

    suggested = {
        "name": built.name,
        "email": built.email if "@" in built.email and "firebase.local" not in built.email
                 else (profile.email if profile else None),
        "current_role": built.current_role,
        "years_experience": built.years_experience,
        "desired_roles": built.desired_roles,
        "skills": built.skills,
        "industries": built.industries,
        "preferred_locations": built.preferred_locations,
        "remote_preference": built.remote_preference,
        "company_size_preference": built.company_size_preference,
    }
    return {"ok": True, "suggested_profile": suggested}


@app.delete("/api/resume")
async def delete_resume(user: dict = Depends(require_user)):
    p = _find_user_resume(user["id"])
    if not p:
        raise HTTPException(404, "No resume to delete")
    p.unlink()
    return {"ok": True}


@app.get("/api/diagnostics")
async def get_diagnostics(user: dict = Depends(require_user)):
    """Last cycle's source fan-out + funnel counts."""
    return {"diagnostics": STATE.last_diagnostics}


@app.get("/api/status")
async def get_status(user: dict | None = Depends(get_current_user)):
    db = _db()
    if user:
        stats = db.get_stats(user_id=user["id"])
    else:
        stats = {"total_jobs": 0, "auto_applied": 0, "pending": 0, "manual_flag": 0}
    elapsed = 0
    if STATE.started_at:
        elapsed = int((datetime.now() - STATE.started_at).total_seconds())

    return {
        "running": STATE.running,
        "paused": STATE.paused,
        "cycle": STATE.cycle,
        "elapsed_seconds": elapsed,
        "total_jobs": stats.get("total_jobs", 0),
        "auto_applied": stats.get("auto_applied", 0),
        "semi_auto": stats.get("pending", 0),
        "manual_flag": stats.get("manual_flag", 0),
    }


@app.post("/api/search/start")
async def start_search(duration_minutes: int = 30, user: dict = Depends(require_user)):
    if STATE.running:
        raise HTTPException(409, "Search already running")

    profile = _db().get_profile(user_id=user["id"])
    if not profile:
        raise HTTPException(400, "No profile configured")
    if not profile.desired_roles:
        raise HTTPException(400, "Profile has no desired jobs")
    if profile.strict_salary_filter and not profile.salary_min:
        raise HTTPException(400, "Strict salary filter on but no expected range")
    if not profile.llm_api_key:
        raise HTTPException(
            400,
            f"No API key set for provider '{profile.llm_provider}'. Add one in Settings."
        )

    STATE.running = True
    STATE.paused = False
    STATE.cycle = 0
    STATE.started_at = datetime.now()
    STATE.events.clear()
    STATE._last_seen = 0
    STATE.user_id = user["id"]
    STATE.push({"type": "info", "message": f"Search started — {duration_minutes} min"})

    STATE.thread = threading.Thread(
        target=_run_search_loop, args=(duration_minutes, user["id"]), daemon=True
    )
    STATE.thread.start()
    return {"ok": True}


@app.post("/api/search/pause")
async def pause_search(user: dict = Depends(require_user)):
    STATE.paused = True
    STATE.push({"type": "warning", "message": "Search paused"})
    return {"ok": True}


@app.post("/api/search/resume")
async def resume_search(user: dict = Depends(require_user)):
    STATE.paused = False
    STATE.push({"type": "info", "message": "Search resumed"})
    return {"ok": True}


@app.post("/api/search/stop")
async def stop_search(user: dict = Depends(require_user)):
    STATE.running = False
    STATE.push({"type": "info", "message": "Search stopped"})
    return {"ok": True}


@app.get("/api/applications")
async def list_applications(
    status: str | None = None,
    min_score: int = 51,
    user: dict = Depends(require_user),
):
    """Returns applications with match_score >= min_score (default 51) for current user."""
    apps = _db().get_applications(user_id=user["id"], status=status, min_score=min_score)
    return {"applications": [a.model_dump(mode="json") for a in apps]}


class StatusUpdatePayload(BaseModel):
    status: str
    notes: str | None = None


@app.patch("/api/applications/{app_id}/status")
async def update_application_status(
    app_id: str,
    payload: StatusUpdatePayload,
    user: dict = Depends(require_user),
):
    """Mark an application's status (e.g., 'auto_applied' after applying externally)."""
    valid = {s.value for s in ApplicationStatus}
    if payload.status not in valid:
        raise HTTPException(400, f"Invalid status. Must be one of: {sorted(valid)}")

    db = _db()
    apps = db.get_applications(user_id=user["id"])
    target = next((a for a in apps if a.id == app_id), None)
    if not target:
        raise HTTPException(404, "Application not found")

    target.status = ApplicationStatus(payload.status)
    if payload.status in {"auto_applied", "semi_auto_applied"} and not target.applied_at:
        target.applied_at = datetime.now()
        target.applied_by = "manual"
    if payload.notes:
        target.notes = (target.notes or "") + f"\n[user note] {payload.notes}"
    db.add_application(target, user_id=user["id"])
    return {"ok": True, "application": target.model_dump(mode="json")}


@app.get("/api/applications/{app_id}")
async def application_detail(app_id: str, user: dict = Depends(require_user)):
    apps = _db().get_applications(user_id=user["id"], app_id=app_id)
    if not apps:
        # Fallback: company name search (legacy behaviour)
        all_apps = _db().get_applications(user_id=user["id"])
        apps = [a for a in all_apps if app_id.lower() in a.company.lower()]
    if not apps:
        raise HTTPException(404, "Application not found")
    return apps[0].model_dump(mode="json")


@app.get("/api/events")
async def events(request: Request):
    """Server-sent events stream for live search updates."""

    async def publisher():
        while True:
            if await request.is_disconnected():
                break
            new = STATE.unseen()
            for evt in new:
                yield {"event": "update", "data": json.dumps(evt)}
            # Poll fast during active search, slow otherwise to save resources
            await asyncio.sleep(0.5 if STATE.running else 5)

    return EventSourceResponse(publisher())


def _run_search_loop(duration_minutes: int, user_id: str) -> None:
    """Worker thread, scoped to one user.
    Rebuilds matcher from profile each cycle so API key edits during a live
    search take effect on the next cycle."""
    try:
        cfg = _cfg()
        db = JobDatabase(db_path=cfg.database_path)
        end_time = time.time() + duration_minutes * 60
        stats = {"applied": 0, "semi_auto": 0, "manual": 0}
        last_provider_signature = None

        while STATE.running and time.time() < end_time:
            if STATE.paused:
                time.sleep(2)
                continue

            profile = db.get_profile(user_id=user_id)
            if profile is None:
                STATE.push({"type": "error", "message": "Profile missing — aborting"})
                break

            # Re-build matcher if the user changed provider/key mid-flight
            signature = (profile.llm_provider, profile.llm_api_key)
            if signature != last_provider_signature:
                try:
                    matcher = JobMatcher.from_profile(profile, env_fallback_key=cfg.gemini_api_key)
                    last_provider_signature = signature
                    STATE.push({
                        "type": "info",
                        "message": f"Using {profile.llm_provider} ({matcher.model_name})",
                    })
                except Exception as e:
                    STATE.push({"type": "error", "message": f"Cannot build matcher: {e}"})
                    break

            STATE.cycle += 1
            STATE.push({"type": "cycle", "cycle": STATE.cycle})

            searcher = JobSearcher(profile)
            discovered = searcher.run_search()
            STATE.last_diagnostics = searcher.diagnostics.as_dict()
            STATE.push({"type": "diagnostics", "data": STATE.last_diagnostics})
            new_jobs = [j for j in discovered if db.add_job(j, user_id=user_id)]
            STATE.push({"type": "discovered", "count": len(new_jobs)})

            for job in new_jobs:
                if not STATE.running:
                    break
                while STATE.paused and STATE.running:
                    time.sleep(1)

                score = matcher.evaluate_job(job, profile)
                db.add_match_score(score, user_id=user_id)
                application = _route_application(job, score, profile, user_id=user_id)
                db.add_application(application, user_id=user_id)

                if score.tier == "auto" and profile.auto_apply_enabled:
                    stats["applied"] += 1
                elif score.tier == "semi_auto":
                    stats["semi_auto"] += 1
                else:
                    stats["manual"] += 1

                # Only stream jobs scoring above 50 to the live feed
                if score.score > 50:
                    STATE.push({
                        "type": "job",
                        "title": job.title,
                        "company": job.company,
                        "location": job.location,
                        "source": job.source,
                        "url": job.url,
                        "salary_min": job.salary_min,
                        "salary_max": job.salary_max,
                        "score": score.score,
                        "tier": score.tier,
                        "reason": score.reason,
                        "matched_skills": score.matched_skills,
                        "missing_skills": score.missing_skills,
                    })

            if STATE.running and time.time() < end_time:
                wait = min(cfg.search_interval_seconds, int(end_time - time.time()))
                if wait > 0:
                    STATE.push({"type": "waiting", "seconds": wait})
                    for _ in range(wait):
                        if not STATE.running:
                            break
                        time.sleep(1)

        STATE.running = False
        STATE.push({"type": "complete", "stats": stats})
    except Exception as e:
        STATE.push({"type": "error", "message": str(e)})
        STATE.running = False


def _route_application(job: Job, score: MatchScore, profile: UserProfile, user_id: str | None = None) -> Application:
    """Route a scored job. For score≥85 + auto-apply ON + safe source, attempt
    real Playwright submission. LinkedIn/Naukri/iimjobs/Instahyre are NEVER
    auto-submitted (login required, ban risk) — they're flagged for manual.
    """
    note_prefix = ""
    status = ApplicationStatus.MANUAL_FLAG
    applied_at: datetime | None = None
    applied_by = "manual"

    if score.tier == "auto" and profile.auto_apply_enabled:
        # Try real auto-submission via Playwright
        try:
            from applier import is_auto_applicable, auto_submit_sync
            from pathlib import Path as _P
            allowed, reason = is_auto_applicable(job)
            if allowed:
                resume = _find_user_resume(user_id) if user_id else None
                result = auto_submit_sync(job, profile, resume)
                if result.get("submitted"):
                    status = ApplicationStatus.AUTO_APPLIED
                    applied_at = datetime.now()
                    applied_by = "system"
                    note_prefix = f"[AUTO-SUBMITTED — {result.get('ats','?')}, {result.get('fields_filled',0)} fields] "
                else:
                    status = ApplicationStatus.PENDING
                    note_prefix = f"[HIGH MATCH — auto-submit failed: {result.get('reason','?')[:80]}] "
            else:
                status = ApplicationStatus.PENDING
                note_prefix = f"[HIGH MATCH — {reason}, apply manually] "
        except Exception as e:
            status = ApplicationStatus.PENDING
            note_prefix = f"[HIGH MATCH — auto-submit error: {str(e)[:80]}] "
    elif score.tier == "semi_auto":
        status = ApplicationStatus.PENDING
        note_prefix = "[Review recommended] "
    # else: MANUAL_FLAG (default already set)

    return Application(
        job_id=job.id,
        job_title=job.title,
        company=job.company,
        status=status,
        match_score=score.score,
        match_tier=score.tier,
        applied_at=applied_at,
        applied_by=applied_by,
        notes=note_prefix + (score.reason or ""),
    )


@app.get("/health")
async def health():
    return {"status": "ok", "version": app.version}


@app.get("/favicon.ico")
async def favicon():
    p = STATIC_DIR / "favicon.ico"
    if p.exists():
        return FileResponse(p)
    return JSONResponse({"status": "no favicon"}, status_code=204)
