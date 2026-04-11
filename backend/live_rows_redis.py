"""
Buffer opzionale in Redis: un processo worker scrive le righe Evolution JSON;
il web service le legge senza rifare httpx (e senza Playwright).

Env: REDIS_URL (obbligatorio per worker e lettura), LIVE_ROWS_FROM_REDIS=1 sul web.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

LIVE_ROWS_REDIS_KEY = os.getenv("LIVE_ROWS_REDIS_KEY", "crazybrain:live_rows_json:v1")
DEFAULT_TTL = int(os.getenv("LIVE_ROWS_REDIS_TTL", "60"))

_redis = None  # type: ignore


def _client():
    global _redis
    if _redis is False:
        return None
    if _redis is not None:
        return _redis
    url = (os.getenv("REDIS_URL") or "").strip()
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
        logger.info("Redis live rows client OK")
        return c
    except Exception as exc:
        logger.warning("Redis live rows non disponibile: %s", exc)
        _redis = False
        return None


def push_live_rows(rows: List[Dict[str, Any]]) -> bool:
    """Serializza e pubblica le righe (lista di dict JSON-safe)."""
    c = _client()
    if not c:
        return False
    ttl = int(os.getenv("LIVE_ROWS_REDIS_TTL", str(DEFAULT_TTL)))
    try:
        c.set(LIVE_ROWS_REDIS_KEY, json.dumps(rows, default=str), ex=max(15, ttl))
        return True
    except Exception as exc:
        logger.exception("push_live_rows fallito: %s", exc)
        return False


def try_load_live_rows() -> Optional[List[Dict[str, Any]]]:
    c = _client()
    if not c:
        return None
    try:
        raw = c.get(LIVE_ROWS_REDIS_KEY)
        if not raw:
            return None
        data = json.loads(raw)
        if not isinstance(data, list):
            return None
        out: List[Dict[str, Any]] = []
        for x in data:
            if isinstance(x, dict):
                out.append(x)
        return out or None
    except Exception as exc:
        logger.debug("try_load_live_rows: %s", exc)
        return None
