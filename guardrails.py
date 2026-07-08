"""
guardrails.py — Input/output validation, prompt injection sanitization,
email content guardrails, token usage tracking, and structured logging.

Covers:
  1. Pydantic output schemas  — catch LLM hallucinations at parse time
  2. Prompt injection guard   — sanitize user-controlled text before LLM injection
  3. Email content guardrails — buzzword detection, word count, recipient validation
  4. Token tracking           — log usage + estimated cost per LLM call
  5. Structured logging       — consistent log format across all modules
"""

import re
import logging
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


# ── 1. STRUCTURED LOGGING ──────────────────────────────────────────────────────

def get_logger(name: str) -> logging.Logger:
    """Return a consistently formatted logger for the given module name."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


# ── 2. PYDANTIC OUTPUT SCHEMAS ─────────────────────────────────────────────────

class RoleEntry(BaseModel):
    title: str
    company: str
    start: str
    end: str
    duration_months: int = Field(ge=0)
    domain: str = ""


class EducationEntry(BaseModel):
    degree: str
    field: str
    institution: str
    year: Optional[str] = None


class DomainEntry(BaseModel):
    name: str
    yoe: float = Field(ge=0, le=60)


class ParsedProfile(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    total_yoe: float = Field(ge=0, le=60)
    current_role: str
    roles: list[RoleEntry] = []
    skills: list[str] = []
    tools: list[str] = []
    domains: list[DomainEntry] = []
    education: list[EducationEntry] = []
    certifications: list[str] = []

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, v):
        if v and not re.match(r"[^@]+@[^@]+\.[^@]+", v):
            return None  # nullify malformed email rather than crashing
        return v

    @field_validator("skills", "tools", "certifications", mode="before")
    @classmethod
    def deduplicate_list(cls, v):
        if isinstance(v, list):
            seen, result = set(), []
            for item in v:
                if isinstance(item, str) and item.lower() not in seen:
                    seen.add(item.lower())
                    result.append(item)
            return result
        return v


class ScoreBreakdown(BaseModel):
    skills_match: int = Field(ge=0, le=100)
    tools_match: int = Field(ge=0, le=100)
    yoe_fit: int = Field(ge=0, le=100)
    domain_alignment: int = Field(ge=0, le=100)
    role_alignment: int = Field(ge=0, le=100)


class ScoringResult(BaseModel):
    overall_score: int = Field(ge=0, le=100)
    verdict: Literal["Strong Match", "Good Match", "Partial Match", "Weak Match"]
    breakdown: ScoreBreakdown
    matched_skills: list[str] = []
    missing_skills: list[str] = []
    yoe_assessment: str = ""
    recommendation: str = ""

    @model_validator(mode="after")
    def sync_verdict_with_score(self):
        """Auto-correct verdict if it doesn't match the score band."""
        score = self.overall_score
        expected = (
            "Strong Match"  if score >= 80 else
            "Good Match"    if score >= 65 else
            "Partial Match" if score >= 45 else
            "Weak Match"
        )
        if self.verdict != expected:
            get_logger("guardrails").warning(
                "Verdict mismatch — score=%d, model said '%s', corrected to '%s'",
                score, self.verdict, expected,
            )
            self.verdict = expected
        return self


class EmailDraftContent(BaseModel):
    subject: str = Field(min_length=5, max_length=150)
    body: str = Field(min_length=10, max_length=800)

    @field_validator("body")
    @classmethod
    def enforce_word_limit(cls, v):
        words = v.split()
        if len(words) > 120:
            v = " ".join(words[:100]) + "..."
        return v


# ── 3. PROMPT INJECTION SANITIZATION ──────────────────────────────────────────

_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"disregard\s+(all\s+)?prior",
    r"you\s+are\s+now\s+a",
    r"act\s+as\s+(a\s+)?(?:different|new|another)",
    r"forget\s+(all\s+)?previous",
    r"system\s*:\s*you\s+are",
    r"<\s*system\s*>",
    r"\[INST\]",
    r"###\s*instruction",
    r"new\s+role\s*:",
    r"jailbreak",
    r"prompt\s+injection",
]

_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)

_MAX_INPUT_CHARS = 15_000  # ~3,750 tokens — enough for any resume or JD


def sanitize_input(text: str, label: str = "input") -> str:
    """
    Strip prompt injection patterns from user-controlled text (resume, JD)
    before it is injected into an LLM prompt. Also caps length.
    """
    logger = get_logger("guardrails")
    cleaned = _INJECTION_RE.sub("[REDACTED]", text)
    if cleaned != text:
        logger.warning("Prompt injection pattern detected and redacted in %s", label)
    if len(cleaned) > _MAX_INPUT_CHARS:
        cleaned = cleaned[:_MAX_INPUT_CHARS]
        logger.warning("Input '%s' truncated to %d chars to prevent context stuffing", label, _MAX_INPUT_CHARS)
    return cleaned


# ── 4. EMAIL CONTENT GUARDRAILS ────────────────────────────────────────────────

_BUZZWORDS = [
    "passionate", "excited", "leverage", "synergy", "innovative",
    "disruptive", "rockstar", "ninja", "guru", "thought leader",
    "game-changer", "paradigm", "holistic", "scalable solution",
    "move the needle", "circle back", "deep dive", "bandwidth",
    "best-in-class", "world-class", "cutting-edge", "state-of-the-art",
]


def validate_email_content(draft: dict) -> tuple[bool, list[str]]:
    """
    Run content guardrails on a drafted email.
    Returns (is_valid, list_of_warnings).
    Warnings do not block sending — they surface issues for human review.
    """
    issues = []
    body    = draft.get("body", "")
    subject = draft.get("subject", "")
    company = draft.get("company", "")

    word_count = len(body.split())
    if word_count > 120:
        issues.append(f"Body too long: {word_count} words (target ≤100)")

    found_buzzwords = [bw for bw in _BUZZWORDS if bw in body.lower()]
    if found_buzzwords:
        issues.append(f"Buzzwords found: {', '.join(found_buzzwords)}")

    to_email = draft.get("to_email", "")
    if not to_email or "@" not in to_email:
        issues.append("Missing or invalid recipient email address")

    if len(subject) < 5:
        issues.append("Subject line too short (< 5 chars)")
    if len(subject) > 150:
        issues.append("Subject line too long (> 150 chars)")

    if company and company.lower() not in body.lower() and company.lower() not in subject.lower():
        issues.append(f"Company name '{company}' not mentioned — email may feel generic")

    return len(issues) == 0, issues


# ── 5. TOKEN USAGE TRACKING ────────────────────────────────────────────────────

# Approximate Gemini 2.5 Flash pricing (USD per 1M tokens, as of mid-2025)
_COST_INPUT_PER_1M  = 0.075
_COST_OUTPUT_PER_1M = 0.30


def track_token_usage(node: str, response) -> dict:
    """
    Extract token usage from an LLM response, log it, and return a usage dict.
    Safe to call even if the response has no usage attribute.
    """
    logger = get_logger("token_tracker")
    try:
        usage = getattr(response, "usage", None)
        if usage is None:
            return {}
        input_tokens  = getattr(usage, "prompt_tokens", 0) or 0
        output_tokens = getattr(usage, "completion_tokens", 0) or 0
        cost = (
            (input_tokens  / 1_000_000) * _COST_INPUT_PER_1M +
            (output_tokens / 1_000_000) * _COST_OUTPUT_PER_1M
        )
        result = {
            "node":          node,
            "input_tokens":  input_tokens,
            "output_tokens": output_tokens,
            "cost_usd":      round(cost, 6),
        }
        logger.info(
            "[%s] %d in / %d out tokens | est. cost $%.5f",
            node, input_tokens, output_tokens, cost,
        )
        return result
    except Exception:
        return {}  # never crash the pipeline over telemetry
