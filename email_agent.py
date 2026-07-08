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

DRAFT_PROMPT = """\
You are writing a cold outreach email from a job seeker to a founder/recruiter.

CANDIDATE PROFILE:
{profile}

JOB THEY ARE APPLYING FOR:
- Company: {company}
- Role: {job_title}
- Score match: {score}/100
- Matched skills: {matched_skills}

RECIPIENT:
- Name: {contact_name}
- Title: {contact_title}
- Company: {company}

Write a SHORT, personalized cold email (max 4 sentences in the body). Rules:
- Open with one specific thing about what {company} is building
- Mention 2 matched skills that are directly relevant to the role
- End with a specific ask (15-min call or reviewing the resume)
- Do NOT use buzzwords like "passionate", "excited", "leverage"
- Sound like a human, not a template
- Keep total body under 100 words

Return ONLY a valid JSON object — no markdown fences:
{{
  "subject": "email subject line",
  "body": "full email body including greeting and sign-off"
}}
"""


def _strip_fences(text: str) -> str:
    if text.startswith("```"):
        lines = text.splitlines()
        inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        return "\n".join(inner).strip()
    return text


def draft_outreach(profile: dict, job: dict, contact: dict) -> dict:
    """
    Draft a personalized outreach email for a job + contact.
    Returns a validated dict with to_email, subject, body, guardrail_warnings, etc.
    """
    matched_skills = ", ".join(job.get("matched_skills", [])[:5]) or "relevant skills"

    prompt = DRAFT_PROMPT.format(
        profile=json.dumps({
            "name":         profile.get("name"),
            "current_role": profile.get("current_role"),
            "total_yoe":    profile.get("total_yoe"),
            "skills":       profile.get("skills", [])[:10],
            "tools":        profile.get("tools", [])[:10],
        }, indent=2),
        company=job.get("company", ""),
        job_title=job.get("title", ""),
        score=job.get("score", ""),
        matched_skills=matched_skills,
        contact_name=contact.get("name", "there"),
        contact_title=contact.get("title", ""),
    )

    res = _llm.completion(
        model=SCORE_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )

    # Guardrail: track token usage
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
