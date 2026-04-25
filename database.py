"""Database layer — supports both SQLite (local dev) and Postgres (Supabase prod).

Driver selection is via DATABASE_URL env var:
- postgresql://...   → psycopg2 (Supabase)
- sqlite:///path     → sqlite3
- (unset)            → falls back to DATABASE_PATH config (local sqlite file)
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

from models import Application, ApplicationStatus, Job, MatchScore, UserProfile


def _is_postgres(url: str | None) -> bool:
    return bool(url) and url.startswith(("postgres://", "postgresql://"))


class JobDatabase:
    """Unified DB handler. Detects backend from DATABASE_URL or falls back to sqlite path."""

    def __init__(self, db_path: str | None = None):
        url = os.getenv("DATABASE_URL")
        self.is_postgres = _is_postgres(url)

        if self.is_postgres:
            import psycopg2
            self._psycopg2 = psycopg2
            # psycopg2 needs the URL with `postgresql://` scheme
            self.conn_str = url.replace("postgres://", "postgresql://", 1)
        else:
            self.is_postgres = False
            sqlite_path = db_path or os.getenv("DATABASE_PATH", "./data/jobs.db")
            self.db_path = Path(sqlite_path)
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_db()

    @contextmanager
    def _connect(self):
        if self.is_postgres:
            conn = self._psycopg2.connect(self.conn_str)
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()
        else:
            conn = sqlite3.connect(self.db_path)
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()

    def _ph(self, n: int = 1) -> str:
        """Returns parameter placeholder(s) for the active backend."""
        if self.is_postgres:
            return ", ".join(["%s"] * n)
        return ", ".join(["?"] * n)

    def _q(self, sql: str) -> str:
        """Convert SQLite-style `?` placeholders to Postgres `%s` if needed."""
        if self.is_postgres:
            return sql.replace("?", "%s")
        return sql

    def _init_db(self):
        """Create tables. Idempotent. Schema is type-portable."""
        if self.is_postgres:
            integer = "INTEGER"
            text = "TEXT"
            real = "REAL"
            ts = "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            bool_t = "BOOLEAN"
            true_lit = "TRUE"
            autoincrement_pk = "TEXT PRIMARY KEY"
        else:
            integer = "INTEGER"
            text = "TEXT"
            real = "REAL"
            ts = "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            bool_t = "BOOLEAN"
            true_lit = "1"
            autoincrement_pk = "TEXT PRIMARY KEY"

        ddl = [
            f"""CREATE TABLE IF NOT EXISTS queries (
                id {autoincrement_pk},
                name {text} NOT NULL,
                email {text} NOT NULL,
                phone {text},
                message {text} NOT NULL,
                status {text} DEFAULT 'new',
                created_at {ts}
            )""",
            f"""CREATE TABLE IF NOT EXISTS jobs (
                id {autoincrement_pk},
                title {text} NOT NULL,
                company {text} NOT NULL,
                location {text},
                remote {text},
                salary_min {real},
                salary_max {real},
                currency {text},
                description {text} NOT NULL,
                requirements {text},
                source {text} NOT NULL,
                url {text} UNIQUE NOT NULL,
                posted_date TIMESTAMP,
                discovered_at {ts}
            )""",
            f"""CREATE TABLE IF NOT EXISTS applications (
                id {autoincrement_pk},
                job_id {text} NOT NULL,
                job_title {text} NOT NULL,
                company {text} NOT NULL,
                status {text} NOT NULL,
                match_score {integer},
                match_tier {text},
                applied_at TIMESTAMP,
                applied_by {text},
                notes {text},
                created_at {ts}
            )""",
            f"""CREATE TABLE IF NOT EXISTS match_scores (
                id {autoincrement_pk},
                job_id {text} NOT NULL,
                score {integer} NOT NULL,
                reason {text},
                matched_skills {text},
                missing_skills {text},
                cultural_fit {text},
                salary_alignment {text},
                tier {text},
                confidence {real},
                created_at {ts}
            )""",
            f"""CREATE TABLE IF NOT EXISTS profiles (
                id {autoincrement_pk},
                name {text} NOT NULL,
                email {text} UNIQUE NOT NULL,
                "current_role" {text},
                years_experience {integer},
                desired_roles {text},
                skills {text},
                preferred_locations {text},
                remote_preference {text},
                current_salary {real},
                hike_percent_min {real} DEFAULT 20,
                hike_percent_max {real} DEFAULT 40,
                salary_min {real},
                salary_max {real},
                salary_currency {text} DEFAULT 'USD',
                industries {text},
                company_size_preference {text},
                job_type {text},
                availability {text},
                willing_to_relocate {bool_t},
                auto_apply_enabled {bool_t},
                strict_salary_filter {bool_t} DEFAULT {true_lit},
                llm_provider {text} DEFAULT 'gemini',
                llm_api_key {text},
                llm_model {text},
                created_at {ts}
            )""",
        ]
        with self._connect() as conn:
            cur = conn.cursor()
            for stmt in ddl:
                cur.execute(stmt)

            # Lazy migrations on SQLite (Postgres CREATE handles new cols already)
            if not self.is_postgres:
                cur.execute("PRAGMA table_info(profiles)")
                existing = {row[1] for row in cur.fetchall()}
                for col, defn in [
                    ("current_salary", "REAL"),
                    ("hike_percent_min", "REAL DEFAULT 20"),
                    ("hike_percent_max", "REAL DEFAULT 40"),
                    ("salary_currency", "TEXT DEFAULT 'USD'"),
                    ("strict_salary_filter", "BOOLEAN DEFAULT 1"),
                    ("llm_provider", "TEXT DEFAULT 'gemini'"),
                    ("llm_api_key", "TEXT"),
                    ("llm_model", "TEXT"),
                ]:
                    if col not in existing:
                        cur.execute(f"ALTER TABLE profiles ADD COLUMN {col} {defn}")

    # ─── Jobs ────────────────────────────────────────────────────

    def add_job(self, job: Job) -> bool:
        try:
            with self._connect() as conn:
                cur = conn.cursor()
                if self.is_postgres:
                    cur.execute("""
                        INSERT INTO jobs
                        (id, title, company, location, remote, salary_min, salary_max,
                         currency, description, requirements, source, url, posted_date)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (url) DO NOTHING
                    """, (
                        job.id, job.title, job.company, job.location, job.remote,
                        job.salary_min, job.salary_max, job.currency, job.description,
                        json.dumps(job.requirements), job.source, job.url, job.posted_date,
                    ))
                    return cur.rowcount > 0
                else:
                    cur.execute(self._q("""
                        INSERT OR IGNORE INTO jobs
                        (id, title, company, location, remote, salary_min, salary_max,
                         currency, description, requirements, source, url, posted_date)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """), (
                        job.id, job.title, job.company, job.location, job.remote,
                        job.salary_min, job.salary_max, job.currency, job.description,
                        json.dumps(job.requirements), job.source, job.url, job.posted_date,
                    ))
                    return cur.rowcount > 0
        except Exception as e:
            print(f"Error adding job: {e}")
            return False

    # ─── Applications ────────────────────────────────────────────

    def add_application(self, app: Application) -> bool:
        try:
            with self._connect() as conn:
                cur = conn.cursor()
                if self.is_postgres:
                    cur.execute("""
                        INSERT INTO applications
                        (id, job_id, job_title, company, status, match_score,
                         match_tier, applied_at, applied_by, notes)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET
                            status = EXCLUDED.status,
                            applied_at = EXCLUDED.applied_at,
                            applied_by = EXCLUDED.applied_by,
                            notes = EXCLUDED.notes
                    """, (
                        app.id, app.job_id, app.job_title, app.company, app.status.value,
                        app.match_score, app.match_tier, app.applied_at, app.applied_by, app.notes,
                    ))
                else:
                    cur.execute(self._q("""
                        INSERT OR REPLACE INTO applications
                        (id, job_id, job_title, company, status, match_score,
                         match_tier, applied_at, applied_by, notes)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """), (
                        app.id, app.job_id, app.job_title, app.company, app.status.value,
                        app.match_score, app.match_tier, app.applied_at, app.applied_by, app.notes,
                    ))
            return True
        except Exception as e:
            print(f"Error adding application: {e}")
            return False

    # ─── Match scores ────────────────────────────────────────────

    def add_match_score(self, score: MatchScore) -> bool:
        try:
            with self._connect() as conn:
                cur = conn.cursor()
                if self.is_postgres:
                    cur.execute("""
                        INSERT INTO match_scores
                        (id, job_id, score, reason, matched_skills, missing_skills,
                         cultural_fit, salary_alignment, tier, confidence)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET
                            score = EXCLUDED.score, reason = EXCLUDED.reason,
                            tier = EXCLUDED.tier, confidence = EXCLUDED.confidence
                    """, (
                        score.job_id, score.job_id, score.score, score.reason,
                        json.dumps(score.matched_skills), json.dumps(score.missing_skills),
                        score.cultural_fit, score.salary_alignment, score.tier, score.confidence,
                    ))
                else:
                    cur.execute(self._q("""
                        INSERT OR REPLACE INTO match_scores
                        (id, job_id, score, reason, matched_skills, missing_skills,
                         cultural_fit, salary_alignment, tier, confidence)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """), (
                        score.job_id, score.job_id, score.score, score.reason,
                        json.dumps(score.matched_skills), json.dumps(score.missing_skills),
                        score.cultural_fit, score.salary_alignment, score.tier, score.confidence,
                    ))
            return True
        except Exception as e:
            print(f"Error adding match score: {e}")
            return False

    # ─── Profile ─────────────────────────────────────────────────

    def save_profile(self, profile: UserProfile) -> bool:
        try:
            profile.compute_expected_salary()
            with self._connect() as conn:
                cur = conn.cursor()
                cols = (
                    'id, name, email, "current_role", years_experience, desired_roles, skills, '
                    "preferred_locations, remote_preference, current_salary, hike_percent_min, "
                    "hike_percent_max, salary_min, salary_max, salary_currency, industries, "
                    "company_size_preference, job_type, availability, willing_to_relocate, "
                    "auto_apply_enabled, strict_salary_filter, llm_provider, llm_api_key, llm_model"
                )
                vals = (
                    "profile_1", profile.name, profile.email, profile.current_role,
                    profile.years_experience, json.dumps(profile.desired_roles),
                    json.dumps(profile.skills), json.dumps(profile.preferred_locations),
                    profile.remote_preference,
                    profile.current_salary, profile.hike_percent_min, profile.hike_percent_max,
                    profile.salary_min, profile.salary_max, profile.salary_currency,
                    json.dumps(profile.industries), profile.company_size_preference,
                    json.dumps(profile.job_type), profile.availability,
                    profile.willing_to_relocate, profile.auto_apply_enabled,
                    profile.strict_salary_filter,
                    profile.llm_provider, profile.llm_api_key, profile.llm_model,
                )
                if self.is_postgres:
                    placeholders = ", ".join(["%s"] * len(vals))
                    raw_cols = [c.strip() for c in cols.split(",") if c.strip() != "id"]
                    update_set = ", ".join([
                        f'{c} = EXCLUDED.{c}' for c in raw_cols
                    ])
                    cur.execute(
                        f"INSERT INTO profiles ({cols}) VALUES ({placeholders}) "
                        f"ON CONFLICT (id) DO UPDATE SET {update_set}",
                        vals,
                    )
                else:
                    placeholders = ", ".join(["?"] * len(vals))
                    cur.execute(
                        f"INSERT OR REPLACE INTO profiles ({cols}) VALUES ({placeholders})",
                        vals,
                    )
            return True
        except Exception as e:
            print(f"Error saving profile: {e}")
            return False

    def get_profile(self) -> UserProfile | None:
        try:
            with self._connect() as conn:
                cur = conn.cursor()
                cur.execute(self._q("SELECT * FROM profiles WHERE id = 'profile_1'"))
                row = cur.fetchone()
                if not row:
                    return None
                colnames = [d[0] for d in cur.description]
                d = dict(zip(colnames, row))

                return UserProfile(
                    name=d.get("name"),
                    email=d.get("email"),
                    current_role=d.get("current_role"),
                    years_experience=d.get("years_experience") or 0,
                    desired_roles=json.loads(d.get("desired_roles") or "[]"),
                    skills=json.loads(d.get("skills") or "[]"),
                    preferred_locations=json.loads(d.get("preferred_locations") or "[]"),
                    remote_preference=d.get("remote_preference") or "any",
                    current_salary=d.get("current_salary"),
                    hike_percent_min=d.get("hike_percent_min") or 20.0,
                    hike_percent_max=d.get("hike_percent_max") or 40.0,
                    salary_min=d.get("salary_min"),
                    salary_max=d.get("salary_max"),
                    salary_currency=d.get("salary_currency") or "USD",
                    industries=json.loads(d.get("industries") or "[]"),
                    company_size_preference=d.get("company_size_preference"),
                    job_type=json.loads(d.get("job_type") or "[]"),
                    availability=d.get("availability") or "immediate",
                    willing_to_relocate=bool(d.get("willing_to_relocate")),
                    auto_apply_enabled=bool(d.get("auto_apply_enabled")),
                    strict_salary_filter=bool(d.get("strict_salary_filter")
                                              if d.get("strict_salary_filter") is not None else 1),
                    llm_provider=d.get("llm_provider") or "gemini",
                    llm_api_key=d.get("llm_api_key"),
                    llm_model=d.get("llm_model"),
                )
        except Exception as e:
            print(f"Error retrieving profile: {e}")
            return None

    def get_applications(self, status: str | None = None) -> list[Application]:
        try:
            with self._connect() as conn:
                cur = conn.cursor()
                if status:
                    cur.execute(
                        self._q("SELECT * FROM applications WHERE status = ? ORDER BY created_at DESC"),
                        (status,),
                    )
                else:
                    cur.execute(self._q("SELECT * FROM applications ORDER BY created_at DESC"))

                colnames = [d[0] for d in cur.description]
                apps = []
                for row in cur.fetchall():
                    d = dict(zip(colnames, row))
                    apps.append(Application(
                        id=d["id"], job_id=d["job_id"], job_title=d["job_title"],
                        company=d["company"], status=ApplicationStatus(d["status"]),
                        match_score=d.get("match_score") or 0,
                        match_tier=d.get("match_tier") or "manual",
                        applied_at=d.get("applied_at"),
                        applied_by=d.get("applied_by") or "system",
                        notes=d.get("notes"),
                        created_at=d.get("created_at"),
                    ))
                return apps
        except Exception as e:
            print(f"Error retrieving applications: {e}")
            return []

    def get_stats(self) -> dict:
        try:
            with self._connect() as conn:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM jobs")
                jobs_count = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM applications")
                apps_count = cur.fetchone()[0]
                cur.execute(
                    self._q("SELECT COUNT(*) FROM applications WHERE status = ?"),
                    (ApplicationStatus.AUTO_APPLIED.value,),
                )
                auto = cur.fetchone()[0]
                return {
                    "total_jobs": jobs_count,
                    "total_applications": apps_count,
                    "auto_applied": auto,
                }
        except Exception as e:
            print(f"Error getting stats: {e}")
            return {}
