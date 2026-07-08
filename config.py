PARSE_MODEL   = "gemini/gemini-2.5-flash"
SCORE_MODEL   = "gemini/gemini-2.5-flash"
FALLBACK_MODEL = "gemini/gemini-2.0-flash"  # used on final retry if primary fails

DRAUP_LLM_ENV      = "prod"
DRAUP_LLM_USER     = "math"
DRAUP_LLM_PROVIDER = "gemini"

VERDICT_THRESHOLDS = {
    "Strong Match":  80,
    "Good Match":    65,
    "Partial Match": 45,
    "Weak Match":     0,
}

# Retry settings for API calls
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds (doubles each retry)

# ── Semantic matching (feature/semantic-matching branch) ───────────────────────
EMBED_MODEL = "gemini/text-embedding-004"   # Gemini embedding model via LiteLLM
EMBED_DIMENSIONS = 768                       # supported: 768 or 256

# Jobs below this semantic score are dropped before LLM scoring (saves API calls)
SEMANTIC_FILTER_THRESHOLD = 50

# Hybrid final score weights (must sum to 1.0)
SEMANTIC_WEIGHT  = 0.35
LLM_SCORE_WEIGHT = 0.65
