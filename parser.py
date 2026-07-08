"""
parser.py — Resume text extraction + structured profile extraction via DraupLLMManager.

Guardrails applied:
  - sanitize_input()     : strips prompt injection from resume text before LLM injection
  - ParsedProfile        : Pydantic schema validates LLM output (types, ranges, dedup)
  - track_token_usage()  : logs token count + estimated cost per call
  - Fallback model       : switches to FALLBACK_MODEL on the final retry attempt
  - Structured logging   : replaces print() with get_logger()
"""

import json
import time
import pdfplumber
import docx
from pathlib import Path
from draup_packages.draup_llm_manager import DraupLLMManager
from pydantic import ValidationError

from config import PARSE_MODEL, FALLBACK_MODEL, DRAUP_LLM_ENV, DRAUP_LLM_USER, DRAUP_LLM_PROVIDER
from config import MAX_RETRIES, RETRY_DELAY
from guardrails import get_logger, sanitize_input, ParsedProfile, track_token_usage

logger = get_logger("parser")

_llm = DraupLLMManager(env=DRAUP_LLM_ENV, user=DRAUP_LLM_USER, llm_provider=DRAUP_LLM_PROVIDER)

PARSE_PROMPT = """\
Today's date is {today}. Use this to calculate durations for roles marked "present".
Extract structured information from the resume text below.
Return ONLY a valid JSON object with exactly these fields — no explanation, no markdown fences:

{{
  "name": "full name",
  "email": "email or null",
  "phone": "phone or null",
  "total_yoe": <total years of experience as a float>,
  "current_role": "most recent job title",
  "roles": [
    {{
      "title": "job title",
      "company": "company name",
      "start": "YYYY-MM or YYYY",
      "end": "YYYY-MM or YYYY or present",
      "duration_months": <integer>,
      "domain": "e.g. Data Science, Software Engineering, Product Management"
    }}
  ],
  "skills": ["skill1", "skill2"],
  "tools": ["tool1", "tool2"],
  "domains": [
    {{"name": "domain name", "yoe": <float>}}
  ],
  "education": [
    {{"degree": "degree type", "field": "field of study", "institution": "university name", "year": "year or null"}}
  ],
  "certifications": ["cert1", "cert2"]
}}

Resume text:
{resume_text}
"""


def _extract_text(file_path: str) -> str:
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        with pdfplumber.open(file_path) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        return "\n".join(pages).strip()

    if suffix in (".docx", ".doc"):
        doc = docx.Document(file_path)
        return "\n".join(p.text for p in doc.paragraphs).strip()

    raise ValueError(f"Unsupported file type: {suffix}. Use PDF or DOCX.")


def _strip_fences(text: str) -> str:
    """Remove markdown code fences if the model wraps its JSON output."""
    if text.startswith("```"):
        lines = text.splitlines()
        inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        return "\n".join(inner).strip()
    return text


def parse_resume(file_path: str) -> dict:
    """
    Parse a resume file (PDF or DOCX) and return a validated structured profile dict.
    """
    raw_text = _extract_text(file_path)
    if not raw_text:
        raise ValueError("Could not extract any text from the resume file.")

    # Guardrail: sanitize before injecting into prompt
    safe_text = sanitize_input(raw_text, label="resume")

    from datetime import date
    today = date.today().strftime("%B %Y")
    prompt = PARSE_PROMPT.format(resume_text=safe_text, today=today)

    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        # Fallback model on the final attempt
        model = FALLBACK_MODEL if attempt == MAX_RETRIES else PARSE_MODEL
        if attempt == MAX_RETRIES:
            logger.warning("Switching to fallback model %s on attempt %d", model, attempt)
        try:
            res = _llm.completion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
            )

            # Guardrail: track token usage + cost
            track_token_usage("parse_resume", res)

            content = res.choices[0].message.content.strip()
            content = _strip_fences(content)
            raw_dict = json.loads(content)

            # Guardrail: validate output against Pydantic schema
            profile = ParsedProfile(**raw_dict)
            logger.info(
                "Resume parsed: %s | %s | %.1f YOE",
                profile.name, profile.current_role, profile.total_yoe,
            )
            return profile.model_dump()

        except json.JSONDecodeError as e:
            last_exc = e
            logger.warning("Attempt %d/%d — invalid JSON from model: %s", attempt, MAX_RETRIES, e)
        except ValidationError as e:
            last_exc = e
            logger.warning("Attempt %d/%d — Pydantic validation failed: %s", attempt, MAX_RETRIES, e)
        except Exception as e:
            last_exc = e
            logger.warning("Attempt %d/%d — unexpected error: %s", attempt, MAX_RETRIES, e)

        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY * (2 ** (attempt - 1)))

    raise ValueError(f"Failed to parse resume after {MAX_RETRIES} attempts: {last_exc}")
