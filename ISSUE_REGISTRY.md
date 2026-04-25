# Issue Registry — Job Hunt Agent

## Open Issues (Not Yet Fixed)

| ID | Severity | Category | Description | Blocker | Status |
|---|---|---|---|---|---|
| ISS-001 | CRITICAL | Phase2 | Design spec not written — UX flows, wireframes, interactive design layer missing | YES | OPEN |
| ISS-002 | CRITICAL | Phase3 | Architecture ADR not written — system blueprint, data models, API contracts undefined | YES | OPEN |
| ISS-003 | HIGH | Phase4 | Testing framework not configured — no unit/integration/E2E tests | YES | OPEN |
| ISS-004 | HIGH | Phase4 | Linting & formatting not set up — ESLint, Black, Ruff, git hooks missing | NO | OPEN |
| ISS-005 | HIGH | Phase4 | Docker not configured — dev + prod Dockerfiles missing | NO | OPEN |
| ISS-006 | HIGH | Phase4 | CI/CD not set up — GitHub Actions pipeline missing | NO | OPEN |
| ISS-007 | HIGH | Protocol5 | Credential Gate not enforced — GEMINI_API_KEY required but no gate check | YES | OPEN |
| ISS-008 | MEDIUM | Protocol3 | Interactive design not implemented — CLI needs animations, real-time progress, glassmorphism | NO | OPEN |
| ISS-009 | MEDIUM | Phase5 | Resume parsing not integrated — parse_resume() not called in agent flow | NO | OPEN |
| ISS-010 | MEDIUM | Phase5 | Job search limited to HN + RSS — LinkedIn/Indeed/GitHub APIs not integrated | NO | OPEN |
| ISS-011 | MEDIUM | Phase5 | Browser automation not implemented — Playwright skeleton present but no auto-apply logic | NO | OPEN |
| ISS-012 | LOW | Phase4 | README not written — setup, run, deploy instructions missing | NO | OPEN |

## Resolved Issues (None Yet)

(No issues resolved in this session yet)

## Regression Watch List

(No prior regressions detected — fresh start)

## Critical Blockers Preventing Phase 5 Continuation

✋ **HALT — Cannot proceed to Phase 5 (DEVELOPMENT) until:**

1. **ISS-001**: Phase 2 Design complete — UX spec needed
2. **ISS-002**: Phase 3 Architecture complete — ADR needed
3. **ISS-003**: Phase 4 Testing setup complete — test framework configured
4. **ISS-007**: Credential Gate implemented — GEMINI_API_KEY validated

## Phase Completion Checklist

### ✅ PHASE 1 — IDEATION [COMPLETE]
- [x] Problem statement articulated
- [x] Target users identified
- [x] Core value proposition stated
- [x] MVP scope defined (in vs out)
- [x] Success metrics defined
- [x] Constraints captured
- [x] Non-functional requirements noted
- **Output**: PRODUCT_BRIEF.md ✅

---

### ❌ PHASE 2 — DESIGN [NOT STARTED]
**BLOCKER**: This phase must complete before Phase 5 continues.

- [ ] User flows mapped (happy path + edge cases)
- [ ] Wireframes or component hierarchy defined
- [ ] Navigation structure decided
- [ ] Responsive/adaptive breakpoints specified
- [ ] Design system selected/created
- [ ] Interactive design layer planned (animations, real-time, micro-interactions)
- [ ] Auth + Dashboard included by default
- [ ] Accessibility requirements noted (WCAG 2.1 AA)
- [ ] Data display patterns decided
- [ ] Error, empty, loading states designed
- [ ] Interaction patterns defined
- [ ] Dark mode variant defined
- **Output**: DESIGN_SPEC.md (TODO)

**Required Deliverables**:
- CLI UI component hierarchy
- Interactive design specs (Rich animations, progress bars, live updates)
- Error/loading/empty states
- Color system & typography for terminal

---

### ❌ PHASE 3 — ARCHITECTURE [NOT STARTED]
**BLOCKER**: This phase must complete before Phase 5 continues.

- [ ] Architecture pattern selected (monolith → microservices → serverless → hybrid)
- [ ] Service boundaries defined
- [ ] Data models designed (entities, relationships, indexes)
- [ ] API contract defined (if external APIs used)
- [ ] Authentication & authorization model
- [ ] State management strategy
- [ ] Third-party integrations listed with fallback plans
- [ ] Scalability plan (horizontal vs vertical)
- [ ] Failure modes mapped
- [ ] Observability plan (logging, metrics, tracing)
- [ ] Data retention & backup strategy
- [ ] Compliance requirements baked in
- [ ] AI/ML model serving strategy (Gemini integration, token budget, hallucination mitigation)
- **Output**: ARCHITECTURE_ADR.md (TODO)

**Required Decisions**:
- Monolith architecture (single agent script)
- Database: SQLite (local) vs PostgreSQL (if scaling)
- Job search sources: prioritization & fallback handling
- Gemini token budget: limits per evaluation, batch size
- Error handling for LLM failures
- State persistence across pause/resume cycles

---

### 🟡 PHASE 4 — TOOL STRUCTURE [PARTIAL]
**BLOCKER on**: Testing framework, Credential Gate, CI/CD

**Completed**:
- [x] Package manager locked (pip + requirements.txt)
- [x] Project structure scaffolded
- [x] .env.example created
- [x] .gitignore created

**Not Done**:
- [ ] Linting configured (Black, Ruff, pylint)
- [ ] Formatting configured (Prettier for output?)
- [ ] Git hooks set up (Husky equivalent for Python)
- [ ] Environment variable management (currently manual dotenv)
- [ ] Docker configured (dev + prod)
- [ ] CI/CD pipeline scaffolded (GitHub Actions)
- [ ] Testing framework initialized (pytest + pytest-cov)
- [ ] Directory structure finalized
- [ ] README written
- [ ] Dependency audit run

**Action Required**:
- [ ] Create `pyproject.toml` with linting/test config
- [ ] Create `Dockerfile` (dev + prod)
- [ ] Create `.github/workflows/ci.yml`
- [ ] Create `tests/` directory with conftest.py
- [ ] Write setup instructions in README.md

---

### 🔴 PHASE 5 — DEVELOPMENT [STARTED EARLY, REGRESSING]
**Status**: Code written, but phases 2-4 not complete. **REGRESSION REQUIRED.**

**Code Written (at risk)**:
- models.py ✅ (foundational, safe)
- database.py ✅ (safe)
- matcher.py ✅ (safe, but needs Gemini key validation)
- searcher.py ✅ (safe, extensible)
- cli.py ✅ (safe, but no animations yet — Protocol 3 debt)
- resume_parser.py ✅ (safe)
- agent.py 🟡 (partial, CLI loop needs refinement)

**Cannot Proceed To** next files without:
- [ ] Phase 2 Design sign-off (UX refinements needed to agent.py)
- [ ] Phase 3 Architecture decision (will affect database schema, error handling)
- [ ] Phase 4 Testing setup (must write tests alongside new code)
- [ ] Credential Gate implementation (GEMINI_API_KEY validation)

---

## Recommended Action Plan

### Immediate (Before Resuming Phase 5):

**Step 1**: Complete PHASE 2 DESIGN (30 min)
```
Deliverable: DESIGN_SPEC.md with:
- CLI component breakdown (header, profile, job cards, status table, progress bar)
- Interactive design specs (Rich animations, real-time job discovery display)
- Error/loading/empty states
- Terminal color & typography system
```

**Step 2**: Complete PHASE 3 ARCHITECTURE (30 min)
```
Deliverable: ARCHITECTURE_ADR.md with:
- Monolith architecture justification
- Data flow diagram (search → match → apply → persist)
- Gemini token budget strategy
- Error handling & fallback logic for LLM failures
- State persistence across pause/resume
- Scalability notes
```

**Step 3**: Complete PHASE 4 TOOL STRUCTURE (30 min)
```
Deliverables:
- pyproject.toml (Black, Ruff, pytest config)
- Dockerfile (dev + prod)
- .github/workflows/ci.yml (basic lint → test → build)
- tests/ directory structure
- README.md (setup, run, test, deploy)
```

**Step 4**: Implement Credential Gate (15 min)
```
In agent.py initialize():
  if not os.getenv("GEMINI_API_KEY"):
      << CREDENTIAL GATE >>
      Stop. Print setup instructions.
      Wait for user.
```

---

## SMEM Integration

After each phase completion, update SMEM with:
```
SMEM_PATCH|seq:N
P|PHASE_2_COMPLETE|DESIGN_SPEC.md written, reviewed, approved
P|PHASE_3_COMPLETE|ARCHITECTURE_ADR.md written, reviewed, approved
P|PHASE_4_COMPLETE|pyproject.toml, Dockerfile, .github/workflows/ci.yml, README.md complete
P|PHASE_5_GATES_MET|All blockers cleared — Phase 5 resumes
```

---

## Notes

- **Current state**: Code written, protocols not fully followed
- **Risk level**: Medium (code is good, but architecture decisions not documented, tests missing)
- **Regression danger**: ISS-001/ISS-002 not resolved may require refactoring later
- **Next session**: Can resume Phase 5 immediately after phases 2-4 complete

