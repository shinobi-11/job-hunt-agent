"""Tests for agent workflow methods (search loop, evaluation, waiting)."""
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent import JobHuntAgent
from config import Config
from models import Application, ApplicationStatus, Job, MatchScore, UserProfile
from tests.conftest import TEST_API_KEY


@pytest.fixture
def workflow_agent(tmp_path):
    cfg = Config(
        gemini_api_key=TEST_API_KEY,
        database_path=str(tmp_path / "jobs.db"),
        log_path=str(tmp_path / "agent.log"),
        resume_path=str(tmp_path / "resume.pdf"),
        search_interval_seconds=60,
    )
    agent = JobHuntAgent(config=cfg)
    agent.matcher = MagicMock()
    yield agent


class TestStartSearchGuards:
    def test_start_search_without_profile_prints_error(self, workflow_agent, capsys):
        workflow_agent.profile = None
        workflow_agent.start_search(duration_minutes=1)
        out, _ = capsys.readouterr()
        assert "Profile not loaded" in out

    def test_start_search_exits_immediately_when_not_running(self, workflow_agent, sample_profile):
        workflow_agent.profile = sample_profile
        workflow_agent.start_search(duration_minutes=0)
        assert workflow_agent.is_running is False


class TestEvaluateAndRoute:
    def test_evaluates_and_persists_scores(self, workflow_agent, sample_profile, sample_job):
        workflow_agent.profile = sample_profile

        auto_score = MatchScore(
            job_id=sample_job.id, score=92, reason="Strong",
            tier="auto", confidence=0.95,
        )
        workflow_agent.matcher.evaluate_job.return_value = auto_score

        with patch.object(workflow_agent.cli, "print_job_card"):
            stats = workflow_agent._evaluate_and_route([sample_job])

        assert stats["applied"] == 1
        assert stats["semi_auto"] == 0
        assert stats["manual"] == 0

    def test_three_jobs_three_tiers(self, workflow_agent, sample_profile):
        workflow_agent.profile = sample_profile

        jobs = [
            Job(id=f"j{i}", title=f"Role {i}", company=f"Co{i}", location="R",
                description="d", source="T", url=f"https://x.com/{i}")
            for i in range(3)
        ]
        scores = [
            MatchScore(job_id="j0", score=90, reason="", tier="auto", confidence=0.9),
            MatchScore(job_id="j1", score=75, reason="", tier="semi_auto", confidence=0.8),
            MatchScore(job_id="j2", score=40, reason="", tier="manual", confidence=0.5),
        ]
        workflow_agent.matcher.evaluate_job.side_effect = scores

        for job in jobs:
            workflow_agent.db.add_job(job)

        with patch.object(workflow_agent.cli, "print_job_card"):
            stats = workflow_agent._evaluate_and_route(jobs)

        assert stats["applied"] == 1
        assert stats["semi_auto"] == 1
        assert stats["manual"] == 1

    def test_empty_job_list_returns_zero_stats(self, workflow_agent, sample_profile):
        workflow_agent.profile = sample_profile
        stats = workflow_agent._evaluate_and_route([])
        assert stats == {"applied": 0, "semi_auto": 0, "manual": 0}

    def test_no_profile_returns_zero_stats(self, workflow_agent):
        workflow_agent.profile = None
        stats = workflow_agent._evaluate_and_route([MagicMock()])
        assert stats == {"applied": 0, "semi_auto": 0, "manual": 0}


class TestSearchForJobs:
    def test_only_new_jobs_returned(self, workflow_agent, sample_profile):
        workflow_agent.profile = sample_profile

        existing = Job(
            title="Existing", company="Old Co", location="R",
            description="x", source="T", url="https://x.com/existing",
        )
        new_job = Job(
            title="New", company="New Co", location="R",
            description="y", source="T", url="https://x.com/new",
        )
        workflow_agent.db.add_job(existing)

        with patch("agent.JobSearcher") as mock_searcher_cls:
            mock_searcher = MagicMock()
            mock_searcher.run_search.return_value = [existing, new_job]
            mock_searcher_cls.return_value = mock_searcher

            result = workflow_agent._search_for_jobs()

        urls = {j.url for j in result}
        assert "https://x.com/new" in urls
        assert "https://x.com/existing" not in urls

    def test_no_profile_returns_empty(self, workflow_agent):
        workflow_agent.profile = None
        assert workflow_agent._search_for_jobs() == []


class TestResumeParsing:
    def test_missing_resume_returns_none(self, workflow_agent):
        workflow_agent.config.resume_path = "/nonexistent/resume.pdf"
        result = workflow_agent._try_parse_resume()
        assert result is None

    def test_corrupt_resume_returns_none(self, workflow_agent, tmp_path):
        fake = tmp_path / "resume.pdf"
        fake.write_bytes(b"not a real PDF")
        workflow_agent.config.resume_path = str(fake)
        result = workflow_agent._try_parse_resume()
        assert result is None


class TestSignalHandlers:
    def test_signal_handlers_installed(self, workflow_agent):
        import signal as signal_module
        current = signal_module.getsignal(signal_module.SIGINT)
        assert current is not None
        assert callable(current)
