# Job Hunt Agent — Product Brief

## Problem Statement
Job searching is time-consuming and repetitive. Users spend hours manually searching job boards, tailoring applications, and tracking submissions. This agent automates the entire workflow—discovering jobs across the internet, evaluating fit, and applying with zero user friction (auto-apply), minimal friction (semi-auto with review), or manual flag for complex applications.

## Target Users
- **Primary**: Software engineers, data scientists, and technical professionals actively job hunting
- **Secondary**: Anyone seeking employment who wants to maximize application volume while maintaining quality
- **Platform**: CLI-based, desktop environment (macOS, Linux, Windows)

## Core Value Proposition
Deploy once with your resume and preferences → agent runs continuously → job applications happen automatically while you focus on interviews and preparation. Transforms passive job search into an active, automated pipeline.

## MVP Scope

### In Scope ✅
- Resume upload & parsing (PDF/DOCX)
- Interactive profile builder (skills, experience, job preferences, salary expectations)
- Continuous internet-wide job search (Claude web_search API)
- **AI Model for Job Matching**: Gemini Pro evaluation engine that scores each discovered job against user profile, producing match score (0-100%)
- Job evaluation & scoring engine powered by Claude AI with detailed reasoning
- 3-tier routing: Auto-apply (score ≥85), Semi-auto (score 70-84, user review), Manual (score <70 or complex forms)
- SQLite database for application tracking
- Pause/Resume/Stop search controls
- Rich terminal UI with real-time progress and match visualizations
- Basic browser automation for 1-2 major job platforms (LinkedIn Easy Apply)

### Out of Scope ❌
- Interview prep or scheduling
- Complex multi-form applications (Workday, etc.) — manual tier only
- Email notifications (CLI output only for MVP)
- Dashboard analytics or reporting
- Mobile app or web UI (CLI-first)

## Success Metrics
1. **Functional**: Agent can search, evaluate, and apply to 5+ jobs per session without user intervention
2. **Accuracy**: Match score correctly identifies good-fit jobs (validated against manual review)
3. **Automation Rate**: ≥70% of suitable jobs go auto-apply, ≤30% require manual review
4. **Zero Errors**: No incomplete applications, no data loss, graceful error handling

## Constraints
- **Timeline**: MVP in 1 session
- **Team**: Solo (shinobi_dev)
- **Budget**: Free tier APIs only (Claude API key required, no Stripe/payment services)
- **Compliance**: No login scraping, respect job board ToS, use official APIs where available

## Success Criteria ✅
- Agent boots, loads profile, starts searching
- User can pause/resume/stop anytime
- Applications tracked in database
- Zero placeholder code, fully functional integrations
- Rich CLI with real-time updates and animations
