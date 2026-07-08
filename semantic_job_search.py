"""
semantic_job_search.py — Job search with semantic pre-filtering + hybrid ranking.

Drop-in replacement for job_search.search_and_rank() on the
feature/semantic-matching branch.

Pipeline:
  1. Fetch raw jobs from Google Jobs via SerpAPI (same as job_search.py)
  2. Embed resume profile ONCE using Gemini text-embedding-004
  3. For each job: compute semantic similarity (fast, cheap embedding call)
  4. Drop jobs below SEMANTIC_FILTER_THRESHOLD — skip LLM scoring for these
  5. Run LLM scoring (scorer.py) only on semantically relevant jobs
  6. Compute hybrid score = 0.35 * semantic + 0.65 * llm
  7. Return top-N ranked by hybrid score

Why this is better:
  - Embedding is ~100x cheaper than an LLM completion
  - Pre-filtering means we only burn LLM calls on jobs that are actually relevant
  - Hybrid ranking captures both surface relevance (semantic) and nuance (LLM)
"""

import time

from job_search import _build_queries, _fetch_jobs, _parse_job  # reuse fetch logic
from scorer import score_job
from embedder import embed_profile, semantic_score, hybrid_score
from guardrails import get_logger, sanitize_input, track_token_usage
from config import SEMANTIC_FILTER_THRESHOLD, SEMANTIC_WEIGHT, LLM_SCORE_WEIGHT

logger = get_logger("semantic_job_search")


def search_and_rank_semantic(
    profile:    dict,
    locations:  list[str] | None = None,
    top_n:      int = 10,
    min_score:  int = 60,
    sem_threshold: int = SEMANTIC_FILTER_THRESHOLD,
) -> list[dict]:
    """
    Search Google Jobs, semantically pre-filter, LLM-score survivors,
    and return top-N ranked by hybrid score.

    Args:
        profile:       Parsed resume profile dict (from parser.py)
        locations:     List of locations to search
        top_n:         Return top N results
        min_score:     Minimum hybrid score to include in output
        sem_threshold: Minimum semantic score to proceed to LLM scoring

    Returns:
        List of job dicts sorted by hybrid_score descending.
        Each job has extra keys: semantic_score, llm_score, hybrid_score.
    """
    if locations is None:
        locations = ["Remote", "United States", "Bangalore, India"]

    # ── Step 1: Fetch raw jobs ──────────────────────────────────────────────────
    queries = _build_queries(profile, locations)
    seen, jobs = set(), []

    for query, location in queries:
        logger.info("Searching: '%s' in %s", query, location)
        try:
            raw_jobs = _fetch_jobs(query, location)
            for raw in raw_jobs:
                job = _parse_job(raw)
                key = (job["title"].lower(), job["company"].lower())
                if key not in seen and job["description"]:
                    seen.add(key)
                    jobs.append(job)
            time.sleep(0.5)
        except Exception as e:
            logger.warning("Search error for '%s' in %s: %s", query, location, e)

    logger.info("Fetched %d unique jobs total", len(jobs))

    # ── Step 2: Embed resume profile (once) ────────────────────────────────────
    logger.info("Embedding resume profile...")
    try:
        profile_vec = embed_profile(profile)
    except Exception as e:
        logger.error("Profile embedding failed: %s — falling back to LLM-only scoring", e)
        profile_vec = None

    # ── Step 3 & 4: Semantic pre-filter ────────────────────────────────────────
    if profile_vec is not None:
        logger.info(
            "Running semantic pre-filter (threshold=%d) on %d jobs...",
            sem_threshold, len(jobs),
        )
        candidates = []
        for i, job in enumerate(jobs, 1):
            try:
                safe_desc = sanitize_input(job["description"], label=f"jd_{i}")
                sem = semantic_score(profile_vec, safe_desc)
                job["semantic_score"] = sem

                if sem >= sem_threshold:
                    candidates.append(job)
                    logger.info(
                        "  [%d/%d] %s — %s | semantic=%.1f ✓ (above threshold)",
                        i, len(jobs), job["company"], job["title"], sem,
                    )
                else:
                    logger.info(
                        "  [%d/%d] %s — %s | semantic=%.1f ✗ (filtered out)",
                        i, len(jobs), job["company"], job["title"], sem,
                    )
                time.sleep(0.2)
            except Exception as e:
                logger.warning("Semantic scoring failed for %s: %s — keeping job", job["company"], e)
                job["semantic_score"] = 50.0  # neutral score, don't drop it
                candidates.append(job)

        logger.info(
            "Semantic filter: %d/%d jobs passed (threshold=%d)",
            len(candidates), len(jobs), sem_threshold,
        )
    else:
        # Embedding failed — process all jobs with LLM only
        candidates = jobs
        for job in candidates:
            job["semantic_score"] = None

    # ── Step 5: LLM scoring on candidates ──────────────────────────────────────
    logger.info("LLM scoring %d candidates...", len(candidates))
    for i, job in enumerate(candidates, 1):
        logger.info(
            "  [%d/%d] %s — %s",
            i, len(candidates), job["company"], job["title"],
        )
        try:
            safe_desc = sanitize_input(job["description"], label=f"llm_jd_{i}")
            result = score_job(profile, safe_desc)

            job["llm_score"]      = result["overall_score"]
            job["score"]          = result["overall_score"]   # keep compat key
            job["verdict"]        = result["verdict"]
            job["matched_skills"] = result.get("matched_skills", [])
            job["missing_skills"] = result.get("missing_skills", [])
            job["recommendation"] = result.get("recommendation", "")
            job["breakdown"]      = result.get("breakdown", {})

            # ── Step 6: Hybrid score ────────────────────────────────────────────
            sem = job.get("semantic_score")
            if sem is not None:
                h = hybrid_score(sem, result["overall_score"], SEMANTIC_WEIGHT, LLM_SCORE_WEIGHT)
            else:
                h = float(result["overall_score"])  # no semantic — use LLM only

            job["hybrid_score"] = h
            job["score"]        = int(round(h))  # update primary score to hybrid

            logger.info(
                "    semantic=%.1f | llm=%d | hybrid=%.1f | %s",
                sem if sem is not None else -1,
                result["overall_score"],
                h,
                result["verdict"],
            )
        except Exception as e:
            logger.warning("LLM scoring failed for %s: %s", job["company"], e)
            job["llm_score"]    = 0
            job["hybrid_score"] = job.get("semantic_score", 0) or 0
            job["score"]        = 0

        time.sleep(0.3)

    # ── Step 7: Filter + rank ───────────────────────────────────────────────────
    ranked = sorted(
        [j for j in candidates if (j.get("hybrid_score") or 0) >= min_score],
        key=lambda j: j.get("hybrid_score") or 0,
        reverse=True,
    )

    logger.info(
        "Final: %d jobs above min_score=%d, returning top %d",
        len(ranked), min_score, top_n,
    )
    return ranked[:top_n]
