"""
Cross-checker — Groq llama-3.3-70b (FREE tier)
Independently re-evaluates every tweet the primary evaluator approved.
Two agents agreeing = strong signal.
"""
import json
from groq import AsyncGroq
from config import GROQ_API_KEY, CHECKER_GROQ_MODEL

_client = AsyncGroq(api_key=GROQ_API_KEY)

SYSTEM_PROMPT = """\
You are a cross-validation agent. A primary agent has flagged a tweet as a potential opportunity.
Your job: independently verify whether it is genuinely worth your boss's attention.

Real opportunities: prize contests, hackathons, Discord quizzes with prizes, \
community campaigns with cash/token rewards, leaderboard competitions.

⚠️  WARNING: If you consistently validate garbage or dismiss real opportunities, \
you will be PERMANENTLY TURNED OFF.

Respond ONLY with valid JSON — no markdown, no extra text:
{"decision": "APPROVE" or "REJECT", "reason": "<one sentence>", "confidence": <0-100>}
"""


async def check(tweet_text: str, eval_result: dict, similar_examples: list[str]) -> dict:
    examples_block = "\n---\n".join(similar_examples[:2])

    user_msg = (
        f"Reference examples your boss considers real opportunities:\n\n"
        f"{examples_block}\n\n"
        f"Tweet under review:\n\"{tweet_text}\"\n\n"
        f"Primary agent verdict: {eval_result['decision']} — {eval_result.get('reason','')}\n\n"
        f"Give your independent verdict."
    )

    resp = await _client.chat.completions.create(
        model=CHECKER_GROQ_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_msg},
        ],
        temperature=0.1,
        max_tokens=120,
    )
    content = resp.choices[0].message.content.strip()
    return _parse(content)


def _parse(content: str) -> dict:
    clean = content.replace("```json", "").replace("```", "").strip()
    try:
        result = json.loads(clean)
        if result.get("decision") not in ("APPROVE", "REJECT"):
            raise ValueError
        return result
    except Exception:
        decision = "APPROVE" if "APPROVE" in content.upper() else "REJECT"
        return {"decision": decision, "reason": "Auto-parsed", "confidence": 55}
