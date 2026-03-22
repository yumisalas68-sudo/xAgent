"""
Tiebreaker Agent — Final arbitrator when Evaluator and Checker disagree.
Uses OpenRouter nvidia/nemotron-3-super-120b-a12b:free (correct model ID).
⚠️  Nemotron is a reasoning model — content field can be null.
    We fall back to the 'reasoning' field and then to Groq as last resort.
"""
import json
import httpx
from groq import AsyncGroq
from config import OPENROUTER_API_KEY, GROQ_API_KEY, TIEBREAKER_MODEL

OR_HEADERS = {
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

# Lazy Groq fallback client
_groq: AsyncGroq | None = None
def _get_groq() -> AsyncGroq:
    global _groq
    if _groq is None:
        _groq = AsyncGroq(api_key=GROQ_API_KEY)
    return _groq


def _extract_content(resp_json: dict) -> str:
    """Extract text content from OpenRouter response.
    Nemotron (reasoning model) sometimes returns null content — fall back to reasoning field."""
    try:
        msg = resp_json["choices"][0]["message"]
        content = msg.get("content") or msg.get("reasoning") or ""
        return content.strip()
    except (KeyError, IndexError, TypeError):
        return ""


async def tiebreak(tweet_text: str, eval_res: dict, check_res: dict, similar_examples: list) -> dict:
    examples_block = "\n---\n".join(similar_examples[:2])
    user_msg = (
        f"Reference examples:\n\n{examples_block}\n\n"
        f"Tweet: \"{tweet_text}\"\n\n"
        f"Agent 1 (Evaluator): {eval_res['decision']} — {eval_res.get('reason', '')}\n"
        f"Agent 2 (Checker): {check_res['decision']} — {check_res.get('reason', '')}\n\n"
        f"They disagree. Your final verdict? Reply with JSON only."
    )
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_msg},
    ]

    # Try OpenRouter (Nemotron) first
    try:
        async with httpx.AsyncClient(timeout=40) as client:
            r = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=OR_HEADERS,
                json={"model": TIEBREAKER_MODEL, "messages": messages,
                      "temperature": 0.1, "max_tokens": 150},
            )
            if r.is_success:
                content = _extract_content(r.json())
                if content:
                    return _parse(content)
                print(f"[TIEBREAKER] Nemotron returned empty content — falling back to Groq")
            else:
                print(f"[TIEBREAKER] OpenRouter {r.status_code}: {r.text[:300]}")
    except Exception as e:
        print(f"[TIEBREAKER] OpenRouter error: {e} — falling back to Groq")

    # Fallback: Groq llama-3.1-8b-instant (different from evaluator to keep independence)
    resp = await _get_groq().chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=messages,
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
