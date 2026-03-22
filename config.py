import os
from dotenv import load_dotenv
load_dotenv()

# ── API credentials ────────────────────────────────────────────────────────────
SCRAPEBADGER_API_KEYS = [k.strip() for k in os.getenv("SCRAPEBADGER_API_KEYS", "").split(",") if k.strip()]
OPENROUTER_API_KEY    = os.getenv("OPENROUTER_API_KEY", "")
GROQ_API_KEY          = os.getenv("GROQ_API_KEY", "")
TELEGRAM_BOT_TOKEN    = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID      = os.getenv("TELEGRAM_CHAT_ID", "")
WEBHOOK_BASE_URL      = os.getenv("WEBHOOK_BASE_URL", "")
APP_PORT              = int(os.getenv("PORT", 8000))

# ── Data file paths ────────────────────────────────────────────────────────────
SEARCH_PHRASES_FILE   = "data/search_phrases.txt"
REFERENCE_FILE        = "data/real_opportunities.txt"

# ── Model assignments ──────────────────────────────────────────────────────────
# Evaluator  → Groq llama-3.3-70b-versatile  (PRIMARY — free, reliable, NO 400 errors)
# Checker    → Groq llama-3.1-8b-instant     (SECONDARY — fast cross-validator)
# Tiebreaker → OpenRouter nemotron free      (RARELY called — only on Eval/Check disagreement)
# Inventor   → OpenRouter nemotron free      (phrase generation — large context)
# Embedder   → OpenRouter pplx-embed-v1-0.6b ($0.004/M — practically free)

EVALUATOR_GROQ_MODEL  = "llama-3.3-70b-versatile"        # used in evaluator.py directly
EVALUATOR_MODEL       = EVALUATOR_GROQ_MODEL              # backward-compat alias (old evaluator.py)
CHECKER_GROQ_MODEL    = "llama-3.1-8b-instant"           # used in checker.py
TIEBREAKER_MODEL      = "nvidia/nemotron-3-super-120b-a12b:free"   # OpenRouter
INVENTOR_MODEL        = "nvidia/nemotron-3-super-120b-a12b:free"   # OpenRouter
EMBED_MODEL           = "perplexity/pplx-embed-v1-0.6b"            # OpenRouter embeddings

# ── Pipeline thresholds ────────────────────────────────────────────────────────
SIMILARITY_MIN        = 0.45   # Below this → discard immediately (no LLM cost)
SIMILARITY_FAST_TRACK = 0.75   # Above this → skip tiebreaker even if checker disagrees
AGENT_DEATH_SCORE     = 15.0   # Agent disabled if accuracy falls below this %
INVENT_PHRASES_EVERY_N_APPROVALS = 10  # Trigger phrase invention every N approvals
