"""Job matching engine — delegates generation to a pluggable LLM provider."""
from __future__ import annotations

import json
import logging
import time

from llm_providers import LLMProvider, PROVIDERS, build_provider
from models import Job, MatchScore, UserProfile

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_VERSION = "v1.1.0"

MATCH_PROMPT_TEMPLATE = """Score this job-candidate fit. Return ONLY JSON.

CANDIDATE
Roles wanted: {desired_roles}
Skills: {skills}
Exp: {years_experience}y as {current_role}
Locations: {preferred_locations} | Remote: {remote_preference}
Salary: {salary_range}

JOB
{job_title} @ {company}
Location: {location} | Remote: {remote}
Salary: {salary}
{description}
Req: {requirements}

RUBRIC
85-100 = strong fit (critical skills + location + salary all match) → "auto"
70-84 = good fit, minor trainable gaps → "semi_auto"
<70 = poor fit → "manual"

JSON ONLY (no markdown):
{{"score":int,"tier":"auto|semi_auto|manual","reason":"1 sentence","matched_skills":[...top 5],"missing_skills":[...top 5],"confidence":float}}"""


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
        """Prefer the user's chosen provider + key + model; fall back to env var for backwards compat."""
        provider = (getattr(profile, "llm_provider", None) or "gemini").lower()
        key = getattr(profile, "llm_api_key", None) or env_fallback_key
        model = getattr(profile, "llm_model", None)
        if not key:
            raise ValueError(
                f"No API key available for provider={provider}. "
                f"Set one in the profile or provide a fallback."
            )
        return cls(api_key=key, provider=provider, model_name=model)

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
            current_role=(profile.current_role or "—")[:50],
            years_experience=profile.years_experience,
            desired_roles=", ".join(profile.desired_roles[:5]) or "Any",
            skills=", ".join(profile.skills[:10]) or "—",
            preferred_locations=", ".join(profile.preferred_locations[:3]) or "Any",
            remote_preference=profile.remote_preference,
            salary_range=salary_range,
            job_title=job.title[:120],
            company=job.company[:60],
            location=(job.location or "—")[:60],
            remote=job.remote or "—",
            salary=job_salary,
            description=job.description[:600],  # cut from 1500 → 600 chars (saves ~250 tokens/call)
            requirements=", ".join((job.requirements or [])[:8])[:300] if job.requirements else "—",
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
