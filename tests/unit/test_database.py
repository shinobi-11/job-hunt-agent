"""Unit tests for database module."""
import pytest

from database import JobDatabase
from models import ApplicationStatus


class TestJobDatabase:
    def test_database_initialization(self, temp_db_path):
        db = JobDatabase(db_path=temp_db_path)
        stats = db.get_stats()
        assert stats["total_jobs"] == 0
        assert stats["total_applications"] == 0

    def test_save_and_get_profile(self, temp_db_path, sample_profile):
        db = JobDatabase(db_path=temp_db_path)

        result = db.save_profile(sample_profile)
        assert result is True

        retrieved = db.get_profile()
        assert retrieved is not None
        assert retrieved.name == sample_profile.name
        assert retrieved.email == sample_profile.email
        assert retrieved.skills == sample_profile.skills

    def test_add_job(self, temp_db_path, sample_job):
        db = JobDatabase(db_path=temp_db_path)
        result = db.add_job(sample_job)
        assert result is True

        stats = db.get_stats()
        assert stats["total_jobs"] == 1

    def test_add_duplicate_job(self, temp_db_path, sample_job):
        db = JobDatabase(db_path=temp_db_path)
        db.add_job(sample_job)
        db.add_job(sample_job)  # Duplicate URL

        stats = db.get_stats()
        assert stats["total_jobs"] == 1  # Deduped

    def test_add_application(self, temp_db_path, sample_job, sample_application):
        db = JobDatabase(db_path=temp_db_path)
        db.add_job(sample_job)

        result = db.add_application(sample_application)
        assert result is True

        stats = db.get_stats()
        assert stats["total_applications"] == 1
        assert stats["auto_applied"] == 1

    def test_get_applications_filtered_by_status(
        self, temp_db_path, sample_job, sample_application
    ):
        db = JobDatabase(db_path=temp_db_path)
        db.add_job(sample_job)
        db.add_application(sample_application)

        applied = db.get_applications(status=ApplicationStatus.AUTO_APPLIED.value)
        assert len(applied) == 1
        assert applied[0].match_score == 92

        pending = db.get_applications(status=ApplicationStatus.PENDING.value)
        assert len(pending) == 0

    def test_add_match_score(self, temp_db_path, sample_job, sample_match_score):
        db = JobDatabase(db_path=temp_db_path)
        db.add_job(sample_job)

        result = db.add_match_score(sample_match_score)
        assert result is True
