import os
from dotenv import load_dotenv

load_dotenv()

# ── ScrapeBadger ─────────────────────────────────────────────────────────────
# Comma-separated list of API keys, one per account
SCRAPEBADGER_API_KEYS = [k.strip() for k in os.getenv("SCRAPEBADGER_API_KEYS", "").split(",") if k.strip()]

# ── OpenRouter ────────────────────────────────────────────────────────────────
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# ── Groq ──────────────────────────────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

# ── App ───────────────────────────────────────────────────────────────────────
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "")   # e.g. https://xyz.railway.app
APP_PORT         = int(os.getenv("PORT", 8000))

# ── Data files ────────────────────────────────────────────────────────────────
SEARCH_PHRASES_FILE  = "data/search_phrases.txt"
REFERENCE_FILE       = "data/real_opportunities.txt"

# ── Models ────────────────────────────────────────────────────────────────────
# Primary evaluator  – NVIDIA Nemotron 3 Super FREE via OpenRouter
EVALUATOR_MODEL     = "nvidia/nemotron-3-super:free"
# Cross-checker      – Groq llama-3.3-70b  (free tier)
CHECKER_GROQ_MODEL  = "llama-3.3-70b-versatile"
# Tiebreaker         – Mistral Small 4 (cheapest paid: $0.15/$0.60 per M)
TIEBREAKER_MODEL    = "mistralai/mistral-small"
# Phrase inventor    – Nemotron free  (no cost)
INVENTOR_MODEL      = "nvidia/nemotron-3-super:free"
# Embeddings         – Perplexity Embed 0.6B  ($0.004/M ≈ free)
EMBED_MODEL         = "perplexity/pplx-embed-v1-0.6b"

# ── Pipeline thresholds ───────────────────────────────────────────────────────
SIMILARITY_MIN        = 0.45   # below this → instant discard, no LLM call
SIMILARITY_FAST_TRACK = 0.75   # above this → if eval says APPROVE, skip tiebreaker

# ── Agent survival ────────────────────────────────────────────────────────────
AGENT_DEATH_SCORE = 35.0       # score% below which agent is marked DEAD

# ── Phrase invention schedule ─────────────────────────────────────────────────
INVENT_PHRASES_EVERY_N_APPROVALS = 10   # invent new phrases after every 10 approvals
