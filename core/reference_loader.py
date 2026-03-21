"""
Watches  data/real_opportunities.txt  for changes.
On change it re-embeds every example so similarity search
is always in sync with whatever the user added.

File format:  plain text, entries separated by  ---
"""
import os
import asyncio
from config import REFERENCE_FILE
from core.embedder import embed_many, cosine_sim


class ReferenceStore:
    def __init__(self):
        self.examples:    list[str]        = []
        self.embeddings:  list[list[float]]= []
        self._last_mtime: float            = 0.0
        self._lock = asyncio.Lock()

    # ── public ────────────────────────────────────────────────────────────────

    async def refresh_if_needed(self):
        """Call this on every webhook hit; does nothing if file unchanged."""
        try:
            mtime = os.path.getmtime(REFERENCE_FILE)
        except FileNotFoundError:
            print(f"[REF] ⚠️  {REFERENCE_FILE} not found — creating empty file")
            os.makedirs("data", exist_ok=True)
            open(REFERENCE_FILE, "w").close()
            return

        if mtime == self._last_mtime:
            return

        async with self._lock:
            if mtime == self._last_mtime:   # double-check under lock
                return
            print("[REF] File changed – reloading reference examples…")
            examples = self._parse_file()
            if not examples:
                print("[REF] ⚠️  No examples found in reference file")
                return
            embeddings = await embed_many(examples)
            self.examples   = examples
            self.embeddings = embeddings
            self._last_mtime = mtime
            print(f"[REF] ✅ Loaded {len(examples)} reference examples")

    def top_k(self, tweet_emb: list[float], k: int = 3) -> tuple[float, list[str]]:
        """Returns (best_score, [top_k example texts])"""
        if not self.embeddings:
            return 0.0, []
        scored = sorted(
            ((cosine_sim(tweet_emb, ref_emb), self.examples[i])
             for i, ref_emb in enumerate(self.embeddings)),
            reverse=True
        )
        best_score = scored[0][0]
        top_texts  = [t for _, t in scored[:k]]
        return best_score, top_texts

    # ── private ───────────────────────────────────────────────────────────────

    def _parse_file(self) -> list[str]:
        with open(REFERENCE_FILE, "r", encoding="utf-8") as f:
            raw = f.read()
        return [chunk.strip() for chunk in raw.split("---") if chunk.strip()]


# Singleton used across the whole app
reference_store = ReferenceStore()
