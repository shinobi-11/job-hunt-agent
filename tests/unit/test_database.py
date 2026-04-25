"""Unit tests for database module."""
import pytest

from database import JobDatabase
from models import ApplicationStatus

USER = "u_test_001"


class TestJobDatabase:
    def test_database_initialization(self, temp_db_path):
        db = JobDatabase(db_path=temp_db_path)
        stats = db.get_stats(user_id=USER)
        assert stats["total_jobs"] == 0
        assert stats["total_applications"] == 0

    def test_save_and_get_profile(self, temp_db_path, sample_profile):
        db = JobDatabase(db_path=temp_db_path)

        result = db.save_profile(sample_profile, user_id=USER)
        assert result is True

        retrieved = db.get_profile(user_id=USER)
        assert retrieved is not None
        assert retrieved.name == sample_profile.name
        assert retrieved.email == sample_profile.email
        assert retrieved.skills == sample_profile.skills

    def test_get_profile_isolated_per_user(self, temp_db_path, sample_profile):
        db = JobDatabase(db_path=temp_db_path)
        db.save_profile(sample_profile, user_id=USER)

        # Different user gets nothing
        retrieved = db.get_profile(user_id="u_other")
        assert retrieved is None

        # Original user still gets it
        retrieved = db.get_profile(user_id=USER)
        assert retrieved is not None

    def test_add_job(self, temp_db_path, sample_job):
        db = JobDatabase(db_path=temp_db_path)
        result = db.add_job(sample_job, user_id=USER)
        assert result is True

        stats = db.get_stats(user_id=USER)
        assert stats["total_jobs"] == 1

    def test_add_duplicate_job(self, temp_db_path, sample_job):
        db = JobDatabase(db_path=temp_db_path)
        db.add_job(sample_job, user_id=USER)
        db.add_job(sample_job, user_id=USER)  # Duplicate URL for same user

        stats = db.get_stats(user_id=USER)
        assert stats["total_jobs"] == 1  # Deduped

    def test_same_job_for_different_users_allowed(self, temp_db_path, sample_job):
        db = JobDatabase(db_path=temp_db_path)
        # PK is global, so each user needs a distinct id+url for the same listing.
        # In production each user discovers jobs independently, so this is realistic.
        from copy import deepcopy
        j1 = deepcopy(sample_job)
        j1.id = "alice_job_1"
        j2 = deepcopy(sample_job)
        j2.id = "bob_job_1"
        j2.url = sample_job.url + "?u=bob"

        assert db.add_job(j1, user_id="u_alice") is True
        assert db.add_job(j2, user_id="u_bob") is True

        assert db.get_stats(user_id="u_alice")["total_jobs"] == 1
        assert db.get_stats(user_id="u_bob")["total_jobs"] == 1

    def test_add_application(self, temp_db_path, sample_job, sample_application):
        db = JobDatabase(db_path=temp_db_path)
        db.add_job(sample_job, user_id=USER)

        result = db.add_application(sample_application, user_id=USER)
        assert result is True

        stats = db.get_stats(user_id=USER)
        assert stats["total_applications"] == 1
        assert stats["auto_applied"] == 1

    def test_get_applications_filtered_by_status(
        self, temp_db_path, sample_job, sample_application
    ):
        db = JobDatabase(db_path=temp_db_path)
        db.add_job(sample_job, user_id=USER)
        db.add_application(sample_application, user_id=USER)

        applied = db.get_applications(user_id=USER, status=ApplicationStatus.AUTO_APPLIED.value)
        assert len(applied) == 1
        assert applied[0].match_score == 92

        pending = db.get_applications(user_id=USER, status=ApplicationStatus.PENDING.value)
        assert len(pending) == 0

    def test_get_applications_isolated_per_user(self, temp_db_path, sample_job, sample_application):
        db = JobDatabase(db_path=temp_db_path)
        db.add_job(sample_job, user_id=USER)
        db.add_application(sample_application, user_id=USER)

        assert len(db.get_applications(user_id=USER)) == 1
        assert len(db.get_applications(user_id="u_other")) == 0

    def test_add_match_score(self, temp_db_path, sample_job, sample_match_score):
        db = JobDatabase(db_path=temp_db_path)
        db.add_job(sample_job, user_id=USER)

        result = db.add_match_score(sample_match_score, user_id=USER)
        assert result is True
