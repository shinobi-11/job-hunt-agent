"""AI-powered profile builder — provider-agnostic via llm_providers.build_provider."""
import json
import logging
import re

from llm_providers import PROVIDERS, build_provider
from models import UserProfile

logger = logging.getLogger(__name__)


EXTRACTION_PROMPT = """You are an expert resume parser. Extract structured profile data.

=== RESUME TEXT ===
{resume_text}

=== OUTPUT FORMAT ===
Return ONLY valid JSON (no markdown, no prose):
{{
  "name": "<full name>",
  "email": "<email address>",
  "current_role": "<most recent job title>",
  "years_experience": <integer>,
  "desired_roles": [<3-5 next-step roles>],
  "skills": [<8-15 hard skills/tools>],
  "industries": [<1-3 industries>],
  "preferred_locations": [<1-3 likely target locations>],
  "remote_preference": "<remote|hybrid|on-site|any>",
  "company_size_preference": "<startup|scale-up|enterprise|any>"
}}

Guidelines:
- Be generous with desired_roles (Senior X, Staff X, Lead X)
- Skills = concrete tools/technologies, not soft skills
- India-based location → ["Bangalore","Remote","Gurugram"]
- <3 years exp → "any" company size
- Default remote_preference: "any"
"""


class ProfileBuilder:
    """Build a UserProfile from a resume using any supported LLM provider."""

    def __init__(self, api_key: str, provider: str = "gemini", model_name: str | None = None):
        if not api_key or len(api_key) < 20:
            raise ValueError("API key is required")
        self.provider = provider.lower()
        self.api_key = api_key
        self.model_name = model_name or PROVIDERS.get(self.provider, {}).get("default_model")
        self._llm = build_provider(self.provider, api_key, self.model_name)

    def build_from_resume(self, resume_text: str) -> UserProfile | None:
        """Extract profile from resume. Returns None on parse failure."""
        if not resume_text or not resume_text.strip():
            logger.warning("Empty resume text provided")
            return None

        prompt = EXTRACTION_PROMPT.format(resume_text=resume_text[:6000])

        try:
            raw = self._llm.generate(prompt)
            data = self._parse_response(raw)
            if not data:
                return None

            return UserProfile(
                name=str(data.get("name") or "Unknown")[:120],
                email=str(data.get("email") or "unknown@example.com")[:200],
                current_role=str(data.get("current_role") or "")[:120] or None,
                years_experience=int(data.get("years_experience") or 0),
                desired_roles=[str(r)[:80] for r in (data.get("desired_roles") or [])][:8],
                skills=[str(s)[:60] for s in (data.get("skills") or [])][:20],
                industries=[str(i)[:60] for i in (data.get("industries") or [])][:5],
                preferred_locations=[str(l)[:60] for l in (data.get("preferred_locations") or [])][:5],
                remote_preference=str(data.get("remote_preference") or "any"),
                company_size_preference=str(data.get("company_size_preference") or "any"),
                job_type=["full-time"],
                auto_apply_enabled=True,
            )
        except Exception as e:
            logger.error(f"Failed to build profile from resume: {e}")
            return None

    @staticmethod
    def _parse_response(text: str) -> dict | None:
        cleaned = (text or "").strip()
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
