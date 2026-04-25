"""Tests for matcher retry logic and edge cases."""
from unittest.mock import MagicMock, patch

from matcher import JobMatcher
from tests.conftest import TEST_API_KEY


def _matcher_with_responses(responses):
    """Build a matcher whose LLM raises/returns the given sequence."""
    fake_llm = MagicMock()
    fake_llm.generate.side_effect = responses
    with patch("matcher.build_provider", return_value=fake_llm):
        m = JobMatcher(api_key=TEST_API_KEY, provider="gemini")
    return m, fake_llm


class TestRetryLogic:
    def test_retries_on_429_error(self, sample_job, sample_profile):
        matcher, fake = _matcher_with_responses([
            Exception("429 Too Many Requests"),
            Exception("429 Too Many Requests"),
            '{"score": 85, "reason": "good", "tier": "auto", "confidence": 0.9}',
        ])
        with patch("matcher.time.sleep"):
            score = matcher.evaluate_job(sample_job, sample_profile)
        assert score.score == 85
        assert fake.generate.call_count == 3

    def test_non_retryable_error_fails_fast(self, sample_job, sample_profile):
        matcher, fake = _matcher_with_responses([Exception("Invalid API key")])
        with patch("matcher.time.sleep"):
            score = matcher.evaluate_job(sample_job, sample_profile)
        assert score.tier == "manual"
        assert score.score == 50

    def test_max_retries_exhausted(self, sample_job, sample_profile):
        matcher, fake = _matcher_with_responses([
            Exception("429 quota") for _ in range(3)
        ])
        with patch("matcher.time.sleep"):
            score = matcher.evaluate_job(sample_job, sample_profile)
        assert score.tier == "manual"
        assert score.score == 50
        assert fake.generate.call_count == matcher.MAX_RETRIES


class TestResponseParsing:
    def test_strips_markdown_fences(self, sample_job, sample_profile):
        matcher, _ = _matcher_with_responses([
            '```json\n{"score": 88, "reason": "x", "tier": "auto", "confidence": 0.9}\n```'
        ])
        score = matcher.evaluate_job(sample_job, sample_profile)
        assert score.score == 88
        assert score.tier == "auto"

    def test_clamps_score_above_100(self, sample_job, sample_profile):
        matcher, _ = _matcher_with_responses([
            '{"score": 150, "reason": "x", "tier": "auto", "confidence": 0.9}'
        ])
        score = matcher.evaluate_job(sample_job, sample_profile)
        assert score.score == 100

    def test_clamps_negative_score(self, sample_job, sample_profile):
        matcher, _ = _matcher_with_responses([
            '{"score": -20, "reason": "x", "tier": "manual", "confidence": 0.5}'
        ])
        score = matcher.evaluate_job(sample_job, sample_profile)
        assert score.score == 0

    def test_infers_tier_from_score_when_invalid(self, sample_job, sample_profile):
        matcher, _ = _matcher_with_responses([
            '{"score": 90, "reason": "x", "tier": "invalid_tier", "confidence": 0.9}'
        ])
        score = matcher.evaluate_job(sample_job, sample_profile)
        assert score.tier == "auto"

    def test_clamps_confidence_to_01_range(self, sample_job, sample_profile):
        matcher, _ = _matcher_with_responses([
            '{"score": 80, "reason": "x", "tier": "semi_auto", "confidence": 2.5}'
        ])
        score = matcher.evaluate_job(sample_job, sample_profile)
        assert 0.0 <= score.confidence <= 1.0


class TestFallbackMessages:
    def test_429_error_shortened(self):
        score = JobMatcher._fallback_score("j1", "429 quota exceeded on model X")
        assert "quota/rate limit hit" in score.reason

    def test_timeout_shortened(self):
        score = JobMatcher._fallback_score("j1", "Request timeout after 30s")
        assert "timeout" in score.reason

    def test_long_errors_truncated(self):
        long_err = "A" * 500
        score = JobMatcher._fallback_score("j1", long_err)
        assert len(score.reason) < 200
