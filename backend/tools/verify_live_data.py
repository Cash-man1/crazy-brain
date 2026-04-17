#!/usr/bin/env python3
"""
Verifica pratica: confronto fonte Evolution vs righe normalizzate e input brain.
Esecuzione: dalla cartella backend, con `pip install httpx` se necessario:
  python tools/verify_live_data.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# backend/ sul path
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import httpx  # noqa: E402

from brain_engine import ALL_SEGMENTS  # noqa: E402
from crazytime_api import (  # noqa: E402
    EVOLUTION_CRAZY_TIME_EVENTS_URL,
    _HEADERS,
    _row_from_event,
)
from live_data_pipeline import brain_spin_kwargs, row_valid_for_brain  # noqa: E402


def _normalize_segment(raw_text: str) -> Optional[str]:
    t = raw_text.lower().strip()
    t_norm = re.sub(r"[\s_\-]+", "", t)
    if "cash hunt" in t or "cashhunt" in t_norm:
        return "CH"
    if "coin flip" in t or "coinflip" in t_norm:
        return "CF"
    if "pachinko" in t or "pachiko" in t or "pachinko" in t_norm or "pachiko" in t_norm:
        return "PA"
    if "crazy time" in t or "crazytime" in t_norm:
        return "CT"
    if "crazy bonus" in t or "crazybonus" in t_norm:
        return "CT"
    for n in ("10", "5", "2", "1"):
        if re.search(rf"(^|\D){n}x?($|\D)", t):
            return n
    return None


def clean_one(row: Dict[str, Any]) -> Dict[str, Any]:
    """Stessa logica di api_brain._clean_rows per una riga."""
    slot = str(row.get("slot_result") or "").strip()
    slot_icon = str(row.get("slot_icon") or "").strip()
    wheel = str(row.get("wheel_result") or "").strip()
    wheel_icon = str(row.get("wheel_icon") or "").strip()
    wheel_visual_seg = _normalize_segment(wheel_icon) or _normalize_segment(wheel)
    wheel_legacy_seg = _normalize_segment(str(row.get("wheel_segment") or "")) or _normalize_segment(
        str(row.get("segment") or "")
    )
    wheel_seg = wheel_visual_seg or wheel_legacy_seg
    slot_seg = _normalize_segment(slot_icon) or _normalize_segment(slot) or _normalize_segment(
        str(row.get("slot_segment") or "")
    )
    top = row.get("top_slot_multipliers") or []
    max_m = row.get("max_multiplier")
    final_mult: Optional[int] = None
    if max_m is not None:
        try:
            final_mult = int(max_m)
        except (TypeError, ValueError):
            final_mult = None
    if final_mult is None and top:
        ints = [int(x) for x in top if x is not None]
        if ints:
            final_mult = ints[-1]
    elif final_mult is None and wheel_seg and str(wheel_seg).isdigit():
        final_mult = int(wheel_seg)
    return {
        "wheel_segment": wheel_seg,
        "slot_segment": slot_seg,
        "slot_result": slot,
        "wheel_result": wheel,
        "top_slot_multiplier": row.get("top_slot_multiplier"),
        "max_multiplier": int(max_m) if max_m is not None else None,
        "final_multiplier": final_mult,
        "settled_at_utc": row.get("settled_at_utc") or "",
        "event_id": row.get("event_id") or "",
        "data_source": row.get("data_source") or "",
        **{k: row[k] for k in ("top_slot_multipliers",) if k in row},
    }


def source_settled_raw(item: Dict[str, Any]) -> str:
    data = item.get("data") or {}
    return str(data.get("settledAt") or data.get("startedAt") or "")


def main() -> None:
    n = 20
    with httpx.Client(timeout=20.0, follow_redirects=True, headers=_HEADERS) as client:
        r = client.get(EVOLUTION_CRAZY_TIME_EVENTS_URL)
        r.raise_for_status()
        payload = r.json()
    if not isinstance(payload, list):
        print("Risposta API non è una lista")
        sys.exit(1)

    rows_parsed: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        row = _row_from_event(item)
        if row:
            rows_parsed.append((item, row))
    rows_parsed.sort(key=lambda x: x[1].get("settled_at_utc") or "", reverse=True)
    sample = rows_parsed[:n]

    print("=" * 100)
    print(f"VERIFICA 1:1 - ultimi {len(sample)} eventi (ordinati per settled_at_utc decrescente)")
    print("=" * 100)
    print(
        f"{'#':<3} {'settledAt RAW (fonte)':<28} {'settled_at_utc (sistema)':<28} "
        f"{'slot':<18} {'wheel':<12} {'mult UI':<8} {'ordine':<6}"
    )
    print("-" * 100)
    for i, (item, row) in enumerate(sample, 1):
        raw_ts = source_settled_raw(item)
        sys_ts = row.get("settled_at_utc") or ""
        c = clean_one(row)
        mult_ui = c.get("final_multiplier")
        print(
            f"{i:<3} {raw_ts[:26]:<28} {sys_ts[:26]:<28} "
            f"{str(row.get('slot_result'))[:16]:<18} {str(row.get('wheel_result'))[:10]:<12} {str(mult_ui):<8} {i:<6}"
        )

    print("\n" + "=" * 100)
    print("VERIFICA BRAIN - 5 eventi: raw (estratti) -> normalizzato -> add_spin (multiplier, mult_segment, bonus_data)")
    print("=" * 100)
    for j, (item, row) in enumerate(sample[:5], 1):
        c = clean_one(row)
        ws = c.get("wheel_segment")
        ss = c.get("slot_segment")
        ok = row_valid_for_brain(row, ws)
        mult, mseg, bonus = brain_spin_kwargs(str(ws), ss, row) if ws else (None, None, {})
        raw_compact = {
            "settledAt": (item.get("data") or {}).get("settledAt"),
            "topSlot": ((item.get("data") or {}).get("result") or {}).get("outcome", {}).get("topSlot"),
            "wheelResult": ((item.get("data") or {}).get("result") or {}).get("outcome", {}).get("wheelResult"),
            "maxMultiplier": ((item.get("data") or {}).get("result") or {}).get("outcome", {}).get("maxMultiplier"),
        }
        print(f"\n--- Evento {j} | valid_for_brain={ok} wheel_seg={ws} slot_seg={ss} ---")
        print("RAW (campi chiave):")
        print(json.dumps(raw_compact, indent=2, default=str)[:1200])
        print("ROW post _row_from_event (principali):")
        print(
            json.dumps(
                {
                    k: row.get(k)
                    for k in (
                        "event_id",
                        "settled_at_utc",
                        "time",
                        "slot_result",
                        "wheel_result",
                        "top_slot_multiplier",
                        "max_multiplier",
                        "top_slot_multipliers",
                        "data_source",
                    )
                },
                indent=2,
                default=str,
            )
        )
        print("CLEAN (segmenti + final_multiplier):")
        print(json.dumps(c, indent=2, default=str))
        print("-> add_spin: multiplier=", mult, " mult_segment=", mseg)
        print("-> bonus_data keys:", sorted(bonus.keys()))
        print("-> top_slot_applied:", bonus.get("top_slot_applied"))


if __name__ == "__main__":
    main()
