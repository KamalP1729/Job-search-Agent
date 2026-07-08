# Job Agent — Agentic Job Search Pipeline

An end-to-end agentic job search system built with **LangGraph**, **SerpAPI**, **Hunter.io**, and **Gmail SMTP**. It parses your resume, finds relevant jobs, scores them against your profile, discovers recruiter contacts, drafts personalized cold emails, and sends them — with a human-in-the-loop approval gate before any email is sent.

---

## Architecture

```
Resume PDF/DOCX
      │
      ▼
┌─────────────────┐
│  ParseResume    │  pdfplumber / python-docx → Gemini LLM → structured profile JSON
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   JobSearch     │  SerpAPI Google Jobs → score each result → ranked list
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ RecruiterFinder │  Hunter.io domain search → founder / recruiter emails
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  EmailDraft     │  Gemini LLM → personalized cold email per job+contact
└────────┬────────┘
         │
         ▼
┌─────────────────┐   ◄── BREAKPOINT (human approval required)
│  HumanReview    │  CLI: approve / reject / edit each draft
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   SendEmail     │  Gmail SMTP (app password) → sends approved emails
└─────────────────┘
```

All nodes are wired as a **LangGraph `StateGraph`** with:
- `MemorySaver` checkpointing — full state persisted at each node
- `interrupt_before=["human_review"]` — pipeline pauses before sending any emails
- Conditional routing with graceful failure at each stage
- Accumulated error list across the entire run

---

## Features

| Feature | Tech |
|---|---|
| Resume parsing (PDF + DOCX) | `pdfplumber`, `python-docx`, Gemini 2.5 Flash |
| JD scoring (0–100 + breakdown) | Gemini 2.5 Flash, structured JSON output |
| Batch scoring + ranking | CLI, sorted by overall score |
| Google Jobs search | SerpAPI (`google_jobs` engine, remote filter `ltype=1`) |
| Recruiter discovery | Hunter.io domain search, founder/CTO/recruiter title filter |
| Cold email drafting | Gemini 2.5 Flash, <100-word rule-enforced prompt |
| Human-in-the-loop approval | LangGraph breakpoint, CLI approve/reject/edit |
| Email sending | Gmail SMTP via app password |
| Multi-agent orchestration | LangGraph `StateGraph`, 6 nodes, conditional edges |

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Set environment variables

```bash
cp .env.example .env
# Edit .env with your keys
```

Required keys:
- `SERPAPI_API_KEY` — [serpapi.com](https://serpapi.com) (free tier: 100 searches/month)
- `HUNTER_API_KEY` — [hunter.io](https://hunter.io) (free tier: 25 searches/month)
- `GMAIL_USER` — your Gmail address
- `GMAIL_APP_PASSWORD` — 16-char app password from [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)

> **LLM note:** This project uses `DraupLLMManager` (Draup internal). To run publicly, swap it for `litellm.completion()` directly with a `GEMINI_API_KEY`.

---

## Usage

### Parse a resume
```bash
python main.py parse resume.pdf --output profile.json
```

### Score against a single JD
```bash
python main.py score profile.json --jd-file jds/zenskar.txt
```

### Batch score against multiple JDs (ranked)
```bash
python main.py batch-score profile.json --jd-dir jds/ --output results.json
```

### Search + score live Google Jobs
```bash
python main.py search profile.json --locations "Remote" "Bangalore, India" --top-n 10
```

### Find recruiter contacts
```bash
python main.py find-recruiters "MinusX" "Brainfish" "DrDroid"
```

### Run the full end-to-end pipeline
```bash
python main.py run resume.pdf --locations "Remote" "United States" --top-n 10 --min-score 65
```

The pipeline will pause at **HumanReview** and prompt you to approve/reject/edit each drafted email before sending.

---

## Project Structure

```
job_agent/
├── main.py              # CLI entry point (argparse, 6 subcommands)
├── config.py            # Model names, thresholds, retry settings
├── parser.py            # Resume → structured profile JSON
├── scorer.py            # Profile + JD → score (0–100) + recommendation
├── job_search.py        # SerpAPI search + inline scoring → ranked list
├── recruiter_finder.py  # Hunter.io email discovery per company
├── email_agent.py       # LLM email drafting + Gmail SMTP sending
├── graph.py             # LangGraph multi-agent orchestration
├── jds/                 # Sample job description .txt files
├── requirements.txt
├── .env.example
└── .gitignore
```

---

## Sample Output

```
========================================
  JOB AGENT — LangGraph Pipeline
========================================

[1/6] ParseResumeAgent — parsing resume...
  ✓ Kamal Pattanayak | AI Engineer | 2.5 YOE

[2/6] JobSearchAgent — searching and scoring jobs...
  ✓ Found 8 jobs above threshold

[3/6] RecruiterFinderAgent — finding contacts...
  Searching: MinusX ... 3 found
  Searching: DrDroid ... 2 found
  ✓ Found contacts for 2/8 companies

[4/6] EmailDraftAgent — drafting outreach emails...
  ✓ Drafted email → Nikhil Kothari at MinusX
  ✓ Drafted email → Aravind Srinivas at DrDroid

[5/6] HumanReviewAgent — review email drafts before sending

────────────────────────────────────────
Email 1/2
To:      Nikhil Kothari <nikhil@minusx.ai>
Company: MinusX
Role:    AI Engineer

Subject: Data tools + AI agents → MinusX

Hi Nikhil, ...

Send this email? [y/n/e(dit)]: y
  ✓ Approved

[6/6] EmailSendAgent — sending approved emails...
  ✓ Sent → nikhil@minusx.ai
```
