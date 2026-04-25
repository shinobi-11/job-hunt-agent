# ARCHITECTURE DECISION RECORD — Job Hunt Agent

## Phase 3 Architecture Document

**Project**: Job Hunt Agent  
**Date**: 2026-04-23  
**Status**: ✅ APPROVED  
**Author**: shinobi_dev (Principal Full-Stack)

---

## Executive Summary

The Job Hunt Agent is a **single-user, local-first Python CLI application** that continuously searches for jobs across the internet, evaluates them using Gemini AI, and routes applications into three tiers (auto/semi-auto/manual). This ADR captures all architectural decisions, data models, error handling strategies, and scalability considerations.

**Chosen Architecture**: Modular Monolith with Async I/O

---

## ADR-001: Monolith vs Microservices

### Decision
**CHOSEN**: Modular Monolith (single Python process)

### Alternatives Considered
| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **Modular Monolith** | Simple deploy, no network overhead, easy debugging | Limited horizontal scaling | ✅ **CHOSEN** |
| Microservices | Independent scaling, language polyglot | Network overhead, complex deployment, overkill for single user | ❌ Rejected |
| Serverless | Pay-per-use, auto-scaling | Cold starts for continuous search, state management complexity | ❌ Rejected |

### Rationale
- **Single-user tool**: No multi-tenancy requirements
- **Continuous execution**: Agent runs for hours/days — serverless cold starts hurt
- **Local deployment**: User runs on their machine, not cloud
- **Simple state**: SQLite sufficient; no distributed data needed
- **Easy debugging**: Single process = one log, one stack trace

### Trade-offs Accepted
- Not horizontally scalable (acceptable: 1 user = 1 process)
- Entire app restarts if agent crashes (mitigated by state persistence)
- Future SaaS version will require refactor (documented in roadmap)

---

## ADR-002: Module Structure

### Decision
Modular monolith with **domain-driven separation**:

```
job-hunt-agent/
├── agent.py              # Orchestrator (main entry point)
├── models.py             # Pydantic data models (domain objects)
├── database.py           # Data persistence layer
├── matcher.py            # AI matching engine (Gemini)
├── searcher.py           # Job discovery (multi-source)
├── applier.py            # Browser automation (Playwright)
├── resume_parser.py      # Resume parsing utilities
├── cli.py                # Rich terminal UI
├── config.py             # Configuration management
└── tests/                # All tests organized by module
```

### Module Responsibilities
| Module | Responsibility | Dependencies |
|---|---|---|
| `agent.py` | Orchestration, workflow control, pause/resume/stop | All modules |
| `models.py` | Pydantic schemas (single source of truth) | pydantic |
| `database.py` | SQLite CRUD, migrations, queries | models, sqlite3 |
| `matcher.py` | Gemini AI evaluation, prompt management | models, google-generativeai |
| `searcher.py` | Multi-source job discovery (async) | models, aiohttp, beautifulsoup |
| `applier.py` | Playwright auto-apply, form filling | models, playwright |
| `resume_parser.py` | PDF/DOCX parsing | PyPDF2, python-docx |
| `cli.py` | Rich UI rendering | rich, models |
| `config.py` | Env var loading, validation | python-dotenv, pydantic |

### Dependency Graph (DAG)
```
agent.py
   ├── cli.py
   ├── config.py
   ├── database.py ──→ models.py
   ├── matcher.py  ──→ models.py
   ├── searcher.py ──→ models.py
   ├── applier.py  ──→ models.py
   └── resume_parser.py

models.py ──→ (foundational — no internal deps)
```

**No cycles. Unidirectional dependencies. models.py is the foundation.**

---

## ADR-003: Data Flow Architecture

### High-Level Flow
```
┌─────────────────────────────────────────────────────────────────┐
│                     JOB HUNT AGENT LIFECYCLE                     │
└─────────────────────────────────────────────────────────────────┘

1. BOOTSTRAP
   ├─ Load .env (config.py)
   ├─ Validate GEMINI_API_KEY (credential gate)
   ├─ Initialize SQLite DB (database.py)
   ├─ Load/Create UserProfile (database.py)
   └─ Parse resume (resume_parser.py) [one-time]

2. SEARCH LOOP (every 5 minutes, async)
   ├─ Build search queries from profile (searcher.py)
   ├─ Query multiple sources in parallel (async):
   │    ├─ HackerNews Jobs API
   │    ├─ RemoteOK RSS
   │    ├─ GitHub Jobs (future)
   │    └─ LinkedIn (future, rate-limited)
   ├─ Deduplicate by job URL
   └─ Return List[Job]

3. EVALUATION (per job, sequential)
   ├─ Build prompt (matcher.py)
   ├─ Call Gemini API with retry logic
   ├─ Parse JSON response
   ├─ Persist MatchScore (database.py)
   └─ Route based on tier:
        ├─ score ≥ 85 → AUTO_APPLY → applier.py
        ├─ 70 ≤ score < 85 → SEMI_AUTO → queue for review
        └─ score < 70 → MANUAL → flag for user

4. APPLICATION (async, auto tier only)
   ├─ Detect platform (LinkedIn/Greenhouse/Lever/etc.)
   ├─ Launch Playwright (headless)
   ├─ Navigate, fill forms, attach resume
   ├─ Submit and verify
   └─ Record Application status

5. DISPLAY (real-time, Rich UI)
   ├─ Update counters (jobs found, applied, pending)
   ├─ Stream new job cards
   ├─ Show animated spinner during search
   └─ Handle user commands (pause/resume/stop)
```

### Concurrency Model
- **Main loop**: Synchronous (orchestrator)
- **Job search**: Async (aiohttp + asyncio.gather for parallel source queries)
- **Gemini evaluation**: Sequential (avoid rate limits, easier debugging)
- **Browser automation**: Async Playwright, one job at a time
- **UI rendering**: Synchronous (Rich handles its own threading)

---

## ADR-004: Database Schema

### Decision
**SQLite** (local, file-based, zero-config)

### Schema Design
```sql
-- Core entities
CREATE TABLE profiles (
    id TEXT PRIMARY KEY DEFAULT 'profile_1',
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    current_role TEXT,
    years_experience INTEGER DEFAULT 0,
    desired_roles TEXT,           -- JSON array
    skills TEXT,                  -- JSON array
    preferred_locations TEXT,     -- JSON array
    remote_preference TEXT DEFAULT 'any',
    salary_min REAL,
    salary_max REAL,
    industries TEXT,              -- JSON array
    company_size_preference TEXT,
    job_type TEXT,                -- JSON array
    availability TEXT DEFAULT 'immediate',
    willing_to_relocate BOOLEAN DEFAULT 0,
    auto_apply_enabled BOOLEAN DEFAULT 1,
    resume_text TEXT,             -- Parsed resume content
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE jobs (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    location TEXT,
    remote TEXT,                  -- 'remote', 'hybrid', 'on-site'
    salary_min REAL,
    salary_max REAL,
    currency TEXT DEFAULT 'USD',
    description TEXT NOT NULL,
    requirements TEXT,            -- JSON array
    source TEXT NOT NULL,         -- 'LinkedIn', 'HN', 'RemoteOK', etc.
    url TEXT UNIQUE NOT NULL,     -- Natural dedup key
    posted_date TIMESTAMP,
    discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE match_scores (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    score INTEGER NOT NULL CHECK (score >= 0 AND score <= 100),
    reason TEXT,
    matched_skills TEXT,          -- JSON array
    missing_skills TEXT,          -- JSON array
    cultural_fit TEXT,
    salary_alignment TEXT,
    tier TEXT NOT NULL CHECK (tier IN ('auto', 'semi_auto', 'manual')),
    confidence REAL CHECK (confidence >= 0 AND confidence <= 1),
    evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
);

CREATE TABLE applications (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    job_title TEXT NOT NULL,
    company TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN (
        'pending', 'auto_applied', 'semi_auto_applied',
        'manual_flag', 'rejected', 'error'
    )),
    match_score INTEGER,
    match_tier TEXT,
    applied_at TIMESTAMP,
    applied_by TEXT DEFAULT 'system',  -- 'system' or 'manual'
    notes TEXT,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
);

CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP,
    jobs_found INTEGER DEFAULT 0,
    jobs_applied INTEGER DEFAULT 0,
    status TEXT DEFAULT 'active',  -- 'active', 'paused', 'stopped', 'completed'
    notes TEXT
);

-- Indexes for query performance
CREATE INDEX idx_jobs_url ON jobs(url);
CREATE INDEX idx_jobs_discovered ON jobs(discovered_at DESC);
CREATE INDEX idx_applications_status ON applications(status);
CREATE INDEX idx_applications_created ON applications(created_at DESC);
CREATE INDEX idx_match_scores_tier ON match_scores(tier);
CREATE INDEX idx_match_scores_score ON match_scores(score DESC);
```

### Schema Notes
- **JSON arrays** stored as TEXT (SQLite has no native array; use `json.dumps/loads`)
- **CHECK constraints** enforce data integrity
- **FOREIGN KEY with CASCADE** cleans up child records automatically
- **Indexes** on common query patterns (URL uniqueness, tier filtering, date sorting)
- **Natural key** (job URL) prevents duplicates across search cycles

### Migration Strategy
- Schema versioned in `database.py` (SCHEMA_VERSION constant)
- On startup, check current version → apply pending migrations
- Never drop tables without user confirmation

---

## ADR-005: Gemini AI Integration Strategy

### Decision
**Model**: `gemini-pro` (default), fallback to `gemini-1.5-flash` if rate limited  
**Protocol**: Official `google-generativeai` SDK  
**Credential**: `GEMINI_API_KEY` env var (✅ provided)

### Token Budget Management
| Component | Est. Tokens | Notes |
|---|---|---|
| System prompt | 300 | Fixed (scoring guidelines, output format) |
| User profile | 400 | Variable (skills, preferences) |
| Job description | 500 | Truncated to 500 chars |
| Response (JSON) | 300 | Scored output |
| **TOTAL per eval** | **~1,500** | Well under 32K context |

**Monthly Budget (assuming 100 evals/day)**:
- Input: 1,200 tokens × 100 × 30 = 3.6M tokens/month
- Output: 300 tokens × 100 × 30 = 0.9M tokens/month
- **Cost**: ~$0.00 on Gemini Pro (free tier: 60 req/min)

### Prompt Engineering
```python
SYSTEM_PROMPT_VERSION = "v1.0.0"
SYSTEM_PROMPT = """
Analyze this job posting against the user's profile and provide a match score.

[USER PROFILE]
[JOB POSTING]

Scoring Guidelines:
- 85-100: Auto-apply (strong fit, critical skills present)
- 70-84: Semi-auto (good fit, minor gaps)
- 0-69: Manual (unclear fit, missing core skills)

Return JSON only:
{
  "score": 0-100,
  "reason": "...",
  "matched_skills": [...],
  "missing_skills": [...],
  "cultural_fit": "...",
  "salary_alignment": "...",
  "tier": "auto|semi_auto|manual",
  "confidence": 0.0-1.0
}
"""
```

**Prompt Versioning**: Stored as constant in `matcher.py`. Bump version on any change.

### Error Handling & Retry Logic
```python
RETRY_CONFIG = {
    "max_retries": 3,
    "backoff_base": 2,           # 2s → 4s → 8s
    "retryable_errors": [
        "ResourceExhausted",      # Rate limit
        "DeadlineExceeded",       # Timeout
        "ServiceUnavailable",     # 503
    ],
    "non_retryable": [
        "InvalidArgument",        # Bad prompt
        "PermissionDenied",       # Bad key
        "NotFound",               # Model removed
    ]
}
```

### Fallback Strategy
If Gemini unavailable after retries:
1. Log error in `applications.error_message`
2. Assign default score of **50** with tier **'manual'**
3. Flag for user review with note: "AI evaluation failed, manual review required"
4. Continue processing (don't crash the agent)

### Hallucination Mitigation
- **Structured output**: Force JSON format, parse defensively
- **Score validation**: `assert 0 <= score <= 100`
- **Tier validation**: `assert tier in {'auto', 'semi_auto', 'manual'}`
- **Schema check**: Pydantic validation on `MatchScore` instantiation

### PII Handling
- **Resume text**: NOT sent to Gemini (use profile fields only)
- **Skills/experience**: Sent (user opt-in via profile)
- **Email/phone**: NEVER sent to Gemini
- **Company data**: Public job posting info only

---

## ADR-006: Job Search Source Strategy

### Decision
**Tiered, multi-source approach** with graceful degradation

### Source Tiers
| Tier | Source | Priority | Status | Rate Limits |
|---|---|---|---|---|
| 1 | HackerNews Jobs | HIGH | ✅ Active | None (public) |
| 1 | RemoteOK RSS | HIGH | ✅ Active | None (RSS) |
| 2 | GitHub Jobs API | MEDIUM | 🔲 Roadmap | 60/hr unauth |
| 2 | LinkedIn Jobs | MEDIUM | 🔲 Roadmap | ⚠️ ToS restrictions |
| 3 | Indeed | LOW | 🔲 Future | API access paid |
| 3 | Greenhouse ATS | LOW | 🔲 Future | Per-company boards |

### Query Building
Profile → Queries:
```python
def build_queries(profile: UserProfile) -> List[str]:
    queries = []
    for role in profile.desired_roles:
        queries.append(f"{role} job")
        for location in profile.preferred_locations[:2]:
            queries.append(f"{role} in {location}")
        if profile.remote_preference == "remote":
            queries.append(f"remote {role}")
    return list(set(queries))[:5]  # Cap at 5 unique
```

### Deduplication Strategy
- **Primary key**: Job URL (SQL UNIQUE constraint)
- **Secondary check**: Title + Company fuzzy match (future)
- **Cache TTL**: Job considered "seen" for 30 days; re-evaluate after

### Failure Handling
```python
SEARCH_FAILURE_POLICY = {
    "min_sources_required": 1,   # At least 1 source must succeed
    "source_timeout": 10,         # 10s per source
    "retry_delay": 30,            # 30s before retrying failed source
}
```

If all sources fail → display error, wait 5 min, retry.

---

## ADR-007: Browser Automation (Auto-Apply)

### Decision
**Playwright (Chromium, headless)** for auto-apply on supported platforms

### Supported Platforms (Roadmap)
| Platform | Support | Complexity | Status |
|---|---|---|---|
| LinkedIn Easy Apply | ✅ Target | Medium | Phase 5 |
| Greenhouse | ✅ Target | Low (uniform forms) | Phase 5 |
| Lever | ✅ Target | Low | Phase 5 |
| Workday | ❌ Manual | Very High (multi-step) | Flag for user |
| Custom ATS | ❌ Manual | Unknown | Flag for user |

### Auto-Apply Flow
```
1. Detect platform (URL pattern matching)
2. Navigate to job page (headless Chromium)
3. Click "Apply" / "Easy Apply" button
4. Fill form fields from UserProfile:
   - Name, email, phone
   - Work authorization (Y/N from profile)
   - Years of experience
5. Attach resume (upload file from ./data/resume.pdf)
6. Answer screening questions (use Gemini to generate responses)
7. Submit
8. Verify success (confirmation page/message)
9. Screenshot final state → ./data/applications/{app_id}.png
10. Record status in DB
```

### Safety Rails
- **Dry-run mode**: `--dry-run` flag runs entire flow except final submit
- **User confirmation**: First-time auto-apply requires explicit user OK
- **Rate limiting**: Max 10 auto-applies per hour (LinkedIn ToS concern)
- **Screenshot evidence**: Every auto-apply saves a screenshot for audit trail
- **Stealth mode**: Playwright with anti-detection (playwright-stealth)

### Credential Storage
- LinkedIn credentials in `.env` (LINKEDIN_EMAIL, LINKEDIN_PASSWORD)
- Encrypted at rest? → **No for MVP**, documented as known risk
- Future: macOS Keychain / system credential manager

---

## ADR-008: State Management & Persistence

### Decision
**Layered state model** with SQLite as source of truth

### State Layers
| Layer | Persistence | Scope | Example |
|---|---|---|---|
| **Runtime** | Memory | Session | `is_paused: bool`, current cycle counter |
| **Session** | `sessions` table | Per-session | Started at, jobs found, duration |
| **Persistent** | All other tables | Forever | Jobs, applications, profile |

### Pause/Resume Mechanics
```python
class AgentState:
    is_running: bool = False
    is_paused: bool = False
    current_cycle: int = 0
    last_search_at: datetime

    def pause(self):
        self.is_paused = True
        # Loop checks self.is_paused every iteration
        # Mid-cycle work completes; next cycle waits

    def resume(self):
        self.is_paused = False

    def stop(self):
        self.is_running = False
        # Graceful shutdown: finish current eval, save state
```

### Crash Recovery
- **Jobs in progress**: Marked `status='pending'` until complete
- **On restart**: Agent loads profile, checks pending apps, resumes search
- **Atomic writes**: All DB ops in transactions (rollback on error)
- **Idempotent**: Duplicate job URLs ignored (UNIQUE constraint)

---

## ADR-009: Error Handling Strategy

### Decision
**Layered error handling** with graceful degradation

### Error Categories
| Category | Example | Strategy |
|---|---|---|
| **Transient** | Network timeout, rate limit | Retry with exponential backoff |
| **Configuration** | Missing API key, invalid profile | Halt, prompt user |
| **Data** | Malformed job posting, parse error | Log, skip, continue |
| **Infrastructure** | DB corruption, disk full | Halt, alert user |
| **Logic** | Bug in scoring, invalid state | Log, raise (dev mode) |

### Global Error Boundary
```python
def run_agent():
    try:
        agent.initialize()
        agent.start_search()
    except ConfigurationError as e:
        cli.print_error(f"Configuration issue: {e}")
        cli.print_message("Please check .env and restart.")
        sys.exit(1)
    except KeyboardInterrupt:
        cli.print_warning("Interrupted. Saving state...")
        agent.stop()
        sys.exit(0)
    except Exception as e:
        cli.print_error(f"Unexpected error: {e}")
        logger.exception("Unhandled exception")
        agent.stop()
        sys.exit(2)
```

### Per-Module Error Handling
- **matcher.py**: Retry Gemini calls → fallback to manual tier
- **searcher.py**: Skip failed source → continue with others
- **applier.py**: Screenshot on failure → flag as error, don't crash
- **database.py**: Rollback transactions → log, surface error

---

## ADR-010: Observability & Logging

### Decision
**Structured logging** to file + Rich console output

### Logging Levels
| Level | Use Case | Destination |
|---|---|---|
| DEBUG | Verbose, dev only | File only |
| INFO | Normal operations | File + Console (if verbose) |
| WARNING | Recoverable issues | File + Console |
| ERROR | Unrecoverable for task | File + Console (red) |
| CRITICAL | System failure | File + Console (red, halt) |

### Log Format
```python
LOG_FORMAT = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
LOG_FILE = "./data/agent.log"
LOG_ROTATION = "10 MB"  # Rotate at 10MB, keep 5 files
```

### Key Metrics Tracked
- Jobs found per cycle
- Match score distribution (histogram)
- Auto-apply success rate
- Gemini API latency (p50, p95, p99)
- Error counts by category

### No Third-Party Observability for MVP
- ❌ Sentry / Datadog / PostHog (overkill for local tool)
- ✅ Local file logs + periodic SQL queries for metrics

---

## ADR-011: Security Decisions

### Decision
**Defense in depth** with focus on credential hygiene

### Security Controls
| Control | Implementation | Rationale |
|---|---|---|
| **API keys** | `.env` only, never in code | Standard practice |
| **`.env` in gitignore** | ✅ Enforced | Prevent accidental commit |
| **Resume data** | Local only, never uploaded to 3P | User privacy |
| **SQL injection** | Parameterized queries (SQLite) | Prevent injection |
| **XSS** | N/A (no web UI) | CLI only |
| **CSRF** | N/A (no browser interaction for user) | CLI only |
| **Dependency CVEs** | `pip audit` in CI | Catch known vulns |
| **Secrets rotation** | Manual (user responsibility) | Simple approach |

### Threat Model
- **Adversary**: Accidental credential leak, supply chain attack
- **NOT covered**: Nation-state, physical access, insider threat
- **Assumptions**: User machine is trusted

### Data Retention
- **Resume**: Stored locally, never deleted (user-managed)
- **Profile**: Stored in DB, never expires
- **Jobs**: Retained indefinitely (useful for analytics)
- **Applications**: Retained indefinitely (audit trail)
- **Logs**: Rotated at 10MB, kept last 5 files (~50MB max)

### Compliance
- **GDPR**: User's own data on user's own machine → N/A
- **HIPAA**: No health data → N/A
- **PCI**: No payment data → N/A

---

## ADR-012: Performance & Scalability

### Decision
**Optimize for single-user throughput**, not horizontal scaling

### Performance Targets
| Metric | Target | Notes |
|---|---|---|
| Gemini API call | <5s p95 | Network-bound |
| Job search cycle | <30s | Depends on sources |
| Auto-apply flow | <60s per job | Playwright + network |
| UI update latency | <100ms | Rich framework |
| DB query (1M jobs) | <10ms | SQLite with indexes |

### Scaling Roadmap (Future)
If this becomes SaaS:
- **Phase A** (10 users): Current code + shared SQLite
- **Phase B** (100 users): Migrate to PostgreSQL + Celery workers
- **Phase C** (1000+ users): Microservices, Redis cache, load balancer

**NOT in current scope** — acknowledge and move on.

### Caching Strategy
- **No caching for MVP**: Fresh job searches every cycle
- **Deduplication** via DB uniqueness (effectively cache)
- **Future**: Redis cache for search queries, LLM responses

---

## ADR-013: Testing Strategy

### Decision
**Pyramid testing** with heavy unit coverage

### Test Layers
| Layer | Target Coverage | Tools |
|---|---|---|
| Unit | ≥80% on logic | pytest, pytest-cov |
| Integration | All API endpoints | pytest + fixtures |
| E2E | 1-2 golden paths | pytest + Playwright |

### Test Organization
```
tests/
├── conftest.py                 # Shared fixtures
├── unit/
│   ├── test_models.py
│   ├── test_matcher.py
│   ├── test_database.py
│   └── test_searcher.py
├── integration/
│   ├── test_agent_flow.py
│   └── test_gemini_integration.py
└── e2e/
    └── test_full_search_cycle.py
```

### Mocking Policy
- **Unit tests**: Mock all external dependencies (DB, APIs)
- **Integration tests**: Real DB, mocked external APIs
- **E2E tests**: Real DB + VCR cassettes for API responses

### CI/CD Integration
- Every commit triggers: `black → ruff → pytest` 
- Failing tests block merge
- Coverage report posted to PR

---

## ADR-014: Configuration Management

### Decision
**Pydantic Settings** with `.env` file loading

### Config Hierarchy (override order)
1. Default values (in `config.py`)
2. `.env` file (loaded by `python-dotenv`)
3. OS environment variables
4. Command-line flags (future, via click)

### Config Schema
```python
class Config(BaseSettings):
    # Required
    gemini_api_key: str = Field(..., min_length=39)
    
    # Optional with defaults
    search_interval_seconds: int = 300
    auto_apply_threshold: int = 85
    semi_auto_threshold: int = 70
    max_jobs_per_search: int = 10
    database_path: str = "./data/jobs.db"
    resume_path: str = "./data/resume.pdf"
    playwright_headless: bool = True
    linkedin_email: Optional[str] = None
    linkedin_password: Optional[str] = None
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
```

### Validation on Startup
- Missing GEMINI_API_KEY → halt with credential gate
- Invalid thresholds (<0 or >100) → halt with error
- Missing resume file → prompt user to provide
- Log level not in valid set → default to INFO + warning

---

## Architecture Decision Summary

| # | Decision | Rationale |
|---|---|---|
| 001 | Modular Monolith | Single-user, local deploy, simple |
| 002 | Domain-based modules | Clean separation, testable |
| 003 | Async I/O for search, sync for orchestration | Concurrency without complexity |
| 004 | SQLite with indexes | Zero-config, sufficient scale |
| 005 | Gemini Pro with fallback | AI matching, free tier |
| 006 | Tiered multi-source search | Resilient, extensible |
| 007 | Playwright for auto-apply | Headless automation, widely supported |
| 008 | Layered state (memory + DB) | Recoverable, atomic |
| 009 | Graceful error handling | Never crash mid-work |
| 010 | Structured file logging | Simple, rotatable |
| 011 | Defense-in-depth security | Credential hygiene, local-first |
| 012 | Single-user performance | Not scaling yet, measure first |
| 013 | Pyramid testing | Balanced coverage, fast feedback |
| 014 | Pydantic settings | Type-safe config |

---

## Non-Functional Requirements Verified

| NFR | Requirement | Design Support |
|---|---|---|
| **Reliability** | Agent runs 24/7 | Retry logic + state persistence |
| **Performance** | <30s search cycle | Async parallel sources |
| **Scalability** | 1 user now, extensible later | Modular monolith → microservices path |
| **Security** | No credential leaks | `.env` + gitignore + env-only loading |
| **Observability** | Understand what agent did | Structured logs + DB audit trail |
| **Maintainability** | Future devs can extend | Clean DAG, documented, tested |
| **Accessibility** | WCAG AA for terminal UI | Covered in DESIGN_SPEC.md |

---

## Phase 3 Sign-Off Checklist

- [x] Architecture pattern selected (Modular Monolith ✅)
- [x] Service boundaries defined (9 modules with clear responsibilities ✅)
- [x] Data models designed (5 tables with indexes ✅)
- [x] API contracts defined (Gemini integration spec ✅)
- [x] Authentication model (N/A for CLI, env-based auth ✅)
- [x] State management strategy (3-layer persistence ✅)
- [x] Third-party integrations listed (Gemini, HN, RemoteOK, future: LinkedIn, GitHub ✅)
- [x] Scalability plan documented (roadmap to SaaS ✅)
- [x] Failure modes mapped (5 categories + per-module strategy ✅)
- [x] Observability plan (structured logging + metrics ✅)
- [x] Data retention strategy (indefinite + log rotation ✅)
- [x] Compliance requirements (N/A — local user data ✅)
- [x] AI/ML strategy (token budget, versioning, hallucination mitigation ✅)

✅ **PHASE 3 ARCHITECTURE COMPLETE** — Ready for Phase 4 Tool Structure

---

## Open Questions for Future Phases

1. **Multi-language resumes**: Support non-English profiles?
2. **Offline mode**: Fallback when no internet?
3. **Push notifications**: Alert on new high-match jobs?
4. **Analytics dashboard**: Web UI for visualizing application history?
5. **Team/company edition**: Recruiter-side matching?

**Status**: Deferred to roadmap, not MVP scope.
