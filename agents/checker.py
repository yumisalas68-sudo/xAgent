"""
Checker Agent — Cross-validation (second opinion).
Uses Groq llama-3.1-8b-instant: fast, free, independent from Evaluator.
"""
import json
from groq import AsyncGroq
from config import GROQ_API_KEY

_client: AsyncGroq | None = None

def _get_client() -> AsyncGroq:
    global _client
    if _client is None:
        _client = AsyncGroq(api_key=GROQ_API_KEY)
    return _client

SYSTEM_PROMPT = """\
You are a cross-validation agent. A primary agent flagged a tweet — verify independently.
A REAL opportunity MUST have: tangible prizes (cash/tokens/USD), a clear participation method.
Do NOT approve vague marketing, hype without prizes, or follow/retweet spam.
⚠️ WARNING: Consistently wrong = PERMANENTLY TURNED OFF.
Respond ONLY with valid JSON, no markdown:
{"decision": "APPROVE" or "REJECT", "reason": "<one sentence max 15 words>", "confidence": <0-100>}"""


async def check(tweet_text: str, eval_result: dict, similar_examples: list) -> dict:
    examples_block = "\n---\n".join(similar_examples[:2])
    user_msg = (
        f"Reference examples:\n\n{examples_block}\n\n"
        f"Tweet: \"{tweet_text}\"\n\n"
        f"Primary agent verdict: {eval_result['decision']} — {eval_result.get('reason', '')}\n\n"
        f"Do you agree? Reply with JSON only."
    )
    resp = await _get_client().chat.completions.create(
        model="llama-3.1-8b-instant",
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
