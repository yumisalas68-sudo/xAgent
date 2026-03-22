"""
Phrase Inventor Agent — Generates new search phrases from approved opportunities.
Uses OpenRouter nvidia/nemotron-3-super-120b-a12b:free (free, large context).
Fires every N approved opportunities (set in config).
"""
import json
import httpx
from config import OPENROUTER_API_KEY, INVENTOR_MODEL

HEADERS = {
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "Content-Type": "application/json",
    "HTTP-Referer": "https://opportunity-hunter",
    "X-Title": "OpportunityHunter",
}

SYSTEM_PROMPT = """\
You are a creative search-phrase inventor for a prize-opportunity hunting system.
Analyze approved opportunities and generate NEW search phrases that will find MORE
similar high-value tweets on Twitter/X.

Rules:
- Phrases must be 2-4 words (Twitter search style)
- Focus on prize/reward/competition signals
- Avoid duplicating existing phrases
- Think about what real organizers write when announcing prizes
- Mix English variations, abbreviations, crypto slang

Respond ONLY with valid JSON array of strings, no markdown:
["phrase one", "phrase two", "phrase three", ...]"""


async def invent_phrases(approved_tweets: list[str], existing_phrases: list[str]) -> list[str]:
    approved_sample = "\n".join(f"• {t[:200]}" for t in approved_tweets[:15])
    existing_block  = ", ".join(existing_phrases[:30])

    user_msg = (
        f"Recent approved opportunities:\n{approved_sample}\n\n"
        f"Existing search phrases (DO NOT duplicate):\n{existing_block}\n\n"
        f"Generate 5-8 new search phrases. Reply with JSON array only."
    )
    async with httpx.AsyncClient(timeout=40) as client:
        r = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=HEADERS,
            json={
                "model": INVENTOR_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": user_msg},
                ],
                "temperature": 0.7,
                "max_tokens": 200,
            },
        )
        if not r.is_success:
            print(f"[INVENTOR] OpenRouter error {r.status_code}: {r.text[:500]}")
            r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"].strip()
    return _parse(content, existing_phrases)


def _parse(content: str, existing: list[str]) -> list[str]:
    clean = content.replace("```json", "").replace("```", "").strip()
    existing_lower = {p.lower() for p in existing}
    try:
        phrases = json.loads(clean)
        if isinstance(phrases, list):
            return [
                p.strip() for p in phrases
                if isinstance(p, str) and p.strip()
                and p.strip().lower() not in existing_lower
            ][:8]
    except Exception:
        pass
    # Fallback: extract quoted strings
    import re
    found = re.findall(r'"([^"]{3,50})"', content)
    return [p for p in found if p.lower() not in existing_lower][:8]
