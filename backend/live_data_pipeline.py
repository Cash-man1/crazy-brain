"""
Pipeline dati live Crazy Time: ordinamento UTC, lag, dedup, parametri sicuri per BrainEngine.

Obiettivo: il cervello riceve moltiplicatori Top Slot solo quando slot e ruota coincidono
(stesso segmento), come nella logica di gioco reale. I dati Evolution includono sempre
`settled_at_utc` e `top_slot_multiplier` separato da `max_multiplier` (payout finale).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from brain_engine import ALL_SEGMENTS


def _parse_utc(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def settled_epoch(row: Dict[str, Any]) -> float:
    z = row.get("settled_at_utc")
    dt = _parse_utc(z) if z else None
    if dt:
        return dt.timestamp()
    return 0.0


def rows_newest_first(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Più recente in testa (richiede `settled_at_utc` dove possibile)."""
    return sorted(rows, key=settled_epoch, reverse=True)


def rows_oldest_first(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(rows, key=settled_epoch, reverse=False)


def time_lag_seconds(rows: List[Dict[str, Any]]) -> Optional[int]:
    """Secondi tra ultimo evento (UTC) e clock server UTC. None se non stimabile."""
    if not rows:
        return None
    r0 = rows[0]
    dt = _parse_utc(str(r0.get("settled_at_utc") or ""))
    if not dt:
        return None
    delta = datetime.now(timezone.utc) - dt
    return max(0, int(delta.total_seconds()))


def row_dedupe_key(row: Dict[str, Any]) -> str:
    eid = row.get("event_id")
    if eid:
        return f"id:{eid}"
    dt = str(row.get("settled_at_utc") or row.get("datetime_text") or row.get("time") or "").strip().lower()
    slot = str(row.get("slot_result") or "").strip().lower()
    wheel = str(row.get("wheel_result") or "").strip().lower()
    mults = row.get("top_slot_multipliers") or []
    mult_sig = ",".join(str(x) for x in mults)
    return f"{dt}|{slot}|{wheel}|{mult_sig}"


def row_valid_for_brain(row: Dict[str, Any], wheel_seg: Optional[str]) -> bool:
    if not wheel_seg or wheel_seg not in ALL_SEGMENTS:
        return False
    if row.get("data_source") == "evolution-api" and not row.get("settled_at_utc"):
        return False
    return True


def brain_spin_kwargs(wheel_seg: str, slot_seg: Optional[str], row: Dict[str, Any]) -> Tuple[Optional[int], Optional[str], Dict[str, Any]]:
    """
    Restituisce (multiplier, mult_segment) per add_spin — None, None se il Top Slot
    non deve influenzare il motore (nessun match o dati insufficienti).
    """
    top_only = row.get("top_slot_multiplier")
    top_only_int: Optional[int] = int(top_only) if top_only is not None else None

    bonus_data: Dict[str, Any] = {
        "slot_result": row.get("slot_result"),
        "wheel_result": row.get("wheel_result"),
        "slot_segment": slot_seg,
        "wheel_segment": wheel_seg,
        "top_slot_multipliers": row.get("top_slot_multipliers") or [],
        "top_slot_multiplier": top_only_int,
        "max_multiplier": row.get("max_multiplier"),
        "settled_at_utc": row.get("settled_at_utc"),
        "data_source": row.get("data_source"),
    }

    match = bool(slot_seg and wheel_seg and slot_seg == wheel_seg)
    if match and top_only_int is not None:
        bonus_data["top_slot_applied"] = True
        return top_only_int, wheel_seg, bonus_data

    bonus_data["top_slot_applied"] = False
    if str(wheel_seg).isdigit():
        try:
            bonus_data["base_wheel"] = int(wheel_seg)
        except ValueError:
            pass

    # Sorgente legacy (Playwright/HTML): non dedurre Top Slot da max(lista) — evita mismatch.
    return None, None, bonus_data


def apply_brain_spin(brain: Any, wheel_seg: str, slot_seg: Optional[str], row: Dict[str, Any]) -> None:
    """Singola chiamata centralizzata a brain.add_spin."""
    mult, mseg, bonus = brain_spin_kwargs(wheel_seg, slot_seg, row)
    if mult is not None and mseg:
        brain.add_spin(segment=wheel_seg, multiplier=mult, mult_segment=mseg, bonus_data=bonus)
    else:
        brain.add_spin(segment=wheel_seg, bonus_data=bonus)
