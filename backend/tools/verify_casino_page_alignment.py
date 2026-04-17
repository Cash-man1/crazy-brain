#!/usr/bin/env python3
"""
Verifica pratica: allineamento tra dati letti dalla pagina casino.org (Playwright worker)
e dati normalizzati che Crazy Brain usa nel brain pipeline.

Uso:
  cd backend
  python tools/verify_casino_page_alignment.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from api_brain import _clean_rows, _run_scrape_worker_fresh  # noqa: E402


def _fmt_mult(r: Dict[str, Any]) -> str:
    m = r.get("final_multiplier")
    return str(m) if m is not None else "-"


def main() -> int:
    # Forza test della pagina HTML via worker Playwright.
    os.environ["SCRAPER_USE_EVOLUTION_API"] = "0"
    os.environ["SCRAPER_PLAYWRIGHT_FALLBACK"] = "1"

    payload = _run_scrape_worker_fresh(limit=20)
    source_rows = payload.get("rows") or []
    clean_rows = _clean_rows(source_rows)

    n = min(len(source_rows), len(clean_rows), 20)
    if n == 0:
        print("ERRORE: nessuna riga letta dalla pagina casino.org")
        dbg = str(payload.get("_worker_debug") or "").strip()
        if dbg:
            print("worker_debug:", dbg)
        return 1

    print("=" * 120)
    print(f"CASINO PAGE -> CRAZY BRAIN | confronto prime {n} righe")
    print("=" * 120)
    print(
        f"{'#':<3} {'time(source)':<12} {'time(system)':<12} "
        f"{'slot(source)':<20} {'slot(system)':<20} "
        f"{'wheel(source)':<18} {'wheel(system)':<18} {'mult(system)':<12} {'OK':<4}"
    )
    print("-" * 120)

    mismatches = 0
    for i in range(n):
        src = source_rows[i]
        sysr = clean_rows[i]
        ok = (
            str(src.get("time") or "") == str(sysr.get("time") or "")
            and str(src.get("slot_result") or "") == str(sysr.get("slot_result") or "")
            and str(src.get("wheel_result") or "") == str(sysr.get("wheel_result") or "")
        )
        if not ok:
            mismatches += 1
        print(
            f"{i+1:<3} {str(src.get('time') or '')[:10]:<12} {str(sysr.get('time') or '')[:10]:<12} "
            f"{str(src.get('slot_result') or '')[:18]:<20} {str(sysr.get('slot_result') or '')[:18]:<20} "
            f"{str(src.get('wheel_result') or '')[:16]:<18} {str(sysr.get('wheel_result') or '')[:16]:<18} "
            f"{_fmt_mult(sysr):<12} {('OK' if ok else 'NO'):<4}"
        )

    print("-" * 120)
    print(f"Righe confrontate: {n} | mismatch base fields (time/slot/wheel): {mismatches}")
    dbg = str(payload.get("_worker_debug") or "").strip()
    if dbg:
        print("worker_debug:", dbg[:400])
    return 0 if mismatches == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())

