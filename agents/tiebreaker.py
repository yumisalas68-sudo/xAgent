"""
Tiebreaker Agent — Final arbitrator when Evaluator and Checker disagree.
Uses OpenRouter nvidia/nemotron-3-super-120b-a12b:free (correct model ID).
Only called when Evaluator=APPROVE + Checker=REJECT + sim < FAST_TRACK threshold.
Called rarely — conserves OpenRouter credits.
"""
import json
import httpx
from config import OPENROUTER_API_KEY, TIEBREAKER_MODEL

HEADERS = {
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "Content-Type": "application/json",
    "HTTP-Referer": "https://opportunity-hunter",
    "X-Title": "OpportunityHunter",
}

SYSTEM_PROMPT = """\
You are the final arbitrator. Two agents disagree on a tweet. Your call is final.
A REAL opportunity MUST have: tangible prizes (cash/tokens), clear deadline or participation method.
Do NOT approve vague hype or marketing without defined prizes.
⚠️ WARNING: Wrong calls = PERMANENT SHUTDOWN.
Respond ONLY with valid JSON, no markdown:
{"decision": "APPROVE" or "REJECT", "reason": "<one sentence max 15 words>", "confidence": <0-100>}"""


async def tiebreak(tweet_text: str, eval_res: dict, check_res: dict, similar_examples: list) -> dict:
    examples_block = "\n---\n".join(similar_examples[:2])
    user_msg = (
        f"Reference examples:\n\n{examples_block}\n\n"
        f"Tweet: \"{tweet_text}\"\n\n"
        f"Agent 1 (Evaluator): {eval_res['decision']} — {eval_res.get('reason', '')}\n"
        f"Agent 2 (Checker): {check_res['decision']} — {check_res.get('reason', '')}\n\n"
        f"They disagree. Your final verdict? Reply with JSON only."
    )
    async with httpx.AsyncClient(timeout=40) as client:
        r = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=HEADERS,
            json={
                "model": TIEBREAKER_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": user_msg},
                ],
                "temperature": 0.1,
                "max_tokens": 120,
            },
        )
        if not r.is_success:
            # Log the full error body so we can diagnose future issues
            print(f"[TIEBREAKER] OpenRouter error {r.status_code}: {r.text[:500]}")
            r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"].strip()
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
