"""
recruiter_finder.py — Finds recruiter/founder emails for a company using Hunter.io.
Falls back to Apollo enrichment if Hunter finds nothing.
"""

import os
import re
import json
import requests

HUNTER_API_KEY = os.environ.get("HUNTER_API_KEY", "")
HUNTER_BASE    = "https://api.hunter.io/v2"

# Titles we care about (checked case-insensitively)
TARGET_TITLES = [
    "founder", "co-founder", "ceo", "cto", "cpo",
    "head of engineering", "vp engineering", "engineering manager",
    "recruiter", "talent acquisition", "head of people",
    "people operations", "hr", "hiring",
]

COMPANY_DOMAINS = {
    "minusx":      "minusx.ai",
    "ragie":       "ragie.io",
    "scispot":     "scispot.com",
    "brainfish":   "brainfish.ai",
    "junction":    "junction.dev",
    "klavis":      "klavis.ai",
    "wildcard":    "wildcard.ai",
    "resend":      "resend.com",
    "raven":       "raven.ai",
    "superkalam":  "superkalam.com",
    "zenopsys":    "zenopsys.com",
    "refold":      "refold.ai",
    "growthsphere":"growthsphere.ai",
    "expertia":    "expertia.ai",
    "drdroid":     "drdroid.io",
    "smallest":    "smallest.ai",
    "8byte":       "8byte.in",
    "zenteiq":     "zenteiq.ai",
    "voiceops":    "voiceops.com",
    "deepaware":   "deepaware.ai",
    "palladio":    "palladio.ai",
    "zenskar":     "zenskar.com",
}


_STRIP_SUFFIXES = re.compile(
    r"\b(inc\.?|llc\.?|ltd\.?|corp\.?|co\.?|pvt\.?|group|technologies|"
    r"technology|tech|solutions|systems|labs?|services|consulting|global|"
    r"international|enterprises?|ventures?|innovation|networks?)\b",
    re.IGNORECASE,
)

_TLDS_TO_TRY = [".com", ".io", ".ai", ".co"]


def _guess_domains(company: str) -> list[str]:
    """
    Return a prioritised list of likely domains for a company name.
    E.g. "DigitalXNode" → ["digitalxnode.com", "digitalxnode.io", "digitalxnode.ai"]
    """
    cleaned = _STRIP_SUFFIXES.sub("", company)
    slug = re.sub(r"[^a-z0-9]", "", cleaned.lower())
    if not slug:
        slug = re.sub(r"[^a-z0-9]", "", company.lower())
    return [f"{slug}{tld}" for tld in _TLDS_TO_TRY if slug]


def _is_target(title: str | None) -> bool:
    if not title:
        return False
    return any(kw in title.lower() for kw in TARGET_TITLES)


def find_by_domain(domain: str) -> dict:
    """
    Search Hunter.io for all known emails at a domain.
    Returns filtered contacts + email pattern.
    """
    if not HUNTER_API_KEY:
        raise ValueError("HUNTER_API_KEY not set.")

    r = requests.get(
        f"{HUNTER_BASE}/domain-search",
        params={
            "domain":  domain,
            "api_key": HUNTER_API_KEY,
            "limit":   10,
        },
        timeout=10,
    )
    if not r.ok:
        err = r.json().get("errors", r.text)
        raise ValueError(f"Hunter API error {r.status_code}: {err}")
    data = r.json().get("data", {})

    pattern    = data.get("pattern", "unknown")
    all_emails = data.get("emails", [])

    # Filter to relevant titles, fall back to all verified if none match
    relevant = [e for e in all_emails if _is_target(e.get("position"))]
    if not relevant:
        relevant = [e for e in all_emails if e.get("verification", {}).get("status") == "valid"]
    if not relevant:
        relevant = all_emails[:5]

    contacts = []
    for e in relevant:
        contacts.append({
            "name":       f"{e.get('first_name') or ''} {e.get('last_name') or ''}".strip(),
            "email":      e.get("value", ""),
            "title":      e.get("position") or "unknown",
            "confidence": e.get("confidence", 0),
            "linkedin":   e.get("linkedin") or "",
            "verified":   e.get("verification", {}).get("status", "unknown"),
        })

    return {
        "domain":        domain,
        "email_pattern": pattern,
        "total_found":   len(all_emails),
        "contacts":      sorted(contacts, key=lambda x: x["confidence"], reverse=True),
    }


def find_contacts(company: str, domain: str | None = None) -> dict:
    """
    Find recruiter/founder contacts for a company.
    Priority: explicit domain > COMPANY_DOMAINS map > inferred domain candidates.
    """
    if not domain:
        domain = COMPANY_DOMAINS.get(company.lower().split()[0])

    if domain:
        result = find_by_domain(domain)
        result["company"] = company
        return result

    candidates = _guess_domains(company)
    for candidate in candidates:
        try:
            result = find_by_domain(candidate)
            if result.get("contacts") or result.get("total_found", 0) > 0:
                result["company"] = company
                return result
        except Exception:
            continue

    tried = ", ".join(candidates)
    return {
        "company": company,
        "contacts": [],
        "error": f"No contacts found (tried: {tried})",
    }


def find_all(companies: list[str]) -> list[dict]:
    """Find contacts for a list of company names."""
    results = []
    for company in companies:
        print(f"  Searching: {company} ...", end=" ", flush=True)
        try:
            r = find_contacts(company)
            found = len(r.get("contacts", []))
            print(f"{found} contacts found (pattern: {r.get('email_pattern')})")
            results.append(r)
        except Exception as e:
            print(f"error: {e}")
            results.append({"company": company, "error": str(e)})
    return results


def print_results(results: list[dict]):
    for r in results:
        print(f"\n{'='*60}")
        print(f"Company : {r.get('company')}")
        if "error" in r:
            print(f"Error   : {r['error']}")
            continue
        print(f"Domain  : {r.get('domain')}")
        print(f"Pattern : {r.get('email_pattern')}")
        print(f"Total   : {r.get('total_found')} emails on file")
        print(f"Contacts:")
        for c in r.get("contacts", []):
            verified = "✓" if c["verified"] == "valid" else "~"
            print(f"  {verified} {c['name']:<25} {c['title']:<35} {c['email']}  ({c['confidence']}%)")
