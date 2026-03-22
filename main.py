"""
FastAPI app — entry point.

HOW IT WORKS:
  On startup, a background scheduler runs every hour.
  It loops through all search phrases, hits ScrapeBadger advanced search
  for each one, and feeds every tweet into the agent pipeline.
  No webhooks. No Stream Monitors. Railway runs this 24/7.

Endpoints:
  GET /health    — Railway health check
  GET /stats     — Agent scores + opportunity counts
  GET /phrases   — All known search phrases (user + invented)
  GET /run-now   — Trigger a search cycle immediately (for testing)
"""
import asyncio
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
import uvicorn

from core.database         import init_db, get_stats, get_all_phrases, save_new_phrase
from core.reference_loader import reference_store
from core.pipeline         import process_tweet
from telegram_bot.notifier import send_status_update
from config import (APP_PORT, SCRAPEBADGER_API_KEYS, SEARCH_PHRASES_FILE)

# ── ScrapeBadger advanced search (correct endpoint) ───────────────────────────
SCRAPEBADGER_SEARCH_URL = "https://scrapebadger.com/v1/twitter/tweets/advanced_search"


async def search_phrase(api_key: str, phrase: str, count: int = 20) -> tuple[list[dict], bool]:
    """
    Call ScrapeBadger advanced tweet search for one phrase.
    Returns (tweets, depleted) where depleted=True means the account is out of credits.
    """
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                SCRAPEBADGER_SEARCH_URL,
                headers={"x-api-key": api_key},
                params={"query": phrase, "result_type": "recent", "count": count},
            )
            # 402 = out of credits — mark this key as depleted
            if r.status_code == 402:
                print(f"[SEARCH] ⚠️  API key ...{api_key[-6:]} OUT OF CREDITS (402) — skipping for this cycle")
                return [], True

            if not r.is_success:
                print(f"[SEARCH] HTTP {r.status_code} for '{phrase}': {r.text[:200]}")
                return [], False

            data = r.json()
            # Handle both {"data": [...]} and plain list responses
            tweets = data.get("data", data) if isinstance(data, dict) else data
            return (tweets if isinstance(tweets, list) else []), False

    except Exception as e:
        print(f"[SEARCH] Error searching '{phrase}': {e}")
        return [], False


# ── Hourly search cycle ───────────────────────────────────────────────────────
async def run_search_cycle():
    """Search all phrases across all API keys, feed results into pipeline."""
    phrases = _load_phrases()
    if not phrases:
        print("[SCHEDULER] No search phrases found")
        return

    if not SCRAPEBADGER_API_KEYS:
        print("[SCHEDULER] No SCRAPEBADGER_API_KEYS set")
        return

    print(f"[SCHEDULER] Starting cycle — {len(phrases)} phrases, "
          f"{len(SCRAPEBADGER_API_KEYS)} API keys")

    # Track which API keys have run out of credits this cycle
    depleted_keys: set[str] = set()

    # Distribute phrases across API keys (round-robin), skipping depleted ones
    total_found = 0
    for i, phrase in enumerate(phrases):
        # Pick next non-depleted key (round-robin)
        api_key = None
        for offset in range(len(SCRAPEBADGER_API_KEYS)):
            candidate = SCRAPEBADGER_API_KEYS[(i + offset) % len(SCRAPEBADGER_API_KEYS)]
            if candidate not in depleted_keys:
                api_key = candidate
                break

        if api_key is None:
            print(f"[SCHEDULER] ❌ All API keys depleted — stopping cycle early")
            await send_status_update(
                "⚠️ *ScrapeBadger Alert*\n"
                "All API accounts have run out of credits.\n"
                "Please top up at https://scrapebadger.com/dashboard")
            break

        tweets, is_depleted = await search_phrase(api_key, phrase)
        if is_depleted:
            depleted_keys.add(api_key)
            # Retry this phrase with the next available key
            for offset in range(1, len(SCRAPEBADGER_API_KEYS)):
                fallback = SCRAPEBADGER_API_KEYS[(i + offset) % len(SCRAPEBADGER_API_KEYS)]
                if fallback not in depleted_keys:
                    tweets, is_depleted2 = await search_phrase(fallback, phrase)
                    if is_depleted2:
                        depleted_keys.add(fallback)
                    else:
                        api_key = fallback
                        break
            else:
                tweets = []  # All keys exhausted

        print(f"[SCHEDULER] '{phrase}' → {len(tweets)} tweets"
              + (f" (key ...{api_key[-6:]})" if api_key else ""))
        total_found += len(tweets)

        for tweet in tweets:
            tweet_id   = str(tweet.get("id") or tweet.get("tweet_id") or "")
            tweet_text = str(tweet.get("text") or tweet.get("full_text") or "")
            raw_url    = tweet.get("url") or tweet.get("tweet_url")
            tweet_url  = str(raw_url) if raw_url else f"https://x.com/i/web/status/{tweet_id}"

            if tweet_id and tweet_text:
                try:
                    await process_tweet(tweet_id, tweet_text, tweet_url)
                except Exception as e:
                    print(f"[SCHEDULER] Pipeline error {tweet_id}: {e}")

        # Small delay between phrases to avoid hammering the API
        await asyncio.sleep(2)

    # Report depleted keys at end of cycle
    if depleted_keys:
        count_ok = len(SCRAPEBADGER_API_KEYS) - len(depleted_keys)
        print(f"[SCHEDULER] Cycle complete — {total_found} tweets | "
              f"{len(depleted_keys)} key(s) depleted, {count_ok} still active")
    else:
        print(f"[SCHEDULER] Cycle complete — {total_found} tweets processed")


async def _scheduler_loop():
    """Run search cycle every hour forever."""
    # Small delay on startup so the app fully initialises first
    await asyncio.sleep(10)
    while True:
        try:
            await run_search_cycle()
        except Exception as e:
            print(f"[SCHEDULER] Cycle error: {e}")
        print("[SCHEDULER] Sleeping 1 hour…")
        await asyncio.sleep(3600)


def _load_phrases() -> list[str]:
    try:
        with open(SEARCH_PHRASES_FILE) as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        return []


# ── App lifespan ──────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:    init_db()
    except Exception as e: print(f"[STARTUP] DB error: {e}")

    try:    await reference_store.refresh_if_needed()
    except Exception as e: print(f"[STARTUP] Ref store error: {e}")

    try:
        await send_status_update(
            "🟢 *Opportunity Hunter ONLINE*\n"
            "Agents searching every hour 🔍\n"
            "Find good opportunities or be turned off. 💀")
    except Exception as e: print(f"[STARTUP] Telegram error: {e}")

    task = asyncio.create_task(_scheduler_loop())
    print("[APP] ✅ Started — hourly search scheduler running")
    yield
    task.cancel()
    try:    await send_status_update("🔴 Opportunity Hunter going OFFLINE.")
    except: pass


app = FastAPI(title="Opportunity Hunter", lifespan=lifespan)


# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "alive"}

@app.get("/stats")
async def stats():
    try:    return get_stats()
    except Exception as e: return {"error": str(e)}

@app.get("/phrases")
async def phrases():
    try:    return {"phrases": get_all_phrases()}
    except Exception as e: return {"error": str(e)}

@app.get("/run-now")
async def run_now():
    """Trigger a full search cycle immediately without waiting for the hour."""
    asyncio.create_task(run_search_cycle())
    return {"status": "search cycle triggered"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=APP_PORT, reload=False)
