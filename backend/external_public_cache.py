"""
Cache opzionale per il payload di /brain/auto-brain-public su Redis esterno.

- Se REDIS_URL è impostato: il JSON grande vive su Redis (meno RSS sul dyno Render).
- Se assente o errore Redis: fallback in-process (come prima).

Il BrainEngine e auto_state restano in RAM (stato di calcolo); spostarli richiederebbe redesign.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

KEY = "crazybrain:public_auto_brain:v1"
TTL_SECONDS = 300

_memory: Dict[str, Any] = {"ts": 0.0, "payload": None}
_redis = None  # lazy: Redis client, False = disabled, None = not yet tried


def _client():
    global _redis
    if _redis is False:
        return None
    if _redis is not None:
        return _redis
    from config import get_settings

    url = (get_settings().REDIS_URL or "").strip()
    if not url:
        _redis = False
        return None
    try:
        import redis as redis_lib

        c = redis_lib.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=2.5,
            socket_timeout=2.5,
        )
        c.ping()
        _redis = c
        logger.info("Redis public cache attivo")
        return c
    except Exception as exc:
        logger.warning("Redis non disponibile, uso cache in-process: %s", exc)
        _redis = False
        return None


def public_cache_load() -> Tuple[Optional[Dict[str, Any]], float]:
    r = _client()
    if r:
        try:
            raw = r.get(KEY)
            if raw:
                data = json.loads(raw)
                return data.get("payload"), float(data.get("ts") or 0.0)
        except Exception as exc:
            logger.debug("Lettura Redis cache fallita: %s", exc)
    p = _memory.get("payload")
    ts = float(_memory.get("ts") or 0.0)
    return p, ts


def public_cache_store(payload: Optional[Dict[str, Any]], ts: Optional[float] = None) -> None:
    t = time.time() if ts is None else float(ts)
    r = _client()
    if r:
        try:
            r.set(KEY, json.dumps({"payload": payload, "ts": t}, default=str), ex=TTL_SECONDS)
            _memory["payload"] = None
            _memory["ts"] = t
            return
        except Exception as exc:
            logger.debug("Scrittura Redis cache fallita: %s", exc)
    _memory["payload"] = payload
    _memory["ts"] = t
