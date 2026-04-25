"""AI-powered profile builder that extracts UserProfile from resume text using Gemini."""
import json
import logging
import re

import google.generativeai as genai

from models import UserProfile

logger = logging.getLogger(__name__)


EXTRACTION_PROMPT = """You are an expert resume parser. Extract structured profile data from this resume.

=== RESUME TEXT ===
{resume_text}

=== OUTPUT FORMAT ===
Return ONLY valid JSON matching this schema (no markdown, no prose):
{{
  "name": "<full name>",
  "email": "<email address>",
  "current_role": "<most recent job title>",
  "years_experience": <integer total years of professional experience>,
  "desired_roles": [<list of 3-5 roles this person should target based on their background>],
  "skills": [<list of 8-15 hard skills and tools from resume>],
  "industries": [<list of 1-3 industries relevant to their background>],
  "preferred_locations": [<list of 1-3 likely target locations based on current location>],
  "remote_preference": "<remote|hybrid|on-site|any>",
  "company_size_preference": "<startup|scale-up|enterprise|any>"
}}

Guidelines:
- Be generous with desired_roles — include natural next-step roles (e.g., Senior X, Staff X, Lead X)
- Skills should be concrete tools/technologies, not soft skills
- If current location is in India, default preferred_locations to ["Bangalore", "Remote", "Gurugram"]
- If the person has <3 years experience, suggest "any" for company size
- Default remote_preference to "any" unless resume suggests otherwise"""


class ProfileBuilder:
    """Build a UserProfile from a resume using Gemini."""

    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash"):
        if not api_key or len(api_key) < 30:
            raise ValueError("GEMINI_API_KEY is required")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)

    def build_from_resume(self, resume_text: str) -> UserProfile | None:
        """Extract profile from resume. Returns None on parse failure."""
        if not resume_text.strip():
            logger.warning("Empty resume text provided")
            return None

        prompt = EXTRACTION_PROMPT.format(resume_text=resume_text[:8000])

        try:
            response = self.model.generate_content(prompt)
            data = self._parse_response(response.text)
            if not data:
                return None

            return UserProfile(
                name=data.get("name", "Unknown"),
                email=data.get("email", "unknown@example.com"),
                current_role=data.get("current_role"),
                years_experience=int(data.get("years_experience", 0)),
                desired_roles=list(data.get("desired_roles", [])),
                skills=list(data.get("skills", [])),
                industries=list(data.get("industries", [])),
                preferred_locations=list(data.get("preferred_locations", [])),
                remote_preference=data.get("remote_preference", "any"),
                company_size_preference=data.get("company_size_preference"),
                job_type=["full-time"],
                auto_apply_enabled=True,
            )
        except Exception as e:
            logger.error(f"Failed to build profile from resume: {e}")
            return None

    @staticmethod
    def _parse_response(text: str) -> dict | None:
        """Strip markdown fences and parse JSON."""
        cleaned = text.strip()
        if "```json" in cleaned:
            cleaned = cleaned.split("```json", 1)[1].split("```", 1)[0]
        elif "```" in cleaned:
            cleaned = cleaned.split("```", 1)[1].split("```", 1)[0]
        cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", cleaned)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError as e:
                    logger.error(f"Could not parse profile JSON: {e}")
        return None
