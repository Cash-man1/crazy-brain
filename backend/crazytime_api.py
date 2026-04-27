"""
Lettura leggera cronologia Crazy Time via API pubblica CasinoScores / Evolution.
Evita Playwright quando l'endpoint risponde (meno RAM su Render).

Sorgente individuata nel bundle Next.js (chunk 2404): svc-evolution-game-events.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

try:
    from zoneinfo import ZoneInfo

    def _to_rome(dt: datetime) -> datetime:
        try:
            return dt.astimezone(ZoneInfo("Europe/Rome"))
        except Exception:
            return dt.astimezone(timezone.utc)

except Exception:

    def _to_rome(dt: datetime) -> datetime:
        return dt.astimezone(timezone.utc)

EVOLUTION_CRAZY_TIME_EVENTS_URL = "https://api-cs.casino.org/svc-evolution-game-events/api/crazytime"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept": "application/json",
}


def _sector_label(code: str) -> str:
    c = (code or "").strip()
    if not c:
        return ""
    if re.fullmatch(r"\d+", c):
        return c
    u = c.lower().replace(" ", "")
    mapping = {
        "cashhunt": "Cash Hunt",
        "coinflip": "Coin Flip",
        "pachinko": "Pachinko",
        "crazytime": "Crazy Time",
        "crazybonus": "Crazy Bonus",
    }
    return mapping.get(u, re.sub(r"([a-z])([A-Z])", r"\1 \2", c))


def _abbrev_slot_sector(code: str) -> str:
    """Abbreviazione coerente con badge UI (PA, CF, CH, CT) o cifra 1/2/5/10."""
    c = (code or "").strip()
    if not c:
        return ""
    if re.fullmatch(r"\d+", c):
        return c
    u = re.sub(r"[\s_\-]+", "", c.lower())
    mapping = {
        "cashhunt": "CH",
        "coinflip": "CF",
        "pachinko": "PA",
        "crazytime": "CT",
        "crazybonus": "CT",
    }
    return mapping.get(u, "")


def _format_slot_cell(top_code: str, top_mult_int: Optional[int]) -> str:
    """Es. PA x4, oppure 2 - 2x (settore slot numerico + moltiplicatore Top Slot)."""
    abbr = _abbrev_slot_sector(top_code)
    if not abbr:
        return ""
    if top_mult_int is None:
        return abbr
    tc = str(top_code or "").strip()
    if re.fullmatch(r"\d+", tc):
        return f"{abbr} - {top_mult_int}x"
    return f"{abbr} x{top_mult_int}"


def _hhmm_rome(iso_utc: str) -> str:
    dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
    return _to_rome(dt).strftime("%H:%M")


def _moltip_chain_from_outcome(outcome: Dict[str, Any]) -> List[int]:
    """
    Esito finale colonna Moltip., allineato a Evolution / schermata casino:

    - `maxMultiplier` su outcome e' il moltiplicatore effettivo dopo Top Slot quando applicabile
      (match: es. ruota 2 x slot 5x → 10; Perso sul numero → solo base 2).
    - Coin Flip / Pachinko: una sola cifra finale → niente duplicati tipo 50x 50x.
    - Crazy Bonus (CT): si mostrano ancora i tre flap (sinistra/alto/destra).
    - Cash Hunt: range min/max da outcome (due valori → UI con trattino lungo).
    """
    wr = outcome.get("wheelResult") or {}
    wt = wr.get("type")

    if wt != "BonusRound":
        mx = outcome.get("maxMultiplier")
        if mx is not None:
            return [int(mx)]
        ws = str(wr.get("wheelSector") or "").strip()
        if ws in ("1", "2", "5", "10"):
            return [int(ws)]
        return []

    bonus = wr.get("bonus") or {}
    btype = bonus.get("type")

    if btype == "CashHunt":
        mn = outcome.get("cashHuntMinMultiplier")
        mx = outcome.get("cashHuntMaxMultiplier") or outcome.get("maxMultiplier")
        out: List[int] = []
        if mn is not None:
            out.append(int(mn))
        if mx is not None:
            ix = int(mx)
            if not out or ix != out[-1]:
                out.append(ix)
        if not out:
            fallback = outcome.get("maxMultiplier")
            return [int(fallback)] if fallback is not None else []
        if len(out) == 2 and out[0] == out[1]:
            return [out[0]]
        return out

    if btype == "CrazyBonus":
        fr = bonus.get("flapperResult") or {}
        order = ("left", "top", "right")
        chain: List[int] = []
        for key in order:
            slot = fr.get(key) or {}
            v = slot.get("bonusMultiplier")
            if v is not None:
                chain.append(int(v))
        return chain

    mx = outcome.get("maxMultiplier")
    if mx is not None:
        return [int(mx)]

    bm2 = bonus.get("bonusMultiplier") or {}
    chain2: List[int] = []
    if bm2.get("value") is not None:
        chain2.append(int(bm2["value"]))
    res2 = bonus.get("result") or {}
    if res2.get("multiplier") is not None:
        chain2.append(int(res2["multiplier"]))
    return chain2


def _settled_iso_utc_z(settled: str) -> str:
    """Normalizza timestamp sorgente a ISO-8601 UTC con Z."""
    s = (settled or "").strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def _row_from_event(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    data = item.get("data") or {}
    settled = data.get("settledAt") or data.get("startedAt")
    if not settled:
        return None
    settled_utc_z = _settled_iso_utc_z(str(settled))
    if not settled_utc_z:
        return None

    outcome = (data.get("result") or {}).get("outcome") or {}
    ts = outcome.get("topSlot") or {}
    wr = outcome.get("wheelResult") or {}

    top_code = str(ts.get("wheelSector") or "")
    top_mult_raw = ts.get("multiplier")
    top_mult_int: Optional[int] = int(top_mult_raw) if top_mult_raw is not None else None
    slot_result = _format_slot_cell(top_code, top_mult_int)

    wt = wr.get("type")
    if wt == "WinningNumber":
        wheel_result = str(wr.get("wheelSector") or "")
    elif wt == "BonusRound":
        wheel_result = _sector_label(str(wr.get("wheelSector") or ""))
    else:
        wheel_result = str(wr.get("wheelSector") or "")

    moltip_chain = _moltip_chain_from_outcome(outcome)
    max_mult = outcome.get("maxMultiplier")
    max_mult_int: Optional[int] = int(max_mult) if max_mult is not None else None

    ev_id = item.get("id") or item.get("eventId") or item.get("event_id")
    event_id = str(ev_id).strip() if ev_id is not None else ""

    dt_text = settled.replace("T", " ")[:19]

    return {
        "event_id": event_id,
        "settled_at_utc": settled_utc_z,
        "datetime_text": dt_text,
        "time": _hhmm_rome(settled),
        "slot_result": slot_result,
        "wheel_result": wheel_result,
        "moltip_chain": moltip_chain,
        "top_slot_multipliers": moltip_chain,
        "top_slot_multiplier": top_mult_int,
        "max_multiplier": max_mult_int,
        "slot_icon": top_code,
        "wheel_icon": str(wr.get("wheelSector") or ""),
        "data_source": "evolution-api",
    }


def fetch_evolution_crazytime_rows(
    limit: int = 40,
    timeout: float = 12.0,
    duration_hours: int = 72,
) -> List[Dict[str, Any]]:
    """
    Scarica gli ultimi round da API JSON (nessun browser), seguendo la stessa API paginata
    che usa la pagina CasinoScores per la tabella "Cronologia Giocate".
    """
    lim = max(1, min(int(limit), 20000))
    dur = max(1, min(int(duration_hours), 72))
    page_size = min(250, lim)
    max_pages = max(1, min(200, (lim + page_size - 1) // page_size + 2))
    rows: List[Dict[str, Any]] = []
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=_HEADERS) as client:
        for page in range(max_pages):
            params = {
                "page": page,
                "size": page_size,
                "sort": "data.settledAt,desc",
                "duration": dur,
                "wheelResults": "Pachinko,CashHunt,CrazyBonus,CoinFlip,1,2,5,10",
                "isTopSlotMatched": "true,false",
                "tableId": "CrazyTime0000001",
            }
            r = client.get(EVOLUTION_CRAZY_TIME_EVENTS_URL, params=params)
            r.raise_for_status()
            payload = r.json()
            if not isinstance(payload, list) or not payload:
                break
            page_rows = 0
            for item in payload:
                if not isinstance(item, dict):
                    continue
                row = _row_from_event(item)
                if row:
                    rows.append(row)
                    page_rows += 1
                if len(rows) >= lim:
                    break
            if len(rows) >= lim or page_rows == 0 or len(payload) < page_size:
                break
    rows.sort(key=lambda x: x.get("settled_at_utc") or "", reverse=True)
    return rows[:lim]
