"""
Pipeline — processes each tweet through the agent chain.

Scoring logic (fixed):
  Agents are scored on CORRECTNESS vs final outcome, not on approval rate.
  checker=REJECT + final=REJECT → checker was RIGHT → score goes UP
  checker=APPROVE + final=REJECT → checker was wrong (false alarm) → score goes DOWN
  checker=REJECT + final=APPROVE → checker missed it → score goes DOWN
"""
import asyncio
from core.database import (is_seen, mark_seen, save_opportunity, update_agent,
                            get_approved_tweets, get_all_phrases, save_new_phrase)
from core.embedder import embed_one
from core.reference_loader import reference_store
from agents.evaluator import evaluate
from agents.checker import check
from agents.tiebreaker import tiebreak
from agents.phrase_inventor import invent_phrases
from telegram_bot.notifier import send_opportunity, send_status_update
from config import SIMILARITY_MIN, SIMILARITY_FAST_TRACK, INVENT_PHRASES_EVERY_N_APPROVALS

_approvals_since_invention = 0


async def process_tweet(tweet_id: str, tweet_text: str, tweet_url: str):
    global _approvals_since_invention

    # ── Dedup ─────────────────────────────────────────────────────────────────
    if is_seen(tweet_id):
        return
    mark_seen(tweet_id)

    # ── Refresh reference store if file changed ────────────────────────────────
    await reference_store.refresh_if_needed()

    # ── Embed tweet ────────────────────────────────────────────────────────────
    try:
        tweet_emb = await embed_one(str(tweet_text))
    except Exception as e:
        print(f"[PIPELINE] Embed error {tweet_id}: {e}")
        return

    # ── Similarity filter ──────────────────────────────────────────────────────
    sim_score, similar_examples = reference_store.top_k(tweet_emb)
    if sim_score < SIMILARITY_MIN:
        return

    print(f"[PIPELINE] Tweet {tweet_id} | sim={sim_score:.2f} | passed filter")

    # ── Evaluator (Groq llama-3.3-70b) ────────────────────────────────────────
    try:
        eval_res = await evaluate(str(tweet_text), similar_examples)
    except Exception as e:
        print(f"[PIPELINE] Evaluator error {tweet_id}: {e}")
        return

    update_agent("nemotron_evaluator", approved=(eval_res["decision"] == "APPROVE"))

    # Evaluator rejected — log and exit early (no Telegram)
    if eval_res["decision"] == "REJECT":
        save_opportunity(tweet_id, str(tweet_text), str(tweet_url), sim_score,
                         eval_res["decision"], str(eval_res.get("reason") or ""),
                         "N/A", "REJECT")
        return

    # ── Checker (Groq llama-3.1-8b) ───────────────────────────────────────────
    try:
        check_res = await check(str(tweet_text), eval_res, similar_examples)
    except Exception as e:
        print(f"[PIPELINE] Checker error {tweet_id}: {e}")
        check_res = {"decision": "APPROVE", "reason": "Checker unavailable", "confidence": 50}

    # ── Consensus ─────────────────────────────────────────────────────────────
    if eval_res["decision"] == "APPROVE" and check_res["decision"] == "APPROVE":
        final = "APPROVE"

    elif eval_res["decision"] == "APPROVE" and check_res["decision"] == "REJECT":
        # High similarity → trust evaluator even without checker agreement
        if sim_score >= SIMILARITY_FAST_TRACK:
            final = "APPROVE"
        else:
            # Tiebreaker (Nemotron/Groq fallback)
            try:
                tb = await tiebreak(str(tweet_text), eval_res, check_res, similar_examples)
                final = tb["decision"]
                # NOTE: Tiebreaker IS the final decision — there is no ground truth
                # to compare it against in real-time, so we don't score it here.
                # It will only be scored when user feedback is added later.
            except Exception as e:
                print(f"[PIPELINE] Tiebreaker error {tweet_id}: {e}")
                final = "REJECT"
    else:
        final = "REJECT"

    # ── Score checker on CORRECTNESS (not just approval rate) ────────────────
    # Checker is correct when its decision matches the final outcome.
    checker_correct   = (check_res["decision"] == final)
    checker_false_alarm = (check_res["decision"] == "APPROVE" and final == "REJECT")
    update_agent("groq_checker", approved=checker_correct, false_alarm=checker_false_alarm)

    # ── Persist ───────────────────────────────────────────────────────────────
    save_opportunity(
        tweet_id, str(tweet_text), str(tweet_url), sim_score,
        eval_res["decision"], str(eval_res.get("reason") or ""),
        check_res["decision"], final,
    )

    # ── Notify ────────────────────────────────────────────────────────────────
    if final == "APPROVE":
        avg_conf = (eval_res.get("confidence", 70) + check_res.get("confidence", 70)) / 2
        try:
            await send_opportunity(
                str(tweet_text), str(tweet_url), sim_score,
                str(eval_res.get("reason") or ""),
                str(check_res.get("reason") or ""),
                avg_conf,
            )
        except Exception as e:
            print(f"[PIPELINE] Telegram error {tweet_id}: {e}")

        _approvals_since_invention += 1
        if _approvals_since_invention >= INVENT_PHRASES_EVERY_N_APPROVALS:
            _approvals_since_invention = 0
            asyncio.create_task(_invent())


async def _invent():
    try:
        approved = get_approved_tweets(20)
        existing = get_all_phrases()
        if not approved:
            return
        new_phrases = await invent_phrases(approved, existing)
        for p in new_phrases:
            save_new_phrase(p)
        if new_phrases:
            await send_status_update(
                f"💡 *Phrase Inventor* generated {len(new_phrases)} new phrases:\n"
                + "\n".join(f"• `{p}`" for p in new_phrases))
    except Exception as e:
        print(f"[INVENTOR] Error: {e}")
