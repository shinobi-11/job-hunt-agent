"""Real-world E2E integration tests — hit the real resume, real Gemini API.

Skipped by default to avoid consuming API quota. Enable with:
    pytest tests/integration/test_real_flow.py --run-real
"""
import json
import os
from pathlib import Path

import pytest

from database import JobDatabase
from matcher import JobMatcher
from models import Job, UserProfile
from profile_builder import ProfileBuilder
from resume_parser import ResumeParser


def _real_enabled(request) -> bool:
    return bool(request.config.getoption("--run-real", default=False))


def _real_api_key() -> str | None:
    """Read real key directly from .env (bypasses autouse fixture)."""
    env_file = Path(__file__).parent.parent.parent / ".env"
    if not env_file.exists():
        return None
    for line in env_file.read_text().splitlines():
        if line.startswith("GEMINI_API_KEY="):
            key = line.split("=", 1)[1].strip()
            if len(key) >= 30 and not key.startswith("AIzaSy_test"):
                return key
    return None


REAL_RESUME_PATH = Path(__file__).parent.parent.parent / "data" / "resume.pdf"


@pytest.mark.integration
@pytest.mark.slow
class TestRealWorldFlow:
    def test_parse_real_resume(self, request):
        if not _real_enabled(request):
            pytest.skip("--run-real not set")
        if not REAL_RESUME_PATH.exists():
            pytest.skip("No real resume present in ./data/")

        text = ResumeParser.parse_resume(str(REAL_RESUME_PATH))
        assert len(text) > 500
        assert "@" in text

    def test_ai_profile_from_real_resume(self, request):
        if not _real_enabled(request):
            pytest.skip("--run-real not set")
        if not REAL_RESUME_PATH.exists():
            pytest.skip("No real resume")

        api_key = _real_api_key()
        if not api_key:
            pytest.skip("Real API key not present in .env")

        text = ResumeParser.parse_resume(str(REAL_RESUME_PATH))
        builder = ProfileBuilder(api_key=api_key)
        profile = builder.build_from_resume(text)

        assert isinstance(profile, UserProfile)
        assert profile.name != "Unknown"
        assert len(profile.skills) >= 3
        assert len(profile.desired_roles) >= 1

    def test_real_gemini_scoring(self, request, tmp_path):
        if not _real_enabled(request):
            pytest.skip("--run-real not set")

        api_key = _real_api_key()
        if not api_key:
            pytest.skip("Real API key not present in .env")

        matcher = JobMatcher(api_key=api_key)
        profile = UserProfile(
            name="Test Finance Pro",
            email="t@t.com",
            current_role="Financial Analyst",
            years_experience=2,
            desired_roles=["Senior Financial Analyst", "Investment Banking Associate"],
            skills=["DCF Valuation", "Financial Modeling", "Power BI", "Excel VBA"],
            industries=["Financial Services", "Investment Banking"],
        )
        job = Job(
            title="Senior Financial Analyst — Corporate Development",
            company="Goldman Sachs",
            location="New York, NY",
            remote="hybrid",
            salary_min=120000,
            salary_max=180000,
            description=(
                "We're hiring a Senior Financial Analyst for Corporate Development. "
                "You'll build DCF models, lead M&A analysis, prepare executive board "
                "presentations. Strong Excel/VBA and financial modeling required."
            ),
            requirements=[
                "MBA Finance or equivalent",
                "3+ years financial analysis",
                "DCF modeling",
                "M&A experience",
                "Excel/PowerPoint mastery",
            ],
            source="TestFixture",
            url="https://example.com/test-real-score",
        )

        score = matcher.evaluate_job(job, profile)
        assert 0 <= score.score <= 100
        assert score.tier in {"auto", "semi_auto", "manual"}
        assert len(score.reason) > 10
