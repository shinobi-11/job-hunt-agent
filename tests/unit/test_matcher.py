"""Unit tests for matcher module."""
import json
from unittest.mock import MagicMock, patch

import pytest

from matcher import JobMatcher
from models import MatchScore
from tests.conftest import TEST_API_KEY


def _patched_matcher(provider="gemini", llm_response='{"score": 92, "reason": "great", "matched_skills": ["Python"], "missing_skills": [], "tier": "auto", "confidence": 0.95}'):
    """Build a matcher whose LLM provider returns the given canned text."""
    fake_llm = MagicMock()
    fake_llm.generate.return_value = llm_response
    fake_llm.name = provider

    with patch("matcher.build_provider", return_value=fake_llm):
        m = JobMatcher(api_key=TEST_API_KEY, provider=provider)
    return m, fake_llm


class TestJobMatcher:
    def test_matcher_rejects_missing_key(self):
        with pytest.raises(ValueError, match="API_KEY"):
            JobMatcher(api_key="")

    def test_matcher_rejects_short_key(self):
        with pytest.raises(ValueError, match="API_KEY"):
            JobMatcher(api_key="short")

    def test_evaluate_job_returns_match_score(self, sample_job, sample_profile):
        matcher, _ = _patched_matcher()
        score = matcher.evaluate_job(sample_job, sample_profile)

        assert isinstance(score, MatchScore)
        assert score.job_id == sample_job.id
        assert score.score == 92
        assert score.tier == "auto"

    def test_evaluate_job_handles_malformed_response(self, sample_job, sample_profile):
        matcher, _ = _patched_matcher(llm_response="not valid json")
        score = matcher.evaluate_job(sample_job, sample_profile)

        assert score.tier == "manual"
        assert score.score == 50

    def test_batch_evaluate(self, sample_job, sample_profile):
        matcher, _ = _patched_matcher()
        scores = matcher.batch_evaluate([sample_job, sample_job], sample_profile)

        assert len(scores) == 2
        assert all(isinstance(s, MatchScore) for s in scores)

    def test_infer_tier_boundaries(self):
        assert JobMatcher._infer_tier(100) == "auto"
        assert JobMatcher._infer_tier(85) == "auto"
        assert JobMatcher._infer_tier(84) == "semi_auto"
        assert JobMatcher._infer_tier(70) == "semi_auto"
        assert JobMatcher._infer_tier(69) == "manual"
        assert JobMatcher._infer_tier(0) == "manual"

    def test_fallback_score_safe_defaults(self):
        fallback = JobMatcher._fallback_score("job_123", "API timeout")
        assert fallback.job_id == "job_123"
        assert fallback.score == 50
        assert fallback.tier == "manual"
        assert fallback.confidence == 0.0

    def test_fallback_message_for_quota(self):
        f = JobMatcher._fallback_score("j", "429 quota exceeded")
        assert "quota/rate limit hit" in f.reason

    def test_fallback_message_for_unauthorized(self):
        f = JobMatcher._fallback_score("j", "401 Unauthorized")
        assert "Invalid API key" in f.reason

    def test_provider_selection_via_factory(self, sample_job, sample_profile):
        matcher, fake = _patched_matcher(provider="openai")
        assert matcher.provider_name == "openai"
        score = matcher.evaluate_job(sample_job, sample_profile)
        fake.generate.assert_called_once()
        assert score.score == 92

    def test_from_profile_uses_profile_key(self, sample_profile):
        sample_profile.llm_provider = "anthropic"
        sample_profile.llm_api_key = TEST_API_KEY
        with patch("matcher.build_provider") as bp:
            bp.return_value = MagicMock()
            m = JobMatcher.from_profile(sample_profile)
            assert m.provider_name == "anthropic"
            bp.assert_called_once()

    def test_from_profile_falls_back_to_env_key(self, sample_profile):
        sample_profile.llm_provider = "gemini"
        sample_profile.llm_api_key = None
        with patch("matcher.build_provider") as bp:
            bp.return_value = MagicMock()
            m = JobMatcher.from_profile(sample_profile, env_fallback_key=TEST_API_KEY)
            assert m.api_key == TEST_API_KEY
