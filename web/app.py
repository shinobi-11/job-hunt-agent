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


def _cfg():
    return get_config()


def _db() -> JobDatabase:
    return JobDatabase(db_path=_cfg().database_path)


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


@app.get("/api/auth/me")
async def api_me(user: dict | None = Depends(get_current_user)):
    if not user:
        return {"user": None}
    return {"user": {"id": user["id"], "email": user["email"], "name": user.get("name")}}


@app.get("/api/profile")
async def get_profile(user: dict = Depends(require_user)):
    profile = _db().get_profile()
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
    existing = _db().get_profile()
    data = payload.model_dump()
    if existing and (not data.get("llm_api_key") or data["llm_api_key"] == "●●●●●●●●"):
        data["llm_api_key"] = existing.llm_api_key

    profile = UserProfile(**data)
    profile.compute_expected_salary()
    _db().save_profile(profile)
    return {"ok": True, "profile": _mask_key(profile.model_dump(mode="json"))}


def _mask_key(payload: dict) -> dict:
    """Never return the full API key to the client after it's saved."""
    if payload.get("llm_api_key"):
        k = payload["llm_api_key"]
        payload["llm_api_key"] = k[:6] + "..." + k[-4:] if len(k) > 12 else "●●●●●●●●"
    return payload


@app.post("/api/resume")
async def upload_resume(file: UploadFile = File(...), user: dict = Depends(require_user)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".pdf", ".docx", ".doc"}:
        raise HTTPException(400, "Only PDF or DOCX supported")

    dest = Path(_cfg().resume_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        text = ResumeParser.parse_resume(str(dest))
    except Exception as e:
        raise HTTPException(400, f"Parse failed: {e}")

    return {"ok": True, "filename": file.filename, "chars": len(text)}


@app.get("/api/resume")
async def get_resume_info(user: dict = Depends(require_user)):
    p = Path(_cfg().resume_path)
    if not p.exists():
        return {"exists": False}
    return {
        "exists": True,
        "filename": p.name,
        "size_bytes": p.stat().st_size,
        "modified": datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
    }


@app.get("/api/diagnostics")
async def get_diagnostics(user: dict = Depends(require_user)):
    """Last cycle's source fan-out + funnel counts."""
    return {"diagnostics": STATE.last_diagnostics}


@app.get("/api/status")
async def get_status():
    db = _db()
    stats = db.get_stats()
    apps = db.get_applications()
    auto = sum(1 for a in apps if a.status == ApplicationStatus.AUTO_APPLIED)
    semi = sum(1 for a in apps if a.status == ApplicationStatus.PENDING)
    manual = sum(1 for a in apps if a.status == ApplicationStatus.MANUAL_FLAG)
    elapsed = 0
    if STATE.started_at:
        elapsed = int((datetime.now() - STATE.started_at).total_seconds())

    return {
        "running": STATE.running,
        "paused": STATE.paused,
        "cycle": STATE.cycle,
        "elapsed_seconds": elapsed,
        "total_jobs": stats.get("total_jobs", 0),
        "auto_applied": auto,
        "semi_auto": semi,
        "manual_flag": manual,
    }


@app.post("/api/search/start")
async def start_search(duration_minutes: int = 30, user: dict = Depends(require_user)):
    if STATE.running:
        raise HTTPException(409, "Search already running")

    profile = _db().get_profile()
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
    STATE.push({"type": "info", "message": f"Search started — {duration_minutes} min"})

    STATE.thread = threading.Thread(
        target=_run_search_loop, args=(duration_minutes,), daemon=True
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
    """Returns applications with match_score > min_score (default 50, exclusive)."""
    apps = _db().get_applications(status=status)
    apps = [a for a in apps if (a.match_score or 0) >= min_score]
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
    apps = db.get_applications()
    target = next((a for a in apps if a.id == app_id), None)
    if not target:
        raise HTTPException(404, "Application not found")

    target.status = ApplicationStatus(payload.status)
    if payload.status in {"auto_applied", "semi_auto_applied"} and not target.applied_at:
        target.applied_at = datetime.now()
        target.applied_by = "manual"
    if payload.notes:
        target.notes = (target.notes or "") + f"\n[user note] {payload.notes}"
    db.add_application(target)
    return {"ok": True, "application": target.model_dump(mode="json")}


@app.get("/api/applications/{app_id}")
async def application_detail(app_id: str, user: dict = Depends(require_user)):
    apps = _db().get_applications()
    match = next(
        (a for a in apps if a.id == app_id or app_id.lower() in a.company.lower()),
        None,
    )
    if not match:
        raise HTTPException(404, "Application not found")
    return match.model_dump(mode="json")


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
            await asyncio.sleep(1)

    return EventSourceResponse(publisher())


def _run_search_loop(duration_minutes: int) -> None:
    """Worker thread. Rebuilds matcher from profile each cycle so API key edits
    made via Settings during a live search take effect on the next cycle."""
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

            profile = db.get_profile()
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
            new_jobs = [j for j in discovered if db.add_job(j)]
            STATE.push({"type": "discovered", "count": len(new_jobs)})

            for job in new_jobs:
                if not STATE.running:
                    break
                while STATE.paused and STATE.running:
                    time.sleep(1)

                score = matcher.evaluate_job(job, profile)
                db.add_match_score(score)
                application = _route_application(job, score, profile)
                db.add_application(application)

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


def _route_application(job: Job, score: MatchScore, profile: UserProfile) -> Application:
    if score.tier == "auto" and profile.auto_apply_enabled:
        status = ApplicationStatus.AUTO_APPLIED
        applied_at: datetime | None = datetime.now()
        applied_by = "system"
    elif score.tier == "semi_auto":
        status = ApplicationStatus.PENDING
        applied_at = None
        applied_by = "manual"
    else:
        status = ApplicationStatus.MANUAL_FLAG
        applied_at = None
        applied_by = "manual"

    return Application(
        job_id=job.id,
        job_title=job.title,
        company=job.company,
        status=status,
        match_score=score.score,
        match_tier=score.tier,
        applied_at=applied_at,
        applied_by=applied_by,
        notes=score.reason,
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
