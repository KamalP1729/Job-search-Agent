"""
embedder.py — Resume and JD text embedding + semantic similarity scoring.

Uses Gemini text-embedding-004 via LiteLLM (no GPU required —
all inference runs on Google's servers).

Public API:
  profile_to_text(profile)              → str
  embed_text(text)                      → list[float]
  embed_profile(profile)                → list[float]
  cosine_similarity(vec_a, vec_b)       → float  (-1..1)
  semantic_score(profile_vec, jd_text)  → float  (0..100)
  hybrid_score(semantic, llm)           → float  (0..100)
"""

import math
import time
import logging
from draup_packages.draup_llm_manager import DraupLLMManager

from config import EMBED_MODEL, EMBED_DIMENSIONS, MAX_RETRIES, RETRY_DELAY
from config import DRAUP_LLM_ENV, DRAUP_LLM_USER, DRAUP_LLM_PROVIDER
from guardrails import get_logger

logger = get_logger("embedder")

logging.getLogger("LiteLLM").setLevel(logging.CRITICAL)

_llm = DraupLLMManager(env=DRAUP_LLM_ENV, user=DRAUP_LLM_USER, llm_provider=DRAUP_LLM_PROVIDER)


# ── PROFILE → TEXT ─────────────────────────────────────────────────────────────

def profile_to_text(profile: dict) -> str:
    """
    Serialize a parsed resume profile into a rich natural-language string
    for embedding. Captures role, experience, skills, tools, domains, and history.

    Keeping this as text (not raw JSON) gives the embedding model better
    semantic context — JSON keys add noise.
    """
    parts = []

    if profile.get("current_role"):
        parts.append(f"Current role: {profile['current_role']}")

    if profile.get("total_yoe") is not None:
        parts.append(f"Total experience: {profile['total_yoe']} years")

    if profile.get("skills"):
        parts.append(f"Skills: {', '.join(profile['skills'][:20])}")

    if profile.get("tools"):
        parts.append(f"Tools and technologies: {', '.join(profile['tools'][:15])}")

    if profile.get("domains"):
        domain_parts = []
        for d in profile["domains"][:8]:
            if isinstance(d, dict) and d.get("name"):
                domain_parts.append(f"{d['name']} ({d.get('yoe', '?')} years)")
        if domain_parts:
            parts.append(f"Domain expertise: {', '.join(domain_parts)}")

    if profile.get("roles"):
        role_lines = []
        for r in profile["roles"][:6]:
            if isinstance(r, dict) and r.get("title") and r.get("company"):
                role_lines.append(f"{r['title']} at {r['company']}")
        if role_lines:
            parts.append(f"Work history: {'; '.join(role_lines)}")

    if profile.get("certifications"):
        parts.append(f"Certifications: {', '.join(profile['certifications'][:5])}")

    if profile.get("education"):
        edu_parts = []
        for e in profile["education"][:3]:
            if isinstance(e, dict) and e.get("degree"):
                edu_parts.append(f"{e['degree']} in {e.get('field', '')} from {e.get('institution', '')}")
        if edu_parts:
            parts.append(f"Education: {'; '.join(edu_parts)}")

    return "\n".join(parts)


# ── EMBEDDING ──────────────────────────────────────────────────────────────────

def embed_text(text: str) -> list[float]:
    """
    Embed a piece of text using Gemini text-embedding-004 via LiteLLM.
    Retries with exponential backoff. No GPU needed — cloud API.

    Args:
        text: The text to embed (resume profile text or JD text).

    Returns:
        A list of floats representing the embedding vector.
    """
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = _llm.embedding(
                model=EMBED_MODEL,
                input=[text],
                dimensions=EMBED_DIMENSIONS,
            )
            vector: list[float] = response.data[0]["embedding"]
            logger.info(
                "Embedded %d chars → %d-dim vector (attempt %d)",
                len(text), len(vector), attempt,
            )
            return vector
        except Exception as e:
            last_exc = e
            logger.warning("Embed attempt %d/%d failed: %s", attempt, MAX_RETRIES, e)
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * (2 ** (attempt - 1)))

    raise ValueError(f"Embedding failed after {MAX_RETRIES} attempts: {last_exc}")


def embed_profile(profile: dict) -> list[float]:
    """
    Convert a parsed resume profile dict into an embedding vector.
    Call this ONCE per run — reuse the vector across all JD comparisons.
    """
    text = profile_to_text(profile)
    logger.info("Embedding profile: %s", profile.get("name", "unknown"))
    return embed_text(text)


# ── SIMILARITY ─────────────────────────────────────────────────────────────────

def cosine_similarity(a: list[float], b: list[float]) -> float:
    """
    Compute cosine similarity between two equal-length vectors.
    Returns a value in [-1, 1]. Pure Python — no numpy dependency.
    """
    dot    = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def semantic_score(profile_embedding: list[float], jd_text: str) -> float:
    """
    Compute semantic similarity between a pre-computed profile embedding
    and a job description string. Returns 0–100.

    The profile_embedding should be computed ONCE (embed_profile) and
    passed in for every JD — avoids re-embedding the resume on each call.

    Cosine similarity is in [-1, 1]; we map to [0, 100] linearly.
    In practice, relevant matches score 60–85; unrelated ones score 40–55.
    """
    jd_embedding = embed_text(jd_text)
    sim   = cosine_similarity(profile_embedding, jd_embedding)
    score = round((sim + 1) / 2 * 100, 1)
    logger.info("Semantic score: %.1f (cosine=%.4f)", score, sim)
    return score


# ── HYBRID SCORING ─────────────────────────────────────────────────────────────

def hybrid_score(
    semantic: float,
    llm: float,
    semantic_weight: float = 0.35,
    llm_weight: float = 0.65,
) -> float:
    """
    Combine a semantic similarity score and an LLM-based score into a
    single ranking value.

    Default weights: 35% semantic + 65% LLM.
    LLM gets higher weight because it understands nuance (YOE, domain fit)
    while semantic captures surface-level relevance quickly.

    Args:
        semantic:        semantic_score() result (0-100)
        llm:             score_job() overall_score (0-100)
        semantic_weight: weight for semantic component
        llm_weight:      weight for LLM component

    Returns:
        Hybrid score (0-100), rounded to 1 decimal place.
    """
    return round(semantic * semantic_weight + llm * llm_weight, 1)
