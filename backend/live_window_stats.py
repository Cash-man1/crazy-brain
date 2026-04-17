"""
Statistiche tipo tracker (finestre su cronologia) senza toccare il motore decisionale.
Usa solo righe già normalizzate (wheel_segment, slot_segment, moltiplicatori).
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Sequence


def _max_mult_in_row(row: Dict[str, Any]) -> int:
    fm = row.get("final_multiplier")
    if fm is not None:
        try:
            return int(fm)
        except (TypeError, ValueError):
            pass
    top = row.get("top_slot_multipliers") or []
    if isinstance(top, list) and top:
        try:
            ints = [int(x) for x in top]
            return int(ints[-1])
        except (TypeError, ValueError):
            pass
    ws = row.get("wheel_segment") or row.get("segment")
    if ws is not None and str(ws).isdigit():
        try:
            return int(ws)
        except ValueError:
            pass
    return 0


def compute_live_window_stats(
    rows_oldest_first: List[Dict[str, Any]],
    all_segments: Sequence[str],
    theoretical_probs: Dict[str, float],
) -> Dict[str, Any]:
    """
    rows_oldest_first: cronologia ordinata dal piu vecchio al piu recente (es. da _rows_oldest_first).
    """
    valid: List[Dict[str, Any]] = []
    for row in rows_oldest_first:
        if not isinstance(row, dict):
            continue
        w = row.get("wheel_segment") or row.get("segment")
        if w in all_segments:
            valid.append(row)

    n_all = len(valid)
    out: Dict[str, Any] = {
        "buffer_valid_spins": n_all,
        "windows": [],
        "note": (
            "Ogni riga confronta quante volte è uscita una casella della ruota rispetto a quanto "
            "ci si aspetterebbe in media (probabilità ufficiale del gioco)."
        ),
    }

    if n_all == 0:
        return out

    sizes: List[int] = []
    for cap in (50, 100, 150, 300, 500, 1000, 2000, 5000):
        if n_all >= cap:
            sizes.append(cap)
    if not sizes or sizes[-1] != n_all:
        sizes.append(n_all)

    seen: set = set()
    unique_sizes: List[int] = []
    for s in sizes:
        if s not in seen:
            seen.add(s)
            unique_sizes.append(s)

    for size in unique_sizes:
        chunk = valid[-size:]
        n = len(chunk)
        counts: Dict[str, int] = {seg: 0 for seg in all_segments}
        for row in chunk:
            w = row.get("wheel_segment") or row.get("segment")
            if w in counts:
                counts[w] += 1

        per_seg: Dict[str, Any] = {}
        chi2 = 0.0
        for seg in all_segments:
            obs = counts[seg]
            p = float(theoretical_probs.get(seg, 0) or 0)
            exp = n * p
            ratio = round(obs / exp, 3) if exp > 1e-9 else None
            z: Optional[float] = None
            if exp > 1e-9 and n * p * (1 - p) > 1e-9:
                z = round((obs - exp) / math.sqrt(exp * (1 - p) + 1e-12), 3)
            if exp > 1e-9:
                chi2 += ((obs - exp) ** 2) / exp
            per_seg[seg] = {
                "count": obs,
                "expected": round(exp, 2),
                "ratio_vs_expected": ratio,
                "z_vs_expected": z,
            }

        matched = 0
        compared = 0
        for row in chunk:
            w = row.get("wheel_segment") or row.get("segment")
            s = row.get("slot_segment")
            if w in all_segments and s in all_segments:
                compared += 1
                if w == s:
                    matched += 1

        max_m = 0
        for row in chunk:
            max_m = max(max_m, _max_mult_in_row(row))

        if size != n_all:
            label = f"Solo le ultime {size} uscite"
        else:
            label = f"Tutte le uscite caricate ({size})"

        out["windows"].append(
            {
                "label": label,
                "size": size,
                "spins_in_window": n,
                "per_segment": per_seg,
                "chi_square_vs_theory": round(chi2, 2),
                "slot_wheel_match": {
                    "matched": matched,
                    "compared": compared,
                    "rate": round(matched / compared, 4) if compared else None,
                },
                "max_multiplier_in_window": max_m,
            }
        )

    return out
