"""Data models for Job Hunt Agent."""
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ApplicationStatus(str, Enum):
    """Application status enum."""
    PENDING = "pending"
    AUTO_APPLIED = "auto_applied"
    SEMI_AUTO_APPLIED = "semi_auto_applied"
    MANUAL_FLAG = "manual_flag"
    REJECTED = "rejected"
    ERROR = "error"


class Job(BaseModel):
    """Job posting model."""
    id: str = Field(default_factory=lambda: f"job_{datetime.now().timestamp()}")
    title: str
    company: str
    location: str
    remote: str | None = None  # "remote", "hybrid", "on-site"
    salary_min: float | None = None
    salary_max: float | None = None
    currency: str | None = "USD"
    description: str
    requirements: list[str] = Field(default_factory=list)
    source: str  # LinkedIn, Indeed, etc.
    url: str
    posted_date: datetime | None = None
    discovered_at: datetime = Field(default_factory=datetime.now)


class MatchScore(BaseModel):
    """Job match score and analysis."""
    job_id: str
    score: int = Field(ge=0, le=100)  # 0-100
    reason: str
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    cultural_fit: str | None = None
    salary_alignment: str | None = None
    tier: str = Field(default="manual")  # "auto", "semi_auto", "manual"
    confidence: float | None = None  # 0.0-1.0


class UserProfile(BaseModel):
    """User job search profile."""
    name: str
    email: str
    current_role: str | None = None
    years_experience: int = 0
    desired_roles: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    remote_preference: str = "any"  # "any", "remote", "hybrid", "on-site"
    current_salary: float | None = None
    hike_percent_min: float = 20.0
    hike_percent_max: float = 40.0
    salary_min: float | None = None  # computed: current_salary * (1 + hike_min/100)
    salary_max: float | None = None  # computed: current_salary * (1 + hike_max/100)
    salary_currency: str = "USD"
    industries: list[str] = Field(default_factory=list)
    company_size_preference: str | None = None
    job_type: list[str] = Field(default_factory=list)
    availability: str = "immediate"
    willing_to_relocate: bool = False
    auto_apply_enabled: bool = True
    strict_salary_filter: bool = True
    llm_provider: str = "gemini"
    llm_api_key: str | None = None
    llm_model: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)

    def compute_expected_salary(self) -> None:
        """Derive salary_min/salary_max from current_salary and hike range."""
        if self.current_salary is None:
            return
        self.salary_min = self.current_salary * (1 + self.hike_percent_min / 100.0)
        self.salary_max = self.current_salary * (1 + self.hike_percent_max / 100.0)


class Application(BaseModel):
    """Job application record."""
    id: str = Field(default_factory=lambda: f"app_{datetime.now().timestamp()}")
    job_id: str
    job_title: str
    company: str
    status: ApplicationStatus = ApplicationStatus.PENDING
    match_score: int
    match_tier: str  # "auto", "semi_auto", "manual"
    applied_at: datetime | None = None
    applied_by: str = "system"  # "system" or "manual"
    notes: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)


class SearchState(BaseModel):
    """Current search session state."""
    session_id: str
    is_running: bool = False
    is_paused: bool = False
    jobs_found: int = 0
    jobs_applied: int = 0
    jobs_auto_applied: int = 0
    jobs_semi_auto: int = 0
    jobs_manual_flag: int = 0
    started_at: datetime | None = None
    paused_at: datetime | None = None
    last_search: datetime | None = None
    search_queries: list[str] = Field(default_factory=list)
