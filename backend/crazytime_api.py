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

EVOLUTION_CRAZY_TIME_EVENTS_URL = (
    "https://api-cs.casino.org/svc-evolution-game-events/api/crazytime"
)

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


def _hhmm_rome(iso_utc: str) -> str:
    dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
    return _to_rome(dt).strftime("%H:%M")


def _collect_multipliers(outcome: Dict[str, Any]) -> List[int]:
    """Lista per UI (dedup): include solo valori distinti utili alla dashboard."""
    mults: List[int] = []
    ts = outcome.get("topSlot") or {}
    if ts.get("multiplier") is not None:
        mults.append(int(ts["multiplier"]))
    wr = outcome.get("wheelResult") or {}
    if wr.get("type") == "BonusRound":
        bonus = wr.get("bonus") or {}
        bm = bonus.get("bonusMultiplier") or {}
        if bm.get("value") is not None:
            mults.append(int(bm["value"]))
        res = bonus.get("result") or {}
        if res.get("multiplier") is not None:
            mults.append(int(res["multiplier"]))
    mx = outcome.get("maxMultiplier")
    if mx is not None:
        mults.append(int(mx))
    out: List[int] = []
    for m in mults:
        if m not in out:
            out.append(m)
    return out


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
    top_label = _sector_label(top_code)
    top_mult_raw = ts.get("multiplier")
    top_mult_int: Optional[int] = int(top_mult_raw) if top_mult_raw is not None else None
    if top_mult_int is not None:
        slot_result = f"{top_label} x{top_mult_int}"
    else:
        slot_result = top_label

    wt = wr.get("type")
    if wt == "WinningNumber":
        wheel_result = str(wr.get("wheelSector") or "")
    elif wt == "BonusRound":
        wheel_result = _sector_label(str(wr.get("wheelSector") or ""))
    else:
        wheel_result = str(wr.get("wheelSector") or "")

    mults = _collect_multipliers(outcome)
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
        "top_slot_multipliers": mults,
        "top_slot_multiplier": top_mult_int,
        "max_multiplier": max_mult_int,
        "slot_icon": top_code,
        "wheel_icon": str(wr.get("wheelSector") or ""),
        "data_source": "evolution-api",
    }


def fetch_evolution_crazytime_rows(limit: int = 40, timeout: float = 12.0) -> List[Dict[str, Any]]:
    """Scarica gli ultimi round da API JSON (nessun browser). Ordine: più recente per primo."""
    lim = max(1, min(int(limit), 5000))
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=_HEADERS) as client:
        # L'endpoint supporta "size": consente storico molto più ampio rispetto al default.
        r = client.get(EVOLUTION_CRAZY_TIME_EVENTS_URL, params={"size": lim})
        r.raise_for_status()
        payload = r.json()
    if not isinstance(payload, list):
        return []
    rows: List[Dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        row = _row_from_event(item)
        if row:
            rows.append(row)
    rows.sort(key=lambda x: x.get("settled_at_utc") or "", reverse=True)
    return rows[:lim]
