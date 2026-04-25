"""Job matching engine — delegates generation to a pluggable LLM provider."""
from __future__ import annotations

import json
import logging
import time

from llm_providers import LLMProvider, PROVIDERS, build_provider
from models import Job, MatchScore, UserProfile

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_VERSION = "v1.1.0"

MATCH_PROMPT_TEMPLATE = """You are an expert technical recruiter evaluating job-candidate fit.

Analyze the following job posting against the candidate's profile and return a structured JSON score.

=== CANDIDATE PROFILE ===
Name: {name}
Current Role: {current_role}
Years of Experience: {years_experience}
Desired Roles: {desired_roles}
Skills: {skills}
Preferred Locations: {preferred_locations}
Remote Preference: {remote_preference}
Salary Expectation: {salary_range}
Industries of Interest: {industries}
Company Size Preference: {company_size}
Willing to Relocate: {willing_to_relocate}

=== JOB POSTING ===
Title: {job_title}
Company: {company}
Location: {location}
Remote: {remote}
Salary: {salary}
Description: {description}
Requirements: {requirements}

=== SCORING RUBRIC ===
- 85-100 (AUTO tier): Strong fit. Critical skills match, location/remote acceptable, salary aligned.
- 70-84 (SEMI_AUTO tier): Good fit with minor gaps. Most skills present, trainable gaps.
- 0-69 (MANUAL tier): Unclear fit. Missing core skills, or niche/unusual requirements.

=== OUTPUT FORMAT ===
Return ONLY valid JSON matching this schema (no markdown, no prose):
{{
  "score": <integer 0-100>,
  "reason": "<brief 1-2 sentence explanation of overall fit>",
  "matched_skills": [<list of skills from profile that match job requirements>],
  "missing_skills": [<list of required skills NOT in profile>],
  "cultural_fit": "<assessment of company/role culture fit>",
  "salary_alignment": "<salary analysis: aligned, below, above, or unknown>",
  "tier": "<auto|semi_auto|manual>",
  "confidence": <float 0.0-1.0, how confident in this score>
}}"""


class JobMatcher:
    """LLM-powered job matching engine with retry and fallback logic."""

    RETRYABLE_ERROR_KEYWORDS = (
        "resourceexhausted", "deadlineexceeded", "unavailable",
        "timeout", "429", "503", "rate limit", "overloaded",
    )
    MAX_RETRIES = 3
    BACKOFF_BASE = 2.0

    def __init__(
        self,
        api_key: str,
        model_name: str | None = None,
        provider: str = "gemini",
    ):
        if not api_key or len(api_key) < 20:
            raise ValueError(f"{provider.upper()}_API_KEY is missing or too short")

        self.provider_name = provider
        self.api_key = api_key
        self.model_name = model_name or PROVIDERS.get(provider, {}).get("default_model", "unknown")
        self._llm: LLMProvider = build_provider(provider, api_key, self.model_name)
        logger.info(
            f"JobMatcher initialized — provider={provider} model={self.model_name} "
            f"(prompt {SYSTEM_PROMPT_VERSION})"
        )

    @classmethod
    def from_profile(cls, profile: UserProfile, env_fallback_key: str | None = None) -> "JobMatcher":
        """Prefer the user's chosen provider + key; fall back to env var for backwards compat."""
        provider = (getattr(profile, "llm_provider", None) or "gemini").lower()
        key = getattr(profile, "llm_api_key", None) or env_fallback_key
        if not key:
            raise ValueError(
                f"No API key available for provider={provider}. "
                f"Set one in the profile or provide a fallback."
            )
        return cls(api_key=key, provider=provider)

    def evaluate_job(self, job: Job, profile: UserProfile) -> MatchScore:
        """Evaluate a job. Retries transient errors, falls back to manual on failure."""
        prompt = self._build_prompt(job, profile)

        for attempt in range(self.MAX_RETRIES):
            try:
                raw = self._llm.generate(prompt)
                return self._parse_response(raw, job.id)
            except Exception as e:
                error_str = str(e).lower()
                is_retryable = any(kw in error_str for kw in self.RETRYABLE_ERROR_KEYWORDS)

                if is_retryable and attempt < self.MAX_RETRIES - 1:
                    delay = self.BACKOFF_BASE ** (attempt + 1)
                    logger.warning(
                        f"{self.provider_name} error (attempt {attempt + 1}/{self.MAX_RETRIES}), "
                        f"retrying in {delay}s: {e}"
                    )
                    time.sleep(delay)
                    continue

                logger.error(f"{self.provider_name} evaluation failed for {job.title}: {e}")
                return self._fallback_score(job.id, str(e))

        return self._fallback_score(job.id, "Max retries exceeded")

    def batch_evaluate(self, jobs: list[Job], profile: UserProfile) -> list[MatchScore]:
        return [self.evaluate_job(job, profile) for job in jobs]

    def _build_prompt(self, job: Job, profile: UserProfile) -> str:
        salary_range = "Not specified"
        if profile.salary_min and profile.salary_max:
            cur = profile.salary_currency or "USD"
            salary_range = f"{cur} {int(profile.salary_min):,} - {int(profile.salary_max):,}"

        job_salary = "Not specified"
        if job.salary_min and job.salary_max:
            job_salary = f"${int(job.salary_min):,} - ${int(job.salary_max):,} {job.currency or ''}"

        return MATCH_PROMPT_TEMPLATE.format(
            name=profile.name,
            current_role=profile.current_role or "Not specified",
            years_experience=profile.years_experience,
            desired_roles=", ".join(profile.desired_roles) or "Any",
            skills=", ".join(profile.skills) or "Not specified",
            preferred_locations=", ".join(profile.preferred_locations) or "Any",
            remote_preference=profile.remote_preference,
            salary_range=salary_range,
            industries=", ".join(profile.industries) or "Any",
            company_size=profile.company_size_preference or "Any",
            willing_to_relocate="Yes" if profile.willing_to_relocate else "No",
            job_title=job.title,
            company=job.company,
            location=job.location,
            remote=job.remote or "Not specified",
            salary=job_salary,
            description=job.description[:1500],
            requirements=", ".join(job.requirements) if job.requirements else "Not listed",
        )

    def _parse_response(self, response_text: str, job_id: str) -> MatchScore:
        text = (response_text or "").strip()

        if "```json" in text:
            text = text.split("```json", 1)[1].split("```", 1)[0]
        elif "```" in text:
            text = text.split("```", 1)[1].split("```", 1)[0]
        text = text.strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"Malformed JSON from {self.provider_name}: {e}\nResponse: {text[:200]}")
            return self._fallback_score(job_id, "Malformed AI response")

        score = int(data.get("score", 0))
        score = max(0, min(100, score))

        tier = data.get("tier", "manual")
        if tier not in {"auto", "semi_auto", "manual"}:
            tier = self._infer_tier(score)

        confidence = float(data.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))

        return MatchScore(
            job_id=job_id,
            score=score,
            reason=data.get("reason", "No reasoning provided"),
            matched_skills=list(data.get("matched_skills", [])),
            missing_skills=list(data.get("missing_skills", [])),
            cultural_fit=data.get("cultural_fit"),
            salary_alignment=data.get("salary_alignment"),
            tier=tier,
            confidence=confidence,
        )

    @staticmethod
    def _infer_tier(score: int) -> str:
        if score >= 85:
            return "auto"
        if score >= 70:
            return "semi_auto"
        return "manual"

    @staticmethod
    def _fallback_score(job_id: str, error_context: str) -> MatchScore:
        short_error = error_context.split("\n")[0][:120]
        lower = error_context.lower()
        if "429" in lower or "quota" in lower or "rate limit" in lower:
            short_error = "LLM quota/rate limit hit"
        elif "timeout" in lower:
            short_error = "LLM API timeout"
        elif "malformed" in lower:
            short_error = "Malformed AI response"
        elif "unauthorized" in lower or "401" in lower or "403" in lower:
            short_error = "Invalid API key (check settings)"

        return MatchScore(
            job_id=job_id,
            score=50,
            reason=f"AI evaluation unavailable ({short_error}) — manual review required",
            matched_skills=[],
            missing_skills=[],
            cultural_fit=None,
            salary_alignment=None,
            tier="manual",
            confidence=0.0,
        )
