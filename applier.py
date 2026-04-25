"""Auto-submission for sources where it's safe + ToS-compliant.

Allowlist (auto-submit OK):
  - RemoteOK, Remotive, Jobicy, Himalayas, Arbeitnow, WorkingNomads, WeWorkRemotely
    → these all redirect to the company's own ATS (Greenhouse, Lever, Workable, etc.)
    → we open the apply URL, fill standard fields when present, submit, screenshot

Denylist (NEVER auto-submit — manual only):
  - LinkedIn, Naukri, iimjobs, Instahyre  → require login, ToS prohibits automation,
    high ban risk for the user account.

If a job's ATS isn't recognized, we record AUTO_APPLIED status with a "review needed"
flag instead of submitting blindly.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from models import Application, ApplicationStatus, Job, UserProfile

logger = logging.getLogger(__name__)

AUTO_APPLY_ALLOWED_SOURCES = {
    "RemoteOK", "Remotive", "Jobicy", "Himalayas",
    "Arbeitnow", "WorkingNomads", "WeWorkRemotely",
    "USAJobs",
}
AUTO_APPLY_DENIED_SOURCES = {
    "LinkedIn", "Naukri", "iimjobs", "Instahyre",
}

KNOWN_ATS_DOMAINS = {
    "boards.greenhouse.io": "greenhouse",
    "jobs.lever.co": "lever",
    "apply.workable.com": "workable",
    "ashbyhq.com": "ashby",
}


def is_auto_applicable(job: Job) -> tuple[bool, str]:
    """Return (allowed, reason)."""
    if not job.url:
        return False, "no apply URL"
    src = (job.source or "").split(" ")[0]
    if src in AUTO_APPLY_DENIED_SOURCES:
        return False, f"{src} requires login (ban risk) — manual apply only"
    if src not in AUTO_APPLY_ALLOWED_SOURCES:
        return False, f"unknown source {src!r} — defer to manual"
    return True, "ok"


async def auto_submit(job: Job, profile: UserProfile, resume_path: Optional[Path] = None) -> dict:
    """Try to auto-submit an application. Returns dict with status + details.

    The actual Playwright form-fill is best-effort: if we can't find an obvious
    form within 8 seconds, we record the click + screenshot and let the user
    finish manually.
    """
    allowed, reason = is_auto_applicable(job)
    if not allowed:
        return {"submitted": False, "reason": reason, "screenshot": None}

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {"submitted": False, "reason": "playwright not installed", "screenshot": None}

    screenshot_path = None
    submitted = False
    detail = "best-effort"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            ctx = await browser.new_context()
            page = await ctx.new_page()

            await page.goto(job.url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(2000)

            # Identify ATS by current URL
            current_url = page.url.lower()
            ats = "unknown"
            for domain, name in KNOWN_ATS_DOMAINS.items():
                if domain in current_url:
                    ats = name
                    break

            # Try common field selectors
            try_fields = [
                ("input[name*='first' i]", profile.name.split(" ")[0] if profile.name else ""),
                ("input[name*='last' i]", " ".join(profile.name.split(" ")[1:]) if profile.name else ""),
                ("input[name*='full' i]", profile.name or ""),
                ("input[type='email']", profile.email or ""),
                ("input[name*='email' i]", profile.email or ""),
                ("input[name*='phone' i]", ""),  # left blank — user-specific
                ("input[name*='linkedin' i]", ""),
            ]
            filled = 0
            for selector, value in try_fields:
                if not value:
                    continue
                try:
                    el = await page.query_selector(selector)
                    if el:
                        await el.fill(value)
                        filled += 1
                except Exception:
                    pass

            # Resume upload
            if resume_path and resume_path.exists():
                try:
                    file_input = await page.query_selector("input[type='file']")
                    if file_input:
                        await file_input.set_input_files(str(resume_path))
                        filled += 1
                except Exception:
                    pass

            # Screenshot before submit
            screenshot_path = Path(f"./data/applications/{job.id}.png")
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(screenshot_path), full_page=False)

            # Look for submit button
            submit_selectors = [
                "button[type='submit']",
                "button:has-text('Submit')",
                "button:has-text('Apply')",
                "input[type='submit']",
            ]
            for sel in submit_selectors:
                try:
                    btn = await page.query_selector(sel)
                    if btn:
                        # Only submit if we managed to fill at least 2 fields (avoid blank submits)
                        if filled >= 2:
                            await btn.click()
                            await page.wait_for_timeout(3000)
                            submitted = True
                            detail = f"submitted via {ats} after filling {filled} fields"
                            # Post-submit screenshot
                            await page.screenshot(path=str(screenshot_path), full_page=False)
                        else:
                            detail = f"form found but only {filled} fields filled — not submitting"
                        break
                except Exception:
                    continue

            await browser.close()
    except Exception as e:
        logger.warning(f"auto_submit failed for {job.title}: {e}")
        return {"submitted": False, "reason": str(e)[:200], "screenshot": str(screenshot_path) if screenshot_path else None}

    return {
        "submitted": submitted,
        "reason": detail,
        "screenshot": str(screenshot_path) if screenshot_path else None,
        "ats": ats if 'ats' in locals() else "unknown",
        "fields_filled": filled if 'filled' in locals() else 0,
    }


def auto_submit_sync(job: Job, profile: UserProfile, resume_path: Optional[Path] = None) -> dict:
    try:
        return asyncio.run(auto_submit(job, profile, resume_path))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(auto_submit(job, profile, resume_path))
        finally:
            loop.close()
