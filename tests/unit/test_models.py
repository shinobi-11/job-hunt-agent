"""Unit tests for models module."""
import pytest
from pydantic import ValidationError

from models import Application, ApplicationStatus, Job, MatchScore, UserProfile


class TestUserProfile:
    def test_create_minimal_profile(self):
        profile = UserProfile(name="Test", email="test@example.com")
        assert profile.name == "Test"
        assert profile.email == "test@example.com"
        assert profile.years_experience == 0
        assert profile.auto_apply_enabled is True

    def test_create_full_profile(self, sample_profile):
        assert sample_profile.name == "Jane Developer"
        assert len(sample_profile.skills) == 5
        assert sample_profile.remote_preference == "hybrid"


class TestJob:
    def test_create_job(self, sample_job):
        assert sample_job.title == "Senior Python Engineer"
        assert sample_job.company == "Acme Corp"
        assert sample_job.salary_min == 150000
        assert len(sample_job.requirements) == 4

    def test_job_auto_generates_id(self):
        job = Job(
            title="Engineer",
            company="Corp",
            location="Remote",
            description="Job",
            source="Test",
            url="https://example.com/1",
        )
        assert job.id.startswith("job_")


class TestMatchScore:
    def test_create_match_score(self, sample_match_score):
        assert sample_match_score.score == 92
        assert sample_match_score.tier == "auto"
        assert 0.0 <= sample_match_score.confidence <= 1.0

    def test_score_range_validation(self):
        with pytest.raises(ValidationError):
            MatchScore(job_id="j1", score=150, reason="Too high")

        with pytest.raises(ValidationError):
            MatchScore(job_id="j1", score=-10, reason="Too low")


class TestApplication:
    def test_create_application(self, sample_application):
        assert sample_application.status == ApplicationStatus.AUTO_APPLIED
        assert sample_application.match_score == 92
        assert sample_application.applied_by == "system"

    def test_application_status_enum(self):
        assert ApplicationStatus.PENDING.value == "pending"
        assert ApplicationStatus.AUTO_APPLIED.value == "auto_applied"
        assert ApplicationStatus.MANUAL_FLAG.value == "manual_flag"
