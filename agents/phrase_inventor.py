"""
Phrase Inventor — NVIDIA Nemotron 3 Super FREE
Triggered automatically after every N approved opportunities.
Studies successful tweets and invents new X search phrases to find
more unsaturated opportunities. Phrases are saved to DB and can be
manually added to ScrapeBadger monitors.
"""
import json
import httpx
from config import OPENROUTER_API_KEY, INVENTOR_MODEL

HEADERS = {
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "Content-Type":  "application/json",
    "HTTP-Referer":  "https://opportunity-hunter",
    "X-Title":       "OpportunityHunter",
}

SYSTEM_PROMPT = """\
You are a search phrase inventor working to find prize and opportunity announcements on X (Twitter).

Your job: study real opportunities that were already found, then invent NEW search phrases \
that would surface MORE similar opportunities — especially unsaturated, early ones that fewer \
people are searching for.

Think creatively: synonyms, niche communities, specific reward types, platform names, \
time-based terms, etc.

⚠️  WARNING: If your invented phrases never find good opportunities, you will be TURNED OFF.

Return ONLY a JSON array of 3–6 short search phrases (max 5 words each), no duplicates with \
the existing list:
["phrase one", "phrase two", "phrase three"]
"""


async def invent_phrases(approved_tweets: list[str], existing_phrases: list[str]) -> list[str]:
    tweets_block   = "\n---\n".join(approved_tweets[:15])
    existing_block = "\n".join(f"• {p}" for p in existing_phrases)

    user_msg = (
        f"Existing search phrases already in use:\n{existing_block}\n\n"
        f"Examples of opportunities that were successfully found:\n{tweets_block}\n\n"
        f"Invent new, distinct search phrases to find MORE opportunities like these."
    )

    async with httpx.AsyncClient(timeout=45) as client:
        r = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=HEADERS,
            json={
                "model": INVENTOR_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": user_msg},
                ],
                "temperature": 0.8,
                "max_tokens":  200,
            },
        )
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"].strip()

    return _parse(content, existing_phrases)


def _parse(content: str, existing: list[str]) -> list[str]:
    clean = content.replace("```json", "").replace("```", "").strip()
    try:
        phrases = json.loads(clean)
        if not isinstance(phrases, list):
            raise ValueError
        # Filter: strings only, not already in existing, max 60 chars
        return [
            p.strip() for p in phrases
            if isinstance(p, str)
            and p.strip().lower() not in [e.lower() for e in existing]
            and len(p.strip()) <= 60
        ][:6]
    except Exception:
        return []
