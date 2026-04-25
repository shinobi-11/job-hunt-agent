"""Shared pytest fixtures for Job Hunt Agent tests."""
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock

import pytest

from models import Application, ApplicationStatus, Job, MatchScore, UserProfile


@pytest.fixture
def temp_db_path() -> Generator[str, None, None]:
    """Create a temporary database file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def sample_profile() -> UserProfile:
    """Sample user profile for testing."""
    return UserProfile(
        name="Jane Developer",
        email="jane@example.com",
        current_role="Software Engineer",
        years_experience=5,
        desired_roles=["Senior Software Engineer", "Staff Engineer"],
        skills=["Python", "React", "AWS", "PostgreSQL", "Docker"],
        preferred_locations=["San Francisco", "Remote"],
        remote_preference="hybrid",
        salary_min=120000,
        salary_max=200000,
        industries=["Technology", "FinTech"],
        company_size_preference="scale-up",
        job_type=["full-time"],
        availability="immediate",
        willing_to_relocate=False,
        auto_apply_enabled=True,
    )


@pytest.fixture
def sample_job() -> Job:
    """Sample job posting for testing."""
    return Job(
        id="job_test_001",
        title="Senior Python Engineer",
        company="Acme Corp",
        location="San Francisco, CA",
        remote="hybrid",
        salary_min=150000,
        salary_max=200000,
        currency="USD",
        description="Looking for an experienced Python engineer with React knowledge.",
        requirements=["Python", "React", "AWS", "5+ years experience"],
        source="TestSource",
        url="https://example.com/jobs/12345",
        posted_date=datetime.now(),
    )


@pytest.fixture
def sample_match_score(sample_job: Job) -> MatchScore:
    """Sample match score for testing."""
    return MatchScore(
        job_id=sample_job.id,
        score=92,
        reason="Strong match with core skills and experience level",
        matched_skills=["Python", "React", "AWS"],
        missing_skills=["Kubernetes"],
        cultural_fit="Strong fit with team-focused culture",
        salary_alignment="Within expected range",
        tier="auto",
        confidence=0.95,
    )


@pytest.fixture
def sample_application(sample_job: Job) -> Application:
    """Sample application record for testing."""
    return Application(
        id="app_test_001",
        job_id=sample_job.id,
        job_title=sample_job.title,
        company=sample_job.company,
        status=ApplicationStatus.AUTO_APPLIED,
        match_score=92,
        match_tier="auto",
        applied_at=datetime.now(),
        applied_by="system",
    )


@pytest.fixture
def mock_gemini_response() -> dict:
    """Mock Gemini API response."""
    return {
        "score": 92,
        "reason": "Strong match",
        "matched_skills": ["Python", "React"],
        "missing_skills": ["Kubernetes"],
        "cultural_fit": "Good fit",
        "salary_alignment": "Aligned",
        "tier": "auto",
        "confidence": 0.95,
    }


@pytest.fixture
def mock_gemini_model(mock_gemini_response: dict) -> MagicMock:
    """Mock Gemini GenerativeModel."""
    import json

    mock = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json.dumps(mock_gemini_response)
    mock.generate_content.return_value = mock_response
    return mock


TEST_API_KEY = "AIzaSy_test_fake_key_for_unit_tests_00000"


def pytest_addoption(parser):
    parser.addoption(
        "--run-real",
        action="store_true",
        default=False,
        help="Run tests that hit real external APIs (costs Gemini quota)",
    )


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    """Set up test environment variables."""
    monkeypatch.setenv("GEMINI_API_KEY", TEST_API_KEY)
    monkeypatch.setenv("AUTO_APPLY_THRESHOLD", "85")
    monkeypatch.setenv("SEMI_AUTO_THRESHOLD", "70")
