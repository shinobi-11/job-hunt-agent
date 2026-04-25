"""Job discovery engine — multi-source parallel search with smart relevance + diagnostics."""
from __future__ import annotations

import asyncio
import hashlib
import html as html_lib
import logging
import re

import aiohttp
from bs4 import BeautifulSoup

from models import Job, UserProfile

logger = logging.getLogger(__name__)

STOPWORDS = {
    "senior", "junior", "lead", "staff", "principal", "sr", "jr",
    "i", "ii", "iii", "iv", "v", "vi",
    "the", "a", "an", "and", "or", "of", "for", "in", "to", "at", "by", "on",
    "remote", "hybrid", "onsite", "office",
}

# Domain synonyms that count as keyword matches.
SYNONYMS: dict[str, set[str]] = {
    "financial": {"finance", "fp&a", "treasury"},
    "investment": {"ib", "private equity", "pe", "venture", "vc", "asset management"},
    "banking": {"bank", "credit", "lending"},
    "analyst": {"analytics", "modelling", "modeling", "research"},
    "associate": {"consultant", "specialist"},
    "data": {"analytics", "bi", "business intelligence"},
    "engineer": {"developer", "engineering", "swe"},
    "marketing": {"growth", "demand gen", "performance marketing"},
    "product": {"pm", "product manager", "product owner"},
}


class SearchDiagnostics:
    """Per-cycle counters surfaced via run_search() for the UI/CLI."""

    def __init__(self):
        self.discovered_per_source: dict[str, int] = {}
        self.discovered_total = 0
        self.deduped = 0
        self.passed_salary = 0
        self.passed_relevance = 0
        self.returned = 0
        self.errors_per_source: dict[str, str] = {}

    def as_dict(self) -> dict:
        return {
            "discovered_per_source": self.discovered_per_source,
            "discovered_total": self.discovered_total,
            "deduped_count": self.deduped,
            "passed_salary": self.passed_salary,
            "passed_relevance": self.passed_relevance,
            "returned": self.returned,
            "errors_per_source": self.errors_per_source,
        }


class JobSearcher:
    """Search 8+ remote/global job sources in parallel and rank by relevance."""

    SOURCE_TIMEOUT = 20

    def __init__(self, profile: UserProfile):
        self.profile = profile
        self.queries = self._build_queries(profile)
        self.keywords = self._extract_keywords(profile)
        self.diagnostics = SearchDiagnostics()

    def _build_queries(self, profile: UserProfile) -> list[str]:
        queries = [r for r in profile.desired_roles if r.strip()]
        return list(dict.fromkeys(queries))[:10]

    def _extract_keywords(self, profile: UserProfile) -> set[str]:
        tokens: set[str] = set()
        for role in profile.desired_roles:
            for token in re.split(r"[\s,/&\-]+", role.lower()):
                token = token.strip()
                if len(token) >= 3 and token not in STOPWORDS:
                    tokens.add(token)
                    tokens |= SYNONYMS.get(token, set())
        # Skills also count as relevance signals
        for skill in profile.skills[:8]:
            for token in re.split(r"[\s,/&\-]+", skill.lower()):
                token = token.strip()
                if len(token) >= 3 and token not in STOPWORDS:
                    tokens.add(token)
        return tokens

    def run_search(self) -> list[Job]:
        try:
            return asyncio.run(self._search_all())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(self._search_all())
            finally:
                loop.close()

    async def _search_all(self) -> list[Job]:
        async with aiohttp.ClientSession(
            headers={"User-Agent": _UA},
            timeout=aiohttp.ClientTimeout(total=self.SOURCE_TIMEOUT),
        ) as session:
            tasks = [
                ("remoteok", self._search_remoteok(session)),
                ("remotive", self._search_remotive(session)),
                ("jobicy", self._search_jobicy(session)),
                ("himalayas", self._search_himalayas(session)),
                ("arbeitnow", self._search_arbeitnow(session)),
                ("workingnomads", self._search_workingnomads(session)),
                ("weworkremotely", self._search_wwr(session)),
                ("usajobs", self._search_usajobs(session)),
            ]
            results = await asyncio.gather(*[t[1] for t in tasks], return_exceptions=True)

        all_jobs: list[Job] = []
        for (name, _), result in zip(tasks, results):
            if isinstance(result, Exception):
                logger.warning(f"Source {name} failed: {result}")
                self.diagnostics.errors_per_source[name] = str(result)[:120]
                self.diagnostics.discovered_per_source[name] = 0
                continue
            self.diagnostics.discovered_per_source[name] = len(result)
            all_jobs.extend(result)

        # Run scrapers (LinkedIn / Naukri / iimjobs / Instahyre / JSearch).
        # These are best-effort; failures are silent. Scraped jobs lack full
        # detail so they'll route to the manual tier after Gemini scoring.
        try:
            import os
            from scrapers import scrape_all
            primary_query = self.queries[0] if self.queries else ""
            primary_location = (self.profile.preferred_locations[0]
                                if self.profile.preferred_locations else "")
            scraped = await scrape_all(
                query=primary_query,
                location=primary_location,
                rapidapi_key=os.environ.get("RAPIDAPI_JSEARCH_KEY"),
            )
            for name, items in scraped.items():
                self.diagnostics.discovered_per_source[name.lower()] = len(items)
                all_jobs.extend(items)
        except Exception as e:
            logger.warning(f"Scrapers crashed: {e}")

        self.diagnostics.discovered_total = len(all_jobs)

        # Dedup
        seen_urls: set[str] = set()
        deduped: list[Job] = []
        for job in all_jobs:
            if not job.url or job.url in seen_urls:
                continue
            seen_urls.add(job.url)
            deduped.append(job)
        self.diagnostics.deduped = len(deduped)

        # Salary filter
        if self.profile.strict_salary_filter and self.profile.salary_min:
            deduped = [j for j in deduped if self._passes_salary_filter(j)]
        self.diagnostics.passed_salary = len(deduped)

        # Relevance filter (uses synonyms)
        relevant = [j for j in deduped if self._is_relevant(j)]
        self.diagnostics.passed_relevance = len(relevant)

        # Sort by relevance score
        scored = sorted(relevant, key=lambda j: self._relevance_score(j), reverse=True)
        result = scored[:25]
        self.diagnostics.returned = len(result)

        logger.info(f"Search diagnostics: {self.diagnostics.as_dict()}")
        return result

    def _is_relevant(self, job: Job) -> bool:
        if not self.keywords:
            return True
        haystack = f"{job.title} {job.description[:1500]}".lower()
        hits = sum(1 for kw in self.keywords if kw in haystack)
        return hits >= 1

    def _relevance_score(self, job: Job) -> int:
        score = 0
        title_lower = job.title.lower()
        desc_lower = job.description[:1500].lower()

        # Exact role match in title gets the highest weight
        for role in self.profile.desired_roles:
            if role.lower() in title_lower:
                score += 20
            elif role.lower() in desc_lower:
                score += 8

        # Keywords in title vs description
        for kw in self.keywords:
            if kw in title_lower:
                score += 4
            elif kw in desc_lower:
                score += 1

        # Industry hits
        for industry in self.profile.industries:
            if industry.lower() in desc_lower:
                score += 3

        # Salary in expected range bonus
        if (job.salary_min and job.salary_max
                and self.profile.salary_min and self.profile.salary_max):
            if job.salary_min >= self.profile.salary_min:
                score += 5
        return score

    def _passes_salary_filter(self, job: Job) -> bool:
        if job.salary_max is None:
            return True  # don't reject missing-salary jobs
        if self.profile.salary_min is None:
            return True
        return job.salary_max >= self.profile.salary_min * 0.85

    # ─── Sources ──────────────────────────────────────────────

    async def _search_remoteok(self, session) -> list[Job]:
        jobs: list[Job] = []
        try:
            async with session.get("https://remoteok.com/api") as resp:
                if resp.status != 200:
                    return jobs
                data = await resp.json(content_type=None)
        except Exception:
            return jobs

        for entry in (data[1:80] if isinstance(data, list) and len(data) > 1 else []):
            try:
                jobs.append(Job(
                    id=f"remoteok_{entry.get('id', entry.get('slug', ''))}",
                    title=_clean(entry.get("position", "Remote Role")),
                    company=_clean(entry.get("company", "Unknown")),
                    location=_clean(entry.get("location", "Remote")),
                    remote="remote",
                    salary_min=float(entry["salary_min"]) if entry.get("salary_min") else None,
                    salary_max=float(entry["salary_max"]) if entry.get("salary_max") else None,
                    currency="USD",
                    description=_strip_html(entry.get("description", ""))[:2000],
                    requirements=entry.get("tags", []) if isinstance(entry.get("tags"), list) else [],
                    source="RemoteOK",
                    url=entry.get("url", entry.get("apply_url", "")),
                ))
            except Exception:
                continue
        return jobs

    async def _search_remotive(self, session) -> list[Job]:
        jobs: list[Job] = []
        try:
            async with session.get("https://remotive.com/api/remote-jobs?limit=80") as resp:
                if resp.status != 200:
                    return jobs
                data = await resp.json()
        except Exception:
            return jobs
        for e in data.get("jobs", []):
            try:
                lo, hi = _salary(e.get("salary", "") or "")
                jobs.append(Job(
                    id=f"remotive_{e.get('id')}",
                    title=_clean(e.get("title", "Remote Role")),
                    company=_clean(e.get("company_name", "Unknown")),
                    location=_clean(e.get("candidate_required_location", "Remote")),
                    remote="remote",
                    salary_min=lo, salary_max=hi, currency="USD",
                    description=_strip_html(e.get("description", ""))[:2000],
                    requirements=[e.get("category", "")] if e.get("category") else [],
                    source="Remotive",
                    url=e.get("url", ""),
                ))
            except Exception:
                continue
        return jobs

    async def _search_jobicy(self, session) -> list[Job]:
        jobs: list[Job] = []
        try:
            async with session.get("https://jobicy.com/api/v3/remote-jobs?count=50") as resp:
                if resp.status != 200:
                    return jobs
                data = await resp.json()
        except Exception:
            return jobs
        for e in data.get("jobs", []):
            try:
                lo, hi = _salary(f"{e.get('annualSalaryMin','')} {e.get('annualSalaryMax','')}")
                jobs.append(Job(
                    id=f"jobicy_{e.get('id')}",
                    title=_clean(e.get("jobTitle", "Remote Role")),
                    company=_clean(e.get("companyName", "Unknown")),
                    location=_clean(", ".join(e.get("jobGeo", ["Remote"]))
                                    if isinstance(e.get("jobGeo"), list)
                                    else (e.get("jobGeo") or "Remote")),
                    remote="remote",
                    salary_min=lo, salary_max=hi,
                    currency=e.get("salaryCurrency", "USD"),
                    description=_strip_html(e.get("jobDescription", ""))[:2000],
                    requirements=e.get("jobIndustry", []) if isinstance(e.get("jobIndustry"), list) else [],
                    source="Jobicy",
                    url=e.get("url", ""),
                ))
            except Exception:
                continue
        return jobs

    async def _search_himalayas(self, session) -> list[Job]:
        jobs: list[Job] = []
        try:
            async with session.get("https://himalayas.app/jobs/api?limit=50") as resp:
                if resp.status != 200:
                    return jobs
                data = await resp.json()
        except Exception:
            return jobs
        for e in data.get("jobs", []):
            try:
                jobs.append(Job(
                    id=f"himalayas_{e.get('slug') or hashlib.md5(str(e).encode()).hexdigest()[:10]}",
                    title=_clean(e.get("title", "Remote Role")),
                    company=_clean(e.get("companyName")
                                   or (e.get("company") or {}).get("name")
                                   or "Unknown"),
                    location=_clean(", ".join(e.get("locationRestrictions", ["Remote"]))
                                    if isinstance(e.get("locationRestrictions"), list)
                                    else "Remote"),
                    remote="remote",
                    salary_min=float(e["minSalary"]) if e.get("minSalary") else None,
                    salary_max=float(e["maxSalary"]) if e.get("maxSalary") else None,
                    currency=e.get("salaryCurrency", "USD"),
                    description=_strip_html(e.get("excerpt", "") or e.get("description", ""))[:2000],
                    requirements=e.get("categories", []) if isinstance(e.get("categories"), list) else [],
                    source="Himalayas",
                    url=(f"https://himalayas.app{e.get('applicationLink', e.get('slug',''))}"
                         if e.get("slug") else e.get("applicationLink", "")),
                ))
            except Exception:
                continue
        return jobs

    async def _search_arbeitnow(self, session) -> list[Job]:
        """Arbeitnow — 100+ jobs across all industries, free public API."""
        jobs: list[Job] = []
        try:
            async with session.get("https://www.arbeitnow.com/api/job-board-api") as resp:
                if resp.status != 200:
                    return jobs
                data = await resp.json()
        except Exception:
            return jobs
        for e in data.get("data", []):
            try:
                jobs.append(Job(
                    id=f"arbeitnow_{e.get('slug')}",
                    title=_clean(e.get("title", "Role")),
                    company=_clean(e.get("company_name", "Unknown")),
                    location=_clean(e.get("location", "Remote")),
                    remote="remote" if e.get("remote") else "on-site",
                    description=_strip_html(e.get("description", ""))[:2000],
                    requirements=e.get("tags", []) if isinstance(e.get("tags"), list) else [],
                    source="Arbeitnow",
                    url=e.get("url", ""),
                ))
            except Exception:
                continue
        return jobs

    async def _search_workingnomads(self, session) -> list[Job]:
        """Working Nomads — JSON feed of vetted remote jobs."""
        jobs: list[Job] = []
        try:
            async with session.get("https://www.workingnomads.com/api/exposed_jobs/") as resp:
                if resp.status != 200:
                    return jobs
                data = await resp.json()
        except Exception:
            return jobs
        items = data if isinstance(data, list) else data.get("results", [])
        for e in items[:80]:
            try:
                jobs.append(Job(
                    id=f"wn_{e.get('id') or hashlib.md5(str(e).encode()).hexdigest()[:10]}",
                    title=_clean(e.get("title", "Remote Role")),
                    company=_clean(e.get("company_name", "Unknown")),
                    location=_clean(e.get("location", "Remote")),
                    remote="remote",
                    description=_strip_html(e.get("description", ""))[:2000],
                    requirements=[c for c in (e.get("category_name", "")).split(",") if c],
                    source="WorkingNomads",
                    url=e.get("url", ""),
                ))
            except Exception:
                continue
        return jobs

    async def _search_wwr(self, session) -> list[Job]:
        """We Work Remotely — RSS feed, all industries."""
        jobs: list[Job] = []
        try:
            async with session.get("https://weworkremotely.com/remote-jobs.rss") as resp:
                if resp.status != 200:
                    return jobs
                xml = await resp.text()
        except Exception:
            return jobs
        try:
            soup = BeautifulSoup(xml, "xml")
            for item in soup.find_all("item")[:60]:
                title_raw = (item.title.text if item.title else "Remote Role")
                # WWR titles look like "Acme Corp: Senior Engineer"
                if ":" in title_raw:
                    company, _, title = title_raw.partition(":")
                else:
                    company, title = "Unknown", title_raw
                desc = item.description.text if item.description else ""
                link = item.link.text if item.link else ""
                jobs.append(Job(
                    id=f"wwr_{hashlib.md5(link.encode()).hexdigest()[:10]}",
                    title=_clean(title),
                    company=_clean(company),
                    location="Remote",
                    remote="remote",
                    description=_strip_html(desc)[:2000],
                    source="WeWorkRemotely",
                    url=link,
                ))
        except Exception:
            return jobs
        return jobs

    async def _search_usajobs(self, session) -> list[Job]:
        """USAJobs — US federal jobs. Public, all industries."""
        jobs: list[Job] = []
        # Build keyword from desired roles
        keyword = (self.profile.desired_roles[0] if self.profile.desired_roles else "")
        if not keyword:
            return jobs
        params = {
            "Keyword": keyword,
            "ResultsPerPage": "25",
        }
        try:
            async with session.get(
                "https://data.usajobs.gov/api/search",
                params=params,
                headers={
                    "User-Agent": "job-hunt-agent (contact@example.com)",
                    "Host": "data.usajobs.gov",
                },
            ) as resp:
                if resp.status != 200:
                    return jobs
                data = await resp.json()
        except Exception:
            return jobs
        for item in (data.get("SearchResult", {}).get("SearchResultItems", []) or []):
            try:
                d = item.get("MatchedObjectDescriptor", {})
                lo = d.get("PositionRemuneration", [{}])[0].get("MinimumRange") if d.get("PositionRemuneration") else None
                hi = d.get("PositionRemuneration", [{}])[0].get("MaximumRange") if d.get("PositionRemuneration") else None
                locs = d.get("PositionLocationDisplay", "USA")
                jobs.append(Job(
                    id=f"usaj_{d.get('PositionID', hashlib.md5(str(d).encode()).hexdigest()[:10])}",
                    title=_clean(d.get("PositionTitle", "Federal Role")),
                    company=_clean(d.get("OrganizationName", "US Federal")),
                    location=_clean(str(locs)),
                    remote="on-site",
                    salary_min=float(lo) if lo else None,
                    salary_max=float(hi) if hi else None,
                    currency="USD",
                    description=_strip_html(
                        " ".join(d.get("UserArea", {}).get("Details", {}).get("MajorDuties", []))
                        or d.get("QualificationSummary", "")
                    )[:2000],
                    requirements=[],
                    source="USAJobs",
                    url=d.get("PositionURI", ""),
                ))
            except Exception:
                continue
        return jobs


# ─── Helpers ────────────────────────────────────────────────────────

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _strip_html(html: str) -> str:
    if not html:
        return ""
    try:
        text = BeautifulSoup(html, "html.parser").get_text(separator=" ")
    except Exception:
        text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", html_lib.unescape(text)).strip()


def _clean(text) -> str:
    if not text:
        return ""
    return html_lib.unescape(str(text)).strip()


def _salary(text: str):
    if not text:
        return None, None
    nums = re.findall(r"(\d+[kKmM]?)", text.replace(",", "").replace("$", ""))
    if not nums:
        return None, None

    def to_num(n):
        try:
            if n.lower().endswith("k"):
                return float(n[:-1]) * 1000
            if n.lower().endswith("m"):
                return float(n[:-1]) * 1_000_000
            return float(n)
        except ValueError:
            return None

    parsed = [v for v in (to_num(n) for n in nums[:2]) if v is not None]
    if len(parsed) == 2:
        return min(parsed), max(parsed)
    if len(parsed) == 1:
        return parsed[0], parsed[0]
    return None, None


# Backwards compat — older tests import these
def _strip_html_compat(html):  # pragma: no cover
    return _strip_html(html)


_clean_text = _clean
_parse_salary_range = _salary
