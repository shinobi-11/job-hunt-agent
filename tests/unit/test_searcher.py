"""Unit tests for searcher module."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models import Job, UserProfile
from searcher import JobSearcher, _parse_salary_range, _strip_html


class TestQueryBuilding:
    def test_uses_only_desired_roles_not_industries(self, sample_profile):
        """User-supplied jobs only — no auto-derivation from industries."""
        searcher = JobSearcher(sample_profile)
        for role in sample_profile.desired_roles:
            assert role in searcher.queries
        for industry in sample_profile.industries:
            assert industry not in searcher.queries

    def test_deduplicates_queries(self):
        profile = UserProfile(
            name="Test",
            email="t@t.com",
            desired_roles=["Engineer", "Engineer", "Developer"],
        )
        searcher = JobSearcher(profile)
        assert searcher.queries.count("Engineer") == 1
        assert "Developer" in searcher.queries

    def test_caps_queries_at_ten(self):
        profile = UserProfile(
            name="Test",
            email="t@t.com",
            desired_roles=[f"Role{i}" for i in range(15)],
        )
        searcher = JobSearcher(profile)
        assert len(searcher.queries) <= 10


class TestSalaryFilter:
    def test_filter_rejects_low_salary(self):
        profile = UserProfile(
            name="T", email="t@t.com",
            desired_roles=["Engineer"],
            current_salary=100000,
            salary_min=120000,
            salary_max=140000,
            strict_salary_filter=True,
        )
        searcher = JobSearcher(profile)
        low = Job(
            title="Engineer", company="X", location="R",
            salary_min=60000, salary_max=80000,
            description="d", source="T", url="https://x.com/low",
        )
        assert searcher._passes_salary_filter(low) is False

    def test_filter_accepts_in_range(self):
        profile = UserProfile(
            name="T", email="t@t.com",
            desired_roles=["Engineer"],
            current_salary=100000,
            salary_min=120000,
            salary_max=140000,
            strict_salary_filter=True,
        )
        searcher = JobSearcher(profile)
        good = Job(
            title="Engineer", company="X", location="R",
            salary_min=125000, salary_max=145000,
            description="d", source="T", url="https://x.com/good",
        )
        assert searcher._passes_salary_filter(good) is True

    def test_filter_accepts_unknown_salary(self):
        profile = UserProfile(
            name="T", email="t@t.com",
            desired_roles=["Engineer"],
            salary_min=120000,
            strict_salary_filter=True,
        )
        searcher = JobSearcher(profile)
        unknown = Job(
            title="Engineer", company="X", location="R",
            salary_min=None, salary_max=None,
            description="d", source="T", url="https://x.com/unknown",
        )
        assert searcher._passes_salary_filter(unknown) is True


class TestExpectedSalaryComputation:
    def test_hike_range_computes_expected_range(self):
        profile = UserProfile(
            name="T", email="t@t.com",
            current_salary=1000000,
            hike_percent_min=20,
            hike_percent_max=50,
        )
        profile.compute_expected_salary()
        assert profile.salary_min == 1200000
        assert profile.salary_max == 1500000

    def test_no_current_salary_leaves_range_none(self):
        profile = UserProfile(name="T", email="t@t.com")
        profile.compute_expected_salary()
        assert profile.salary_min is None
        assert profile.salary_max is None


class TestRelevanceScore:
    def test_matches_desired_role_in_title(self, sample_profile):
        searcher = JobSearcher(sample_profile)
        job = Job(
            title="Senior Software Engineer",
            company="A",
            location="Remote",
            description="Python role",
            source="Test",
            url="https://x.com/1",
        )
        assert searcher._relevance_score(job) >= 5

    def test_matches_skill_in_description(self, sample_profile):
        searcher = JobSearcher(sample_profile)
        job = Job(
            title="Backend Dev",
            company="A",
            location="Remote",
            description="We use Python, React, AWS",
            source="Test",
            url="https://x.com/2",
        )
        assert searcher._relevance_score(job) >= 2

    def test_zero_score_for_unrelated(self, sample_profile):
        searcher = JobSearcher(sample_profile)
        job = Job(
            title="Barista",
            company="Coffee Shop",
            location="Main St",
            description="Make espresso",
            source="Test",
            url="https://x.com/3",
        )
        assert searcher._relevance_score(job) == 0


class TestHtmlStripping:
    def test_strips_tags(self):
        html = "<p>Hello <b>World</b></p>"
        assert _strip_html(html) == "Hello World"

    def test_collapses_whitespace(self):
        html = "<p>Hello\n\n\t  World</p>"
        assert _strip_html(html) == "Hello World"

    def test_empty_returns_empty(self):
        assert _strip_html("") == ""

    def test_no_tags_passes_through(self):
        assert _strip_html("Plain text") == "Plain text"


class TestSalaryParsing:
    def test_parses_dollar_range(self):
        low, high = _parse_salary_range("$50,000 - $80,000")
        assert low == 50000
        assert high == 80000

    def test_parses_k_notation(self):
        low, high = _parse_salary_range("80k-120k")
        assert low == 80000
        assert high == 120000

    def test_parses_single_value(self):
        low, high = _parse_salary_range("$100000")
        assert low == high == 100000

    def test_empty_returns_none(self):
        low, high = _parse_salary_range("")
        assert low is None
        assert high is None

    def test_unparseable_returns_none(self):
        low, high = _parse_salary_range("competitive")
        assert low is None
        assert high is None


class TestSearchIntegration:
    @patch("searcher.aiohttp.ClientSession")
    def test_all_sources_failing_returns_empty(self, mock_session_cls, sample_profile):
        """When all HTTP sources fail, searcher returns empty list, not raises."""
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        mock_response = MagicMock()
        mock_response.status = 500
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = MagicMock(return_value=mock_response)

        mock_session_cls.return_value = mock_session

        searcher = JobSearcher(sample_profile)
        jobs = searcher.run_search()
        assert jobs == []
