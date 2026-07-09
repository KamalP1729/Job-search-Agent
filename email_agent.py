"""
email_agent.py — Drafts and sends personalized outreach emails.
Drafting uses DraupLLMManager (Gemini). Sending uses Gmail SMTP.

Guardrails applied:
  - EmailDraftContent      : Pydantic schema validates subject/body (length, word cap)
  - validate_email_content : buzzword detection, recipient check, company name check
  - track_token_usage()    : logs token count + estimated cost per call
  - Structured logging     : replaces print() with get_logger()
"""

import os
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pydantic import ValidationError
from draup_packages.draup_llm_manager import DraupLLMManager

from config import SCORE_MODEL, DRAUP_LLM_ENV, DRAUP_LLM_USER, DRAUP_LLM_PROVIDER
from guardrails import (
    get_logger,
    EmailDraftContent,
    validate_email_content,
    track_token_usage,
)

logger = get_logger("email_agent")

_llm = DraupLLMManager(env=DRAUP_LLM_ENV, user=DRAUP_LLM_USER, llm_provider=DRAUP_LLM_PROVIDER)

GMAIL_USER         = os.environ.get("GMAIL_USER", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")

ANALYSIS_PROMPT = """\
You are helping a job seeker write a targeted cold email. Analyze this job description and candidate profile to extract the most relevant connection points.

CANDIDATE PROFILE:
{profile}

JOB DESCRIPTION:
{jd}

Extract and return ONLY a valid JSON object — no markdown fences:
{{
  "company_signal": "1 sentence: what is this company building / their core product or mission, based on the JD",
  "top_requirements": ["the 2-3 JD requirements that best match the candidate's actual experience"],
  "candidate_hook": "1 sentence: the single most impressive/relevant thing the candidate has done that maps to this role"
}}
"""

DRAFT_PROMPT = """\
You are writing a cold outreach email from a job seeker to a founder/recruiter.

CANDIDATE:
- Name: {name}
- Role: {current_role}
- YOE: {total_yoe} years

ROLE: {job_title} at {company} (match score: {score}/100)

RECIPIENT: {contact_name} ({contact_title})

JD ANALYSIS (use this to personalize — do NOT copy verbatim):
- What they're building: {company_signal}
- Requirements that match candidate: {top_requirements}
- Candidate's strongest hook for this role: {candidate_hook}

Write a SHORT cold email (max 4 sentences in the body). Rules:
- First sentence: reference what {company} is specifically building (from JD analysis)
- Second sentence: connect candidate's hook to a specific requirement
- Third sentence: one concrete proof point (metric, project, or result)
- Final sentence: specific ask (15-min call or to share resume)
- Do NOT use: "passionate", "excited", "leverage", "synergy", "dynamic"
- Sound like a human writing to a specific person, not a template
- Keep total body under 100 words

Return ONLY a valid JSON object — no markdown fences:
{{
  "subject": "email subject line (specific, not generic)",
  "body": "full email body including greeting and sign-off"
}}
"""


def _strip_fences(text: str) -> str:
    if text.startswith("```"):
        lines = text.splitlines()
        inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        return "\n".join(inner).strip()
    return text


def _analyze_jd(profile: dict, job: dict) -> dict:
    """
    Step 1 (agentic): Read the actual JD and extract what the company is building,
    which requirements match the candidate, and the candidate's strongest hook.
    Falls back to basic info on failure.
    """
    jd_text = (job.get("description") or "")[:4000]  # cap to avoid huge prompts
    profile_summary = json.dumps({
        "name":         profile.get("name"),
        "current_role": profile.get("current_role"),
        "total_yoe":    profile.get("total_yoe"),
        "skills":       profile.get("skills", [])[:15],
        "tools":        profile.get("tools", [])[:15],
        "roles":        [
            f"{r.get('title')} at {r.get('company')}"
            for r in profile.get("roles", [])[:3]
        ],
    }, indent=2)

    try:
        res = _llm.completion(
            model=SCORE_MODEL,
            messages=[{"role": "user", "content": ANALYSIS_PROMPT.format(
                profile=profile_summary,
                jd=jd_text,
            )}],
        )
        track_token_usage("analyze_jd", res)
        raw = json.loads(_strip_fences(res.choices[0].message.content.strip()))
        return raw
    except Exception as e:
        logger.warning("JD analysis failed for %s: %s — using fallback", job.get("company"), e)
        return {
            "company_signal": f"{job.get('company')} is hiring for {job.get('title')}",
            "top_requirements": job.get("matched_skills", [])[:3],
            "candidate_hook": f"{profile.get('current_role')} with {profile.get('total_yoe')} YOE",
        }


def draft_outreach(profile: dict, job: dict, contact: dict) -> dict:
    """
    Draft a personalized outreach email for a job + contact.

    Two-step agentic flow:
      1. _analyze_jd() — reads the actual JD, extracts company signal + matching requirements
      2. DRAFT_PROMPT — writes email grounded in that analysis (not just skill names)

    Returns a validated dict with to_email, subject, body, guardrail_warnings, etc.
    """
    # Step 1: Analyze JD against profile
    logger.info("Analyzing JD for %s — %s", job.get("company"), job.get("title"))
    analysis = _analyze_jd(profile, job)

    top_req = analysis.get("top_requirements", [])
    top_req_str = "; ".join(top_req) if isinstance(top_req, list) else str(top_req)

    # Step 2: Draft email grounded in the analysis
    prompt = DRAFT_PROMPT.format(
        name=profile.get("name", ""),
        current_role=profile.get("current_role", ""),
        total_yoe=profile.get("total_yoe", ""),
        company=job.get("company", ""),
        job_title=job.get("title", ""),
        score=job.get("score", ""),
        contact_name=contact.get("name", "there"),
        contact_title=contact.get("title", ""),
        company_signal=analysis.get("company_signal", ""),
        top_requirements=top_req_str,
        candidate_hook=analysis.get("candidate_hook", ""),
    )

    res = _llm.completion(
        model=SCORE_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    track_token_usage("draft_email", res)

    content = res.choices[0].message.content.strip()
    content = _strip_fences(content)
    raw = json.loads(content)

    # Guardrail: Pydantic validation (word cap, subject length)
    try:
        validated = EmailDraftContent(**raw)
        subject = validated.subject
        body    = validated.body
    except ValidationError as e:
        logger.warning("Email draft failed Pydantic validation: %s — using raw output", e)
        subject = raw.get("subject", "")
        body    = raw.get("body", "")

    draft = {
        "to_name":    contact.get("name", ""),
        "to_email":   contact.get("email", ""),
        "company":    job.get("company", ""),
        "job_title":  job.get("title", ""),
        "score":      job.get("score", 0),
        "subject":    subject,
        "body":       body,
        "apply_link": job.get("apply_link", ""),
    }

    # Guardrail: content quality check (buzzwords, word count, recipient, company mention)
    is_clean, warnings = validate_email_content(draft)
    if warnings:
        logger.warning(
            "Email guardrail warnings for %s → %s: %s",
            job.get("company", ""), contact.get("email", ""), "; ".join(warnings),
        )
    draft["guardrail_warnings"] = warnings  # surface in UI for human reviewer

    return draft


def send_email(draft: dict) -> None:
    """
    Send an approved email draft via Gmail SMTP.
    Requires GMAIL_USER and GMAIL_APP_PASSWORD env vars.
    """
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        raise ValueError(
            "Set GMAIL_USER and GMAIL_APP_PASSWORD env vars to send emails.\n"
            "Get an app password at: myaccount.google.com/apppasswords"
        )

    msg = MIMEMultipart("alternative")
    msg["From"]    = GMAIL_USER
    msg["To"]      = draft["to_email"]
    msg["Subject"] = draft["subject"]
    msg.attach(MIMEText(draft["body"], "plain"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, draft["to_email"], msg.as_string())

    logger.info("Email sent → %s (%s)", draft["to_email"], draft.get("company", ""))
