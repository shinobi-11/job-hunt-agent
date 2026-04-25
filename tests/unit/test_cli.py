"""Unit tests for CLI rendering module."""
from unittest.mock import MagicMock

import pytest
from rich.console import Console

from cli import STATUS_ICONS, TIER_STYLES, JobHuntCLI
from models import Application, ApplicationStatus


class TestCLIRendering:
    def test_cli_uses_rich_console(self):
        cli = JobHuntCLI()
        assert isinstance(cli.console, Console)

    def test_tier_styles_cover_all_tiers(self):
        assert set(TIER_STYLES.keys()) == {"auto", "semi_auto", "manual"}
        for style in TIER_STYLES.values():
            assert "color" in style
            assert "emoji" in style
            assert "label" in style
            assert "border" in style

    def test_status_icons_cover_all_statuses(self):
        covered = {status.value for status in STATUS_ICONS.keys()}
        required = {"auto_applied", "manual_flag", "pending", "error"}
        assert required.issubset(covered)


class TestCLIOutput:
    def test_print_header_renders(self, capsys):
        cli = JobHuntCLI()
        cli.print_header(status="IDLE")
        out, _ = capsys.readouterr()
        assert "JOB HUNT AGENT" in out
        assert "IDLE" in out

    def test_print_header_with_profile_summary(self, capsys):
        cli = JobHuntCLI()
        cli.print_header(status="SEARCHING", profile_summary="Alice • 5 yrs")
        out, _ = capsys.readouterr()
        assert "Alice" in out
        assert "SEARCHING" in out

    def test_print_profile_renders_all_fields(self, capsys, sample_profile):
        cli = JobHuntCLI()
        cli.print_profile(sample_profile)
        out, _ = capsys.readouterr()
        assert "PROFILE" in out
        assert "5 years" in out

    def test_print_job_card_auto_tier(self, capsys, sample_job, sample_match_score):
        cli = JobHuntCLI()
        cli.print_job_card(sample_job, sample_match_score)
        out, _ = capsys.readouterr()
        assert "Senior Python Engineer" in out
        assert "AUTO-APPLY" in out
        assert "92" in out

    def test_print_search_status(self, capsys):
        cli = JobHuntCLI()
        cli.print_search_status(cycle=3, found=50, applied=10, semi_auto=5, manual=2, elapsed_seconds=120)
        out, _ = capsys.readouterr()
        assert "50" in out
        assert "10" in out

    def test_print_empty_applications(self, capsys):
        cli = JobHuntCLI()
        cli.print_applications_table([])
        out, _ = capsys.readouterr()
        assert "No applications yet" in out

    def test_print_applications_with_data(self, capsys, sample_application):
        cli = JobHuntCLI()
        cli.print_applications_table([sample_application])
        out, _ = capsys.readouterr()
        assert sample_application.company in out
        assert str(sample_application.match_score) in out

    def test_print_success_emoji(self, capsys):
        cli = JobHuntCLI()
        cli.print_success("Did it")
        out, _ = capsys.readouterr()
        assert "Did it" in out

    def test_print_error_emoji(self, capsys):
        cli = JobHuntCLI()
        cli.print_error("Broke it")
        out, _ = capsys.readouterr()
        assert "Broke it" in out

    def test_print_credential_gate(self, capsys):
        cli = JobHuntCLI()
        cli.print_credential_gate(
            credential_name="Gemini Key",
            env_var="GEMINI_API_KEY",
            instructions=["1. Visit aistudio.google.com", "2. Copy key"],
        )
        out, _ = capsys.readouterr()
        assert "CREDENTIAL GATE" in out
        assert "GEMINI_API_KEY" in out
        assert "aistudio.google.com" in out

    def test_print_tier_summary_zero_total_silent(self, capsys):
        cli = JobHuntCLI()
        cli.print_tier_summary(auto=0, semi=0, manual=0)
        out, _ = capsys.readouterr()
        assert out.strip() == ""

    def test_print_tier_summary_with_data(self, capsys):
        cli = JobHuntCLI()
        cli.print_tier_summary(auto=6, semi=3, manual=1)
        out, _ = capsys.readouterr()
        assert "Auto 6" in out
        assert "Semi 3" in out
        assert "Manual 1" in out

    def test_progress_bars_are_creatable(self):
        cli = JobHuntCLI()
        search_progress = cli.create_search_progress("Testing")
        eval_progress = cli.create_eval_progress(total=10)
        assert search_progress is not None
        assert eval_progress is not None

    def test_empty_state_renders_with_tips(self, capsys):
        cli = JobHuntCLI()
        cli.print_empty_state(
            title="Empty",
            message="Nothing here",
            tips=["Try broader search", "Add skills"],
        )
        out, _ = capsys.readouterr()
        assert "Empty" in out
        assert "broader search" in out
