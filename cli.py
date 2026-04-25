"""Rich terminal UI for Job Hunt Agent — implements DESIGN_SPEC animations."""
from datetime import datetime, timedelta

from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from models import Application, ApplicationStatus, Job, MatchScore, UserProfile

TIER_STYLES = {
    "auto": {
        "color": "bright_green",
        "emoji": "✅",
        "label": "AUTO-APPLY",
        "border": "bright_green",
    },
    "semi_auto": {
        "color": "yellow",
        "emoji": "⚠️ ",
        "label": "SEMI-AUTO",
        "border": "yellow",
    },
    "manual": {
        "color": "red",
        "emoji": "🚩",
        "label": "MANUAL",
        "border": "red",
    },
}

STATUS_ICONS = {
    ApplicationStatus.AUTO_APPLIED: ("✓", "bright_green"),
    ApplicationStatus.SEMI_AUTO_APPLIED: ("⚠", "yellow"),
    ApplicationStatus.MANUAL_FLAG: ("🚩", "red"),
    ApplicationStatus.PENDING: ("⏳", "bright_black"),
    ApplicationStatus.ERROR: ("✗", "red"),
    ApplicationStatus.REJECTED: ("—", "bright_black"),
}


class JobHuntCLI:
    """Rich terminal UI with animations and live updates (per DESIGN_SPEC)."""

    def __init__(self):
        self.console = Console()
        self.session_start: datetime | None = None

    def print_header(self, status: str = "IDLE", profile_summary: str | None = None):
        """Animated header with status badge and branding."""
        status_color = {
            "SEARCHING": "bright_cyan",
            "PAUSED": "yellow",
            "IDLE": "bright_black",
            "STOPPED": "red",
        }.get(status, "bright_black")

        title = Text()
        title.append("🎯 ", style="bright_cyan")
        title.append("JOB HUNT AGENT", style="bold bright_cyan")
        title.append("  ")
        title.append(f"[{status}]", style=f"bold {status_color}")

        subtitle = Text(
            "AI-powered job application automation",
            style="dim",
        )

        content = Group(
            Align.left(title),
            Align.left(subtitle),
        )

        if profile_summary:
            content = Group(
                Align.left(title),
                Align.left(subtitle),
                Text(profile_summary, style="dim cyan"),
            )

        self.console.print(
            Panel(
                content,
                border_style="bright_cyan",
                padding=(0, 2),
            )
        )

    def print_welcome(self):
        """First-run welcome screen."""
        welcome = Text()
        welcome.append("Welcome to ", style="white")
        welcome.append("Job Hunt Agent", style="bold bright_cyan")
        welcome.append("!\n\n", style="white")
        welcome.append("Let's set up your profile to start finding jobs.", style="dim")

        self.console.print(
            Panel(
                Align.center(welcome, vertical="middle"),
                border_style="bright_cyan",
                padding=(1, 2),
                title="[bold bright_cyan]🎯 Setup[/bold bright_cyan]",
            )
        )

    def print_profile(self, profile: UserProfile):
        """Display profile in 2-column horizontal layout per DESIGN_SPEC."""
        salary = "Not set"
        if profile.salary_min and profile.salary_max:
            salary = f"${int(profile.salary_min):,} - ${int(profile.salary_max):,}"

        remote_label = {
            "remote": "✓ Remote",
            "hybrid": "✓ Hybrid",
            "on-site": "On-site",
            "any": "Any",
        }.get(profile.remote_preference, "Any")

        left_col = [
            ("Role", profile.current_role or "Not set"),
            ("Experience", f"{profile.years_experience} years"),
            ("Salary", salary),
        ]
        right_col = [
            ("Skills", ", ".join(profile.skills[:3]) + ("..." if len(profile.skills) > 3 else "")),
            ("Location", ", ".join(profile.preferred_locations) or "Any"),
            ("Remote", remote_label),
        ]

        table = Table(show_header=False, box=None, padding=(0, 2), expand=True)
        table.add_column(style="bright_cyan", width=12)
        table.add_column(style="white")
        table.add_column(style="bright_cyan", width=12)
        table.add_column(style="white")

        for (lk, lv), (rk, rv) in zip(left_col, right_col):
            table.add_row(lk, lv, rk, rv)

        self.console.print(
            Panel(
                table,
                border_style="bright_cyan",
                padding=(0, 1),
                title="[bold bright_cyan]PROFILE[/bold bright_cyan]",
                title_align="left",
            )
        )

    def print_job_card(self, job: Job, score: MatchScore):
        """Render job card with tier-based styling per DESIGN_SPEC."""
        style = TIER_STYLES.get(score.tier, TIER_STYLES["manual"])

        header = Text()
        header.append(f"MATCH: {score.score}/100 ", style=f"bold {style['color']}")
        header.append(f"{style['emoji']} ", style="")
        header.append(style["label"], style=f"bold {style['color']}")

        title = Text()
        title.append(job.title, style="bold white")

        meta = Text()
        meta.append(f"{job.company}", style="bright_cyan")
        meta.append(" • ", style="dim")
        meta.append(f"{job.location}", style="white")
        if job.remote:
            meta.append(" • ", style="dim")
            meta.append(f"Remote: {job.remote}", style="bright_magenta")

        matched_line = Text()
        matched_line.append("✓ Matched: ", style="bright_green")
        if score.matched_skills:
            matched_line.append(", ".join(score.matched_skills[:5]), style="white")
        else:
            matched_line.append("None", style="dim")

        missing_line = Text()
        missing_line.append("✗ Missing: ", style="yellow")
        if score.missing_skills:
            missing_line.append(", ".join(score.missing_skills[:5]), style="white")
        else:
            missing_line.append("None", style="dim")

        reason = Text(score.reason, style="dim italic")

        details = Text()
        if job.salary_min and job.salary_max:
            details.append(f"📍 ${int(job.salary_min):,} - ${int(job.salary_max):,}", style="bright_magenta")
            details.append("  |  ", style="dim")
        details.append(f"🔗 {job.source}", style="dim")

        body = Group(title, meta, Text(""), matched_line, missing_line, Text(""), reason, Text(""), details)

        self.console.print(
            Panel(
                body,
                border_style=style["border"],
                padding=(0, 2),
                title=header,
                title_align="left",
            )
        )

    def print_search_status(
        self,
        cycle: int,
        found: int,
        applied: int,
        semi_auto: int,
        manual: int,
        elapsed_seconds: int = 0,
    ):
        """Display live search statistics."""
        elapsed = str(timedelta(seconds=elapsed_seconds))

        table = Table(show_header=False, box=None, padding=(0, 2), expand=True)
        table.add_column(style="bright_cyan")
        table.add_column(style="white", justify="right")

        table.add_row("🔍 Cycle", f"#{cycle}")
        table.add_row("📊 Jobs Found", f"{found}")
        table.add_row("✅ Auto-Applied", f"[bright_green]{applied}[/bright_green]")
        table.add_row("⚠️  Semi-Auto", f"[yellow]{semi_auto}[/yellow]")
        table.add_row("🚩 Manual Flag", f"[red]{manual}[/red]")
        table.add_row("⏱  Elapsed", elapsed)

        self.console.print(
            Panel(
                table,
                border_style="bright_cyan",
                padding=(0, 1),
                title="[bold bright_cyan]SEARCH STATUS[/bold bright_cyan]",
                title_align="left",
            )
        )

    def print_applications_table(self, applications: list[Application]):
        """Display applications table per DESIGN_SPEC."""
        if not applications:
            self.console.print(
                Panel(
                    Align.center(
                        Text("No applications yet.\nStart a search to begin!", style="dim"),
                        vertical="middle",
                    ),
                    border_style="bright_black",
                    padding=(1, 2),
                    title="[bold]APPLICATIONS[/bold]",
                )
            )
            return

        table = Table(
            title=f"[bold bright_cyan]APPLICATIONS ({len(applications)} total)[/bold bright_cyan]",
            border_style="bright_cyan",
            show_lines=False,
            expand=True,
        )
        table.add_column("Job Title", style="white", max_width=30)
        table.add_column("Company", style="bright_cyan", max_width=20)
        table.add_column("Score", justify="right", width=6)
        table.add_column("Status", width=20)
        table.add_column("Date", style="dim", width=12)

        for app in applications[:25]:
            icon, color = STATUS_ICONS.get(app.status, ("?", "white"))
            status_text = f"[{color}]{icon} {app.status.value.replace('_', ' ').title()}[/{color}]"

            score_color = (
                "bright_green" if app.match_score >= 85
                else "yellow" if app.match_score >= 70
                else "red"
            )

            date_str = app.created_at.strftime("%m/%d %H:%M") if app.created_at else "—"

            table.add_row(
                app.job_title,
                app.company,
                f"[{score_color}]{app.match_score}[/{score_color}]",
                status_text,
                date_str,
            )

        if len(applications) > 25:
            self.console.print(table)
            self.console.print(
                f"[dim]...and {len(applications) - 25} more (scroll up to view)[/dim]"
            )
        else:
            self.console.print(table)

    def create_search_progress(self, description: str = "Searching for jobs"):
        """Create animated progress bar for search cycle."""
        return Progress(
            SpinnerColumn(spinner_name="dots", style="bright_cyan"),
            TextColumn("[bold bright_cyan]{task.description}[/bold bright_cyan]"),
            BarColumn(complete_style="bright_cyan", finished_style="bright_green"),
            TaskProgressColumn(),
            console=self.console,
            transient=True,
        )

    def create_eval_progress(self, total: int):
        """Progress bar for job evaluation phase."""
        return Progress(
            SpinnerColumn(spinner_name="dots", style="bright_magenta"),
            TextColumn("[bright_magenta]Evaluating jobs with Gemini AI...[/bright_magenta]"),
            BarColumn(complete_style="bright_magenta"),
            TextColumn("[bold]{task.completed}/{task.total}[/bold]"),
            console=self.console,
            transient=True,
        )

    def print_message(self, message: str, style: str = ""):
        """Print a styled message."""
        self.console.print(f"[{style}]{message}[/{style}]" if style else message)

    def print_info(self, message: str):
        self.console.print(f"[bright_cyan]ℹ  {message}[/bright_cyan]")

    def print_success(self, message: str):
        self.console.print(f"[bright_green]✅ {message}[/bright_green]")

    def print_warning(self, message: str):
        self.console.print(f"[yellow]⚠️  {message}[/yellow]")

    def print_error(self, message: str):
        self.console.print(f"[bold red]❌ {message}[/bold red]")

    def print_hint(self, message: str):
        self.console.print(f"[dim magenta]💡 {message}[/dim magenta]")

    def print_rule(self, title: str = "", style: str = "bright_black"):
        if title:
            self.console.print(Rule(f"[{style}]{title}[/{style}]", style=style))
        else:
            self.console.print(Rule(style=style))

    def print_empty_state(self, title: str, message: str, tips: list[str] | None = None):
        """Empty state panel per DESIGN_SPEC."""
        content: list = [Text(message, style="white", justify="center"), Text("")]

        if tips:
            content.append(Text("💡 Tips:", style="bold bright_magenta"))
            for tip in tips:
                content.append(Text(f"  • {tip}", style="dim"))

        self.console.print(
            Panel(
                Align.center(Group(*content), vertical="middle"),
                border_style="bright_black",
                padding=(1, 2),
                title=f"[bold]{title}[/bold]",
            )
        )

    def print_credential_gate(
        self, credential_name: str, env_var: str, instructions: list[str]
    ):
        """Credential Gate block per shinobi_dev PROTOCOL 5."""
        content: list = [
            Text(f"Required:    {credential_name}", style="bold yellow"),
            Text(f"Env var:     {env_var}", style="yellow"),
            Text(""),
            Text("HOW TO GET IT:", style="bold bright_cyan"),
        ]
        for step in instructions:
            content.append(Text(f"  {step}", style="white"))

        content.append(Text(""))
        content.append(
            Text(
                "⏸  Waiting: add the key to .env and restart",
                style="bold yellow",
            )
        )

        self.console.print(
            Panel(
                Group(*content),
                border_style="yellow",
                padding=(1, 2),
                title="[bold yellow]🔐 CREDENTIAL GATE — PAUSED[/bold yellow]",
            )
        )

    def print_tier_summary(self, auto: int, semi: int, manual: int):
        """Horizontal summary of tier distribution."""
        total = auto + semi + manual
        if total == 0:
            return

        auto_pct = int(auto / total * 100) if total else 0
        semi_pct = int(semi / total * 100) if total else 0
        manual_pct = int(manual / total * 100) if total else 0

        summary = Text()
        summary.append(f"✅ Auto {auto} ({auto_pct}%)", style="bright_green")
        summary.append("   ")
        summary.append(f"⚠️  Semi {semi} ({semi_pct}%)", style="yellow")
        summary.append("   ")
        summary.append(f"🚩 Manual {manual} ({manual_pct}%)", style="red")

        self.console.print(Align.center(summary))

    def print_salary_summary(
        self,
        current: float | None,
        hike_min: float,
        hike_max: float,
        expected_min: float | None,
        expected_max: float | None,
        currency: str = "USD",
    ):
        """Show current salary, hike %, and computed expected range."""
        if current is None or expected_min is None or expected_max is None:
            return

        body = Text()
        body.append("Current:         ", style="bright_cyan")
        body.append(f"{currency} {int(current):,}\n", style="white")
        body.append("Expected hike:   ", style="bright_cyan")
        body.append(f"{int(hike_min)}% – {int(hike_max)}%\n", style="white")
        body.append("Expected range:  ", style="bright_cyan")
        body.append(
            f"{currency} {int(expected_min):,} – {int(expected_max):,}",
            style="bold bright_green",
        )

        self.console.print(
            Panel(
                body,
                border_style="bright_green",
                padding=(0, 2),
                title="[bold bright_green]💰 SALARY EXPECTATIONS[/bold bright_green]",
                title_align="left",
            )
        )

    def print_application_detail(self, app):
        """Render full detail card for a single application."""
        from models import ApplicationStatus

        icon, color = STATUS_ICONS.get(app.status, ("?", "white"))
        status_label = app.status.value.replace("_", " ").title()

        score_color = (
            "bright_green" if app.match_score >= 85
            else "yellow" if app.match_score >= 70
            else "red"
        )

        body = Text()
        body.append(f"{app.job_title}\n", style="bold white")
        body.append(f"{app.company}\n\n", style="bright_cyan")

        body.append("Status:      ", style="bright_cyan")
        body.append(f"{icon} {status_label}\n", style=color)

        body.append("Match Score: ", style="bright_cyan")
        body.append(f"{app.match_score}/100 ({app.match_tier})\n", style=score_color)

        body.append("Applied:     ", style="bright_cyan")
        body.append(
            f"{app.applied_at.strftime('%Y-%m-%d %H:%M') if app.applied_at else '—'}\n",
            style="white",
        )

        body.append("Applied by:  ", style="bright_cyan")
        body.append(f"{app.applied_by}\n", style="white")

        body.append("Discovered:  ", style="bright_cyan")
        body.append(
            f"{app.created_at.strftime('%Y-%m-%d %H:%M') if app.created_at else '—'}\n",
            style="white",
        )

        body.append("App ID:      ", style="bright_cyan")
        body.append(f"{app.id}\n", style="dim")

        if app.notes:
            body.append("\nReasoning:\n", style="bright_cyan")
            body.append(app.notes, style="dim italic")

        self.console.print(
            Panel(
                body,
                border_style=score_color,
                padding=(1, 2),
                title=f"[bold {score_color}]APPLICATION DETAILS[/bold {score_color}]",
                title_align="left",
            )
        )

    def clear(self):
        """Clear the console."""
        self.console.clear()
