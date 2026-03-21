"""
Perplexity Embed 0.6B via OpenRouter  —  $0.004 / M tokens ≈ free
Used to vectorise both reference examples and incoming tweets,
then cosine-similarity filters out noise before any LLM is called.
"""
import httpx
import numpy as np
from config import OPENROUTER_API_KEY, EMBED_MODEL


HEADERS = {
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "Content-Type": "application/json",
    "HTTP-Referer": "https://opportunity-hunter",
    "X-Title": "OpportunityHunter",
}


async def _embed(payload) -> list:
    """Raw embedding call – payload is str or list[str]"""
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            "https://openrouter.ai/api/v1/embeddings",
            headers=HEADERS,
            json={"model": EMBED_MODEL, "input": payload},
        )
        r.raise_for_status()
        data = r.json()
        return [item["embedding"] for item in data["data"]]


async def embed_one(text: str) -> list[float]:
    results = await _embed(text)
    return results[0]


async def embed_many(texts: list[str]) -> list[list[float]]:
    # OpenRouter may cap batch size; chunk if needed
    CHUNK = 64
    all_embeddings = []
    for i in range(0, len(texts), CHUNK):
        batch = texts[i : i + CHUNK]
        all_embeddings.extend(await _embed(batch))
    return all_embeddings


def cosine_sim(a: list[float], b: list[float]) -> float:
    a, b = np.array(a, dtype=np.float32), np.array(b, dtype=np.float32)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / denom) if denom else 0.0
