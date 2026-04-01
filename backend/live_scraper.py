from __future__ import annotations

import asyncio
import re
import traceback
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from playwright.sync_api import sync_playwright


CRAZY_TIME_URL = "https://www.casino.org/casinoscores/it/crazy-time/"


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

    m = re.search(r"\b(10|5|2|1)\b", t)
    return m.group(1) if m else None


def extract_multipliers(text: str) -> List[int]:
    if not text:
        return []
    return [int(x) for x in re.findall(r"\b(\d{1,4})x\b", text.lower())]


def _is_label_only_text(value: str) -> bool:
    t = (value or "").strip().lower()
    labels = {
        "risultato top slot",
        "risultato slot",
        "esito",
        "moltip.",
        "moltip",
        "alle ore",
    }
    return t in labels


@dataclass
class ScrapedRow:
    time: str
    slot_result: str
    wheel_result: str
    multipliers: List[int]

    def to_dict(self) -> Dict[str, Any]:
        seg = normalize_segment(self.wheel_result) or normalize_segment(self.slot_result) or ""
        return {
            "time": self.time,
            "segment": seg,
            "slot_result": seg or self.slot_result,
            "wheel_result": seg or self.wheel_result,
            "top_slot_multipliers": self.multipliers,
        }


class CasinoScoresScraper:
    """
    Browser scraper persistente (1 browser/tab) per leggere la tabella live.
    """

    def __init__(self):
        self._lock = asyncio.Lock()
        self.last_error: Optional[str] = None
        self.last_rows_count: int = 0

    def _scrape_sync(self, limit: int) -> List[Dict[str, Any]]:
        with sync_playwright() as pw:
            try:
                try:
                    browser = pw.chromium.launch(channel="msedge", headless=True)
                except Exception:
                    browser = pw.chromium.launch(headless=True)

                ctx = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
                    viewport={"width": 1280, "height": 720},
                )
                page = ctx.new_page()
                page.goto(CRAZY_TIME_URL, wait_until="domcontentloaded", timeout=60000)

                # Cookie banner spesso blocca interazioni/DOM
                try:
                    accept = page.get_by_role("button", name=re.compile(r"accetta", re.IGNORECASE))
                    if accept.count() > 0:
                        accept.first.click(timeout=3000)
                except Exception:
                    pass

                page.wait_for_timeout(1200)

                extracted: List[Dict[str, Any]] = page.evaluate(
                    """(limit) => {
                      const norm = (s) => (s || '').replace(/\\s+/g,' ').trim();
                      const getMults = (node) => {
                        const text = norm(node?.innerText || '');
                        const mults = [];
                        const re = /(\\d{1,4})\\s*x/gi;
                        let m;
                        while ((m = re.exec(text)) !== null) mults.push(parseInt(m[1], 10));
                        return mults;
                      };

                      const nameFromSrc = (src) => {
                        const s = (src || '').toLowerCase();
                        if (s.includes('cash') && s.includes('hunt')) return 'Cash Hunt';
                        if (s.includes('coin') && s.includes('flip')) return 'Coin Flip';
                        if (s.includes('pachinko')) return 'Pachinko';
                        if (s.includes('crazy') && s.includes('time')) return 'Crazy Time';
                        return '';
                      };

                      const getSlotName = (td) => {
                        if (!td) return '';
                        const img = td.querySelector('img');
                        if (img) {
                          const viaAttr = norm(img.getAttribute('alt') || img.getAttribute('title') || img.getAttribute('aria-label') || '');
                          if (viaAttr) return viaAttr;
                          const viaSrc = nameFromSrc(img.getAttribute('src') || '');
                          if (viaSrc) return viaSrc;
                        }
                        return norm(td.innerText || td.textContent || '');
                      };

                      const pickTable = () => {
                        const tables = Array.from(document.querySelectorAll('table'));
                        for (const t of tables) {
                          const head = norm(t.querySelector('thead')?.innerText || '').toLowerCase();
                          if (head.includes('alle ore') && head.includes('risultato slot') && head.includes('esito') && !head.includes('top slot')) return t;
                        }
                        return null;
                      };

                      const t = pickTable();
                      if (!t) return [];
                      const trs = Array.from(t.querySelectorAll('tbody tr')).slice(0, limit);
                      const out = [];
                      for (const tr of trs) {
                        const tds = tr.querySelectorAll('td');
                        if (tds.length < 3) continue;
                        const timeText = norm(tds[0]?.innerText || '');
                        const timeMatch = timeText.match(/\\b\\d{1,2}:\\d{2}\\b/);
                        if (!timeMatch) continue;
                        const slot = getSlotName(tds[1]);
                        const wheel = getSlotName(tds[2]) || norm(tds[2]?.innerText || tds[2]?.textContent || '');
                        const mults = getMults(tds[3]);
                        if (slot.toLowerCase().includes('risultato top slot')) continue;
                        out.push({ time: timeMatch[0], slot_result: slot, wheel_result: wheel, top_slot_multipliers: mults });
                      }
                      return out;
                    }""",
                    limit,
                )

                browser.close()
                return extracted
            except Exception:
                raise

    async def scrape_latest_rows(self, limit: int = 20) -> List[Dict[str, Any]]:
        async with self._lock:
            try:
                extracted = await asyncio.to_thread(self._scrape_sync, limit)
            except Exception as exc:
                self.last_error = f"Playwright init failed: {type(exc).__name__}: {repr(exc)}"
                return []

            rows: List[ScrapedRow] = []
            for r in extracted:
                time = (r.get("time") or "").strip()
                slot_text = (r.get("slot_result") or "").strip()
                wheel_text = (r.get("wheel_result") or "").strip()
                multipliers = r.get("top_slot_multipliers") or []
                if not time:
                    continue

                # Evita righe della tabella "Top Slot" o righe-label
                if _is_label_only_text(slot_text) or "top slot" in slot_text.lower():
                    continue

                # Segmento valido deve essere presente almeno in una colonna
                seg = normalize_segment(wheel_text) or normalize_segment(slot_text)
                if not seg:
                    continue

                rows.append(
                    ScrapedRow(
                        time=time,
                        slot_result=seg,
                        wheel_result=seg,
                        multipliers=multipliers,
                    )
                )

            self.last_rows_count = len(rows)
            self.last_error = None if rows else (self.last_error or "No rows found in table")
            return [r.to_dict() for r in rows][:limit]


scraper = CasinoScoresScraper()

