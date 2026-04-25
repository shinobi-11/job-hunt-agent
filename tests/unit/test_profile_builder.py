"""Unit tests for profile_builder module."""
import json
from unittest.mock import MagicMock, patch

import pytest

from models import UserProfile
from profile_builder import ProfileBuilder
from tests.conftest import TEST_API_KEY


class TestProfileBuilder:
    def test_rejects_short_key(self):
        with pytest.raises(ValueError, match="GEMINI_API_KEY"):
            ProfileBuilder(api_key="short")

    def test_rejects_empty_key(self):
        with pytest.raises(ValueError, match="GEMINI_API_KEY"):
            ProfileBuilder(api_key="")

    def test_returns_none_on_empty_resume(self):
        with patch("profile_builder.genai.configure"):
            builder = ProfileBuilder(api_key=TEST_API_KEY)
            assert builder.build_from_resume("") is None
            assert builder.build_from_resume("   ") is None

    def test_builds_profile_from_gemini_response(self):
        mock_response = MagicMock()
        mock_response.text = json.dumps({
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

        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_response

        with patch("profile_builder.genai.GenerativeModel", return_value=mock_model), \
             patch("profile_builder.genai.configure"):
            builder = ProfileBuilder(api_key=TEST_API_KEY)
            builder.model = mock_model

            profile = builder.build_from_resume("Alice is a senior engineer...")

            assert isinstance(profile, UserProfile)
            assert profile.name == "Alice Engineer"
            assert profile.years_experience == 5
            assert "Python" in profile.skills
            assert profile.remote_preference == "remote"

    def test_handles_markdown_fenced_json(self):
        mock_response = MagicMock()
        mock_response.text = """```json
{"name": "Bob", "email": "b@b.com", "years_experience": 3,
 "desired_roles": ["Dev"], "skills": ["Go"], "industries": ["Tech"],
 "preferred_locations": ["Remote"], "remote_preference": "remote",
 "current_role": "Dev", "company_size_preference": "any"}
```"""

        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_response

        with patch("profile_builder.genai.GenerativeModel", return_value=mock_model), \
             patch("profile_builder.genai.configure"):
            builder = ProfileBuilder(api_key=TEST_API_KEY)
            builder.model = mock_model

            profile = builder.build_from_resume("Bob is a developer")
            assert profile is not None
            assert profile.name == "Bob"

    def test_returns_none_on_unparseable_json(self):
        mock_response = MagicMock()
        mock_response.text = "not json at all, just prose"

        mock_model = MagicMock()
        mock_model.generate_content.return_value = mock_response

        with patch("profile_builder.genai.GenerativeModel", return_value=mock_model), \
             patch("profile_builder.genai.configure"):
            builder = ProfileBuilder(api_key=TEST_API_KEY)
            builder.model = mock_model

            profile = builder.build_from_resume("Some resume")
            assert profile is None

    def test_gemini_error_returns_none(self):
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = Exception("API down")

        with patch("profile_builder.genai.GenerativeModel", return_value=mock_model), \
             patch("profile_builder.genai.configure"):
            builder = ProfileBuilder(api_key=TEST_API_KEY)
            builder.model = mock_model

            profile = builder.build_from_resume("Some resume")
            assert profile is None
