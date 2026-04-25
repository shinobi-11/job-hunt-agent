"""Tests for async searcher source methods."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from searcher import JobSearcher


class _AsyncResponse:
    def __init__(self, status: int, payload):
        self.status = status
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def json(self, content_type=None):
        return self._payload


def _mock_session(responses: dict):
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    def get(url, *args, **kwargs):
        for pattern, response in responses.items():
            if pattern in url:
                return response
        return _AsyncResponse(500, {})

    session.get = MagicMock(side_effect=get)
    return session


class TestRemoteOK:
    @pytest.mark.asyncio
    async def test_parses_valid_payload(self, sample_profile):
        payload = [
            {"legal": "disclaimer"},
            {
                "id": "1",
                "position": "Senior Engineer",
                "company": "Acme",
                "location": "Remote",
                "tags": ["python", "aws"],
                "description": "<p>Great role</p>",
                "url": "https://remoteok.com/job/1",
                "salary_min": 120000,
                "salary_max": 180000,
            },
        ]
        session = MagicMock()
        session.get = MagicMock(return_value=_AsyncResponse(200, payload))

        searcher = JobSearcher(sample_profile)
        jobs = await searcher._search_remoteok(session)
        assert len(jobs) == 1
        assert jobs[0].title == "Senior Engineer"
        assert jobs[0].company == "Acme"
        assert "Great role" in jobs[0].description
        assert jobs[0].salary_min == 120000

    @pytest.mark.asyncio
    async def test_handles_non_200_status(self, sample_profile):
        session = MagicMock()
        session.get = MagicMock(return_value=_AsyncResponse(500, {}))

        searcher = JobSearcher(sample_profile)
        jobs = await searcher._search_remoteok(session)
        assert jobs == []


class TestRemotive:
    @pytest.mark.asyncio
    async def test_parses_valid_payload(self, sample_profile):
        payload = {
            "jobs": [
                {
                    "id": 100,
                    "title": "Staff Engineer",
                    "company_name": "Bigco",
                    "candidate_required_location": "Worldwide",
                    "description": "<p>Lead role</p>",
                    "url": "https://remotive.com/job/100",
                    "category": "Software Development",
                    "salary": "$150k - $200k",
                }
            ]
        }
        session = MagicMock()
        session.get = MagicMock(return_value=_AsyncResponse(200, payload))

        searcher = JobSearcher(sample_profile)
        jobs = await searcher._search_remotive(session)
        assert len(jobs) == 1
        assert jobs[0].title == "Staff Engineer"
        assert jobs[0].salary_min == 150000
        assert jobs[0].salary_max == 200000


class TestJobicy:
    @pytest.mark.asyncio
    async def test_parses_valid_payload(self, sample_profile):
        payload = {
            "jobs": [
                {
                    "id": "abc",
                    "jobTitle": "Data Scientist",
                    "companyName": "DataCo",
                    "jobGeo": ["USA", "Canada"],
                    "jobDescription": "<h1>Science</h1>",
                    "url": "https://jobicy.com/job/abc",
                    "jobIndustry": ["Tech"],
                    "salaryCurrency": "USD",
                    "annualSalaryMin": 120000,
                    "annualSalaryMax": 160000,
                }
            ]
        }
        session = MagicMock()
        session.get = MagicMock(return_value=_AsyncResponse(200, payload))

        searcher = JobSearcher(sample_profile)
        jobs = await searcher._search_jobicy(session)
        assert len(jobs) == 1
        assert jobs[0].title == "Data Scientist"
        assert "USA" in jobs[0].location


class TestHimalayas:
    @pytest.mark.asyncio
    async def test_parses_valid_payload(self, sample_profile):
        payload = {
            "jobs": [
                {
                    "slug": "senior-dev",
                    "title": "Senior Developer",
                    "companyName": "MountainCo",
                    "locationRestrictions": ["Worldwide"],
                    "excerpt": "Great team!",
                    "minSalary": 100000,
                    "maxSalary": 140000,
                    "categories": ["Engineering"],
                }
            ]
        }
        session = MagicMock()
        session.get = MagicMock(return_value=_AsyncResponse(200, payload))

        searcher = JobSearcher(sample_profile)
        jobs = await searcher._search_himalayas(session)
        assert len(jobs) == 1
        assert jobs[0].title == "Senior Developer"


class TestSourceResilience:
    @pytest.mark.asyncio
    async def test_malformed_entry_is_skipped(self, sample_profile):
        payload = [
            {"legal": "x"},
            {"id": "valid", "position": "Job", "company": "Co", "location": "R",
             "description": "x", "url": "https://x.com/v"},
            {},
            "string instead of dict",
        ]
        session = MagicMock()
        session.get = MagicMock(return_value=_AsyncResponse(200, payload))

        searcher = JobSearcher(sample_profile)
        jobs = await searcher._search_remoteok(session)
        assert len(jobs) >= 1

    @pytest.mark.asyncio
    async def test_network_exception_returns_empty(self, sample_profile):
        session = MagicMock()
        session.get = MagicMock(side_effect=Exception("Network down"))

        searcher = JobSearcher(sample_profile)
        jobs = await searcher._search_remoteok(session)
        assert jobs == []
