"""Main orchestrator for Job Hunt Agent (ADR-001: Modular Monolith)."""
from __future__ import annotations

import logging
import shutil
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

import click
import questionary

from cli import JobHuntCLI
from config import Config, get_config
from database import JobDatabase
from llm_providers import PROVIDERS
from matcher import JobMatcher
from models import Application, ApplicationStatus, Job, MatchScore, UserProfile
from resume_parser import ResumeParser
from searcher import JobSearcher


def setup_logging(config: Config) -> None:
    Path(config.log_path).parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=getattr(logging, config.log_level),
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        handlers=[logging.FileHandler(config.log_path), logging.NullHandler()],
    )


class CredentialGateError(Exception):
    """Raised when required credentials are missing (PROTOCOL 5)."""


CLI_USER_ID = "cli_local_user"


class JobHuntAgent:
    """Main orchestrator coordinating search → evaluate → apply workflow."""

    def __init__(self, config: Config | None = None):
        self.config = config or get_config()
        self.cli = JobHuntCLI()
        self.logger = logging.getLogger("agent")

        self.db = JobDatabase(db_path=self.config.database_path)
        self.matcher: JobMatcher | None = None  # built lazily from profile
        self.profile: UserProfile | None = None

        self.is_running = False
        self.is_paused = False
        self.session_start: datetime | None = None

        self._install_signal_handlers()

    def _ensure_matcher(self) -> None:
        """Build (or rebuild) the matcher from the current profile."""
        if not self.profile:
            return
        if not self.profile.llm_api_key:
            meta = PROVIDERS.get(self.profile.llm_provider, {})
            self.cli.print_credential_gate(
                credential_name=f"{meta.get('label', self.profile.llm_provider)} API Key",
                env_var=f"{self.profile.llm_provider.upper()}_API_KEY",
                instructions=[
                    f"1. Visit {meta.get('key_url', '')}",
                    f"2. Create a key (format: {meta.get('key_hint', '...')})",
                    "3. Run 'settings' in the agent and paste it",
                    "OR set llm_api_key on the profile via the web UI",
                ],
            )
            raise CredentialGateError(
                f"No API key set for provider '{self.profile.llm_provider}'"
            )
        try:
            self.matcher = JobMatcher.from_profile(
                self.profile, env_fallback_key=self.config.gemini_api_key
            )
        except Exception as e:
            self.cli.print_error(f"Failed to initialize {self.profile.llm_provider}: {e}")
            raise CredentialGateError(str(e))

    def _install_signal_handlers(self) -> None:
        def handle_shutdown(signum, frame):
            self.cli.print_warning("\nShutdown signal received. Saving state...")
            self.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, handle_shutdown)
        signal.signal(signal.SIGTERM, handle_shutdown)

    # ─── Initialization ──────────────────────────────────────────

    def initialize(self) -> None:
        existing = self.db.get_profile(user_id=CLI_USER_ID)
        profile_summary = None
        if existing:
            profile_summary = (
                f"Profile: {existing.name} • "
                f"{existing.current_role or 'Role not set'} • "
                f"{existing.years_experience} years"
            )
        self.cli.print_header(status="IDLE", profile_summary=profile_summary)

        if existing:
            self.profile = existing
            self.cli.print_success(f"Profile loaded: {existing.name}")
            self.cli.print_profile(self.profile)
            self._print_salary_summary()
        else:
            self.cli.print_welcome()
            self.profile = self._interactive_profile_setup()
            self.db.save_profile(self.profile, user_id=CLI_USER_ID)
            self.cli.print_success(f"Profile created: {self.profile.name}")
            self.cli.print_profile(self.profile)
            self._print_salary_summary()

        self._ensure_matcher()

    # ─── Profile Setup ───────────────────────────────────────────

    def _interactive_profile_setup(self) -> UserProfile:
        self.cli.print_info("Let's build your job search profile.")
        self.cli.print_message("")

        self._prompt_for_resume()

        name = self._ask_text("Your full name:", required=True) or "User"
        email = self._ask_email("Your email:")
        current_role = self._ask_text("Current role (optional):") or None
        years = self._ask_int("Years of experience:", default=0, minimum=0, maximum=60)

        jobs_raw = self._ask_text(
            "Desired jobs (comma-separated, e.g., 'Financial Analyst, Investment Associate'):",
            default="",
            required=True,
        )
        desired_roles = [r.strip() for r in jobs_raw.split(",") if r.strip()]

        locations_raw = self._ask_text(
            "Desired job locations (comma-separated, e.g., 'Bangalore, Gurugram, Remote'):",
            default="Remote",
            required=True,
        )
        locations = [l.strip() for l in locations_raw.split(",") if l.strip()]

        remote_pref = questionary.select(
            "Remote preference:",
            choices=["remote", "hybrid", "on-site", "any"],
            default="any",
        ).ask() or "any"

        currency = questionary.select(
            "Salary currency:",
            choices=["USD", "INR", "EUR", "GBP"],
            default="INR" if any("bangalore" in loc.lower() or "gurugram" in loc.lower() or "india" in loc.lower() for loc in locations) else "USD",
        ).ask() or "USD"

        current_salary = self._ask_float(
            f"Current annual salary ({currency}):",
            minimum=0,
            required=True,
        )

        hike_min = self._ask_float(
            "Minimum expected hike % (e.g., 20):",
            default=20,
            minimum=0,
            maximum=200,
        )
        hike_max = self._ask_float(
            "Maximum expected hike % (e.g., 40):",
            default=max(hike_min + 10, 40),
            minimum=hike_min,
            maximum=500,
        )

        skills_raw = self._ask_text(
            "Your key skills (comma-separated):",
            default="",
        )
        skills = [s.strip() for s in skills_raw.split(",") if s.strip()]

        willing_relocate = questionary.confirm(
            "Willing to relocate?", default=False
        ).ask() or False

        auto_apply = questionary.confirm(
            "Enable auto-apply for high-match jobs (score ≥85)?", default=True
        ).ask()
        auto_apply = True if auto_apply is None else auto_apply

        provider, api_key = self._ask_llm_provider()

        profile = UserProfile(
            name=name.strip(),
            email=email.strip(),
            current_role=current_role,
            years_experience=years,
            desired_roles=desired_roles,
            skills=skills,
            preferred_locations=locations,
            remote_preference=remote_pref,
            current_salary=current_salary,
            hike_percent_min=hike_min,
            hike_percent_max=hike_max,
            salary_currency=currency,
            willing_to_relocate=willing_relocate,
            auto_apply_enabled=auto_apply,
            strict_salary_filter=True,
            llm_provider=provider,
            llm_api_key=api_key,
        )
        profile.compute_expected_salary()
        return profile

    def _ask_llm_provider(self) -> tuple[str, str | None]:
        """Prompt for LLM provider + API key."""
        choices = [
            questionary.Choice(title=meta["label"], value=pid)
            for pid, meta in PROVIDERS.items()
        ]
        provider = questionary.select(
            "AI provider for job matching:",
            choices=choices,
            default="gemini",
        ).ask() or "gemini"

        meta = PROVIDERS[provider]
        self.cli.print_hint(
            f"Get a {meta['label']} key at {meta['key_url']} (format: {meta['key_hint']})"
        )

        existing_env = self.config.gemini_api_key if provider == "gemini" else None
        prompt_text = "API key (leave blank to use .env)" if existing_env else "API key:"

        key = questionary.password(prompt_text).ask()
        if not key and existing_env:
            return provider, existing_env
        return provider, (key or None)

    def _print_salary_summary(self) -> None:
        if self.profile is None:
            return
        self.cli.print_salary_summary(
            current=self.profile.current_salary,
            hike_min=self.profile.hike_percent_min,
            hike_max=self.profile.hike_percent_max,
            expected_min=self.profile.salary_min,
            expected_max=self.profile.salary_max,
            currency=self.profile.salary_currency,
        )

    # ─── Settings / Edit Menu ────────────────────────────────────

    def edit_settings(self) -> None:
        if self.profile is None:
            self.cli.print_error("No profile loaded.")
            return

        while True:
            choice = questionary.select(
                "What would you like to edit?",
                choices=[
                    "Desired jobs (comma-separated)",
                    "Desired locations",
                    "Current salary & hike %",
                    "Remote preference",
                    "Skills",
                    "Auto-apply on/off",
                    "Strict salary filter on/off",
                    "AI provider & API key",
                    "Replace resume",
                    "View full profile",
                    "Done",
                ],
            ).ask()

            if choice is None or choice == "Done":
                break

            if choice.startswith("Desired jobs"):
                raw = self._ask_text(
                    "Desired jobs (comma-separated):",
                    default=", ".join(self.profile.desired_roles),
                    required=True,
                )
                self.profile.desired_roles = [r.strip() for r in raw.split(",") if r.strip()]

            elif choice.startswith("Desired locations"):
                raw = self._ask_text(
                    "Desired locations (comma-separated):",
                    default=", ".join(self.profile.preferred_locations),
                    required=True,
                )
                self.profile.preferred_locations = [l.strip() for l in raw.split(",") if l.strip()]

            elif choice.startswith("Current salary"):
                self.profile.current_salary = self._ask_float(
                    f"Current annual salary ({self.profile.salary_currency}):",
                    default=self.profile.current_salary or 0,
                    minimum=0,
                )
                self.profile.hike_percent_min = self._ask_float(
                    "Minimum expected hike %:",
                    default=self.profile.hike_percent_min,
                    minimum=0,
                    maximum=200,
                )
                self.profile.hike_percent_max = self._ask_float(
                    "Maximum expected hike %:",
                    default=self.profile.hike_percent_max,
                    minimum=self.profile.hike_percent_min,
                    maximum=500,
                )
                self.profile.compute_expected_salary()

            elif choice.startswith("Remote"):
                self.profile.remote_preference = questionary.select(
                    "Remote preference:",
                    choices=["remote", "hybrid", "on-site", "any"],
                    default=self.profile.remote_preference,
                ).ask() or self.profile.remote_preference

            elif choice == "Skills":
                raw = self._ask_text(
                    "Skills (comma-separated):",
                    default=", ".join(self.profile.skills),
                )
                self.profile.skills = [s.strip() for s in raw.split(",") if s.strip()]

            elif choice.startswith("Auto-apply"):
                self.profile.auto_apply_enabled = questionary.confirm(
                    "Enable auto-apply (score ≥85)?",
                    default=self.profile.auto_apply_enabled,
                ).ask()

            elif choice.startswith("Strict salary"):
                self.profile.strict_salary_filter = questionary.confirm(
                    "Strictly filter jobs below expected salary?",
                    default=self.profile.strict_salary_filter,
                ).ask()

            elif choice.startswith("AI provider"):
                provider, key = self._ask_llm_provider()
                self.profile.llm_provider = provider
                if key:
                    self.profile.llm_api_key = key
                self.db.save_profile(self.profile, user_id=CLI_USER_ID)
                try:
                    self._ensure_matcher()
                    self.cli.print_success(
                        f"Switched to {PROVIDERS[provider]['label']} ({self.matcher.model_name})"
                    )
                except Exception as e:
                    self.cli.print_error(f"Provider rebuild failed: {e}")
                continue

            elif choice.startswith("Replace resume"):
                new_path = self._ask_text(
                    "New resume path (PDF/DOCX):",
                    default=self.config.resume_path,
                    required=True,
                )
                try:
                    src = Path(new_path).expanduser()
                    if not src.exists():
                        self.cli.print_error(f"File not found: {src}")
                        continue
                    dest = Path(self.config.resume_path)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy(src, dest)
                    text = ResumeParser.parse_resume(str(dest))
                    self.cli.print_success(f"Resume replaced: {dest.name} ({len(text)} chars)")
                except Exception as e:
                    self.cli.print_error(f"Failed: {e}")
                continue

            elif choice == "View full profile":
                self.cli.print_profile(self.profile)
                self._print_salary_summary()
                continue

            self.db.save_profile(self.profile, user_id=CLI_USER_ID)
            self.cli.print_success("Profile updated.")

        self.cli.print_profile(self.profile)
        self._print_salary_summary()

    # ─── Resume ──────────────────────────────────────────────────

    def _prompt_for_resume(self) -> str | None:
        """Ask the user for a resume file at setup time. Optional but recommended."""
        dest = Path(self.config.resume_path)

        if dest.exists():
            use_existing = questionary.confirm(
                f"Resume already exists at {dest}. Use it?",
                default=True,
            ).ask()
            if use_existing:
                return self._parse_resume_at(dest)

        want_resume = questionary.confirm(
            "Do you want to upload a resume now? (PDF or DOCX — improves match accuracy)",
            default=True,
        ).ask()
        if not want_resume:
            self.cli.print_hint(
                "Skipped. You can add one later via 'settings → Replace resume'."
            )
            return None

        while True:
            path_str = self._ask_text(
                "Resume file path (absolute or ~/...):",
                required=True,
            )
            if not path_str:
                return None

            src = Path(path_str).expanduser()
            if not src.exists():
                self.cli.print_error(f"File not found: {src}")
                retry = questionary.confirm("Try again?", default=True).ask()
                if not retry:
                    return None
                continue

            if src.suffix.lower() not in {".pdf", ".docx", ".doc"}:
                self.cli.print_error(
                    f"Unsupported format: {src.suffix}. Use PDF or DOCX."
                )
                continue

            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                if src.resolve() != dest.resolve():
                    shutil.copy(src, dest)
                return self._parse_resume_at(dest)
            except Exception as e:
                self.cli.print_error(f"Failed to copy/parse: {e}")
                retry = questionary.confirm("Try another file?", default=True).ask()
                if not retry:
                    return None

    def _parse_resume_at(self, path: Path) -> str | None:
        try:
            text = ResumeParser.parse_resume(str(path))
            self.cli.print_success(f"Parsed resume from {path.name} ({len(text)} chars)")
            return text
        except Exception as e:
            self.cli.print_warning(f"Could not parse resume: {e}")
            return None

    def _try_parse_resume(self) -> str | None:
        """Best-effort parse of existing resume (no prompts)."""
        resume_path = Path(self.config.resume_path)
        if not resume_path.exists():
            return None
        return self._parse_resume_at(resume_path)

    # ─── Search Loop ─────────────────────────────────────────────

    def start_search(self, duration_minutes: int = 30) -> None:
        if not self.profile:
            self.cli.print_error("Profile not loaded. Run initialize() first.")
            return
        if not self.profile.desired_roles:
            self.cli.print_error("No desired jobs set. Run 'settings' to add them.")
            return
        if self.profile.strict_salary_filter and not self.profile.salary_min:
            self.cli.print_error(
                "Strict salary filter is on but no expected range set. Update via 'settings'."
            )
            return

        self.is_running = True
        self.is_paused = False
        self.session_start = datetime.now()
        end_time = time.time() + (duration_minutes * 60)

        self.cli.print_rule("🚀 Search Started", style="bright_cyan")
        self.cli.print_info(
            f"Duration: {duration_minutes} min | "
            f"Jobs: {', '.join(self.profile.desired_roles)} | "
            f"Locations: {', '.join(self.profile.preferred_locations)} | "
            f"Remote: {self.profile.remote_preference}"
        )
        if self.profile.salary_min and self.profile.salary_max:
            self.cli.print_info(
                f"Strict salary filter: "
                f"{self.profile.salary_currency} {int(self.profile.salary_min):,} – {int(self.profile.salary_max):,}"
            )

        cycle = 0
        stats = {"applied": 0, "semi_auto": 0, "manual": 0}

        while self.is_running and time.time() < end_time:
            if self.is_paused:
                time.sleep(2)
                continue

            cycle += 1
            self.cli.print_rule(f"Cycle #{cycle}", style="bright_magenta")

            # Re-load profile in case the user edited it via the web UI mid-flight
            fresh = self.db.get_profile(user_id=CLI_USER_ID)
            if fresh:
                self.profile = fresh
                try:
                    self._ensure_matcher()
                except CredentialGateError:
                    self.cli.print_error("API key missing — pausing search.")
                    self.is_paused = True
                    continue

            new_jobs = self._search_for_jobs()
            if not new_jobs:
                self.cli.print_empty_state(
                    title="No new jobs this cycle",
                    message="The agent will try again next cycle.",
                    tips=[
                        "Broaden your locations (e.g., add 'Remote')",
                        "Adjust hike % range (you may be filtering too aggressively)",
                        "Toggle 'strict salary filter' off via 'settings'",
                    ],
                )
            else:
                self.cli.print_success(f"Found {len(new_jobs)} new jobs — evaluating...")
                cycle_stats = self._evaluate_and_route(new_jobs)
                for k, v in cycle_stats.items():
                    stats[k] += v

            total_stats = self.db.get_stats(user_id=CLI_USER_ID)
            elapsed = int((datetime.now() - self.session_start).total_seconds())
            self.cli.print_search_status(
                cycle=cycle,
                found=total_stats.get("total_jobs", 0),
                applied=stats["applied"],
                semi_auto=stats["semi_auto"],
                manual=stats["manual"],
                elapsed_seconds=elapsed,
            )

            if self.is_running and time.time() < end_time:
                wait_seconds = min(self.config.search_interval_seconds, int(end_time - time.time()))
                if wait_seconds > 0:
                    self._wait_with_progress(wait_seconds)

        self.is_running = False
        self.cli.print_rule("🎉 Search Complete", style="bright_green")
        self.cli.print_tier_summary(
            auto=stats["applied"], semi=stats["semi_auto"], manual=stats["manual"]
        )

    def _search_for_jobs(self) -> list[Job]:
        if not self.profile:
            return []
        progress = self.cli.create_search_progress("Searching job sources")
        with progress:
            task = progress.add_task("Searching...", total=100)
            progress.update(task, advance=30)
            searcher = JobSearcher(self.profile)
            discovered = searcher.run_search()
            progress.update(task, advance=70)

        return [job for job in discovered if self.db.add_job(job, user_id=CLI_USER_ID)]

    def _evaluate_and_route(self, jobs: list[Job]) -> dict[str, int]:
        if not self.profile:
            return {"applied": 0, "semi_auto": 0, "manual": 0}

        stats = {"applied": 0, "semi_auto": 0, "manual": 0}
        evaluated: list[tuple[Job, MatchScore]] = []

        progress = self.cli.create_eval_progress(total=len(jobs))
        with progress:
            task = progress.add_task("evaluating", total=len(jobs))
            for job in jobs:
                score = self.matcher.evaluate_job(job, self.profile)
                self.db.add_match_score(score, user_id=CLI_USER_ID)
                application = self._route_application(job, score)
                self.db.add_application(application, user_id=CLI_USER_ID)

                if score.tier == "auto" and self.profile.auto_apply_enabled:
                    stats["applied"] += 1
                elif score.tier == "semi_auto":
                    stats["semi_auto"] += 1
                else:
                    stats["manual"] += 1

                evaluated.append((job, score))
                progress.advance(task)

        for job, score in sorted(evaluated, key=lambda x: x[1].score, reverse=True)[:3]:
            self.cli.print_job_card(job, score)

        return stats

    def _route_application(self, job: Job, score: MatchScore) -> Application:
        if score.tier == "auto" and self.profile and self.profile.auto_apply_enabled:
            status = ApplicationStatus.AUTO_APPLIED
            applied_at: datetime | None = datetime.now()
            applied_by = "system"
        elif score.tier == "semi_auto":
            status = ApplicationStatus.PENDING
            applied_at = None
            applied_by = "manual"
        else:
            status = ApplicationStatus.MANUAL_FLAG
            applied_at = None
            applied_by = "manual"

        return Application(
            job_id=job.id,
            job_title=job.title,
            company=job.company,
            status=status,
            match_score=score.score,
            match_tier=score.tier,
            applied_at=applied_at,
            applied_by=applied_by,
            notes=score.reason,
        )

    def _wait_with_progress(self, seconds: int) -> None:
        progress = self.cli.create_search_progress(f"Next cycle in {seconds}s")
        with progress:
            task = progress.add_task("waiting", total=seconds)
            for _ in range(seconds):
                if not self.is_running or self.is_paused:
                    break
                time.sleep(1)
                progress.advance(task)

    # ─── Lifecycle ───────────────────────────────────────────────

    def pause(self) -> None:
        self.is_paused = True
        self.cli.print_warning("Search paused. Type 'resume' to continue.")

    def resume(self) -> None:
        self.is_paused = False
        self.cli.print_success("Search resumed.")

    def stop(self) -> None:
        self.is_running = False
        self.cli.print_info("Search stopped.")

    # ─── Views ───────────────────────────────────────────────────

    def show_applications(self, status: str | None = None) -> None:
        apps = self.db.get_applications(user_id=CLI_USER_ID, status=status)
        self.cli.print_applications_table(apps)

    def show_application_detail(self, app_id: str) -> None:
        apps = self.db.get_applications(user_id=CLI_USER_ID)
        match = next((a for a in apps if a.id.startswith(app_id) or app_id.lower() in a.company.lower()), None)
        if not match:
            self.cli.print_error(f"No application matching '{app_id}' found.")
            return
        self.cli.print_application_detail(match)

    def show_stats(self) -> None:
        stats = self.db.get_stats(user_id=CLI_USER_ID)
        apps = self.db.get_applications(user_id=CLI_USER_ID)
        auto = sum(1 for a in apps if a.status == ApplicationStatus.AUTO_APPLIED)
        semi = sum(1 for a in apps if a.status == ApplicationStatus.PENDING)
        manual = sum(1 for a in apps if a.status == ApplicationStatus.MANUAL_FLAG)
        self.cli.print_search_status(
            cycle=0,
            found=stats.get("total_jobs", 0),
            applied=auto,
            semi_auto=semi,
            manual=manual,
            elapsed_seconds=0,
        )
        self.cli.print_tier_summary(auto=auto, semi=semi, manual=manual)

    # ─── REPL ────────────────────────────────────────────────────

    def run_repl(self) -> None:
        """Interactive command loop — the main user-facing entry point."""
        self.cli.print_info(
            "Commands: search [min], settings, applications [status|id], stats, help, exit"
        )
        while True:
            try:
                command = input("\n[agent]> ").strip()
            except (EOFError, KeyboardInterrupt):
                self.cli.print_info("Exiting.")
                break

            if not command:
                continue

            parts = command.split(maxsplit=1)
            cmd = parts[0].lower()
            arg = parts[1].strip() if len(parts) > 1 else None

            if cmd in ("exit", "quit", "q"):
                self.cli.print_info("Goodbye!")
                break
            elif cmd == "help":
                self._print_help()
            elif cmd == "search":
                duration = 30
                if arg and arg.isdigit():
                    duration = int(arg)
                self.start_search(duration_minutes=duration)
            elif cmd == "pause":
                self.pause()
            elif cmd == "resume":
                self.resume()
            elif cmd == "stop":
                self.stop()
            elif cmd in ("settings", "edit"):
                self.edit_settings()
            elif cmd == "applications":
                if arg in {"applied", "auto_applied"}:
                    self.show_applications(status=ApplicationStatus.AUTO_APPLIED.value)
                elif arg == "pending":
                    self.show_applications(status=ApplicationStatus.PENDING.value)
                elif arg in {"manual", "manual_flag"}:
                    self.show_applications(status=ApplicationStatus.MANUAL_FLAG.value)
                elif arg:
                    self.show_application_detail(arg)
                else:
                    self.show_applications()
            elif cmd == "profile":
                if self.profile:
                    self.cli.print_profile(self.profile)
                    self._print_salary_summary()
            elif cmd == "stats":
                self.show_stats()
            else:
                self.cli.print_warning(f"Unknown command: {cmd}. Type 'help' for options.")

    def _print_help(self) -> None:
        self.cli.print_message("\n[bold bright_cyan]Available Commands[/bold bright_cyan]\n")
        rows = [
            ("search [minutes]", "Run a search cycle (default: 30 min)"),
            ("settings / edit", "Edit profile, resume, salary, or job requirements"),
            ("applications", "List all applications"),
            ("applications applied", "Show auto-applied jobs only"),
            ("applications pending", "Show jobs awaiting review"),
            ("applications manual", "Show manually flagged jobs"),
            ("applications <company>", "Show details for a specific application"),
            ("profile", "Display current profile + salary summary"),
            ("stats", "Aggregate statistics"),
            ("pause / resume", "Control an active search"),
            ("stop", "Stop current search"),
            ("help", "Show this help"),
            ("exit", "Exit the agent"),
        ]
        for cmd, desc in rows:
            self.cli.print_message(f"  [cyan]{cmd:<28}[/cyan] {desc}")

    # ─── Input Helpers ───────────────────────────────────────────

    def _ask_text(self, prompt: str, default: str = "", required: bool = False) -> str:
        def validator(x: str) -> bool | str:
            if required and not x.strip():
                return "This field is required"
            return True

        result = questionary.text(prompt, default=default, validate=validator).ask()
        return result or default

    def _ask_email(self, prompt: str) -> str:
        def validator(x: str) -> bool | str:
            if "@" not in x or "." not in x:
                return "Enter a valid email"
            return True

        return questionary.text(prompt, validate=validator).ask() or "user@example.com"

    def _ask_int(self, prompt: str, default: int = 0, minimum: int = 0, maximum: int = 1000) -> int:
        def validator(x: str) -> bool | str:
            if not x.strip().isdigit():
                return "Must be a whole number"
            v = int(x)
            if v < minimum or v > maximum:
                return f"Must be between {minimum} and {maximum}"
            return True

        result = questionary.text(prompt, default=str(default), validate=validator).ask()
        return int(result) if result else default

    def _ask_float(
        self,
        prompt: str,
        default: float = 0.0,
        minimum: float = 0.0,
        maximum: float = 1e12,
        required: bool = False,
    ) -> float:
        def validator(x: str) -> bool | str:
            x_stripped = x.strip().replace(",", "")
            if not x_stripped:
                return "Required" if required else True
            try:
                v = float(x_stripped)
            except ValueError:
                return "Must be a number"
            if v < minimum or v > maximum:
                return f"Must be between {minimum} and {maximum}"
            return True

        result = questionary.text(prompt, default=str(default), validate=validator).ask()
        if result is None or not result.strip():
            return default
        return float(result.replace(",", ""))


@click.command()
@click.option("--duration", default=None, type=int, help="Run a one-shot search for N minutes and exit.")
@click.option("--show-apps", is_flag=True, help="Show applications and exit.")
@click.option("--stats", is_flag=True, help="Show stats and exit.")
@click.option("--settings", "open_settings", is_flag=True, help="Open settings menu and exit.")
def main(duration: int | None, show_apps: bool, stats: bool, open_settings: bool):
    """Job Hunt Agent — AI-powered job application automation."""
    try:
        config = get_config()
        setup_logging(config)
        agent = JobHuntAgent(config=config)
        agent.initialize()

        if show_apps:
            agent.show_applications()
            return
        if stats:
            agent.show_stats()
            return
        if open_settings:
            agent.edit_settings()
            return
        if duration is not None:
            agent.start_search(duration_minutes=duration)
            return

        agent.run_repl()

    except CredentialGateError:
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        cli = JobHuntCLI()
        cli.print_error(f"Unexpected error: {e}")
        logging.exception("Unhandled exception in main")
        sys.exit(2)


if __name__ == "__main__":
    main()
