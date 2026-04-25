# DESIGN SPECIFICATION — Job Hunt Agent CLI UI

## Phase 2 Design Document

**Project**: Job Hunt Agent  
**Medium**: Terminal/CLI using Rich Framework  
**Date**: 2026-04-23  
**Status**: ✅ DESIGN PHASE COMPLETE

---

## Design Direction: "Intelligent Minimalism with Kinetic Energy"

### Aesthetic Vision
A refined, purposeful CLI that feels **intelligent and capable** — not cluttered, but never empty. Draws inspiration from:
- **Brutalist tech interfaces** (sparse, functional, powerful)
- **Real-time dashboards** (kinetic animations that show progress)
- **High-contrast accessibility** (clarity over decoration)
- **Kinetic typography** (text reveals, spinners, live counters)

**Core Philosophy**: Every visual element has a job. Motion happens when something *changes*. Silence when waiting. Impact on discovery.

---

## Color System: "Sapphire & Amber Palate"

### Terminal Color Palette
```
Primary Accent:    Cyan (#00D9FF)      [discovery, action, flow]
Success:           Emerald (#00E5A0)   [applied, complete, positive]
Warning:           Amber (#FFB800)     [manual review, attention needed]
Error:             Red (#FF4444)       [critical, blocked, failed]
Neutral Dark:      Slate-800 (#1E293B) [background, secondary text]
Neutral Light:     Slate-200 (#E2E8F0) [borders, dividers, hints]
Accent Secondary:  Purple (#A78BFA)    [insights, metadata, tags]
```

### Usage
- **Cyan**: Headers, loading spinners, primary CTAs, emphasis text
- **Emerald**: Success messages, auto-apply confirmations, progress completion
- **Amber**: Manual review flags, warnings, user action required
- **Red**: Errors, blocked operations, critical alerts
- **Purple**: Secondary stats, metadata, job source tags
- **Slate**: Structure (boxes, borders, background), dimmed text

### Contrast Standards
- All text ≥ 4.5:1 contrast ratio (WCAG AA minimum)
- No information conveyed by color alone (always supplement with icons/symbols)

---

## Component Hierarchy & Layout

### Screen Composition (Terminal-Safe Grid)
```
┌─────────────────────────────────────────────────────────────┐
│ HEADER (Branding + Status)                                   │
├─────────────────────────────────────────────────────────────┤
│ PROFILE SECTION (Read-only after first setup)               │
├─────────────────────────────────────────────────────────────┤
│ SEARCH STATUS BAR (Real-time counter + Spinner)             │
├─────────────────────────────────────────────────────────────┤
│ JOB CARDS STREAM (Scrolling, with match score)              │
├─────────────────────────────────────────────────────────────┤
│ APPLICATIONS TABLE (Summary of submitted + flagged)          │
├─────────────────────────────────────────────────────────────┤
│ COMMAND PROMPT (Interactive input: pause/resume/stop)        │
└─────────────────────────────────────────────────────────────┘
```

---

## Component Specs

### 1. HEADER
**Purpose**: Branding + session state at a glance  
**Dimensions**: Full width, 5 lines

```
╭─────────────────────────────────────────────────────────────╮
│ 🎯 JOB HUNT AGENT                                [SEARCHING] │
│ AI-powered job application automation                        │
│ Resume: resume.pdf • Profile: John Doe • Session: 00:15:32  │
╰─────────────────────────────────────────────────────────────╯
```

**Design Details**:
- Bold cyan emoji (🎯) for visual anchor
- Bright cyan title text (bold)
- Dim gray descriptive text
- Status badge right-aligned: `[SEARCHING]` (cyan, animated), `[PAUSED]` (amber), `[IDLE]` (slate)
- Bottom line: profile summary (dim slate, small font)
- Rich Panel with rounded borders (style="cyan")

**Animations**:
- Status badge pulses when searching (opacity 0.6→1.0, 1s loop)
- Emoji rotates slowly when active (0→10° over 2s, loop)

---

### 2. PROFILE SECTION
**Purpose**: Quick reference of search criteria  
**Dimensions**: Full width, collapsible, 6 lines when expanded

```
┌─ PROFILE ─────────────────────────────────────────────────┐
│ Role: Software Engineer   |   Skills: Python, React, AWS   │
│ Experience: 5 years       |   Location: San Francisco      │
│ Salary: $120k–$200k       |   Remote: ✓ Hybrid             │
└───────────────────────────────────────────────────────────┘
```

**Design Details**:
- Horizontal layout, 2 columns
- Left column (role, experience, salary) in cyan headers
- Right column (values) in neutral text
- Dividers (|) between columns
- Collapsible via `profile` command
- Rich Table with no_lines style, cyan border

**Styling**:
- Cyan table border
- Green checkmark (✓) for enabled preferences
- Dim text for secondary values

---

### 3. SEARCH STATUS BAR
**Purpose**: Real-time visibility into what's happening  
**Dimensions**: Full width, 3 lines

```
┌ SEARCHING (Cycle #42) ──────────────────────────────────┐
│ ⠋ Evaluating 5 jobs...    Found: 247 | Applied: 38     │
│ [████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░] 34% ⏱ 04:23 │
└────────────────────────────────────────────────────────┘
```

**Design Details**:
- **Spinner**: Animated Braille spinner (⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏) in cyan
- **Status Text**: "Evaluating N jobs..." (cyan, updates in real-time)
- **Counters**: "Found: 247 | Applied: 38" (emerald for applied, cyan for found)
- **Progress Bar**: Full-width bar showing cycle progress (20% completed)
- **Timer**: "⏱ MM:SS" (dim gray, right-aligned)

**Animations**:
- Spinner rotates every 100ms (8 frames/rotation)
- Progress bar fills left→right (duration = estimated time remaining)
- Counters flash briefly (+1 pulse) when a job is applied
- Timer counts up in real-time

**State Variations**:
- **Searching**: Cyan spinner, "Evaluating..."
- **Paused**: Amber pause icon (⏸), "Paused", greyed-out progress
- **Idle**: Slate icon (○), "Ready to search", empty progress
- **Error**: Red × icon, error message in red

---

### 4. JOB CARDS
**Purpose**: Present each discovered job with match score and decision path  
**Dimensions**: Full width, 5 lines per card, scrolling stream

```
╭─ MATCH: 92/100 ✅ AUTO-APPLY ────────────────────────╮
│ Senior Python Engineer                                 │
│ Acme Corp • San Francisco, CA • Remote: Hybrid        │
│                                                        │
│ ✓ Matched: Python, FastAPI, PostgreSQL               │
│ ✗ Missing: Kubernetes (trainable)                     │
│ 📍 Salary: $150k–$200k  |  🔗 linkedin.com/job/12345 │
├─────────────────────────────────────────────────────┤
│ [✓ Apply Now]  [📋 Review]  [🚩 Save for Later]     │
╰─────────────────────────────────────────────────────╯

╭─ MATCH: 76/100 ⚠️  SEMI-AUTO ────────────────────────╮
│ Platform Engineer                                      │
│ TechStartup Inc • Remote-Only • USA                   │
│                                                        │
│ ✓ Matched: Go, Kubernetes, AWS                        │
│ ✗ Missing: Rust (strong plus, not required)           │
│ 📊 Growth opportunity: Founding team, early stage     │
├─────────────────────────────────────────────────────┤
│ [⏳ Pending Review...]  [👤 Assign to Me]            │
╰─────────────────────────────────────────────────────╯

╭─ MATCH: 45/100 🚩 MANUAL ────────────────────────────╮
│ Backend Architect                                      │
│ Fortune 500 Corp • NYC Office Only                    │
│                                                        │
│ ✓ Matched: System Design, C++                         │
│ ✗ Missing: Python, AWS, Docker (core stack)           │
│ ⚠️  Location: NYC required (relocation needed)        │
├─────────────────────────────────────────────────────┤
│ [🔗 View Job]  [💭 Why Low Score?]                  │
╰─────────────────────────────────────────────────────╯
```

**Design Details**:

#### Score & Tier Styling
- **85–100** (Auto): Green border, ✅ emoji, bright emerald background
- **70–84** (Semi): Amber border, ⚠️ emoji, amber background
- **<70** (Manual): Red border, 🚩 emoji, dim red background
- Score always in bold, color-coded

#### Card Structure
1. **Header**: Score + Tier + Job Title (bold cyan)
2. **Metadata Row**: Company • Location • Remote status (dim slate)
3. **Spacer**: Empty line for breathing room
4. **Matched Skills**: ✓ in emerald, skill names bold
5. **Missing Skills**: ✗ in amber, skill names + context (trainable/required/nice-to-have)
6. **Additional Info**: Salary, growth opportunity, relocation note (dim purple metadata)
7. **Action Row**: Context-specific buttons

#### Button States
- **Auto-Apply Card**: `[✓ Apply Now]` (emerald), `[📋 Review]`, `[🚩 Save]`
- **Semi-Auto Card**: `[⏳ Pending...]` (animated pulse, amber), `[👤 Assign to Me]`
- **Manual Card**: `[🔗 View Job]`, `[💭 Why Low?]` (shows reasoning)

**Animations**:
- **Card Entrance**: Slide in from left + fade in (200ms, staggered per card)
- **Match Score Reveal**: Number counts up 0→final (300ms, easing: ease-out-quad)
- **Pulse on Apply**: Card briefly glows (emerald border opacity 0→1→0, 600ms)
- **Hover State**: Card border brightens, subtle shadow lift
- **Pending Badge**: Pulsing opacity (0.6→1.0, 1s loop, amber)

**Accessibility**:
- All information also conveyed by emoji + text (color not sole indicator)
- Alt text in parens for screen reader hints: "(score 92 out of 100, auto apply)"

---

### 5. APPLICATIONS TABLE
**Purpose**: Summary of submitted applications and their status  
**Dimensions**: Full width, 8-15 rows (scrollable), bottom of screen

```
┌─ APPLICATIONS (38 total) ──────────────────────────────────┐
│ Job Title        Company          Score  Status    Date    │
├───────────────────────────────────────────────────────────┤
│ Engineer         Acme Corp        92     ✓ Applied  Today  │
│ Architect        TechCo           88     ✓ Applied  Today  │
│ Lead Dev         StartupX         81     ⏳ Pending  Today  │
│ DevOps Eng       BigTech          72     👤 Review  2/20   │
│ SWE              Unicorn          45     🚩 Saved   2/19   │
│ ...more (scroll for full list)                             │
└───────────────────────────────────────────────────────────┘
```

**Design Details**:
- **Columns**: Job Title (20 chars), Company (15 chars), Score (5 chars), Status (12 chars), Date (7 chars)
- **Header Row**: Bold cyan column names with separator line
- **Data Rows**: Alternating row backgrounds (every other row slight tint) for scannability
- **Status Column Icons**:
  - ✓ Applied: Emerald checkmark
  - ⏳ Pending: Amber hourglass (pulsing)
  - 👤 Review: Purple user icon
  - 🚩 Saved: Red flag
  - ❌ Error: Red X

**Styling**:
- Cyan border (top/bottom)
- Slate horizontal divider (none inside, only borders)
- Right-aligned numbers (Score)
- Dim footer text: "...more (scroll for full list)"

**Interactions**:
- `applications [status]` filters (e.g., `applications applied`)
- `applications [id]` shows details
- Hover on row highlights it (brightened border)

---

### 6. COMMAND PROMPT
**Purpose**: User interaction hub for control and information  
**Dimensions**: 2 lines, sticky at bottom

```
[agent]> pause
⏸  Paused. Type 'resume' to continue, 'stop' to end.

[agent]> help
Available commands: search, pause, resume, stop, applications, profile, stats, help, exit
[agent]>
```

**Design Details**:
- Prefix: `[agent]>` (cyan bracket, slate text)
- Input line: User text entry
- Feedback line: Command response (color-coded by type)
- Command history: Up/Down arrow to scroll

**Response Formatting**:
- **Info**: Cyan emoji + slate text
- **Success**: Emerald emoji + emerald text
- **Warning**: Amber emoji + amber text
- **Error**: Red emoji + red text
- **Hint**: Purple emoji + dim text

**Examples**:
```
✅ Applied to 5 new jobs! (Cycle 12 complete)
⏳ Searching... (2:34 remaining)
⚠️  No jobs found in this cycle. Trying different keywords...
❌ Gemini API error: rate limit exceeded. Retrying in 30s...
💡 Tip: Use 'profile' to adjust your search preferences
```

---

## Typography System

### Font Choices (Terminal-Safe)
- **Display/Headers**: Monospace (Terminal default, bold weight)
- **Body Text**: Monospace (Terminal default, regular weight)
- **Emphasis**: Monospace bold or bright color

### Sizing & Spacing
- **Terminal Grid**: 1 character = 1 "pixel"
- **Padding**: 1 line above/below sections
- **Margins**: 2 lines between major sections
- **Line Height**: Default (monospace)

### Text Styles (via Rich)
- `bold`: Headers, important values, action buttons
- `dim`: Secondary text, hints, disabled elements
- `italic`: Not recommended (poor terminal support)
- `underline`: Links and interactive elements
- `reverse`: Selection/focus states

---

## Interactive Design: Animations & Real-Time Updates

### Loading States

#### 1. Search Cycle Spinner
**Animation**: 8-frame Braille spinner, 100ms per frame
**Colors**: Cyan when searching, Amber when paused
**Effect**: Hypnotic, indicates "actively doing work"

```
Progress: ⠋ → ⠙ → ⠹ → ⠸ → ⠼ → ⠴ → ⠦ → ⠧ → (repeat)
```

#### 2. Progress Bar
**Animation**: Fills left→right over the estimated cycle time
**Colors**: Cyan for fill, slate for remaining
**Effect**: Shows "time until next search cycle"

```
[████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░] 34%
```

#### 3. Counter Pulse
**Animation**: Brief flash when counter increments
**Colors**: Emerald for +applied, Cyan for +found
**Effect**: Satisfying visual reward for discovery

```
Found: 247 [pulse on +1]
```

### Interactive Transitions

#### Job Card Entrance
- **Trigger**: New job discovered
- **Animation**: Slide left→right (100ms) + fade-in (150ms), staggered per card
- **Effect**: Feels dynamic, not overwhelming

#### Match Score Reveal
- **Trigger**: Card appears
- **Animation**: Counter from 0 to score (300ms, ease-out)
- **Effect**: Dramatizes the matching process, builds anticipation

#### Auto-Apply Flash
- **Trigger**: Job applied
- **Animation**: Card border glows (emerald, 600ms pulse)
- **Effect**: Celebratory confirmation without modal popup

#### Pending Badge Pulse
- **Trigger**: Application awaiting review
- **Animation**: Opacity pulse (0.6→1.0→0.6, 1s loop)
- **Effect**: Gentle reminder that action pending

#### Pause/Resume State Change
- **Trigger**: User types `pause` or `resume`
- **Animation**: Status badge color shift + spinner pause (200ms)
- **Effect**: Immediate feedback that command was registered

### Real-Time Updates

**Every 1 second during search**:
- Timer increments (⏱ MM:SS)
- Found counter updates if new job discovered
- Applied counter increments when auto-apply succeeds
- Progress bar advances

**On job discovery**:
- New card slides in from top
- Match score counts up
- Counters pulse
- Auto-apply immediately (no user action needed)

**On pause/resume**:
- Status badge changes color
- Spinner stops/resumes
- Command prompt confirms action

---

## Error & Empty States

### No Jobs Found (Idle State)
```
╭─────────────────────────────────────────────────────╮
│                                                     │
│                 No jobs discovered yet              │
│                                                     │
│  Ready to search. Type 'search' to begin!          │
│                                                     │
╰─────────────────────────────────────────────────────╯
```

### No Jobs Matching Profile
```
╭─────────────────────────────────────────────────────╮
│                                                     │
│      No jobs matched your profile (this cycle)     │
│                                                     │
│  💡 Tips:                                          │
│  • Broaden location preferences                    │
│  • Remove optional skill requirements              │
│  • Increase salary range                           │
│                                                     │
╰─────────────────────────────────────────────────────╯
```

### API Error (Gemini Timeout)
```
❌ ERROR: Gemini API timeout (30s)
⏳ Retrying in 10s... [████░░░░░░]
Type 'stop' to cancel search.
```

### Resume Parse Error
```
❌ Error parsing resume: Unsupported format
📋 Please provide a PDF or DOCX file
[📁 Upload New Resume]
```

---

## Accessibility Requirements (WCAG 2.1 Level AA)

### Contrast
- ✅ All text ≥ 4.5:1 contrast ratio
- ✅ All interactive elements ≥ 3:1 contrast ratio

### Color Not Sole Indicator
- ✅ Status conveyed by emoji + color + text
- ✅ Scores use numbers + color + tier label
- ✅ Links underlined, not color alone

### Screen Reader Compatibility
- ✅ Semantic structure (headers, sections, tables)
- ✅ Alt text for emojis in code comments
- ✅ Descriptive command output (not just colors)

### Keyboard Navigation
- ✅ Tab through sections (Header → Profile → Status → Cards → Table → Prompt)
- ✅ Arrow keys to scroll within cards/table
- ✅ Enter to select action
- ✅ Escape to cancel

### Motion Sensitivity
- ✅ Animations can be disabled via config (`prefersReducedMotion: true`)
- ✅ No flashing or rapid color changes
- ✅ Animations are 200–600ms (not jarring)

---

## Implementation Checklist

**Phase 2 Design Sign-Off**:
- [x] Color system defined and validated for contrast
- [x] Component hierarchy complete with detailed specs
- [x] Animation specifications written (timing, easing, colors)
- [x] Interactive design scenarios mapped out
- [x] Error/empty states designed
- [x] Accessibility requirements documented
- [x] Typography system defined
- [x] Real-time update patterns specified

**Ready for Phase 3 Architecture & Phase 4 Tooling**

---

## Design Tokens (for implementation)

```python
COLORS = {
    "primary": "cyan",           # #00D9FF
    "success": "green",          # #00E5A0
    "warning": "yellow",         # #FFB800
    "error": "red",              # #FF4444
    "accent": "magenta",         # #A78BFA
    "neutral_dark": "white",     # Slate-800
    "neutral_light": "bright_black",  # Slate-200
}

TIMING = {
    "spinner_frame": 100,        # ms per frame
    "card_entrance": 200,        # slide duration
    "score_count": 300,          # counting animation
    "pulse": 600,                # auto-apply flash
    "badge_pulse": 1000,         # pending badge loop
    "state_change": 200,         # pause/resume
}

SPACING = {
    "section_pad": 1,            # lines
    "section_margin": 2,         # lines
    "card_height": 5,            # lines
    "card_gap": 1,               # line
}

COMPONENTS = {
    "header_height": 5,
    "profile_height": 6,
    "status_height": 3,
    "table_height": 10,
    "prompt_height": 2,
}
```

---

## Design Direction Summary

**Aesthetic**: Minimalist brutalism with kinetic energy  
**Tone**: Intelligent, capable, transparent  
**Differentiation**: Every animation earns its place; every color has meaning  
**Execution**: Rich framework with precision timing and smooth state transitions  

✅ **PHASE 2 DESIGN COMPLETE** — Ready for Phase 3 Architecture
