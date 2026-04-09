"""
OTP sender (best-effort).

Production: configure an external SMS provider.
For now:
- via Telegram (free) if bot token is configured and phone is linked.
"""

from typing import Optional
import logging

from config import get_settings
from database import AsyncSessionLocal, PhoneTelegramLink
from telegram_client import send_telegram_message

logger = logging.getLogger(__name__)


async def maybe_send_otp(phone_number: str, code: str) -> None:
    """
    Best-effort send.
    Free solution: send OTP via Telegram if phone is linked.
    """
    settings = get_settings()
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN not set; cannot send OTP (phone=%s)", phone_number)
        return

    try:
        async with AsyncSessionLocal() as db:
            res = await db.execute(
                PhoneTelegramLink.__table__.select().where(PhoneTelegramLink.phone_number == phone_number)
            )
            row = res.mappings().first()
        if not row:
            logger.warning("Phone not linked to Telegram; cannot send OTP (phone=%s)", phone_number)
            return
        chat_id = str(row.get("telegram_chat_id") or "")
        if not chat_id:
            return
        text = f"Il tuo codice OTP Crazy Brain è: {code}\nScade tra 5 minuti."
        await send_telegram_message(settings.TELEGRAM_BOT_TOKEN, chat_id, text)
    except Exception:
        logger.exception("Failed sending OTP via Telegram (phone=%s)", phone_number)
        return

