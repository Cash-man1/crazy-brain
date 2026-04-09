"""
Tiny Telegram client helper.
"""

from __future__ import annotations

import httpx


async def send_telegram_message(bot_token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(url, json=payload)
        if r.status_code >= 400:
            raise RuntimeError(f"Telegram error {r.status_code}: {r.text[:200]}")

