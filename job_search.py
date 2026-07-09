"""
job_search.py — Searches Google Jobs via SerpAPI, scores results against a profile,
and returns a ranked list of matching jobs.
"""

import os
import re
import json
import time
from serpapi import GoogleSearch
from scorer import score_job

SERP_API_KEY = os.environ.get("SERP_API_KEY", "")

# Number of results to fetch per search query
RESULTS_PER_QUERY = 10

# Minimum score to include in ranked output
MIN_SCORE = 40


# Keywords in job description that indicate visa sponsorship or on-site requirement.
# Jobs matching these are dropped for international remote-only candidates.
_VISA_REQUIRED_PATTERNS = [
    "must be authorized to work in the us",
    "must be legally authorized",
    "no visa sponsorship",
    "will not sponsor",
    "sponsorship not available",
    "sponsorship is not available",
    "must have us citizenship",
    "us citizen only",
    "security clearance required",
    "active secret clearance",
    "active top secret",
    "requires us citizenship",
]

# Location strings that signal on-site / in-office work
_ONSITE_LOCATION_SIGNALS = [
    "on-site", "onsite", "on site", "in-office", "in office",
]


def _build_queries(profile: dict, locations: list[str]) -> list[tuple]:
    """
    Build search queries from the candidate profile.
    US locations always get "remote" appended — we only want remote-eligible roles.
    """
    role = profile.get("current_role", "AI Engineer")

    base_queries = [
        f"{role}",
        "Generative AI Engineer",
        "AI ML Engineer LLM",
        "Machine Learning Engineer LLM RAG",
    ]

    queries = []
    for loc in locations:
        is_us     = any(k in loc.lower() for k in ["united states", "us", "usa"])
        is_remote = "remote" in loc.lower()

        for q in base_queries:
            # Always add "remote" for US locations — avoids on-site results
            if is_remote or is_us:
                queries.append((f"{q} remote", loc))
            else:
                queries.append((q, loc))
    return queries


def _extract_required_yoe(description: str) -> tuple[float, float] | None:
    """
    Extract min/max required YOE from a job description using regex.
    Returns (min_yoe, max_yoe) or None if no YOE requirement found.
    """
    desc = description.lower()

    match = re.search(r"(\d+)\+\s*years?(?:\s+of)?(?:\s+experience)?", desc)
    if match:
        n = float(match.group(1))
        return (n, n + 5)

    match = re.search(r"(\d+)\s*[-\u2013to]+\s*(\d+)\s*years?(?:\s+of)?(?:\s+experience)?", desc)
    if match:
        return (float(match.group(1)), float(match.group(2)))

    match = re.search(r"(?:minimum|at least|minimum of)\s+(\d+)\s*years?", desc)
    if match:
        n = float(match.group(1))
        return (n, n + 5)

    return None


def _yoe_mismatch(job: dict, candidate_yoe: float, tolerance: float = 2.0) -> bool:
    """
    Return True if the job's required YOE is too far from the candidate's YOE.
    tolerance=2.0 means ±2 years from your actual YOE is acceptable.
    """
    yoe_range = _extract_required_yoe(job.get("description", ""))
    if yoe_range is None:
        return False

    min_req, max_req = yoe_range

    if min_req > candidate_yoe + tolerance:
        return True

    if max_req < candidate_yoe - tolerance and max_req < 1:
        return True

    return False


def _is_stale(job: dict, max_days: int = 30) -> bool:
    """
    Return True if the job was posted more than max_days ago.
    Parses SerpAPI relative strings: "3 days ago", "1 week ago", "2 months ago".
    Jobs with no posted_at are kept (benefit of the doubt).
    """
    posted = (job.get("posted_at") or "").lower().strip()
    if not posted:
        return False

    match = re.search(r"(\d+)\s*(hour|day|week|month|year)s?\s*ago", posted)
    if not match:
        return False

    n, unit = int(match.group(1)), match.group(2)
    days = {"hour": 0, "day": n, "week": n * 7, "month": n * 30, "year": n * 365}[unit]
    return days > max_days


def _requires_visa(job: dict) -> bool:
    """
    Return True if the job description signals it requires US work authorization
    or an on-site presence — both are blockers for an international remote candidate.
    """
    desc     = (job.get("description") or "").lower()
    location = (job.get("location") or "").lower()

    if any(pattern in desc for pattern in _VISA_REQUIRED_PATTERNS):
        return True

    # Drop jobs whose location string says on-site (not remote)
    if any(signal in location for signal in _ONSITE_LOCATION_SIGNALS):
        return True

    return False


def _fetch_jobs(query: str, location: str) -> list[dict]:
    """Fetch jobs from Google Jobs via SerpAPI for a single query+location."""
    if not SERP_API_KEY:
        raise ValueError("SERP_API_KEY environment variable not set.")

    # Always request remote filter for US searches
    is_us     = any(k in location.lower() for k in ["united states", "us", "usa"])
    is_remote = "remote" in location.lower()

    params = {
        "engine":   "google_jobs",
        "q":        query,
        "location": location,
        "hl":       "en",
        "api_key":  SERP_API_KEY,
    }
    if is_remote or is_us:
        params["ltype"] = "1"   # Google Jobs filter: remote only

    search  = GoogleSearch(params)
    results = search.get_dict()
    return results.get("jobs_results", [])


def _parse_job(raw: dict) -> dict:
    """Normalize a raw SerpAPI job result into our schema."""
    description = raw.get("description", "")

    # Some jobs have structured highlights — append them to description
    highlights = raw.get("job_highlights", [])
    for h in highlights:
        title = h.get("title", "")
        items = h.get("items", [])
        description += f"\n\n{title}:\n" + "\n".join(f"- {i}" for i in items)

    apply_link = ""
    for opt in raw.get("apply_options", []):
        if opt.get("link"):
            apply_link = opt["link"]
            break

    extensions   = raw.get("detected_extensions", {})
    posted_at    = extensions.get("posted_at", "")        # e.g. "3 days ago"
    schedule     = extensions.get("schedule_type", "")    # e.g. "Full-time"

    return {
        "title":       raw.get("title", ""),
        "company":     raw.get("company_name", ""),
        "location":    raw.get("location", ""),
        "posted_via":  raw.get("via", ""),
        "posted_at":   posted_at,
        "schedule":    schedule,
        "description": description.strip(),
        "apply_link":  apply_link,
        "score":       None,
        "verdict":     None,
        "matched_skills":  [],
        "missing_skills":  [],
        "recommendation":  "",
    }


def search_and_rank(
    profile: dict,
    locations: list[str] | None = None,
    top_n: int = 10,
    min_score: int = MIN_SCORE,
) -> list[dict]:
    """
    Search Google Jobs for roles matching the profile, score each, return ranked list.

    Args:
        profile:   Parsed resume profile dict (from parser.py)
        locations: List of locations to search. Defaults to Bangalore + Remote.
        top_n:     Return top N results after scoring.
        min_score: Drop results below this score.

    Returns:
        List of job dicts sorted by score descending.
    """
    if locations is None:
        # Remote-first: US remote, then global remote, Bangalore as fallback
        locations = [
            "Remote",          # global remote (includes US remote postings)
            "United States",   # US-based remote/hybrid
            "Bangalore, India",
        ]

    queries = _build_queries(profile, locations)

    # Fetch + deduplicate by (title, company)
    seen   = set()
    jobs   = []
    for query, location in queries:
        print(f"  Searching: '{query}' in {location} ...", flush=True)
        try:
            raw_jobs = _fetch_jobs(query, location)
            for raw in raw_jobs:
                job = _parse_job(raw)
                key = (job["title"].lower(), job["company"].lower())
                if key not in seen and job["description"]:
                    if _requires_visa(job):
                        print(f"    [skipped] {job['company']} — {job['title']} (visa/on-site required)", flush=True)
                        continue
                    if _yoe_mismatch(job, profile.get("total_yoe", 0)):
                        print(f"    [skipped] {job['company']} — {job['title']} (YOE mismatch)", flush=True)
                        continue
                    if _is_stale(job):
                        print(f"    [skipped] {job['company']} — {job['title']} (posted {job.get('posted_at', '?')})", flush=True)
                        continue
                    seen.add(key)
                    jobs.append(job)
            time.sleep(0.5)  # be polite to the API
        except Exception as e:
            print(f"    [error] {e}", flush=True)

    print(f"\nFetched {len(jobs)} unique jobs. Scoring...\n", flush=True)

    # Score each job
    for i, job in enumerate(jobs, 1):
        print(f"  [{i}/{len(jobs)}] {job['company']} — {job['title']} ...", end=" ", flush=True)
        try:
            result = score_job(profile, job["description"])
            job["score"]           = result["overall_score"]
            job["verdict"]         = result["verdict"]
            job["matched_skills"]  = result.get("matched_skills", [])
            job["missing_skills"]  = result.get("missing_skills", [])
            job["recommendation"]  = result.get("recommendation", "")
            job["breakdown"]       = result.get("breakdown", {})
            print(f"{job['score']}/100  [{job['verdict']}]", flush=True)
        except Exception as e:
            print(f"error: {e}", flush=True)
            job["score"] = 0

        time.sleep(0.3)

    # Filter + sort
    ranked = sorted(
        [j for j in jobs if (j["score"] or 0) >= min_score],
        key=lambda j: j["score"],
        reverse=True,
    )
    return ranked[:top_n]
