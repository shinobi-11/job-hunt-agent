"""Unit tests for profile_builder module."""
import json
from unittest.mock import MagicMock, patch

import pytest

from models import UserProfile
from profile_builder import ProfileBuilder
from tests.conftest import TEST_API_KEY


def _patched_builder(response_text):
    """Build a ProfileBuilder whose LLM returns the given canned text."""
    fake_llm = MagicMock()
    fake_llm.generate.return_value = response_text
    fake_llm.name = "gemini"
    with patch("profile_builder.build_provider", return_value=fake_llm):
        b = ProfileBuilder(api_key=TEST_API_KEY)
    return b, fake_llm


class TestProfileBuilder:
    def test_rejects_short_key(self):
        with pytest.raises(ValueError, match="API key"):
            ProfileBuilder(api_key="short")

    def test_rejects_empty_key(self):
        with pytest.raises(ValueError, match="API key"):
            ProfileBuilder(api_key="")

    def test_returns_none_on_empty_resume(self):
        b, _ = _patched_builder("{}")
        assert b.build_from_resume("") is None
        assert b.build_from_resume("   ") is None

    def test_builds_profile_from_gemini_response(self):
        payload = json.dumps({
            "name": "Alice Engineer",
            "email": "alice@example.com",
            "current_role": "Software Engineer",
            "years_experience": 5,
            "desired_roles": ["Senior SWE", "Staff SWE"],
            "skills": ["Python", "AWS", "React"],
            "industries": ["Technology"],
            "preferred_locations": ["San Francisco", "Remote"],
            "remote_preference": "remote",
            "company_size_preference": "scale-up",
        })
        b, _ = _patched_builder(payload)
        profile = b.build_from_resume("Alice is a senior engineer...")

        assert isinstance(profile, UserProfile)
        assert profile.name == "Alice Engineer"
        assert profile.years_experience == 5
        assert "Python" in profile.skills
        assert profile.remote_preference == "remote"

    def test_handles_markdown_fenced_json(self):
        text = """```json
{"name": "Bob", "email": "b@b.com", "years_experience": 3,
 "desired_roles": ["Dev"], "skills": ["Go"], "industries": ["Tech"],
 "preferred_locations": ["Remote"], "remote_preference": "remote",
 "current_role": "Dev", "company_size_preference": "any"}
```"""
        b, _ = _patched_builder(text)
        profile = b.build_from_resume("Bob is a developer")
        assert profile is not None
        assert profile.name == "Bob"

    def test_returns_none_on_unparseable_json(self):
        b, _ = _patched_builder("not json at all, just prose")
        assert b.build_from_resume("Some resume") is None

    def test_provider_error_returns_none(self):
        fake_llm = MagicMock()
        fake_llm.generate.side_effect = Exception("API down")
        with patch("profile_builder.build_provider", return_value=fake_llm):
            b = ProfileBuilder(api_key=TEST_API_KEY)
        assert b.build_from_resume("Some resume") is None
