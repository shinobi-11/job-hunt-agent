"""Admin registrations for Job Hunt Agent data."""
from django.contrib import admin, messages
from django.utils.html import format_html

from .models import AppUser, Application, Job, MatchScore, Profile


def _delete_perm(self, request, obj=None):
    """Always allow delete on managed=False models (override Django's restriction)."""
    return True


@admin.register(AppUser)
class AppUserAdmin(admin.ModelAdmin):
    list_display = ("email", "name", "created_at", "last_login")
    search_fields = ("email", "name")
    readonly_fields = ("id", "password_hash", "created_at", "last_login")
    list_per_page = 25
    actions = ["reset_password_to_temporary", "delete_selected"]

    def has_delete_permission(self, request, obj=None):
        return True

    def has_add_permission(self, request):
        return False  # signups happen via the web UI

    @admin.action(description="🔑 Reset password (sets temporary 'TempPass123!')")
    def reset_password_to_temporary(self, request, queryset):
        import bcrypt
        new_hash = bcrypt.hashpw(b"TempPass123!", bcrypt.gensalt(12)).decode("utf-8")
        count = queryset.update(password_hash=new_hash)
        self.message_user(
            request,
            f"Reset {count} user(s) to temporary password 'TempPass123!' — "
            "tell users to log in and change it.",
            level=messages.SUCCESS,
        )


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ("title", "company", "location_short", "remote", "salary_display", "source", "discovered_at")
    list_filter = ("source", "remote")
    search_fields = ("title", "company", "location", "description")
    readonly_fields = ("id", "discovered_at", "posted_date")
    list_per_page = 50
    actions = ["delete_selected"]

    def has_delete_permission(self, request, obj=None):
        return True

    @admin.display(description="Location")
    def location_short(self, obj):
        return (obj.location or "")[:30]

    @admin.display(description="Salary")
    def salary_display(self, obj):
        if obj.salary_min and obj.salary_max:
            return f"{obj.currency or ''} {int(obj.salary_min):,}–{int(obj.salary_max):,}"
        return "—"


@admin.register(MatchScore)
class MatchScoreAdmin(admin.ModelAdmin):
    list_display = ("job_id_short", "score_badge", "tier", "confidence", "created_at")
    list_filter = ("tier",)
    search_fields = ("job_id", "reason")
    readonly_fields = ("id", "job_id", "created_at")
    actions = ["delete_selected"]

    def has_delete_permission(self, request, obj=None):
        return True

    @admin.display(description="Job ID", ordering="job_id")
    def job_id_short(self, obj):
        return obj.job_id[:30]

    @admin.display(description="Score", ordering="score")
    def score_badge(self, obj):
        color = (
            "#16a34a" if obj.score >= 85
            else "#ea580c" if obj.score >= 70
            else "#dc2626"
        )
        return format_html(
            '<span style="color:{};font-weight:700">{}</span>',
            color, obj.score,
        )


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ("job_title", "company", "score_badge", "status_badge", "match_tier", "applied_at", "applied_by")
    list_filter = ("status", "match_tier", "applied_by")
    search_fields = ("job_title", "company", "notes")
    readonly_fields = ("id", "job_id", "created_at", "applied_at")
    list_per_page = 50
    date_hierarchy = "created_at"
    actions = ["mark_applied", "mark_pending", "mark_manual_flag", "delete_selected"]

    def has_delete_permission(self, request, obj=None):
        return True

    @admin.display(description="Score", ordering="match_score")
    def score_badge(self, obj):
        if obj.match_score is None:
            return "—"
        color = (
            "#16a34a" if obj.match_score >= 85
            else "#ea580c" if obj.match_score >= 70
            else "#dc2626"
        )
        return format_html(
            '<span style="color:{};font-weight:700">{}</span>',
            color, obj.match_score,
        )

    @admin.display(description="Status")
    def status_badge(self, obj):
        colors = {
            "auto_applied": "#16a34a",
            "semi_auto_applied": "#ea580c",
            "pending": "#8b5cf6",
            "manual_flag": "#dc2626",
            "rejected": "#666",
            "error": "#dc2626",
        }
        c = colors.get(obj.status, "#999")
        label = obj.status.replace("_", " ").title()
        return format_html(
            '<span style="color:{};font-weight:600">{}</span>',
            c, label,
        )

    @admin.action(description="✓ Mark as Applied")
    def mark_applied(self, request, queryset):
        from django.utils import timezone
        n = queryset.update(status="auto_applied", applied_at=timezone.now())
        self.message_user(request, f"Marked {n} application(s) as applied.")

    @admin.action(description="⏳ Mark as Pending Review")
    def mark_pending(self, request, queryset):
        n = queryset.update(status="pending")
        self.message_user(request, f"Marked {n} as pending.")

    @admin.action(description="🚩 Mark as Manual Flag")
    def mark_manual_flag(self, request, queryset):
        n = queryset.update(status="manual_flag")
        self.message_user(request, f"Marked {n} as manual flag.")


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "current_role", "years_experience", "expected_range")
    search_fields = ("name", "email")
    readonly_fields = ("id", "created_at", "salary_min", "salary_max")
    actions = ["delete_selected"]
    fieldsets = (
        ("Identity", {"fields": ("id", "name", "email", "current_role", "years_experience")}),
        ("Job Search", {"fields": ("desired_roles", "preferred_locations", "remote_preference", "skills", "industries")}),
        ("Compensation", {"fields": (
            "current_salary", "hike_percent_min", "hike_percent_max",
            "salary_min", "salary_max", "salary_currency",
        )}),
        ("AI Provider", {"fields": ("llm_provider", "llm_api_key")}),
        ("Preferences", {"fields": (
            "willing_to_relocate", "auto_apply_enabled", "strict_salary_filter",
            "company_size_preference", "job_type", "availability",
        )}),
        ("Meta", {"fields": ("created_at",)}),
    )

    def has_delete_permission(self, request, obj=None):
        return True

    @admin.display(description="Expected Range")
    def expected_range(self, obj):
        if obj.salary_min and obj.salary_max:
            return f"{obj.salary_currency or 'USD'} {int(obj.salary_min):,}–{int(obj.salary_max):,}"
        return "—"
