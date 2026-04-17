"""
Signal notifier (Telegram).

Best-effort, deduped in-memory.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple
import time
import logging

from config import get_settings
from database import AsyncSessionLocal, User
from telegram_client import send_telegram_message

logger = logging.getLogger(__name__)

# Dedup cache: {key: ts}
_sent: Dict[str, float] = {}
_SENT_TTL_SEC = 120.0


def _cleanup_sent(now: float) -> None:
    dead = [k for k, ts in _sent.items() if now - ts > _SENT_TTL_SEC]
    for k in dead:
        _sent.pop(k, None)


def _parse_segments_csv(raw: str) -> Set[str]:
    out: Set[str] = set()
    for part in (raw or "").split(","):
        p = part.strip().upper()
        if p:
            out.add(p)
    return out


def _parse_telegram_chat_ids_csv(raw: str) -> List[str]:
    out: List[str] = []
    for part in (raw or "").split(","):
        p = part.strip()
        if p:
            out.append(p)
    return out


def _format_signal_text(signal: Dict[str, Any]) -> str:
    seg = signal.get("segment")
    phase = signal.get("phase")
    conf = signal.get("confidence")
    ev = signal.get("ev")
    rr = signal.get("range_remaining")
    return (
        "Crazy Brain – Segnale\n"
        f"Segmento: {seg}\n"
        f"Fase: {phase}\n"
        f"Confidence: {conf}\n"
        f"EV: {ev}\n"
        f"Range restante: {rr}\n"
    )


async def notify_hot_signals(hot_signals: List[Dict[str, Any]], source: str = "public") -> None:
    settings = get_settings()
    if not settings.NOTIFY_SIGNALS_ENABLED:
        return
    if not settings.TELEGRAM_BOT_TOKEN:
        return

    if not hot_signals:
        return

    now = time.time()
    _cleanup_sent(now)

    # Per-user notify: choose first hot signal that matches user prefs.
    async with AsyncSessionLocal() as db:
        users = (await db.execute(
            User.__table__.select().where(
                User.telegram_chat_id.is_not(None),
                User.notify_enabled == True,
                User.is_active == True,
            )
        )).mappings().all()

    # (chat_id, allowed_segments empty set = tutti i segmenti, dedup_label)
    targets: List[Tuple[str, Set[str], str]] = []
    seen_chat: Set[str] = set()
    for u in users:
        chat_id = str(u.get("telegram_chat_id") or "")
        if not chat_id or chat_id in seen_chat:
            continue
        seen_chat.add(chat_id)
        allowed = _parse_segments_csv(u.get("notify_segments") or "")
        targets.append((chat_id, allowed, f"u{u.get('id')}"))

    broadcast_allowed = _parse_segments_csv(settings.NOTIFY_BROADCAST_SEGMENTS or "")
    for cid in _parse_telegram_chat_ids_csv(settings.TELEGRAM_CHAT_IDS):
        if cid in seen_chat:
            continue
        seen_chat.add(cid)
        targets.append((cid, broadcast_allowed, f"env:{cid}"))

    if not targets:
        return

    min_conf = float(settings.NOTIFY_MIN_CONFIDENCE or 0.0)

    for chat_id, allowed, who in targets:
        picked: Optional[Dict[str, Any]] = None
        for s in hot_signals:
            seg = str(s.get("segment") or "").upper()
            if allowed and seg not in allowed:
                continue
            picked = s
            break
        if not picked:
            continue

        try:
            conf = float(picked.get("confidence") or 0.0)
        except Exception:
            conf = 0.0
        if conf < min_conf:
            continue

        seg = str(picked.get("segment") or "")
        phase = str(picked.get("phase") or "")
        dedup_key = f"{source}:{who}:{seg}:{phase}:{round(conf, 3)}"
        if dedup_key in _sent:
            continue
        _sent[dedup_key] = now

        text = _format_signal_text(picked)
        try:
            await send_telegram_message(settings.TELEGRAM_BOT_TOKEN, chat_id, text)
        except Exception:
            logger.exception("Failed to notify telegram chat_id=%s who=%s", chat_id, who)

