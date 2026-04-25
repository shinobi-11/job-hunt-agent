---
title: Job Hunt Agent
emoji: 🎯
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
pinned: true
license: mit
short_description: AI-powered job application automation with multi-LLM support
---

# Job Hunt Agent

AI-powered job application automation. Upload your resume, set your salary expectations, pick an LLM provider (Gemini, OpenAI, Anthropic, or Grok), and let the agent continuously search 8+ remote job boards and auto-apply to high-match roles.

## Features

- 🤖 **Multi-LLM** — Bring your own Gemini, OpenAI, Anthropic, or xAI Grok key
- 💰 **Strict salary filter** — set a hike % range, jobs below it never reach the LLM
- 🎯 **3-tier routing** — score ≥85 auto-applies, 70–84 queues for review, <70 flagged
- 📡 **Live SSE feed** — watch jobs get discovered, scored, and routed in real time
- 🌐 **8+ job sources** — RemoteOK, Remotive, Jobicy, Himalayas, Arbeitnow, Working Nomads, We Work Remotely, USAJobs

## Stack

- **Backend**: FastAPI + Pydantic
- **Database**: Supabase Postgres (production), SQLite (local dev)
- **Auth**: bcrypt + signed-cookie sessions
- **Frontend**: Liquid Glass theme — vanilla HTML/CSS/JS (no build step)
- **Errors**: Sentry instrumentation

## Required secrets (Space Settings → Repository secrets)

| Name | Required | Notes |
|---|---|---|
| `DATABASE_URL` | ✅ | Supabase Postgres connection string (Transaction pooler) |
| `SESSION_SECRET` | ✅ | 64-char random string for cookie signing |
| `SUPABASE_URL` | ✅ | `https://<ref>.supabase.co` |
| `SUPABASE_SERVICE_KEY` | ✅ | service_role JWT |
| `SENTRY_DSN` | optional | Error tracking |

LLM API keys are **per-user** and stored in each user's profile via the UI — no global key needed.
