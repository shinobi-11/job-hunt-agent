"""Integration tests for agent workflow."""
from unittest.mock import MagicMock, patch

import pytest

from database import JobDatabase
from models import ApplicationStatus


@pytest.mark.integration
class TestAgentFlow:
    def test_profile_persistence_roundtrip(self, temp_db_path, sample_profile):
        db = JobDatabase(db_path=temp_db_path)
        db.save_profile(sample_profile)

        retrieved = db.get_profile()
        assert retrieved is not None
        assert retrieved.email == sample_profile.email
        assert set(retrieved.skills) == set(sample_profile.skills)

    def test_job_evaluation_and_application_flow(
        self, temp_db_path, sample_job, sample_profile, sample_match_score
    ):
        db = JobDatabase(db_path=temp_db_path)

        db.save_profile(sample_profile)
        db.add_job(sample_job)
        db.add_match_score(sample_match_score)

        from models import Application

        app = Application(
            job_id=sample_job.id,
            job_title=sample_job.title,
            company=sample_job.company,
            status=ApplicationStatus.AUTO_APPLIED,
            match_score=sample_match_score.score,
            match_tier=sample_match_score.tier,
        )
        db.add_application(app)

        stats = db.get_stats()
        assert stats["total_jobs"] == 1
        assert stats["total_applications"] == 1
        assert stats["auto_applied"] == 1

    def test_three_tier_routing(self, temp_db_path, sample_job):
        db = JobDatabase(db_path=temp_db_path)
        db.add_job(sample_job)

        from models import Application

        tiers = [
            (ApplicationStatus.AUTO_APPLIED, 92, "auto"),
            (ApplicationStatus.SEMI_AUTO_APPLIED, 75, "semi_auto"),
            (ApplicationStatus.MANUAL_FLAG, 45, "manual"),
        ]

        for i, (status, score, tier) in enumerate(tiers):
            app = Application(
                id=f"app_test_{i}",
                job_id=sample_job.id,
                job_title=sample_job.title,
                company=sample_job.company,
                status=status,
                match_score=score,
                match_tier=tier,
            )
            db.add_application(app)

        all_apps = db.get_applications()
        assert len(all_apps) == 3
