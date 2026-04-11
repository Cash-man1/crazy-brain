#!/usr/bin/env python3
"""
Worker standalone: polling Evolution API + scrittura su Redis.
Deploy su Render come Background Worker (stesso repo, Dockerfile.worker).

Nessun Playwright — RAM bassa. Il web service legge con LIVE_ROWS_FROM_REDIS=1.
"""
from __future__ import annotations

import logging
import os
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("live_worker")

POLL = float(os.getenv("LIVE_WORKER_POLL_SECONDS", "4"))
LIMIT = int(os.getenv("LIVE_WORKER_ROW_LIMIT", "50"))


def main() -> None:
    from crazytime_api import fetch_evolution_crazytime_rows
    from live_rows_redis import push_live_rows

    if not (os.getenv("REDIS_URL") or "").strip():
        logger.error("REDIS_URL non impostato: impossibile pubblicare righe")
        raise SystemExit(1)

    logger.info("live worker avviato poll=%ss limit=%s", POLL, LIMIT)
    while True:
        try:
            rows = fetch_evolution_crazytime_rows(limit=LIMIT)
            if rows:
                if push_live_rows(rows):
                    logger.info("pubblicate %s righe su Redis", len(rows))
                else:
                    logger.warning("push Redis fallito")
            else:
                logger.warning("fetch Evolution: 0 righe")
        except Exception:
            logger.exception("ciclo worker")
        time.sleep(max(2.0, POLL))


if __name__ == "__main__":
    main()
