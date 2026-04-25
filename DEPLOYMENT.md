# Deployment Guide — Job Hunt Agent

**Phase 7 Deliverable**: Operational runbook for localhost deployment + cloud migration roadmap.

---

## Part 1 — Localhost Deployment (Current)

### Deployment Modes

The agent supports two local deployment modes. Both are production-ready for a single user:

| Mode | Use When | Startup Time | Isolation |
|---|---|---|---|
| **venv** (default) | Dev/iteration, fastest feedback | ~2s | Process-level |
| **Docker** | Reproducible builds, multi-host deploy later | ~30s (first build) | Container |

### Prerequisites

| Tool | Minimum Version | Required For |
|---|---|---|
| Python | 3.11+ | venv mode |
| Docker Desktop | 20.10+ | docker mode |
| SQLite | 3.35+ | Bundled with Python |
| Terminal | Any modern emulator | Rich UI rendering |

### 1. First-Run Setup

```bash
cd ~/Documents/job-hunt-agent

# 1. Copy env template and add your Gemini API key
cp .env.example .env
# Edit .env and set GEMINI_API_KEY=AIzaSy...

# 2. Place your resume (optional but recommended)
cp ~/path/to/your-resume.pdf data/resume.pdf

# 3. Verify system health
./scripts/healthcheck.sh

# 4. Launch agent
./scripts/start.sh              # venv mode (default)
./scripts/start.sh docker       # docker mode
```

### 2. Daily Operations

```bash
# Start agent
./scripts/start.sh

# Check health without starting
./scripts/healthcheck.sh

# Back up database (recommended before upgrades)
./scripts/backup.sh

# Stop agent gracefully
./scripts/stop.sh
```

### 3. Makefile Shortcuts

```bash
make run           # Start via python directly
make test          # Run test suite
make test-cov      # With coverage report
make lint          # Ruff + Black
make docker-build  # Build production image
make docker-run    # Run in Docker
```

### 4. Runtime Commands (Inside Agent)

Once the agent is running, these commands work at the `[agent]>` prompt:

| Command | Action |
|---|---|
| `search 30` | Run a 30-minute search cycle |
| `pause` | Pause mid-search |
| `resume` | Continue from pause |
| `stop` | Graceful stop (state saved) |
| `applications` | List all applications |
| `applications applied` | Filter by status |
| `stats` | Aggregate statistics |
| `exit` | Exit agent |

---

## Part 2 — Directory Layout (What Lives Where)

```
job-hunt-agent/
├── .env                      # Your secrets (gitignored)
├── .env.example              # Template
├── data/                     # Persistent state (gitignored)
│   ├── jobs.db              # SQLite database
│   ├── resume.pdf           # Your resume
│   ├── agent.log            # Structured log output
│   └── profile.json         # Profile cache (optional)
├── backups/                  # Timestamped DB backups
├── scripts/                  # Operational tooling
│   ├── start.sh
│   ├── stop.sh
│   ├── backup.sh
│   └── healthcheck.sh
├── docker-compose.yml        # Local Docker config
├── Dockerfile                # Multi-stage build
├── agent.py                  # Entry point
└── [source modules]          # Python code
```

---

## Part 3 — Operations Runbook

### Starting the Agent

**Expected flow**:
1. `.env` validated (GEMINI_API_KEY present & ≥30 chars)
2. venv activated or Docker image built
3. CLI renders cyan header
4. Profile loaded from DB (or interactive setup on first run)
5. `[agent]>` prompt appears
6. User types `search 60` to begin a 60-minute cycle

**If it fails to start**:
- Run `./scripts/healthcheck.sh` — catches 90% of issues
- Check `data/agent.log` for stack traces
- Verify GEMINI_API_KEY works: `make healthcheck` → section 4

### Monitoring (Live Session)

- **CLI Header**: status badge shows `[SEARCHING]` / `[PAUSED]` / `[IDLE]`
- **Search Status Panel**: real-time counters (cycle, jobs found, applied)
- **Log File**: `tail -f data/agent.log` for structured events
- **Gemini Quota**: free tier ≈50 req/day on `gemini-2.5-flash`; agent falls back to `manual` tier on quota

### Graceful Shutdown

```bash
# Option A: inside agent
[agent]> stop

# Option B: from another terminal
./scripts/stop.sh

# Option C: Ctrl+C (SIGINT is caught and handled)
```

On shutdown:
- Current search cycle completes
- In-memory state flushed to SQLite
- Signal handler prints shutdown message
- Exit code 0

### Database Backup & Restore

```bash
# Create backup
./scripts/backup.sh
# → backups/job-hunt-20260424_014000.tar.gz

# Restore from backup
tar -xzf backups/job-hunt-20260424_014000.tar.gz -C data/
mv data/jobs.db.bak data/jobs.db
```

**Retention**: `backup.sh` keeps the last 7 backups; older ones auto-deleted.

### Log Rotation

- **Docker mode**: `docker-compose.yml` rotates at 10MB, keeps 3 files
- **venv mode**: `data/agent.log` grows unbounded — rotate manually with `logrotate` or periodically truncate

### Common Incidents

| Symptom | Likely Cause | Fix |
|---|---|---|
| `CredentialGateError` on boot | GEMINI_API_KEY missing/short | Fix `.env`, restart |
| All jobs scored 50/manual | Gemini quota exhausted | Wait for reset, or upgrade Gemini plan |
| No jobs discovered | Source APIs down | Check `agent.log`; retry in 5min |
| Database locked | Multiple processes writing | `./scripts/stop.sh` then restart one instance |
| Rich UI garbled | Terminal width too narrow | Resize terminal ≥80 cols |

### Upgrade Procedure

```bash
# 1. Stop agent
./scripts/stop.sh

# 2. Backup database
./scripts/backup.sh

# 3. Pull latest code (when git is initialized)
git pull

# 4. Update dependencies
source venv/bin/activate
pip install -r requirements.txt --upgrade

# 5. Run tests
pytest tests/ --no-cov -q

# 6. Restart
./scripts/start.sh
```

### Rollback Procedure

```bash
./scripts/stop.sh
git checkout <previous-commit>
tar -xzf backups/job-hunt-<previous-timestamp>.tar.gz -C data/
mv data/jobs.db.bak data/jobs.db
./scripts/start.sh
```

---

## Part 4 — Performance & Resource Baselines

Measured on M1 Mac with 16GB RAM, running venv mode:

| Metric | Value |
|---|---|
| Memory (idle) | ~80 MB |
| Memory (active search) | ~150 MB |
| CPU (idle) | <1% |
| CPU (Gemini eval) | 5-10% (network-bound) |
| Startup time | 1.5s (venv), 8s (docker cold) |
| Search cycle | 20-40s (4 parallel sources) |
| Gemini eval per job | 2-5s p95 |
| SQLite query (10k jobs) | <20ms |

---

## Part 5 — Cloud Migration Roadmap

This is the path to get off localhost when ready. Captured now per ADR-012.

### Stage 1 — Single-User Cloud (Free Tier, ~0$/mo)

**Goal**: Move from laptop to always-on hosted agent.

| Component | Service | Tier | Why |
|---|---|---|---|
| Compute | **Fly.io** or **Railway** | Free ($5 credit/mo) | Simplest Docker-compatible host; supports persistent volumes for SQLite |
| Database | **Supabase** (Postgres) | Free 500MB | Direct SQLAlchemy migration from SQLite; built-in dashboard |
| Secrets | Host's built-in env vars | Free | No additional service |
| Storage | Host's persistent volume | Free 1GB | For resume.pdf and logs |
| Monitoring | **Better Stack** / **UptimeRobot** | Free | Pings healthcheck URL every 5 min |

**Migration steps**:
1. Swap `database.py` to use `DATABASE_URL` env var (Postgres connection string)
2. Add `alembic` for schema migrations
3. Expose a `/health` HTTP endpoint (FastAPI sidecar)
4. Deploy: `fly launch` or `railway up`
5. Set `GEMINI_API_KEY` in host's secret store
6. Mount persistent volume at `/app/data`

Estimated migration effort: ~4 hours.

### Stage 2 — Multi-User SaaS (~$10-30/mo)

When sharing with other job seekers:

| Component | Service | Notes |
|---|---|---|
| Compute | Fly.io scaled or **Render** | Paid tier for better uptime |
| Database | Supabase Pro | 8GB, dedicated resources |
| Auth | **Supabase Auth** | Google/GitHub OAuth built-in |
| Queue | **Upstash Redis** | Free tier 10k req/day for background jobs |
| Frontend | **Vercel** (Next.js dashboard) | Free hobby tier |
| Monitoring | **Sentry** | Free 5k errors/mo |

**Refactor required**:
- Split agent into API server + background worker (per ADR-012 Phase B)
- Replace Rich CLI with Next.js dashboard (per DESIGN_SPEC Phase 2)
- Add user isolation (each user has their own profile/applications)
- Rate limiting per user (Gemini quota sharing)

### Stage 3 — Production SaaS (~$50+/mo)

Only if traction justifies it:

| Component | Service |
|---|---|
| Compute | **AWS ECS / GCP Cloud Run** |
| Database | **AWS RDS / Supabase Pro** |
| Queue | **AWS SQS / Upstash** |
| CDN | **Cloudflare** |
| Observability | **Datadog / Grafana Cloud** |

---

## Part 6 — Deployment Checklist (Phase 7 Gate)

- [x] `docker-compose.yml` written with healthcheck + log rotation
- [x] `Dockerfile` multi-stage (dev + prod, non-root user)
- [x] `.dockerignore` excludes dev files and secrets
- [x] `scripts/start.sh` — auto-detects venv/docker mode
- [x] `scripts/stop.sh` — graceful SIGTERM + escalation
- [x] `scripts/backup.sh` — timestamped tarball, 7-backup retention
- [x] `scripts/healthcheck.sh` — 5-section diagnostic
- [x] Environment parity documented (dev → prod)
- [x] Logs rotated (10MB/3 files in Docker)
- [x] Secrets in `.env`, never in image
- [x] Runbook written (start/stop/backup/restore/upgrade/rollback)
- [x] Incident response table
- [x] Cloud migration roadmap (3 stages)
- [x] Performance baselines captured
- [x] Healthcheck verified working
