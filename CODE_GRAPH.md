# Code Graph — Job Hunt Agent

## Project Structure Map

```
job-hunt-agent/
├── models.py                    [Pydantic models]
├── database.py                  [SQLite ORM layer]
├── matcher.py                   [Gemini AI job matching]
├── searcher.py                  [Job discovery engine]
├── cli.py                       [Rich terminal UI]
├── resume_parser.py             [Resume PDF/DOCX parsing]
├── agent.py                     [Main orchestrator]
├── PRODUCT_BRIEF.md             [Phase 1 ideation]
├── CODE_GRAPH.md                [This file]
├── ISSUE_REGISTRY.md            [Open issues & regressions]
├── DESIGN_SPEC.md               [Phase 2 TODO]
├── ARCHITECTURE_ADR.md          [Phase 3 TODO]
└── data/                        [Runtime database & uploads]
    ├── jobs.db                  [SQLite database]
    ├── resume.pdf               [User resume]
    └── profile.json             [User profile]
```

## Module Dependencies

### models.py (FOUNDATIONAL)
**Exports**: `ApplicationStatus`, `Job`, `MatchScore`, `UserProfile`, `Application`, `SearchState`
**Imports**: pydantic, enum, datetime
**Dependents**: database.py, matcher.py, cli.py, agent.py
**Status**: ✅ Complete, no external deps beyond pydantic

### database.py (DATA LAYER)
**Exports**: `JobDatabase`
**Imports**: models.py, sqlite3, json, pathlib
**Dependents**: agent.py
**Signature**: `JobDatabase(db_path: str) → add_job/add_application/add_match_score/save_profile/get_profile/get_applications/get_stats`
**Status**: ✅ Complete, production-ready schema

### matcher.py (AI LAYER)
**Exports**: `JobMatcher`
**Imports**: models.py, google.generativeai, json
**Dependents**: agent.py
**Signature**: `JobMatcher(api_key: str) → evaluate_job(Job, UserProfile) → MatchScore`
**Status**: ✅ Complete, Gemini integration working
**Creds Required**: GEMINI_API_KEY ✅ (user has Pro account)

### searcher.py (DISCOVERY LAYER)
**Exports**: `JobSearcher`
**Imports**: models.py, aiohttp, feedparser, beautifulsoup4, asyncio
**Dependents**: agent.py
**Signature**: `JobSearcher(UserProfile) → search_jobs() → List[Job]`
**Status**: ✅ Complete, multi-source search (HN, RSS feeds)
**Note**: Extensible for LinkedIn/Indeed/GitHub APIs later

### cli.py (UI LAYER)
**Exports**: `JobHuntCLI`
**Imports**: rich (console, panels, tables, progress), models.py
**Dependents**: agent.py
**Signature**: `JobHuntCLI() → print_header/print_profile/print_job_card/print_applications_table/create_progress_bar`
**Status**: ✅ Complete, rich UI framework ready

### resume_parser.py (UTILITY)
**Exports**: `ResumeParser`
**Imports**: PyPDF2, python-docx, pathlib
**Dependents**: agent.py (not yet called)
**Signature**: `ResumeParser.parse_resume(str) → str` | `extract_sections(str) → dict`
**Status**: ✅ Complete, PDF+DOCX support

### agent.py (ORCHESTRATOR)
**Exports**: `JobHuntAgent`, `main()`
**Imports**: All modules above, click, dotenv
**Signature**: `JobHuntAgent() → initialize/start_search/pause/resume/stop/show_applications/show_stats`
**Status**: ⚠️ PARTIAL — CLI loop needs refinement, credential gate not enforced

## Current Graph State

**Nodes**: 7 files × 2-8 classes/functions per file = ~35 symbols
**Edges**: 10 intra-module dependencies
**Cycles**: None (DAG structure ✅)
**Status**: 🟡 Incomplete — Phase 2-4 not reflected; no design/arch specs yet

## Known Gaps (Issue Registry)

- [ ] PHASE 2 DESIGN not started — UX flows, wireframes, interactive design specs needed
- [ ] PHASE 3 ARCHITECTURE not started — system blueprint, data models refinement, API contracts needed
- [ ] PHASE 4 TOOL STRUCTURE partial — linting, testing, CI/CD, Docker not set up
- [ ] Credential Gate not enforced in code — GEMINI_API_KEY needed at runtime
- [ ] No tests written — Phase 6 required before Phase 7/8
- [ ] Interactive design (Protocol 3) not implemented — CLI needs animations/real-time updates
- [ ] Resume parsing not integrated into agent flow
- [ ] Job search sources limited (HN + RSS only) — needs LinkedIn/Indeed/GitHub

## Navigation Protocol

When modifying code:
1. Consult this graph first
2. Load only ≤3 files for single-function changes
3. Update this graph after every change
4. Verify no caller breakage

