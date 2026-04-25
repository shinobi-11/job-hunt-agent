"""Best-effort scrapers for sites without public APIs.

These scrape *public job listing pages* (no login). Results are routed to the
manual tier so you apply through the original site. They will break when the
target site changes its HTML — that's expected. Errors are silent.
"""
from __future__ import annotations

import asyncio
import hashlib
import html as _html
import json
import logging
import re
from typing import Iterable

import aiohttp
from bs4 import BeautifulSoup

from models import Job

logger = logging.getLogger(__name__)

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _id(prefix: str, key: str) -> str:
    return f"{prefix}_{hashlib.md5(key.encode()).hexdigest()[:12]}"


def _clean(s: str | None) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", _html.unescape(s)).strip()


# ─────────────────────────────────────────────────────────────────
# LinkedIn — public job-search SSR endpoint (no auth)
# ─────────────────────────────────────────────────────────────────

async def scrape_linkedin(session: aiohttp.ClientSession, query: str, location: str = "") -> list[Job]:
    """LinkedIn exposes a server-rendered jobs search at
    /jobs-guest/jobs/api/seeMoreJobPostings/search — no login, no API key.
    Returns up to ~25 cards per call.
    """
    jobs: list[Job] = []
    url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    params = {
        "keywords": query,
        "location": location or "",
        "start": "0",
    }
    try:
        async with session.get(url, params=params, headers={"User-Agent": UA}) as resp:
            if resp.status != 200:
                return jobs
            html = await resp.text()
    except Exception as e:
        logger.debug(f"LinkedIn scrape failed: {e}")
        return jobs

    soup = BeautifulSoup(html, "html.parser")
    for li in soup.select("li")[:30]:
        try:
            title_a = li.select_one("h3, .base-search-card__title")
            company_a = li.select_one("h4, .base-search-card__subtitle")
            loc_el = li.select_one(".job-search-card__location")
            link_el = li.select_one("a.base-card__full-link") or li.select_one("a")
            if not title_a or not link_el:
                continue
            title = _clean(title_a.get_text())
            company = _clean(company_a.get_text() if company_a else "Unknown")
            loc = _clean(loc_el.get_text() if loc_el else "")
            link = (link_el.get("href") or "").split("?")[0]
            if not link:
                continue
            jobs.append(Job(
                id=_id("linkedin", link),
                title=title,
                company=company,
                location=loc or "Unknown",
                remote="hybrid" if "remote" in loc.lower() else "on-site",
                description=f"{title} at {company}. View full description on LinkedIn.",
                requirements=[],
                source="LinkedIn",
                url=link,
            ))
        except Exception:
            continue
    return jobs


# ─────────────────────────────────────────────────────────────────
# Naukri — public listing JSON in script tag
# ─────────────────────────────────────────────────────────────────

async def scrape_naukri(session: aiohttp.ClientSession, query: str, location: str = "") -> list[Job]:
    """Naukri's search URL pattern: /<keyword>-jobs-in-<location>"""
    jobs: list[Job] = []
    kw = query.lower().replace(" ", "-")
    loc = (location or "").lower().replace(" ", "-").split(",")[0].strip()
    if loc:
        url = f"https://www.naukri.com/{kw}-jobs-in-{loc}"
    else:
        url = f"https://www.naukri.com/{kw}-jobs"
    try:
        async with session.get(
            url,
            headers={"User-Agent": UA, "Accept": "text/html"},
        ) as resp:
            if resp.status != 200:
                return jobs
            html = await resp.text()
    except Exception as e:
        logger.debug(f"Naukri scrape failed: {e}")
        return jobs

    # Naukri stores listing data in a __INITIAL_STATE__ script
    m = re.search(r"window\.__INITIAL_STATE__\s*=\s*(\{.+?\});\s*</script>", html)
    if m:
        try:
            data = json.loads(m.group(1))
            listings = (
                data.get("searchResult", {}).get("jobDetails", [])
                or data.get("results", {}).get("jobs", [])
                or []
            )
            for j in listings[:30]:
                try:
                    jid = str(j.get("jobId") or j.get("id") or _id("naukri", j.get("title", "")))
                    title = _clean(j.get("title", "Role"))
                    company = _clean(j.get("companyName", "Unknown"))
                    locs = j.get("placeholders", []) or j.get("location", "")
                    loc_str = ", ".join([p.get("label", "") for p in locs]) if isinstance(locs, list) else str(locs)
                    desc = _clean(j.get("jobDescription", ""))
                    link = j.get("jdURL") or j.get("staticUrl") or ""
                    if link and not link.startswith("http"):
                        link = "https://www.naukri.com" + link
                    if not link:
                        continue
                    jobs.append(Job(
                        id=_id("naukri", jid),
                        title=title,
                        company=company,
                        location=_clean(loc_str) or "India",
                        remote="hybrid",
                        description=desc[:2000],
                        requirements=[],
                        source="Naukri",
                        url=link,
                    ))
                except Exception:
                    continue
        except Exception:
            pass

    # Fallback: parse anchor cards
    if not jobs:
        soup = BeautifulSoup(html, "html.parser")
        for card in soup.select("article.jobTuple, .srp-jobtuple-wrapper")[:30]:
            try:
                a = card.select_one("a.title, a.jobTitle")
                comp = card.select_one("a.subTitle, .companyInfo a")
                if not a:
                    continue
                title = _clean(a.get_text())
                link = a.get("href", "")
                if link and not link.startswith("http"):
                    link = "https://www.naukri.com" + link
                jobs.append(Job(
                    id=_id("naukri", link or title),
                    title=title,
                    company=_clean(comp.get_text() if comp else "Unknown"),
                    location="India",
                    remote="hybrid",
                    description=f"{title}. View full details on Naukri.",
                    requirements=[],
                    source="Naukri",
                    url=link,
                ))
            except Exception:
                continue

    return jobs


# ─────────────────────────────────────────────────────────────────
# iimjobs — public listing
# ─────────────────────────────────────────────────────────────────

async def scrape_iimjobs(session: aiohttp.ClientSession, query: str, location: str = "") -> list[Job]:
    """iimjobs.com — premium consulting/finance job board. Public listings."""
    jobs: list[Job] = []
    kw = query.lower().replace(" ", "+")
    url = f"https://www.iimjobs.com/search/?q={kw}"
    try:
        async with session.get(url, headers={"User-Agent": UA}) as resp:
            if resp.status != 200:
                return jobs
            html = await resp.text()
    except Exception as e:
        logger.debug(f"iimjobs scrape failed: {e}")
        return jobs

    soup = BeautifulSoup(html, "html.parser")
    for li in soup.select("li.fl-job-listing, .rs-bx, article")[:30]:
        try:
            a = li.select_one("a")
            if not a:
                continue
            title = _clean(a.get_text())
            link = a.get("href", "")
            if link and not link.startswith("http"):
                link = "https://www.iimjobs.com" + link
            company = _clean(li.select_one(".rs-cmp-nm").get_text()) if li.select_one(".rs-cmp-nm") else "Unknown"
            jobs.append(Job(
                id=_id("iimjobs", link or title),
                title=title,
                company=company,
                location="India",
                remote="hybrid",
                description=f"{title} at {company}. View full description on iimjobs.",
                requirements=[],
                source="iimjobs",
                url=link,
            ))
        except Exception:
            continue
    return jobs


# ─────────────────────────────────────────────────────────────────
# Instahyre — public job feed
# ─────────────────────────────────────────────────────────────────

async def scrape_instahyre(session: aiohttp.ClientSession, query: str, location: str = "") -> list[Job]:
    """Instahyre exposes a public JSON feed at /api/v1/job_search."""
    jobs: list[Job] = []
    params = {
        "li": "0",
        "q": query,
    }
    try:
        async with session.get(
            "https://www.instahyre.com/api/v1/job_search",
            params=params,
            headers={"User-Agent": UA, "Accept": "application/json"},
        ) as resp:
            if resp.status != 200:
                return jobs
            data = await resp.json(content_type=None)
    except Exception as e:
        logger.debug(f"Instahyre scrape failed: {e}")
        return jobs

    for j in (data.get("objects") or []):
        try:
            company = _clean(j.get("employer", {}).get("company_name", "Unknown"))
            title = _clean(j.get("title", "Role"))
            link = "https://www.instahyre.com/job/" + str(j.get("id", ""))
            jobs.append(Job(
                id=_id("instahyre", link),
                title=title,
                company=company,
                location=_clean(", ".join([l.get("name", "") for l in j.get("locations", [])])),
                remote="hybrid",
                salary_min=float(j.get("min_ctc")) if j.get("min_ctc") else None,
                salary_max=float(j.get("max_ctc")) if j.get("max_ctc") else None,
                currency="INR",
                description=_clean(j.get("description", ""))[:2000],
                requirements=[],
                source="Instahyre",
                url=link,
            ))
        except Exception:
            continue
    return jobs


# ─────────────────────────────────────────────────────────────────
# JSearch on RapidAPI (LinkedIn + Indeed + Glassdoor + ZipRecruiter)
# ─────────────────────────────────────────────────────────────────

async def scrape_jsearch_rapidapi(
    session: aiohttp.ClientSession, query: str, location: str = "", api_key: str | None = None,
) -> list[Job]:
    """JSearch via RapidAPI — aggregates LinkedIn/Indeed/Glassdoor/ZipRecruiter.
    Free tier: 200 calls/month. Optional — only runs if RAPIDAPI_JSEARCH_KEY set.
    """
    jobs: list[Job] = []
    if not api_key:
        return jobs
    url = "https://jsearch.p.rapidapi.com/search"
    full_q = f"{query} in {location}" if location else query
    params = {"query": full_q, "num_pages": "1"}
    try:
        async with session.get(
            url, params=params,
            headers={
                "X-RapidAPI-Key": api_key,
                "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
            },
        ) as resp:
            if resp.status != 200:
                return jobs
            data = await resp.json()
    except Exception as e:
        logger.debug(f"JSearch failed: {e}")
        return jobs

    for j in data.get("data", []):
        try:
            jobs.append(Job(
                id=_id("jsearch", j.get("job_id", "")),
                title=_clean(j.get("job_title", "Role")),
                company=_clean(j.get("employer_name", "Unknown")),
                location=_clean(f"{j.get('job_city','')} {j.get('job_country','')}"),
                remote="remote" if j.get("job_is_remote") else "on-site",
                salary_min=float(j["job_min_salary"]) if j.get("job_min_salary") else None,
                salary_max=float(j["job_max_salary"]) if j.get("job_max_salary") else None,
                currency=j.get("job_salary_currency", "USD"),
                description=_clean(j.get("job_description", ""))[:2000],
                requirements=[],
                source=f"JSearch ({j.get('job_publisher', 'agg')})",
                url=j.get("job_apply_link", j.get("job_google_link", "")),
            ))
        except Exception:
            continue
    return jobs


# ─────────────────────────────────────────────────────────────────
# Aggregator entry point
# ─────────────────────────────────────────────────────────────────

async def scrape_all(query: str, location: str = "", rapidapi_key: str | None = None) -> dict[str, list[Job]]:
    """Run all scrapers in parallel. Returns dict source_name → list of jobs.
    Sources that fail return [] silently."""
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        results = await asyncio.gather(
            scrape_linkedin(session, query, location),
            scrape_naukri(session, query, location),
            scrape_iimjobs(session, query, location),
            scrape_instahyre(session, query, location),
            scrape_jsearch_rapidapi(session, query, location, rapidapi_key),
            return_exceptions=True,
        )
    names = ["LinkedIn", "Naukri", "iimjobs", "Instahyre", "JSearch"]
    out: dict[str, list[Job]] = {}
    for name, result in zip(names, results):
        if isinstance(result, Exception):
            logger.warning(f"{name} scraper crashed: {result}")
            out[name] = []
        else:
            out[name] = result
    return out


def scrape_all_sync(query: str, location: str = "", rapidapi_key: str | None = None) -> dict[str, list[Job]]:
    try:
        return asyncio.run(scrape_all(query, location, rapidapi_key))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(scrape_all(query, location, rapidapi_key))
        finally:
            loop.close()
