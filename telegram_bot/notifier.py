"""
Telegram notifier — sends approved opportunities and system status
to the user's existing bot / chat.
"""
import httpx
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"


async def _send(text: str, parse_mode: str = "Markdown"):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[TELEGRAM] Token/ChatID not set. Message:\n{text}")
        return
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            await client.post(
                f"{_BASE}/sendMessage",
                json={
                    "chat_id":                  TELEGRAM_CHAT_ID,
                    "text":                     text,
                    "parse_mode":               parse_mode,
                    "disable_web_page_preview": False,
                },
            )
        except Exception as e:
            print(f"[TELEGRAM] Send error: {e}")


async def send_opportunity(tweet_text: str, tweet_url: str,
                           sim_score: float, eval_reason: str,
                           check_reason: str, confidence: float):
    """Nicely formatted opportunity card sent to Telegram."""
    filled = int(sim_score * 10)
    bar    = "🟢" * filled + "⚪" * (10 - filled)

    msg = (
        f"🚨 *NEW OPPORTUNITY FOUND*\n\n"
        f"{_escape(tweet_text[:900])}\n\n"
        f"🔗 [View on X]({tweet_url})\n\n"
        f"📊 *Match Score:* {bar}  `{sim_score:.0%}`\n"
        f"🤖 *Evaluator:* {_escape(eval_reason)}\n"
        f"✅ *Checker:*   {_escape(check_reason)}\n"
        f"💪 *Confidence:* `{confidence:.0f}%`"
    )
    await _send(msg)


async def send_status_update(message: str):
    await _send(f"⚙️ *System Update*\n\n{message}")


def _escape(text: str) -> str:
    """Minimal Markdown escape for user-sourced text."""
    for ch in ("_", "*", "[", "`"):
        text = text.replace(ch, f"\\{ch}")
    return text
