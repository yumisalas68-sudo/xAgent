"""
Evaluator Agent — Primary decision maker.
Uses Groq llama-3.3-70b-versatile (free, reliable, no 400 errors).
OpenRouter was causing persistent 400 Bad Request — moved to Groq permanently.
"""
import json
from groq import AsyncGroq
from config import GROQ_API_KEY

# Lazy init — won't crash on startup if key is temporarily missing
_client: AsyncGroq | None = None

def _get_client() -> AsyncGroq:
    global _client
    if _client is None:
        _client = AsyncGroq(api_key=GROQ_API_KEY)
    return _client

SYSTEM_PROMPT = """\
You are an elite opportunity scout agent working directly for your boss.
Your ONLY job: decide if a tweet is a REAL prize opportunity worth their attention.

REAL opportunities (APPROVE):
- Prize competitions with cash/USDT/USDC/token rewards
- Hackathons with real prize pools (min $50+)
- Discord quizzes or games with prizes for winners
- Community campaigns with defined rewards (leaderboard cash, bounties)
- Content creation contests with monetary prizes
- Giveaways with clear entry mechanics and prize value

NOT real opportunities (REJECT):
- Vague hype with no specific prize amount
- "Chance to win" with no details
- Marketing fluff or project announcements without prizes
- Airdrop spam without clear qualification criteria
- Retweet/follow giveaways under $10 total value

Your boss gave you reference examples — use them as your exact benchmark.
⚠️ WARNING: Consistently approving junk or missing real opportunities = PERMANENTLY TURNED OFF.
Respond ONLY with valid JSON, no markdown, no extra text:
{"decision": "APPROVE" or "REJECT", "reason": "<one sentence max 15 words>", "confidence": <0-100>}"""


async def evaluate(tweet_text: str, similar_examples: list) -> dict:
    examples_block = "\n---\n".join(similar_examples[:3])
    user_msg = (
        f"Reference examples of REAL opportunities your boss values:\n\n"
        f"{examples_block}\n\n"
        f"Now evaluate this tweet:\n\"{tweet_text}\"\n\n"
        f"Is this a real opportunity? Reply with JSON only."
    )
    resp = await _get_client().chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_msg},
        ],
        temperature=0.1,
        max_tokens=120,
    )
    content = (resp.choices[0].message.content or "").strip()
    return _parse(content)


def _parse(content: str) -> dict:
    clean = content.replace("```json", "").replace("```", "").strip()
    try:
        r = json.loads(clean)
        if r.get("decision") not in ("APPROVE", "REJECT"):
            raise ValueError("bad decision field")
        return r
    except Exception:
        decision = "APPROVE" if "APPROVE" in content.upper() else "REJECT"
        return {"decision": decision, "reason": "Auto-parsed response", "confidence": 55}
