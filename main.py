"""
FastAPI application — entry point.

Endpoints:
  POST /webhook   ← ScrapeBadger delivers tweets here
  GET  /health    ← Railway health check
  GET  /stats     ← Agent scores + opportunity counts
  GET  /phrases   ← All known search phrases (user + invented)
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
import uvicorn

from core.database        import init_db, get_stats, get_all_phrases
from core.reference_loader import reference_store
from core.pipeline        import process_tweet
from telegram_bot.notifier import send_status_update
from config import APP_PORT


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────────────────────
    init_db()
    await reference_store.refresh_if_needed()
    await send_status_update(
        "🟢 *Opportunity Hunter is ONLINE*\n"
        "Agents are active and waiting for tweets.\n"
        "Find good opportunities or be turned off. 💀"
    )
    print("[APP] ✅ Startup complete")
    yield
    # ── Shutdown ──────────────────────────────────────────────────────────────
    await send_status_update("🔴 Opportunity Hunter is going OFFLINE.")
    print("[APP] Shutdown")


app = FastAPI(title="Opportunity Hunter", lifespan=lifespan)


# ── Webhook ───────────────────────────────────────────────────────────────────
@app.post("/webhook")
async def webhook(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Normalise ScrapeBadger payload (may vary by endpoint version)
    if isinstance(body, list):
        tweets = body
    elif isinstance(body, dict):
        tweets = body.get("tweets") or body.get("data") or []
    else:
        tweets = []

    if not tweets:
        return {"status": "ok", "processed": 0}

    # Process up to 10 tweets concurrently; rest are queued by the semaphore
    sem = asyncio.Semaphore(10)

    async def _process(tweet):
        async with sem:
            tweet_id   = str(tweet.get("id")   or tweet.get("tweet_id") or "")
            tweet_text = tweet.get("text")      or tweet.get("full_text") or ""
            tweet_url  = (
                tweet.get("url")
                or tweet.get("tweet_url")
                or (f"https://x.com/i/web/status/{tweet_id}" if tweet_id else "")
            )
            if tweet_id and tweet_text:
                try:
                    await process_tweet(tweet_id, tweet_text, tweet_url)
                except Exception as e:
                    print(f"[WEBHOOK] Error processing {tweet_id}: {e}")

    await asyncio.gather(*[_process(t) for t in tweets])
    return {"status": "ok", "processed": len(tweets)}


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "alive"}


# ── Stats ─────────────────────────────────────────────────────────────────────
@app.get("/stats")
async def stats():
    return get_stats()


# ── Phrases ───────────────────────────────────────────────────────────────────
@app.get("/phrases")
async def phrases():
    return {"phrases": get_all_phrases()}


# ── Run locally ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=APP_PORT, reload=False)
