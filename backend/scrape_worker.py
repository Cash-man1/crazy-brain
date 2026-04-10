from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from playwright.sync_api import sync_playwright

CRAZY_TIME_URL = "https://www.casino.org/casinoscores/it/crazy-time/"
DEFAULT_SCREENSHOT_DIR = Path(__file__).resolve().parent / "screenshots"


def _scrape(limit: int, screenshot_prefix: Optional[str], headless: bool, window_pos: Tuple[int, int], window_size: Tuple[int, int]):
    with sync_playwright() as pw:
        def _log(step: str) -> None:
            print(f"[worker] {step}", file=sys.stderr, flush=True)

        started_at = time.monotonic()
        args = [
            "--disable-dev-shm-usage",
            "--no-sandbox",
            f"--window-position={window_pos[0]},{window_pos[1]}",
            f"--window-size={window_size[0]},{window_size[1]}",
        ]

        # Render does not provide Edge channel: use bundled Chromium only.
        _log("browser launch started")
        browser = pw.chromium.launch(headless=True, args=args)
        _log("browser launch finished")

        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
            viewport={"width": window_size[0], "height": window_size[1]},
        )
        page = ctx.new_page()
        _log("page goto started")
        page.goto(CRAZY_TIME_URL, wait_until="networkidle", timeout=45000)
        _log("page goto finished")
        try:
            page.wait_for_selector("table", timeout=20000)
            _log("selector table found")
        except Exception:
            # Keep going: table might still appear after cookie/scroll interactions.
            _log("selector table not found in initial wait")
            pass

        # Cookie banner
        try:
            accept = page.get_by_role("button", name=re.compile(r"accetta", re.IGNORECASE))
            if accept.count() > 0:
                accept.first.click(timeout=3000)
        except Exception:
            pass
        try:
            accept2 = page.get_by_text(re.compile(r"accetta", re.IGNORECASE))
            if accept2.count() > 0:
                accept2.first.click(timeout=2500)
        except Exception:
            pass

        page.wait_for_timeout(4000)
        _log("cookie/banner handling completed")

        def _ensure_cronologia_in_view() -> None:
            try:
                page.get_by_text(re.compile(r"Cronologia\s+Giocate", re.IGNORECASE)).first.scroll_into_view_if_needed(timeout=3000)
            except Exception:
                pass
            try:
                # Force-scroll to the target table (helps with lazy/virtualized rows not being in the DOM).
                page.evaluate(
                    """() => {
                      const norm = (s) => (s || '').replace(/\\s+/g,' ').trim().toLowerCase();
                      const tables = Array.from(document.querySelectorAll('table'));
                      let t = null;
                      for (const x of tables) {
                        const head = norm(x.querySelector('thead')?.innerText || '');
                        const anyText = norm(x.innerText || '');
                        const txt = (head.length >= 8 ? head : anyText);
                        if (txt.includes('alle ore') && txt.includes('risultato slot') && txt.includes('esito') && txt.includes('moltip') && !txt.includes('top slot')) { t = x; break; }
                      }
                      if (t) {
                        t.scrollIntoView({ block: 'start', inline: 'nearest' });
                        const r = t.getBoundingClientRect();
                        window.scrollBy(0, r.top - 120);
                      }
                    }"""
                )
            except Exception:
                pass
            page.wait_for_timeout(350)

        def _warm_load_more_rows() -> None:
            # Brute-force scroll the page to trigger lazy loading of older rows (6h history).
            try:
                for _ in range(18):
                    page.evaluate("() => window.scrollBy(0, 1400)")
                    page.wait_for_timeout(180)
            except Exception:
                pass
            _ensure_cronologia_in_view()

        # Force the same view shown in your screenshots.
        # Important: the time-range controls sometimes mount only after scrolling to the table area.
        _ensure_cronologia_in_view()
        try:
            # Try clicking the dropdown "Seleziona Lasso Di Tempo" if present.
            sel = page.get_by_text(re.compile(r"Seleziona\s+Lasso\s+Di\s+Tempo", re.IGNORECASE))
            if sel.count() > 0:
                sel.first.click(timeout=2500)
                page.wait_for_timeout(250)
            six_hours_btn = page.get_by_role("button", name=re.compile(r"Ultime\s*6\s*ore", re.IGNORECASE))
            if six_hours_btn.count() == 0:
                six_hours_btn = page.get_by_text(re.compile(r"Ultime\s*6\s*ore", re.IGNORECASE))
            if six_hours_btn.count() > 0:
                try:
                    six_hours_btn.first.scroll_into_view_if_needed(timeout=2500)
                except Exception:
                    pass
                six_hours_btn.first.click(timeout=3000, force=True)
                page.wait_for_timeout(900)
        except Exception:
            pass

        try:
            page.evaluate("() => window.scrollTo(0, 0)")
        except Exception:
            pass
        page.wait_for_timeout(500)
        _ensure_cronologia_in_view()
        try:
            page.wait_for_selector("table:has-text('Risultato Slot')", timeout=8000)
            _log("cronologia table selector found")
        except Exception:
            _log("cronologia table selector not found before extraction")
        _warm_load_more_rows()

        def extract_rows() -> List[Dict[str, Any]]:
            return page.evaluate(
            """() => {
              const norm = (s) => (s || '').replace(/\\s+/g,' ').trim();
              const slotFromText = (t) => {
                const x = norm(t || '');
                if (!x) return '';
                const low = x.toLowerCase();
                if (low.includes('perso')) return 'Perso';
                // "2X", "10X", ecc.
                const m = low.match(/\\b(10|5|2|1)\\s*x\\b/);
                if (m) return m[1];
                // fallback se già "2" ecc
                const m2 = low.match(/\\b(10|5|2|1)\\b/);
                if (m2) return m2[1];
                return x;
              };
              const getMults = (node) => {
                const text = norm(node?.innerText || '');
                const mults = [];
                const re = /(\\d{1,4})\\s*x/gi;
                let m;
                while ((m = re.exec(text)) !== null) mults.push(parseInt(m[1], 10));
                return mults;
              };
              const hasAny = (s, parts) => parts.some(p => s.includes(p));
              const segmentFromToken = (token) => {
                const t = (token || '').toLowerCase();
                if (!t) return '';
                // Top Slot icons (cloudinary paths)
                if (t.includes('/one.png') || t.endsWith('one.png')) return '1';
                if (t.includes('/two.png') || t.endsWith('two.png')) return '2';
                if (t.includes('/five.png') || t.endsWith('five.png')) return '5';
                if (t.includes('/ten.png') || t.endsWith('ten.png')) return '10';
                if (t.includes('cash-hunt.png') || t.includes('cash_hunt.png')) return 'Cash Hunt';
                if (t.includes('coin-flip.png') || t.includes('coin_flip.png')) return 'Coin Flip';
                if (t.includes('pachinko.png')) return 'Pachinko';
                if (t.includes('crazy-time.png') || t.includes('crazy_time.png')) return 'Crazy Time';
                if (hasAny(t, ['pachinko','pachinko_logo','pachinko-logo',' pa '])) return 'Pachinko';
                if (hasAny(t, ['coin flip','coin-flip','coin_flip']) || (t.includes('coin') && t.includes('flip'))) return 'Coin Flip';
                if (hasAny(t, ['cash hunt','cash-hunt','cash_hunt']) || (t.includes('cash') && t.includes('hunt'))) return 'Cash Hunt';
                if (hasAny(t, ['ten-card','10-card',' ten '])) return '10';
                if (hasAny(t, ['five-card','5-card',' five '])) return '5';
                if (hasAny(t, ['two-card','2-card',' two '])) return '2';
                if (hasAny(t, ['one-card','1-card',' one '])) return '1';
                // NO "ct-" qui: molte classi CSS del sito contengono "ct-" e fanno scattare CT al posto di Pachinko nella colonna Esito.
                if (hasAny(t, ['crazy time','crazy-time','crazy_time']) && !hasAny(t, ['pachinko','pachiko','coin','flip','cash','hunt'])) return 'Crazy Time';
                return '';
              };
              const collectIconTokens = (root) => {
                if (!root) return '';
                const toks = [];
                try {
                  // imgs
                  root.querySelectorAll('img').forEach((img) => {
                    toks.push(img.getAttribute('src') || '');
                    toks.push(img.getAttribute('alt') || '');
                    toks.push(img.getAttribute('title') || '');
                    toks.push(img.getAttribute('aria-label') || '');
                    toks.push(img.getAttribute('class') || '');
                  });
                  // svg <use href="...">
                  root.querySelectorAll('svg use').forEach((u) => {
                    toks.push(u.getAttribute('href') || '');
                    toks.push(u.getAttribute('xlink:href') || '');
                    toks.push(u.getAttribute('class') || '');
                  });
                  // any aria-label/title on descendants (often contains segment name)
                  root.querySelectorAll('[aria-label],[title]').forEach((n) => {
                    toks.push(n.getAttribute('aria-label') || '');
                    toks.push(n.getAttribute('title') || '');
                    toks.push(n.getAttribute('class') || '');
                  });
                } catch(e) {}
                return toks.filter(Boolean).join(' ');
              };
              const segmentFromImgNode = (img) => {
                if (!img) return '';
                const src = (img.getAttribute('src') || '');
                const alt = (img.getAttribute('alt') || '');
                const aria = (img.getAttribute('aria-label') || '');
                const title = (img.getAttribute('title') || '');
                const cls = (img.getAttribute('class') || '');
                const blob = `${src} ${alt} ${aria} ${title} ${cls}`;
                return segmentFromToken(blob);
              };
              const segmentFromSrc = (src) => {
                const s = (src || '').toLowerCase();
                const file = s.split('/').pop() || s;
                // Top Slot icons (e.g. ".../crazy-time/two.png")
                if (file === 'one.png') return '1';
                if (file === 'two.png') return '2';
                if (file === 'five.png') return '5';
                if (file === 'ten.png') return '10';
                if (file === 'cash-hunt.png' || file === 'cash_hunt.png') return 'Cash Hunt';
                if (file === 'coin-flip.png' || file === 'coin_flip.png') return 'Coin Flip';
                if (file === 'pachinko.png' || file === 'pachiko.png') return 'Pachinko';
                if (file === 'crazy-time.png' || file === 'crazy_time.png') return 'Crazy Time';

                if (file.includes('one-card')) return '1';
                if (file.includes('two-card')) return '2';
                if (file.includes('five-card')) return '5';
                if (file.includes('ten-card')) return '10';
                if (file.includes('cash-hunt') || (file.includes('cash') && file.includes('hunt'))) return 'Cash Hunt';
                if (file.includes('coin-flip') || (file.includes('coin') && file.includes('flip'))) return 'Coin Flip';
                if (file.includes('pachinko')) return 'Pachinko';
                // Crazy Time: solo nomi file espliciti (no "ct-" generico).
                if (hasAny(file, ['crazy-time', 'crazy_time']) && !hasAny(file, ['pachinko','pachiko','coin','flip','cash','hunt'])) return 'Crazy Time';
                return '';
              };

              // Fallback mapping from td HTML (handles Esito icons that are SVG/use/background without <img src>).
              const segmentFromTd = (td) => {
                if (!td) return '';
                // IMPORTANT: do NOT scan full innerHTML (it may contain unrelated "crazy-time" tokens).
                // Only use tokens that belong to the icon elements inside this cell.
                return segmentFromToken(collectIconTokens(td));
              };
              const segmentFromTdStrict = (td) => {
                if (!td) return '';
                // Se compare "pachinko" nel testo o nei token della cella Esito, vince sempre su CT (evita falsi Crazy Time da CSS/url).
                try {
                  const scan = ((collectIconTokens(td) || '') + ' ' + norm(td.innerText || td.textContent || '')).toLowerCase();
                  if (scan.includes('pachinko') || scan.includes('pachiko')) return 'Pachinko';
                } catch (e0) {}
                const hits = [];
                try {
                  // 1) Strongest signal: explicit image filenames used by the row.
                  td.querySelectorAll('img').forEach((img) => {
                    const src = (img.getAttribute('src') || '').toLowerCase();
                    const bySrc = segmentFromSrc(src);
                    if (bySrc) hits.push(bySrc);
                    const byNode = segmentFromImgNode(img);
                    if (byNode) hits.push(byNode);
                  });

                  // 2) CSS background-image URLs sometimes carry exact asset names.
                  td.querySelectorAll('*').forEach((el) => {
                    try {
                      const bg = String(window.getComputedStyle(el).backgroundImage || '').toLowerCase();
                      const m = bg.match(/url\(([^)]+)\)/i);
                      if (m && m[1]) {
                        const url = m[1].replace(/['"]/g, '');
                        const byBg = segmentFromSrc(url);
                        if (byBg) hits.push(byBg);
                      }
                    } catch (e) {}
                  });

                  // 3) Text fallback scoped to this td.
                  const txt = norm(td.innerText || td.textContent || '');
                  const byTxt = segmentFromToken(txt);
                  if (byTxt) hits.push(byTxt);
                } catch (e) {}

                // Prefer PA over CT if both appear in noisy tokens.
                if (hits.includes('Pachinko')) return 'Pachinko';
                if (hits.includes('Coin Flip')) return 'Coin Flip';
                if (hits.includes('Cash Hunt')) return 'Cash Hunt';
                if (hits.includes('Crazy Time')) return 'Crazy Time';
                if (hits.includes('10')) return '10';
                if (hits.includes('5')) return '5';
                if (hits.includes('2')) return '2';
                if (hits.includes('1')) return '1';
                return '';
              };

              const pickTable = () => {
                const tables = Array.from(document.querySelectorAll('table'));
                for (const t of tables) {
                  const head = norm(t.querySelector('thead')?.innerText || '').toLowerCase();
                  const anyText = norm(t.innerText || '').toLowerCase();
                  const txt = (head.length >= 8 ? head : anyText);
                  if (txt.includes('alle ore') && txt.includes('risultato slot') && txt.includes('esito') && txt.includes('moltip') && !txt.includes('top slot')) return t;
                }
                return null;
              };

              const t = pickTable();
              if (!t) return [];
              let trs = Array.from(t.querySelectorAll('tbody tr'));
              if (!trs.length) trs = Array.from(t.querySelectorAll('tr')).filter(tr => !tr.querySelector('th'));

              const out = [];
              for (const tr of trs) {
                const tds = tr.querySelectorAll('td');
                if (tds.length < 3) continue;
                const dtTextRaw = norm(tds[0]?.innerText || '');
                const timeMatch = dtTextRaw.match(/\\b\\d{1,2}:\\d{2}\\b/);
                if (!timeMatch) continue;

                const slotTd = tds[1];
                const slotImg = slotTd?.querySelector('img');
                const slotValue = slotFromText(slotTd?.innerText || slotTd?.textContent || '');
                // For Top Slot, the <img src> filename is the most reliable (one.png/two.png/ten.png/pachinko.png/etc).
                const slotIcon = segmentFromSrc(slotImg?.getAttribute('src') || '') || segmentFromTd(slotTd) || segmentFromImgNode(slotImg);
                // Slot cell can be like "Pachinko + Perso": keep both.
                // slot_result keeps the text outcome if present (Perso / 2 / 5 / 10 / 25X etc), otherwise falls back to icon.
                const slot = slotValue || slotIcon;
                const wheelTd = tds[2];
                const wheelImg = wheelTd?.querySelector('img');
                // Esito: strict parser to avoid CT taking PA place on mixed/noisy HTML tokens.
                const wheelIcon = segmentFromTdStrict(wheelTd) || segmentFromSrc(wheelImg?.getAttribute('src') || '') || segmentFromImgNode(wheelImg) || segmentFromTd(wheelTd);
                const wheel = wheelIcon || norm(wheelTd?.innerText || wheelTd?.textContent || '');
                const mults = getMults(tds[3]);

                if (!slot) continue;
                // Moltiplicatori appartengono alla riga (anche se Risultato Slot è Perso).
                out.push({
                  datetime_text: dtTextRaw,
                  time: timeMatch[0],
                  slot_result: slot,
                  slot_icon: slotIcon || '',
                  wheel_result: wheel,
                  wheel_icon: wheelIcon || '',
                  top_slot_multipliers: mults
                });
              }
              return out;
            }""",
        )
        # The site often virtualizes the table; scroll within the table area
        # to load more rows until we reach the desired limit.
        target_limit = limit
        extracted: List[Dict[str, Any]] = []
        seen_keys: set[str] = set()
        stable_rounds = 0
        table_locator = page.locator("table").filter(has=page.get_by_text(re.compile(r"Risultato\\s+Slot", re.IGNORECASE)))
        # Keep scraping bounded for server runtimes (Render).
        for _ in range(40):
            if (time.monotonic() - started_at) > 50:
                _log("time budget exceeded during extraction loop")
                break
            batch: List[Dict[str, Any]] = extract_rows()
            grew = False
            for r in batch:
                k = f"{r.get('datetime_text')}|{r.get('slot_result')}|{r.get('wheel_result')}|{','.join(str(x) for x in (r.get('top_slot_multipliers') or []))}"
                if k in seen_keys:
                    continue
                seen_keys.add(k)
                extracted.append(r)
                grew = True
            if len(extracted) >= target_limit:
                break
            if not grew:
                stable_rounds += 1
            else:
                stable_rounds = 0
            if stable_rounds >= 6:
                break
            try:
                page.evaluate(
                    """() => {
                      const norm = (s) => (s || '').replace(/\\s+/g,' ').trim().toLowerCase();
                      const tables = Array.from(document.querySelectorAll('table'));
                      let t = null;
                      for (const x of tables) {
                        const head = norm(x.querySelector('thead')?.innerText || '');
                        const anyText = norm(x.innerText || '');
                        const txt = (head.length >= 8 ? head : anyText);
                        if (txt.includes('alle ore') && txt.includes('risultato slot') && txt.includes('esito') && txt.includes('moltip') && !txt.includes('top slot')) { t = x; break; }
                      }
                      if (!t) return;
                      let sc = t.parentElement;
                      for (let i=0;i<10 && sc;i++){
                        const style = window.getComputedStyle(sc);
                        const oy = (style.overflowY || '').toLowerCase();
                        if ((oy === 'auto' || oy === 'scroll') && sc.scrollHeight > sc.clientHeight + 10) break;
                        sc = sc.parentElement;
                      }
                      if (sc && sc.scrollHeight > sc.clientHeight + 10) {
                        sc.scrollTop = Math.min(sc.scrollTop + Math.floor(sc.clientHeight * 0.9), sc.scrollHeight);
                      } else {
                        window.scrollBy(0, 1200);
                      }
                    }"""
                )
            except Exception:
                pass
            try:
                if table_locator.count() > 0:
                    table_locator.first.hover(timeout=1000)
                # Some versions only load more rows on wheel scrolling.
                page.mouse.wheel(0, 2200)
            except Exception:
                pass
            page.wait_for_timeout(450)
        if not extracted:
            try:
                page.wait_for_timeout(1200)
                six_hours_btn = page.get_by_text(re.compile(r"Ultime\s*6\s*ore", re.IGNORECASE))
                if six_hours_btn.count() > 0:
                    six_hours_btn.first.click(timeout=2500)
                    page.wait_for_timeout(900)
                    _ensure_cronologia_in_view()
                # One more attempt after forcing the filter.
                extracted = extract_rows()
            except Exception:
                pass

        # If data appears stale, force one immediate refresh and read again.
        try:
            if extracted:
                now = datetime.now()
                latest_hhmm = str(extracted[0].get("time") or "")
                m = re.match(r"^(\d{1,2}):(\d{2})$", latest_hhmm)
                if m:
                    latest_min = int(m.group(1)) * 60 + int(m.group(2))
                    now_min = now.hour * 60 + now.minute
                    # If lag > 1 minute, reload once (keep source close to live).
                    if now_min - latest_min > 1:
                        page.goto(CRAZY_TIME_URL, wait_until="domcontentloaded", timeout=60000)
                        page.wait_for_timeout(800)
                        extracted = extract_rows()
        except Exception:
            pass

        # Defensive ordering: newest first by HH:MM inside same day block.
        def row_sort_key(r: Dict[str, Any]) -> int:
            t = str(r.get("time") or "")
            m = re.match(r"^(\d{1,2}):(\d{2})$", t)
            if not m:
                return -1
            return int(m.group(1)) * 60 + int(m.group(2))

        extracted = sorted(extracted, key=row_sort_key, reverse=True)

        # Debug signals for Render logs (stderr so JSON stdout remains valid).
        print(f"ROWS TROVATE: {len(extracted)}", file=sys.stderr, flush=True)
        if extracted:
            print(f"PRIMA RIGA: {extracted[0]}", file=sys.stderr, flush=True)
            try:
                page.screenshot(path="/tmp/debug_success.png", full_page=True)
            except Exception:
                pass
        else:
            try:
                page.screenshot(path="/tmp/debug_failure.png", full_page=True)
            except Exception:
                pass

        # Always keep a Render debug screenshot.
        try:
            page.screenshot(path="/tmp/debug.png", full_page=True)
        except Exception:
            pass

        shot: Optional[str] = None
        if screenshot_prefix:
            DEFAULT_SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            shot = str(DEFAULT_SCREENSHOT_DIR / f"{screenshot_prefix}_{ts}.png")
            try:
                locator = page.locator("table", has=page.get_by_text(re.compile(r"Risultato Slot", re.IGNORECASE)))
                if locator.count() > 0:
                    locator.first.screenshot(path=shot)
                else:
                    page.screenshot(path=shot, full_page=True)
            except Exception:
                try:
                    page.screenshot(path=shot, full_page=True)
                except Exception:
                    shot = None

        try:
            ctx.close()
        except Exception:
            pass
        try:
            browser.close()
        except Exception:
            pass

        return extracted, shot


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--screenshot-prefix", type=str, default="cronologia")
    ap.add_argument("--headed", action="store_true", default=False)
    ap.add_argument("--x", type=int, default=0)
    ap.add_argument("--y", type=int, default=0)
    ap.add_argument("--w", type=int, default=960)
    ap.add_argument("--h", type=int, default=1040)
    args = ap.parse_args()

    extracted, shot = _scrape(
        args.limit,
        args.screenshot_prefix if args.screenshot_prefix else None,
        headless=True,
        window_pos=(args.x, args.y),
        window_size=(args.w, args.h),
    )
    # Use ASCII-escaped JSON to avoid Windows cp1252 stdout encoding crashes.
    sys.stdout.write(json.dumps({"rows": extracted, "screenshot": shot}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

