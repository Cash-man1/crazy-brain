"""
Per-user notifications: Telegram connect + preferences.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
from typing import List, Optional

from config import get_settings
from database import get_db, User, TelegramLinkToken, PhoneTelegramLinkToken, PhoneTelegramLink, get_user_by_id
from security import get_current_user_id, hash_token, generate_secure_token

settings = get_settings()
router = APIRouter(prefix="/notify", tags=["Notifications"])
logger = logging.getLogger(__name__)


class NotifyPrefs(BaseModel):
    enabled: bool = True
    segments: List[str] = Field(default_factory=list)  # empty => all


def _norm_segments(segs: List[str]) -> List[str]:
    out: List[str] = []
    for s in segs or []:
        t = str(s).strip().upper()
        if not t:
            continue
        out.append(t)
    # de-dup preserve order
    return list(dict.fromkeys(out))


@router.get("/telegram/status")
async def telegram_status(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Utente non trovato")
    return {
        "connected": bool(user.telegram_chat_id),
        "notify_enabled": bool(user.notify_enabled),
        "notify_segments": (user.notify_segments or ""),
    }


@router.post("/telegram/connect-link")
async def telegram_connect_link(
    request: Request,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Utente non trovato")

    raw = generate_secure_token(24)
    th = hash_token(raw)
    expires = datetime.utcnow() + timedelta(minutes=20)
    db.add(TelegramLinkToken(user_id=user.id, token_hash=th, expires_at=expires, used=False))
    await db.commit()

    if not settings.TELEGRAM_BOT_USERNAME:
        raise HTTPException(status_code=400, detail="TELEGRAM_BOT_USERNAME non configurato")

    link = f"https://t.me/{settings.TELEGRAM_BOT_USERNAME}?start={raw}"
    return {"connect_url": link, "expires_at": expires.isoformat()}


@router.post("/preferences")
async def set_preferences(
    prefs: NotifyPrefs,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Utente non trovato")
    segs = _norm_segments(prefs.segments)
    user.notify_enabled = bool(prefs.enabled)
    user.notify_segments = ",".join(segs) if segs else ""
    await db.commit()
    return {"ok": True}


@router.post("/telegram/disconnect")
async def telegram_disconnect(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Utente non trovato")
    user.telegram_chat_id = None
    user.notify_enabled = False
    await db.commit()
    return {"ok": True}


class TelegramUpdate(BaseModel):
    update_id: Optional[int] = None
    message: Optional[dict] = None


def _telegram_webhook_secret_ok(request: Request) -> None:
    """
    Telegram invia X-Telegram-Bot-Api-Secret-Token solo se setWebhook è stato chiamato
    con lo stesso secret_token. Molti deploy hanno TELEGRAM_WEBHOOK_SECRET_TOKEN in env
    ma webhook registrato senza secret → 403. Qui: header presente ⇒ deve coincidere sempre;
    header assente ⇒ 403 solo in modalità strict.
    """
    expected = (settings.TELEGRAM_WEBHOOK_SECRET_TOKEN or "").strip()
    if not expected:
        return
    hdr = (request.headers.get("X-Telegram-Bot-Api-Secret-Token") or "").strip()
    if hdr:
        if hdr != expected:
            logger.warning(
                "Telegram webhook: secret header presente ma non coincide con TELEGRAM_WEBHOOK_SECRET_TOKEN"
            )
            raise HTTPException(
                status_code=403,
                detail="telegram_webhook_secret_mismatch",
            )
        return
    if settings.TELEGRAM_WEBHOOK_STRICT_SECRET:
        logger.warning(
            "Telegram webhook: TELEGRAM_WEBHOOK_SECRET_TOKEN è impostato ma manca "
            "X-Telegram-Bot-Api-Secret-Token. Riesegui setWebhook con secret_token uguale "
            "all'env, oppure imposta TELEGRAM_WEBHOOK_STRICT_SECRET=false."
        )
        raise HTTPException(
            status_code=403,
            detail="telegram_webhook_secret_header_missing",
        )
    logger.warning(
        "Telegram webhook: accettato senza header secret (strict disattivo). "
        "Per maggiore sicurezza usa setWebhook con secret_token e TELEGRAM_WEBHOOK_STRICT_SECRET=true."
    )


@router.post("/telegram/webhook")
async def telegram_webhook(
    update: TelegramUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Telegram webhook: user links their chat by sending /start <token>.
    """
    _telegram_webhook_secret_ok(request)

    msg = update.message or {}
    text = str(msg.get("text") or "")
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    if not chat_id:
        return {"ok": True}

    # Expect: /start <token>
    parts = text.strip().split()
    if not parts:
        return {"ok": True}
    if parts[0] != "/start" or len(parts) < 2:
        return {"ok": True}
    raw_token = parts[1].strip()
    if not raw_token:
        return {"ok": True}
    th = hash_token(raw_token)

    # 1) Try authenticated-user link token
    res = await db.execute(select(TelegramLinkToken).where(TelegramLinkToken.token_hash == th))
    tok = res.scalar_one_or_none()
    if tok and tok.is_valid():
        user = await get_user_by_id(db, tok.user_id)
        tok.used = True
        if user:
            user.telegram_chat_id = str(chat_id)
        await db.commit()
        return {"ok": True}

    # 2) Try phone pre-link token
    res2 = await db.execute(select(PhoneTelegramLinkToken).where(PhoneTelegramLinkToken.token_hash == th))
    ptok = res2.scalar_one_or_none()
    if not ptok or not ptok.is_valid():
        return {"ok": True}

    phone = ptok.phone_number
    ptok.used = True

    # upsert mapping
    res3 = await db.execute(select(PhoneTelegramLink).where(PhoneTelegramLink.phone_number == phone))
    link = res3.scalar_one_or_none()
    if link:
        link.telegram_chat_id = str(chat_id)
    else:
        db.add(PhoneTelegramLink(phone_number=phone, telegram_chat_id=str(chat_id)))

    await db.commit()
    return {"ok": True}

