from __future__ import annotations

import asyncio
import json
import re
import subprocess
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

CRAZY_TIME_URL = "https://www.casino.org/casinoscores/it/crazy-time/"
DEFAULT_SCREENSHOT_DIR = Path(__file__).resolve().parent / "screenshots"

# Split-screen defaults (Monitor 1)
DEFAULT_WINDOW_POSITION = (0, 0)
DEFAULT_WINDOW_SIZE = (960, 1040)

WORKER_PATH = Path(__file__).resolve().parent / "scrape_worker.py"


def normalize_segment(text: str) -> Optional[str]:
    t = (text or "").lower()
    if "cash hunt" in t:
        return "CH"
    if "coin flip" in t:
        return "CF"
    if "pachinko" in t:
        return "PA"
    if "crazy time" in t:
        return "CT"
    # support "2x" / "2 x" and plain numbers
    m = re.search(r"\b(10|5|2|1)\s*x?\b", t)
    return m.group(1) if m else None


def _is_label_only_text(value: str) -> bool:
    t = (value or "").strip().lower()
    return t in {"risultato top slot", "risultato slot", "esito", "moltip.", "moltip", "alle ore"}


@dataclass
class ScrapedRow:
    datetime_text: str
    time: str
    slot_result: str
    wheel_result: str
    multipliers: List[int]

    def to_dict(self) -> Dict[str, Any]:
        seg = normalize_segment(self.wheel_result) or normalize_segment(self.slot_result) or ""
        return {
            "datetime_text": self.datetime_text,
            "time": self.time,
            "segment": seg,
            "slot_result": seg or self.slot_result,
            "wheel_result": seg or self.wheel_result,
            "top_slot_multipliers": self.multipliers,
        }

    def dedupe_key(self) -> str:
        mult = ",".join(str(x) for x in (self.multipliers or []))
        return "|".join(
            [
                (self.datetime_text or "").strip().lower(),
                (self.slot_result or "").strip().lower(),
                (self.wheel_result or "").strip().lower(),
                mult,
            ]
        )


class CasinoScoresScraper:
    """
    Scraper tabella "Cronologia Giocate".

    Importante (Windows): Playwright async può fallire con `NotImplementedError` (subprocess su event loop).
    Qui usiamo Playwright sync dentro `asyncio.to_thread()` così funziona sempre.
    """

    def __init__(self):
        self._lock = asyncio.Lock()
        self.last_error: Optional[str] = None
        self.last_rows_count: int = 0
        self.last_screenshot: Optional[str] = None

    def _scrape_via_worker(self, limit: int) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        if not WORKER_PATH.exists():
            raise FileNotFoundError(f"Missing worker: {WORKER_PATH}")

        cmd = [
            sys.executable,
            str(WORKER_PATH),
            "--limit",
            str(limit),
            "--screenshot-prefix",
            "cronologia",
            "--x",
            "0",
            "--y",
            "0",
            "--w",
            str(DEFAULT_WINDOW_SIZE[0]),
            "--h",
            str(DEFAULT_WINDOW_SIZE[1]),
        ]
        # Worker prints JSON to stdout
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=70)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"Worker failed rc={proc.returncode}")
        payload = json.loads(proc.stdout)
        return payload.get("rows") or [], payload.get("screenshot")

    async def scrape_latest_rows(self, limit: int = 20) -> List[Dict[str, Any]]:
        async with self._lock:
            try:
                extracted, shot = await asyncio.to_thread(self._scrape_via_worker, limit)
                self.last_screenshot = shot
            except Exception as exc:
                self.last_error = (
                    f"Playwright scrape failed: {type(exc).__name__}: {repr(exc)}\n"
                    f"{traceback.format_exc()}"
                )
                return []

            rows: List[ScrapedRow] = []
            for r in extracted:
                datetime_text = (r.get("datetime_text") or "").strip()
                time = (r.get("time") or "").strip()
                slot_text = (r.get("slot_result") or "").strip()
                wheel_text = (r.get("wheel_result") or "").strip()
                multipliers = r.get("top_slot_multipliers") or []

                if not time:
                    continue
                if _is_label_only_text(slot_text) or "top slot" in slot_text.lower():
                    continue

                rows.append(
                    ScrapedRow(
                        datetime_text=datetime_text or time,
                        time=time,
                        slot_result=slot_text,
                        wheel_result=wheel_text,
                        multipliers=multipliers,
                    )
                )

            unique: List[ScrapedRow] = []
            seen: set[str] = set()
            for rr in rows:
                k = rr.dedupe_key()
                if k in seen:
                    continue
                seen.add(k)
                unique.append(rr)

            self.last_rows_count = len(unique)
            self.last_error = None if unique else (self.last_error or "No rows found in table")
            return [r.to_dict() for r in unique][:limit]


scraper = CasinoScoresScraper()

