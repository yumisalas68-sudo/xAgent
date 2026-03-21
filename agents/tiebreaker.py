"""
Tiebreaker — Mistral Small 4  ($0.15 input / $0.60 output per M tokens)
Only called when primary eval says APPROVE but checker says REJECT
AND similarity score is below the fast-track threshold.
This is the rarest, most expensive call — by design it almost never fires.
"""
import json
import httpx
from config import OPENROUTER_API_KEY, TIEBREAKER_MODEL

HEADERS = {
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "Content-Type":  "application/json",
    "HTTP-Referer":  "https://opportunity-hunter",
    "X-Title":       "OpportunityHunter",
}

SYSTEM_PROMPT = """\
You are the final arbitrator. Two agents disagree on whether a tweet is a real opportunity.
Your decision is final and cannot be appealed.

A real opportunity must offer: tangible prizes (cash, tokens, rewards), a clear deadline or \
participation method, and be genuinely actionable by your boss.

Do NOT approve vague hype, marketing fluff, or announcements without prizes.

⚠️  WARNING: Every wrong call counts against you. Bad calls → PERMANENT SHUTDOWN.

Respond ONLY with valid JSON:
{"decision": "APPROVE" or "REJECT", "reason": "<one sentence>", "confidence": <0-100>}
"""


async def tiebreak(tweet_text: str, eval_res: dict, check_res: dict,
                   similar_examples: list[str]) -> dict:
    examples_block = "\n---\n".join(similar_examples[:2])

    user_msg = (
        f"Reference examples your boss values:\n\n{examples_block}\n\n"
        f"Tweet in dispute:\n\"{tweet_text}\"\n\n"
        f"Agent 1 (Evaluator): {eval_res['decision']} — {eval_res.get('reason','')}\n"
        f"Agent 2 (Checker):   {check_res['decision']} — {check_res.get('reason','')}\n\n"
        f"Make the final call."
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
                "max_tokens":  120,
            },
        )
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"].strip()

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
