"""Smoke tests for the FastAPI web frontend."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "jobs.db"))
    monkeypatch.setenv("LOG_PATH", str(tmp_path / "agent.log"))
    monkeypatch.setenv("RESUME_PATH", str(tmp_path / "resume.pdf"))

    import config as config_mod
    config_mod._config = None

    from web.app import app
    from web.auth import init_users_table
    init_users_table()
    return TestClient(app)


@pytest.fixture
def authed_client(client):
    """Sign up a user and return the authenticated client."""
    r = client.post("/api/auth/signup", json={
        "email": "alice@example.com",
        "password": "secretpass123",
        "name": "Alice",
    })
    assert r.status_code == 200
    return client


class TestPublicRoutes:
    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_homepage_renders(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert "Job Hunt Agent" in r.text
        assert "Sign up" in r.text and "Log in" in r.text

    def test_login_page_renders(self, client):
        r = client.get("/login")
        assert r.status_code == 200
        assert "Welcome back" in r.text

    def test_signup_page_renders(self, client):
        r = client.get("/signup")
        assert r.status_code == 200
        assert "Create your account" in r.text

    def test_dashboard_redirects_when_logged_out(self, client):
        r = client.get("/app", follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/login"

    def test_protected_api_returns_401_when_logged_out(self, client):
        r = client.get("/api/profile")
        assert r.status_code == 401


class TestAuth:
    def test_signup_creates_user(self, client):
        r = client.post("/api/auth/signup", json={
            "email": "bob@example.com",
            "password": "secretpass123",
            "name": "Bob",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["user"]["email"] == "bob@example.com"

    def test_signup_rejects_short_password(self, client):
        r = client.post("/api/auth/signup", json={
            "email": "x@y.com",
            "password": "short",
            "name": "",
        })
        assert r.status_code == 422

    def test_signup_rejects_duplicate_email(self, client):
        client.post("/api/auth/signup", json={
            "email": "dup@example.com", "password": "abcdefgh", "name": "",
        })
        r = client.post("/api/auth/signup", json={
            "email": "dup@example.com", "password": "abcdefgh", "name": "",
        })
        assert r.status_code == 400

    def test_login_with_valid_credentials(self, client):
        client.post("/api/auth/signup", json={
            "email": "login@example.com", "password": "abcdefgh", "name": "",
        })
        client.cookies.clear()
        r = client.post("/api/auth/login", json={
            "email": "login@example.com", "password": "abcdefgh",
        })
        assert r.status_code == 200
        assert "jha_session" in r.cookies

    def test_login_with_invalid_password(self, client):
        client.post("/api/auth/signup", json={
            "email": "x@y.com", "password": "abcdefgh", "name": "",
        })
        r = client.post("/api/auth/login", json={
            "email": "x@y.com", "password": "wrongpass",
        })
        assert r.status_code == 401

    def test_me_returns_user_when_logged_in(self, authed_client):
        r = authed_client.get("/api/auth/me")
        assert r.status_code == 200
        assert r.json()["user"]["email"] == "alice@example.com"

    def test_logout_clears_session(self, authed_client):
        r = authed_client.post("/api/auth/logout")
        assert r.status_code == 200
        authed_client.cookies.clear()
        r2 = authed_client.get("/api/profile")
        assert r2.status_code == 401


class TestProtectedRoutes:
    def test_status_works_when_authed(self, authed_client):
        r = authed_client.get("/api/status")
        assert r.status_code == 200

    def test_empty_profile(self, authed_client):
        r = authed_client.get("/api/profile")
        assert r.status_code == 200
        assert r.json()["profile"] is None

    def test_save_profile_roundtrip(self, authed_client):
        payload = {
            "name": "Test Vivek",
            "email": "test@example.com",
            "current_role": "Analyst",
            "years_experience": 3,
            "desired_roles": ["Senior Analyst", "Manager"],
            "skills": ["SQL", "Power BI"],
            "preferred_locations": ["Remote"],
            "remote_preference": "remote",
            "current_salary": 1000000,
            "hike_percent_min": 20,
            "hike_percent_max": 40,
            "salary_currency": "INR",
            "willing_to_relocate": False,
            "auto_apply_enabled": True,
            "strict_salary_filter": True,
            "llm_provider": "gemini",
            "llm_api_key": "AIzaSy_test_fake_key_for_unit_tests_00000",
        }
        r = authed_client.post("/api/profile", json=payload)
        assert r.status_code == 200
        saved = r.json()["profile"]
        assert saved["salary_min"] == 1200000
        assert saved["salary_max"] == 1400000
        # Key should be masked in response
        assert saved["llm_api_key"] != payload["llm_api_key"]

    def test_start_search_without_profile_rejects(self, authed_client):
        r = authed_client.post("/api/search/start?duration_minutes=1")
        assert r.status_code == 400

    def test_applications_list_empty(self, authed_client):
        r = authed_client.get("/api/applications")
        assert r.status_code == 200
        assert r.json()["applications"] == []

    def test_providers_endpoint(self, authed_client):
        r = authed_client.get("/api/providers")
        assert r.status_code == 200
        ids = {p["id"] for p in r.json()["providers"]}
        assert {"gemini", "openai", "anthropic", "grok"}.issubset(ids)
