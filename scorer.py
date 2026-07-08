"""
scorer.py — Scores a parsed resume profile against a job description via DraupLLMManager.

Guardrails applied:
  - sanitize_input()    : strips prompt injection from JD text before LLM injection
  - ScoringResult       : Pydantic schema validates output (score bounds, verdict sync)
  - track_token_usage() : logs token count + estimated cost per call
  - Fallback model      : switches to FALLBACK_MODEL on the final retry attempt
  - Structured logging  : replaces print() with get_logger()
"""

import json
import time
from draup_packages.draup_llm_manager import DraupLLMManager
from pydantic import ValidationError

from config import SCORE_MODEL, FALLBACK_MODEL, DRAUP_LLM_ENV, DRAUP_LLM_USER, DRAUP_LLM_PROVIDER
from config import MAX_RETRIES, RETRY_DELAY
from guardrails import get_logger, sanitize_input, ScoringResult, track_token_usage

logger = get_logger("scorer")

_llm = DraupLLMManager(env=DRAUP_LLM_ENV, user=DRAUP_LLM_USER, llm_provider=DRAUP_LLM_PROVIDER)

SCORE_PROMPT = """\
You are a senior technical recruiter. Score how well the candidate profile matches the job description.

CANDIDATE PROFILE:
{profile}

JOB DESCRIPTION:
{jd}

Return ONLY a valid JSON object with exactly these fields — no explanation, no markdown fences:

{{
  "overall_score": <integer 0-100>,
  "verdict": "Strong Match" | "Good Match" | "Partial Match" | "Weak Match",
  "breakdown": {{
    "skills_match":      <0-100>,
    "tools_match":       <0-100>,
    "yoe_fit":           <0-100>,
    "domain_alignment":  <0-100>,
    "role_alignment":    <0-100>
  }},
  "matched_skills":  ["skill1", "skill2"],
  "missing_skills":  ["skill1", "skill2"],
  "yoe_assessment":  "e.g. JD requires 5+ years, candidate has 6 years — good fit",
  "recommendation":  "2-3 sentence summary: overall fit + what to emphasize in the application"
}}

Scoring guide for overall_score:
- 80-100 → Strong Match   (candidate meets or exceeds almost all requirements)
- 65-79  → Good Match     (meets most requirements, minor gaps)
- 45-64  → Partial Match  (meets some requirements, notable gaps)
- 0-44   → Weak Match     (significant skill/experience gaps)
"""


def _strip_fences(text: str) -> str:
    if text.startswith("```"):
        lines = text.splitlines()
        inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        return "\n".join(inner).strip()
    return text


def score_job(profile: dict, jd_text: str) -> dict:
    """
    Score a candidate profile (from parser.py) against a job description string.
    Returns a validated structured scoring dict.
    """
    # Guardrail: sanitize JD text before injecting into prompt
    safe_jd = sanitize_input(jd_text, label="job_description")

    prompt = SCORE_PROMPT.format(
        profile=json.dumps(profile, indent=2),
        jd=safe_jd.strip(),
    )

    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        # Fallback model on final attempt
        model = FALLBACK_MODEL if attempt == MAX_RETRIES else SCORE_MODEL
        if attempt == MAX_RETRIES:
            logger.warning("Switching to fallback model %s on attempt %d", model, attempt)
        try:
            res = _llm.completion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
            )

            # Guardrail: track token usage + cost
            track_token_usage("score_job", res)

            content = res.choices[0].message.content.strip()
            content = _strip_fences(content)
            raw_dict = json.loads(content)

            # Guardrail: validate output (score bounds, verdict auto-correction)
            result = ScoringResult(**raw_dict)
            return result.model_dump()

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

    raise ValueError(f"Failed to score job after {MAX_RETRIES} attempts: {last_exc}")
