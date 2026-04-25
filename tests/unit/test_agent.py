"""Unit tests for agent orchestrator."""
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from agent import CredentialGateError, JobHuntAgent
from config import Config
from models import Application, ApplicationStatus, Job, MatchScore, UserProfile
from tests.conftest import TEST_API_KEY


@pytest.fixture
def agent_config(tmp_path):
    return Config(
        gemini_api_key=TEST_API_KEY,
        database_path=str(tmp_path / "jobs.db"),
        log_path=str(tmp_path / "agent.log"),
        resume_path=str(tmp_path / "resume.pdf"),
    )


@pytest.fixture
def agent(agent_config):
    a = JobHuntAgent(config=agent_config)
    a.matcher = MagicMock()  # stub so agent doesn't try to hit a real LLM
    yield a


class TestCredentialGate:
    """Credential gate now fires inside _ensure_matcher() rather than __init__."""

    def test_no_profile_no_gate(self, tmp_path):
        cfg = Config(
            gemini_api_key="",
            database_path=str(tmp_path / "j.db"),
            log_path=str(tmp_path / "a.log"),
        )
        agent = JobHuntAgent(config=cfg)
        assert agent.profile is None
        assert agent.matcher is None

    def test_ensure_matcher_raises_when_no_key(self, tmp_path, sample_profile):
        cfg = Config(
            gemini_api_key="",
            database_path=str(tmp_path / "j.db"),
            log_path=str(tmp_path / "a.log"),
        )
        agent = JobHuntAgent(config=cfg)
        sample_profile.llm_api_key = None
        agent.profile = sample_profile
        with pytest.raises(CredentialGateError):
            agent._ensure_matcher()


class TestRouting:
    def test_auto_tier_creates_auto_applied(self, agent, sample_job):
        agent.profile = UserProfile(
            name="T", email="t@t.com", auto_apply_enabled=True
        )
        score = MatchScore(
            job_id=sample_job.id, score=92, reason="", tier="auto", confidence=0.95
        )
        app = agent._route_application(sample_job, score)
        assert app.status == ApplicationStatus.AUTO_APPLIED
        assert app.applied_at is not None
        assert app.applied_by == "system"

    def test_auto_tier_without_consent_stays_pending(self, agent, sample_job):
        agent.profile = UserProfile(
            name="T", email="t@t.com", auto_apply_enabled=False
        )
        score = MatchScore(
            job_id=sample_job.id, score=92, reason="", tier="auto", confidence=0.95
        )
        app = agent._route_application(sample_job, score)
        assert app.status == ApplicationStatus.MANUAL_FLAG

    def test_semi_auto_tier_is_pending(self, agent, sample_job, sample_profile):
        agent.profile = sample_profile
        score = MatchScore(
            job_id=sample_job.id, score=75, reason="", tier="semi_auto", confidence=0.8
        )
        app = agent._route_application(sample_job, score)
        assert app.status == ApplicationStatus.PENDING
        assert app.applied_at is None

    def test_manual_tier_flagged(self, agent, sample_job, sample_profile):
        agent.profile = sample_profile
        score = MatchScore(
            job_id=sample_job.id, score=40, reason="", tier="manual", confidence=0.6
        )
        app = agent._route_application(sample_job, score)
        assert app.status == ApplicationStatus.MANUAL_FLAG


class TestLifecycle:
    def test_pause_sets_flag(self, agent):
        agent.is_paused = False
        agent.pause()
        assert agent.is_paused is True

    def test_resume_clears_flag(self, agent):
        agent.is_paused = True
        agent.resume()
        assert agent.is_paused is False

    def test_stop_clears_running(self, agent):
        agent.is_running = True
        agent.stop()
        assert agent.is_running is False

    def test_initialize_loads_existing_profile(self, agent, sample_profile):
        from agent import CLI_USER_ID
        sample_profile.llm_api_key = TEST_API_KEY
        agent.db.save_profile(sample_profile, user_id=CLI_USER_ID)
        with patch.object(agent.cli, "print_header"), \
             patch.object(agent.cli, "print_profile"), \
             patch.object(agent, "_ensure_matcher"):
            agent.initialize()
        assert agent.profile is not None
        assert agent.profile.email == sample_profile.email


class TestShowMethods:
    def test_show_applications_calls_cli(self, agent, sample_application):
        from agent import CLI_USER_ID
        agent.db.save_profile(UserProfile(name="T", email="t@t.com"), user_id=CLI_USER_ID)
        agent.db.add_job(Job(
            title="J", company="C", location="L", description="d",
            source="S", url="https://x.com/1",
        ), user_id=CLI_USER_ID)
        with patch.object(agent.cli, "print_applications_table") as mock_print:
            agent.show_applications()
            mock_print.assert_called_once()

    def test_show_stats_calls_cli(self, agent):
        with patch.object(agent.cli, "print_search_status") as mock_print:
            agent.show_stats()
            mock_print.assert_called_once()
