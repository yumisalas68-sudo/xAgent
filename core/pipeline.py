"""
Full processing pipeline for a single incoming tweet.

Steps
──────
1. Dedup check             → skip if already seen
2. Reference store refresh → reload if file changed
3. Embed tweet             → vector
4. Similarity filter       → discard below SIMILARITY_MIN (no LLM)
5. Primary eval            → Nemotron FREE
6. Cross-check             → Groq llama FREE
7. Tiebreaker (if needed)  → Mistral Small (paid, rare)
8. Save + notify Telegram
"""
import asyncio
from core.database      import (is_seen, mark_seen, save_opportunity,
                                 update_agent, get_approved_tweets,
                                 get_all_phrases, save_new_phrase, get_stats)
from core.embedder      import embed_one
from core.reference_loader import reference_store
from agents.evaluator   import evaluate
from agents.checker     import check
from agents.tiebreaker  import tiebreak
from agents.phrase_inventor import invent_phrases
from telegram_bot.notifier  import send_opportunity, send_status_update
from config import (SIMILARITY_MIN, SIMILARITY_FAST_TRACK,
                    INVENT_PHRASES_EVERY_N_APPROVALS)


# Track approvals for phrase-invention trigger
_approvals_since_invention = 0


async def process_tweet(tweet_id: str, tweet_text: str, tweet_url: str):
    global _approvals_since_invention

    # ── 1. Dedup ──────────────────────────────────────────────────────────────
    if is_seen(tweet_id):
        return
    mark_seen(tweet_id)

    # ── 2. Reference store ────────────────────────────────────────────────────
    await reference_store.refresh_if_needed()

    # ── 3. Embed ──────────────────────────────────────────────────────────────
    try:
        tweet_emb = await embed_one(tweet_text)
    except Exception as e:
        print(f"[PIPELINE] Embed error for {tweet_id}: {e}")
        return

    # ── 4. Similarity filter ──────────────────────────────────────────────────
    sim_score, similar_examples = reference_store.top_k(tweet_emb)

    if sim_score < SIMILARITY_MIN:
        return   # silent discard – not remotely relevant

    print(f"[PIPELINE] Tweet {tweet_id} | sim={sim_score:.2f} | passed filter")

    # ── 5. Primary eval (Nemotron free) ───────────────────────────────────────
    try:
        eval_res = await evaluate(tweet_text, similar_examples)
    except Exception as e:
        print(f"[PIPELINE] Evaluator error: {e}")
        return

    update_agent("nemotron_evaluator",
                 approved=eval_res["decision"] == "APPROVE")

    if eval_res["decision"] == "REJECT":
        _log(tweet_id, tweet_text, tweet_url, sim_score,
             eval_res, {"decision": "N/A", "reason": "skipped"}, "REJECT")
        return

    # ── 6. Cross-check (Groq free) ────────────────────────────────────────────
    try:
        check_res = await check(tweet_text, eval_res, similar_examples)
    except Exception as e:
        print(f"[PIPELINE] Checker error: {e}")
        check_res = {"decision": "APPROVE", "reason": "Checker unavailable", "confidence": 50}

    # ── 7. Determine final decision ───────────────────────────────────────────
    if eval_res["decision"] == "APPROVE" and check_res["decision"] == "APPROVE":
        final = "APPROVE"
    elif eval_res["decision"] == "APPROVE" and check_res["decision"] == "REJECT":
        if sim_score >= SIMILARITY_FAST_TRACK:
            final = "APPROVE"   # high similarity → trust eval
        else:
            # Disagreement + borderline similarity → call tiebreaker
            try:
                tb_res = await tiebreak(tweet_text, eval_res, check_res, similar_examples)
                final  = tb_res["decision"]
                update_agent("mistral_tiebreaker", approved=(final == "APPROVE"))
            except Exception as e:
                print(f"[PIPELINE] Tiebreaker error: {e}")
                final = "REJECT"
    else:
        final = "REJECT"

    # ── 8. Update checker score ───────────────────────────────────────────────
    false_alarm = check_res["decision"] == "APPROVE" and final == "REJECT"
    update_agent("groq_checker",
                 approved=check_res["decision"] == "APPROVE",
                 false_alarm=false_alarm)

    # ── 9. Save to DB ─────────────────────────────────────────────────────────
    _log(tweet_id, tweet_text, tweet_url, sim_score,
         eval_res, check_res, final)

    # ── 10. Notify ────────────────────────────────────────────────────────────
    if final == "APPROVE":
        avg_conf = (eval_res.get("confidence", 70) + check_res.get("confidence", 70)) / 2
        await send_opportunity(
            tweet_text    = tweet_text,
            tweet_url     = tweet_url,
            sim_score     = sim_score,
            eval_reason   = eval_res.get("reason", ""),
            check_reason  = check_res.get("reason", ""),
            confidence    = avg_conf,
        )

        _approvals_since_invention += 1

        # ── 11. Phrase invention trigger ──────────────────────────────────────
        if _approvals_since_invention >= INVENT_PHRASES_EVERY_N_APPROVALS:
            _approvals_since_invention = 0
            asyncio.create_task(_run_phrase_inventor())


def _log(tweet_id, tweet_text, tweet_url, sim_score, eval_res, check_res, final):
    save_opportunity(
        tweet_id        = tweet_id,
        tweet_text      = tweet_text,
        tweet_url       = tweet_url,
        similarity_score= sim_score,
        eval_decision   = eval_res["decision"],
        eval_reason     = eval_res.get("reason", ""),
        checker_decision= check_res["decision"],
        final_decision  = final,
    )


async def _run_phrase_inventor():
    """Background task: invent new search phrases from approved tweets."""
    try:
        approved_tweets  = get_approved_tweets(limit=20)
        existing_phrases = get_all_phrases()
        if not approved_tweets:
            return
        new_phrases = await invent_phrases(approved_tweets, existing_phrases)
        for phrase in new_phrases:
            save_new_phrase(phrase)
        if new_phrases:
            await send_status_update(
                f"💡 *Phrase Inventor* generated {len(new_phrases)} new search phrases:\n"
                + "\n".join(f"• `{p}`" for p in new_phrases)
            )
            print(f"[INVENTOR] New phrases: {new_phrases}")
    except Exception as e:
        print(f"[INVENTOR] Error: {e}")
