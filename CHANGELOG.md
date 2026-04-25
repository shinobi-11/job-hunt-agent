# Changelog

All notable changes to Job Hunt Agent are documented here.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] — 2026-04-24

Initial release. Single-user local agent ready for day-to-day use.

### Added

**Core Workflow**
- Continuous job search across 4 sources: RemoteOK, Remotive, Jobicy, Himalayas
- Gemini 2.5 Flash AI matching engine with retry + fallback (`matcher.py`)
- AI-powered resume-to-profile extraction (`profile_builder.py`)
- PDF and DOCX resume parsing (`resume_parser.py`)
- 3-tier application routing: auto (≥85), semi_auto (70-84), manual (<70)
- SQLite persistence for jobs, applications, match scores, profile
- Interactive profile setup via `questionary`
- Pause / resume / stop controls via SIGINT/SIGTERM

**UI (Rich Terminal)**
- Animated cyan header with status badge
- Tier-styled job cards (emerald/amber/red borders)
- Real-time search status panel with Braille spinners
- Applications table with status icons
- Credential gate panel for missing secrets

**Configuration**
- Pydantic Settings (`config.py`) — env-based with validation
- Threshold relationship enforced (semi < auto)
- Log level normalization and bounds checking

**Testing**
- 120 unit + integration tests (82% coverage)
- 3 real-world E2E tests against live Gemini API (`--run-real` flag)
- Pyramid shape: 60% unit / 30% integration / 10% E2E
- Edge case coverage: score clamping, malformed JSON, retry logic

**Tooling**
- `pyproject.toml` with Black, Ruff, MyPy, pytest config
- Multi-stage `Dockerfile` (base + dev + prod, non-root user)
- `docker-compose.yml` with healthcheck + log rotation
- GitHub Actions CI (lint → test → security → build)
- pre-commit hooks (black, ruff, mypy, detect-private-key)
- `Makefile` with 11 shortcuts

**Deployment**
- `scripts/start.sh` — venv or Docker launcher with env validation
- `scripts/stop.sh` — graceful SIGTERM escalation
- `scripts/backup.sh` — timestamped tarball with 7-backup retention
- `scripts/healthcheck.sh` — 5-section diagnostic
- `DEPLOYMENT.md` — operations runbook + cloud migration roadmap

**Protocol Compliance (shinobi_dev)**
- Code Graph maintained across all 7 phases
- SMEM memory log (`.shinobi_mem`) — 20+ session records
- Issue Registry — 12 issues tracked, 9 resolved
- Credential Gate enforced (`GEMINI_API_KEY` validated on boot)
- Real Product Only — no mocks in production code paths

### Security

- `.env` gitignored; secrets never in source or image
- Parameterized SQL queries (no injection vectors)
- No PII sent to Gemini (resume stored locally only)
- Non-root Docker user (`jobagent`)

### Known Limitations

- Single-user local-only (SaaS migration path documented in DEPLOYMENT.md Part 5)
- Free-tier Gemini quota: ~50 evals/day before fallback to manual tier
- Auto-apply (Playwright) scaffold present but LinkedIn Easy Apply flow not yet wired
- Job sources skew tech-heavy; finance roles often route to manual tier
