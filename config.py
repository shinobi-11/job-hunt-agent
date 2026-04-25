"""Centralized configuration using Pydantic Settings (ADR-014)."""
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    """Application configuration loaded from .env and environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    gemini_api_key: str = Field(default="")
    gemini_model: str = Field(default="gemini-2.5-flash")

    search_interval_seconds: int = Field(default=300, ge=30, le=3600)
    auto_apply_threshold: int = Field(default=85, ge=0, le=100)
    semi_auto_threshold: int = Field(default=70, ge=0, le=100)
    max_jobs_per_search: int = Field(default=10, ge=1, le=100)

    database_path: str = Field(default="./data/jobs.db")
    resume_path: str = Field(default="./data/resume.pdf")
    profile_path: str = Field(default="./data/profile.json")
    log_path: str = Field(default="./data/agent.log")
    log_level: str = Field(default="INFO")

    playwright_headless: bool = Field(default=True)
    linkedin_email: str | None = None
    linkedin_password: str | None = None

    dry_run: bool = Field(default=False)

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in valid:
            raise ValueError(f"log_level must be one of {valid}")
        return v_upper

    @field_validator("semi_auto_threshold")
    @classmethod
    def validate_thresholds(cls, v: int, info) -> int:
        auto = info.data.get("auto_apply_threshold", 85)
        if v >= auto:
            raise ValueError(
                f"semi_auto_threshold ({v}) must be less than auto_apply_threshold ({auto})"
            )
        return v

    def ensure_directories(self) -> None:
        """Create required directories if they don't exist."""
        for path_str in [self.database_path, self.resume_path, self.log_path]:
            Path(path_str).parent.mkdir(parents=True, exist_ok=True)


_config: Config | None = None


def get_config() -> Config:
    """Get singleton config instance."""
    global _config
    if _config is None:
        _config = Config()
        _config.ensure_directories()
    return _config
