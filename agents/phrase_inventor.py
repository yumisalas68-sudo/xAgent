"""
Phrase Inventor Agent — Generates new search phrases from approved opportunities.
Uses OpenRouter nvidia/nemotron-3-super-120b-a12b:free (free, large context).
⚠️  Nemotron is a reasoning model — content field can be null.
    Falls back to 'reasoning' field, then to Groq llama-3.1-8b-instant.
"""
import json
import re
import httpx
from groq import AsyncGroq
from config import OPENROUTER_API_KEY, GROQ_API_KEY, INVENTOR_MODEL

OR_HEADERS = {
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

_groq: AsyncGroq | None = None
def _get_groq() -> AsyncGroq:
    global _groq
    if _groq is None:
        _groq = AsyncGroq(api_key=GROQ_API_KEY)
    return _groq


def _extract_content(resp_json: dict) -> str:
    """Extract text content — Nemotron may return null content, fall back to reasoning."""
    try:
        msg = resp_json["choices"][0]["message"]
        content = msg.get("content") or msg.get("reasoning") or ""
        return content.strip()
    except (KeyError, IndexError, TypeError):
        return ""


async def invent_phrases(approved_tweets: list[str], existing_phrases: list[str]) -> list[str]:
    approved_sample = "\n".join(f"• {t[:200]}" for t in approved_tweets[:15])
    existing_block  = ", ".join(existing_phrases[:30])
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": (
            f"Recent approved opportunities:\n{approved_sample}\n\n"
            f"Existing search phrases (DO NOT duplicate):\n{existing_block}\n\n"
            f"Generate 5-8 new search phrases. Reply with JSON array only."
        )},
    ]

    # Try OpenRouter (Nemotron) first
    content = ""
    try:
        async with httpx.AsyncClient(timeout=40) as client:
            r = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=OR_HEADERS,
                json={"model": INVENTOR_MODEL, "messages": messages,
                      "temperature": 0.7, "max_tokens": 250},
            )
            if r.is_success:
                content = _extract_content(r.json())
                if not content:
                    print("[INVENTOR] Nemotron returned empty content — falling back to Groq")
            else:
                print(f"[INVENTOR] OpenRouter {r.status_code}: {r.text[:300]}")
    except Exception as e:
        print(f"[INVENTOR] OpenRouter error: {e} — falling back to Groq")

    # Fallback to Groq if OpenRouter gave nothing
    if not content:
        resp = await _get_groq().chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
            temperature=0.7,
            max_tokens=200,
        )
        content = (resp.choices[0].message.content or "").strip()

    return _parse(content, existing_phrases)


def _parse(content: str, existing: list[str]) -> list[str]:
    existing_lower = {p.lower() for p in existing}
    clean = content.replace("```json", "").replace("```", "").strip()
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
    found = re.findall(r'"([^"]{3,50})"', content)
    return [p for p in found if p.lower() not in existing_lower][:8]
