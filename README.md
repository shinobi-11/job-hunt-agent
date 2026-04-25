# Job Hunt Agent

**AI-powered job application automation with Gemini AI and intelligent 3-tier routing**

[![CI](https://github.com/user/job-hunt-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/user/job-hunt-agent/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## What It Does

Continuously searches the internet for jobs matching your profile, evaluates each one using Gemini AI (scoring 0-100), and routes applications into three tiers:

- **✅ Auto-Apply** (score 85+): Submitted automatically via browser automation
- **⚠️ Semi-Auto** (score 70-84): Presented for your quick review before submission
- **🚩 Manual** (score <70): Flagged for you to evaluate and apply manually

## Features

- 🤖 **Gemini AI Matching** — Evaluates each job against your profile with detailed reasoning
- 🌐 **Multi-Source Search** — HackerNews, RemoteOK, expandable to LinkedIn/Indeed/GitHub
- 📄 **Resume Parsing** — PDF and DOCX support with automatic section extraction
- 💾 **Persistent Tracking** — SQLite database for all jobs, scores, and application history
- 🎨 **Rich Terminal UI** — Animated spinners, real-time counters, glassmorphic cards
- ⏸️ **Pause/Resume/Stop** — Full control over the search cycle
- 🔐 **Credential Gate** — Stops automatically when secrets are missing

## Quick Start

### Prerequisites
- Python 3.11 or higher
- Gemini API key ([get one free](https://aistudio.google.com/app/apikey))
- Resume in PDF or DOCX format

### Installation

```bash
# Clone repository
git clone https://github.com/user/job-hunt-agent.git
cd job-hunt-agent

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers (for auto-apply)
playwright install chromium

# Copy environment template and add your key
cp .env.example .env
# Edit .env and set GEMINI_API_KEY=your_key_here
```

### Run

```bash
python agent.py
```

On first run, you'll be guided through interactive profile creation. After that, the agent will continuously search and evaluate jobs.

### Commands

Once running, type commands at the `[agent]>` prompt:

| Command | Action |
|---|---|
| `search [minutes]` | Start a search session (default: 30 min) |
| `pause` | Pause current search |
| `resume` | Resume paused search |
| `stop` | Stop search and save state |
| `applications` | Show all applications |
| `applications applied` | Filter by status |
| `profile` | Display your profile |
| `stats` | Show aggregate statistics |
| `help` | List all commands |
| `exit` | Exit the agent |

## Project Structure

```
job-hunt-agent/
├── agent.py              # Main orchestrator + CLI entry point
├── models.py             # Pydantic data models (domain)
├── database.py           # SQLite persistence layer
├── matcher.py            # Gemini AI job evaluation
├── searcher.py           # Multi-source job discovery
├── cli.py                # Rich terminal UI
├── resume_parser.py      # PDF/DOCX resume parsing
├── tests/                # Unit + integration tests
│   ├── conftest.py
│   ├── unit/
│   └── integration/
├── .github/workflows/    # CI/CD (lint, test, security, build)
├── PRODUCT_BRIEF.md      # Phase 1 — Product scope
├── DESIGN_SPEC.md        # Phase 2 — UI/UX design
├── ARCHITECTURE_ADR.md   # Phase 3 — System architecture
├── CODE_GRAPH.md         # Live code graph (auto-updated)
├── ISSUE_REGISTRY.md     # Issue tracking
└── .shinobi_mem          # Persistent memory log
```

## Development

### Running Tests

```bash
# All tests
pytest

# Unit tests only (fast)
pytest tests/unit -v

# Integration tests
pytest tests/integration -v

# With coverage
pytest --cov=. --cov-report=html
open htmlcov/index.html
```

### Code Quality

```bash
# Format
black .

# Lint
ruff check .

# Type check
mypy .

# All checks (pre-commit)
pre-commit run --all-files
```

### Docker

```bash
# Development
docker build --target development -t job-hunt-agent:dev .
docker run --env-file .env -it job-hunt-agent:dev

# Production
docker build --target production -t job-hunt-agent:latest .
docker run --env-file .env -v $(pwd)/data:/app/data job-hunt-agent:latest
```

## Configuration

All configuration via `.env` file. See `.env.example` for all options:

| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | *(required)* | Your Gemini API key |
| `SEARCH_INTERVAL_SECONDS` | `300` | Time between search cycles (5 min) |
| `AUTO_APPLY_THRESHOLD` | `85` | Min score for auto-apply |
| `SEMI_AUTO_THRESHOLD` | `70` | Min score for semi-auto |
| `MAX_JOBS_PER_SEARCH` | `10` | Max jobs per cycle |
| `DATABASE_PATH` | `./data/jobs.db` | SQLite database location |
| `RESUME_PATH` | `./data/resume.pdf` | Your resume file |
| `PLAYWRIGHT_HEADLESS` | `true` | Headless browser for auto-apply |
| `LINKEDIN_EMAIL` | *(optional)* | For LinkedIn Easy Apply |
| `LINKEDIN_PASSWORD` | *(optional)* | For LinkedIn Easy Apply |

## Architecture Summary

- **Pattern**: Modular monolith (single Python process)
- **AI**: Gemini Pro with retry/fallback logic
- **Storage**: SQLite with 5 indexed tables
- **Async**: `aiohttp` for parallel job source queries
- **UI**: Rich framework with real-time updates
- **Browser**: Playwright (Chromium, headless)
- **Testing**: Pytest pyramid (80% unit / integration / E2E)

See `ARCHITECTURE_ADR.md` for complete details.

## Roadmap

- [x] Phase 1: Ideation & Product Brief
- [x] Phase 2: Design Specification
- [x] Phase 3: Architecture ADR
- [x] Phase 4: Tool Structure (pyproject, Docker, CI, tests)
- [ ] Phase 5: Production code implementation
- [ ] Phase 6: Full test coverage (80%+)
- [ ] Phase 7: Deployment (Docker Hub, release)
- [ ] Phase 8: Documentation & Delivery

## Contributing

This is a personal project, but PRs are welcome for:
- Additional job sources (LinkedIn, Indeed, GitHub)
- New auto-apply platforms (Greenhouse, Lever, Workday)
- UI improvements
- Test coverage

## License

MIT © 2026

## Credits

Built with:
- [Google Gemini AI](https://ai.google.dev/) — Job matching intelligence
- [Rich](https://github.com/Textualize/rich) — Terminal UI
- [Playwright](https://playwright.dev/) — Browser automation
- [Pydantic](https://docs.pydantic.dev/) — Data validation
- [SQLite](https://sqlite.org/) — Persistence
