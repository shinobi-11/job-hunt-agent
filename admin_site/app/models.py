"""Django ORM models mapped onto the existing SQLite/Postgres schema (managed=False)."""
from django.db import models


class Query(models.Model):
    """Contact form submissions."""
    id = models.TextField(primary_key=True)
    name = models.TextField()
    email = models.TextField()
    phone = models.TextField(null=True, blank=True)
    message = models.TextField()
    status = models.TextField(default="new")
    created_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "queries"
        ordering = ["-created_at"]
        verbose_name = "Contact Query"
        verbose_name_plural = "Contact Queries"

    def __str__(self) -> str:
        return f"{self.name} <{self.email}>"


class AppUser(models.Model):
    """Site-level user accounts (separate from Django auth.User)."""
    id = models.TextField(primary_key=True)
    email = models.TextField(unique=True)
    password_hash = models.TextField()
    name = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)
    last_login = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "users"
        ordering = ["-created_at"]
        verbose_name = "Site User"
        verbose_name_plural = "Site Users"

    def __str__(self) -> str:
        return f"{self.email} ({self.name or '—'})"


class Job(models.Model):
    id = models.TextField(primary_key=True)
    title = models.TextField()
    company = models.TextField()
    location = models.TextField(null=True, blank=True)
    remote = models.TextField(null=True, blank=True)
    salary_min = models.FloatField(null=True, blank=True)
    salary_max = models.FloatField(null=True, blank=True)
    currency = models.TextField(null=True, blank=True)
    description = models.TextField()
    requirements = models.TextField(null=True, blank=True)
    source = models.TextField()
    url = models.TextField(unique=True)
    posted_date = models.DateTimeField(null=True, blank=True)
    discovered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "jobs"
        ordering = ["-discovered_at"]

    def __str__(self) -> str:
        return f"{self.title} @ {self.company}"


class MatchScore(models.Model):
    id = models.TextField(primary_key=True)
    job_id = models.TextField()
    score = models.IntegerField()
    reason = models.TextField(null=True, blank=True)
    matched_skills = models.TextField(null=True, blank=True)
    missing_skills = models.TextField(null=True, blank=True)
    cultural_fit = models.TextField(null=True, blank=True)
    salary_alignment = models.TextField(null=True, blank=True)
    tier = models.TextField(null=True, blank=True)
    confidence = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "match_scores"
        ordering = ["-score"]

    def __str__(self) -> str:
        return f"{self.score}/100 ({self.tier})"


class Application(models.Model):
    id = models.TextField(primary_key=True)
    job_id = models.TextField()
    job_title = models.TextField()
    company = models.TextField()
    status = models.TextField()
    match_score = models.IntegerField(null=True, blank=True)
    match_tier = models.TextField(null=True, blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    applied_by = models.TextField(null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "applications"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.job_title} @ {self.company} ({self.status})"


class Profile(models.Model):
    id = models.TextField(primary_key=True)
    name = models.TextField()
    email = models.TextField(unique=True)
    current_role = models.TextField(null=True, blank=True)
    years_experience = models.IntegerField(null=True, blank=True)
    desired_roles = models.TextField(null=True, blank=True)
    skills = models.TextField(null=True, blank=True)
    preferred_locations = models.TextField(null=True, blank=True)
    remote_preference = models.TextField(null=True, blank=True)
    current_salary = models.FloatField(null=True, blank=True)
    hike_percent_min = models.FloatField(null=True, blank=True)
    hike_percent_max = models.FloatField(null=True, blank=True)
    salary_min = models.FloatField(null=True, blank=True)
    salary_max = models.FloatField(null=True, blank=True)
    salary_currency = models.TextField(null=True, blank=True)
    industries = models.TextField(null=True, blank=True)
    company_size_preference = models.TextField(null=True, blank=True)
    job_type = models.TextField(null=True, blank=True)
    availability = models.TextField(null=True, blank=True)
    willing_to_relocate = models.BooleanField(default=False)
    auto_apply_enabled = models.BooleanField(default=True)
    strict_salary_filter = models.BooleanField(default=True)
    created_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "profiles"

    def __str__(self) -> str:
        return f"{self.name} ({self.email})"
