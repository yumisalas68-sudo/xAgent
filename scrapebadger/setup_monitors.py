"""
ScrapeBadger monitor setup script.

Run ONCE after deployment to create all your Stream Monitors.
Each ScrapeBadger API key gets its own batch of keywords.

Usage:
    python -m scrapebadger.setup_monitors

The script will:
  1. Load search_phrases.txt
  2. Split phrases evenly across your API keys
  3. Create one Stream Monitor per key pointing at YOUR webhook URL
"""
import asyncio
import json
import httpx
import os
import sys

# Allow running as a script from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config import SCRAPEBADGER_API_KEYS, SEARCH_PHRASES_FILE, WEBHOOK_BASE_URL


def load_phrases() -> list[str]:
    with open(SEARCH_PHRASES_FILE, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def split_phrases(phrases: list[str], n_keys: int) -> list[list[str]]:
    """Distribute phrases as evenly as possible across n_keys accounts."""
    chunk_size = max(1, len(phrases) // n_keys + (1 if len(phrases) % n_keys else 0))
    return [phrases[i : i + chunk_size] for i in range(0, len(phrases), chunk_size)]


async def create_monitor(api_key: str, name: str, keywords: list[str]) -> dict:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            "https://scrapebadger.com/v1/twitter/stream/monitors",
            headers={"x-api-key": api_key, "Content-Type": "application/json"},
            json={
                "name":                name,
                "keywords":            keywords,
                "pollIntervalSeconds": 3600,
                "webhookUrl":          f"{WEBHOOK_BASE_URL}/webhook",
            },
        )
        return r.json()


async def list_monitors(api_key: str) -> list:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            "https://scrapebadger.com/v1/twitter/stream/monitors",
            headers={"x-api-key": api_key},
        )
        return r.json()


async def main():
    if not SCRAPEBADGER_API_KEYS:
        print("❌ No SCRAPEBADGER_API_KEYS found in .env")
        return
    if not WEBHOOK_BASE_URL:
        print("❌ WEBHOOK_BASE_URL not set in .env")
        return

    phrases = load_phrases()
    print(f"✅ Loaded {len(phrases)} search phrases")

    chunks = split_phrases(phrases, len(SCRAPEBADGER_API_KEYS))
    print(f"✅ Distributing across {len(SCRAPEBADGER_API_KEYS)} ScrapeBadger accounts")

    for idx, (api_key, chunk) in enumerate(zip(SCRAPEBADGER_API_KEYS, chunks), start=1):
        name   = f"OpportunityHunter-{idx}"
        print(f"\n[Account {idx}] Creating monitor '{name}' with keywords: {chunk}")
        try:
            result = await create_monitor(api_key, name, chunk)
            print(f"  → Result: {json.dumps(result, indent=2)}")
        except Exception as e:
            print(f"  → ❌ Error: {e}")
        await asyncio.sleep(1)

    print("\n✅ Setup complete! Monitors are running and will deliver tweets to your webhook hourly.")


if __name__ == "__main__":
    asyncio.run(main())
