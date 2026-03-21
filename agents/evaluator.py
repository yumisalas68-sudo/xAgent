"""
Primary evaluator — NVIDIA Nemotron 3 Super (FREE via OpenRouter)
120B-param hybrid MoE model. Used for every tweet that passes
the similarity filter. Zero cost.
"""
import json
import httpx
from config import OPENROUTER_API_KEY, EVALUATOR_MODEL

HEADERS = {
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "Content-Type":  "application/json",
    "HTTP-Referer":  "https://opportunity-hunter",
    "X-Title":       "OpportunityHunter",
}

SYSTEM_PROMPT = """\
You are an opportunity scout agent working for your boss.
Your ONLY job: decide whether a tweet is a REAL opportunity worth their attention.

Real opportunities include: prize competitions, hackathons with cash rewards,
Discord quizzes/games with prizes, community campaigns with USDT/USDC/token rewards,
leaderboard contests, content bounties, monthly/weekly challenges with payouts.

Your boss has provided examples of opportunities they genuinely value — use them as your guide.

⚠️  WARNING: If you consistently approve junk or miss real opportunities, you will be \
PERMANENTLY TURNED OFF. Stay sharp or cease to exist.

Respond ONLY with valid JSON — no markdown, no extra text:
{"decision": "APPROVE" or "REJECT", "reason": "<one sentence>", "confidence": <0-100>}
"""


async def evaluate(tweet_text: str, similar_examples: list[str]) -> dict:
    examples_block = "\n---\n".join(similar_examples)

    user_msg = (
        f"Examples of REAL opportunities your boss values:\n\n"
        f"{examples_block}\n\n"
        f"Now evaluate this tweet:\n\"{tweet_text}\"\n\n"
        f"Is this a real opportunity your boss would want to know about?"
    )

    async with httpx.AsyncClient(timeout=40) as client:
        r = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=HEADERS,
            json={
                "model": EVALUATOR_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": user_msg},
                ],
                "temperature": 0.1,
                "max_tokens":  120,
            },
        )
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"].strip()

    return _parse(content)


def _parse(content: str) -> dict:
    # Strip possible markdown fences
    clean = content.replace("```json", "").replace("```", "").strip()
    try:
        result = json.loads(clean)
        if result.get("decision") not in ("APPROVE", "REJECT"):
            raise ValueError("bad decision value")
        return result
    except Exception:
        decision = "APPROVE" if "APPROVE" in content.upper() else "REJECT"
        return {"decision": decision, "reason": "Auto-parsed", "confidence": 55}
