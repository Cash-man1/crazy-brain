"""
API Brain Engine - Crazy Time Tool
Accesso controllato rigorosamente lato backend
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import time
import re
import httpx
import json
import asyncio
import subprocess
import sys
from pathlib import Path
from live_scraper import scraper, DEFAULT_WINDOW_SIZE
import threading
import os
import logging

from database import get_db, User, get_user_by_id
from security import get_current_user_id, get_client_ip, limiter
from brain_engine import BrainEngine, ALL_SEGMENTS, THEORETICAL_PROBS
from live_window_stats import compute_live_window_stats
from notifier import notify_hot_signals

router = APIRouter(prefix="/brain", tags=["Crazy Time Tool"])
logger = logging.getLogger(__name__)
CRAZY_TIME_SOURCE_URL = "https://www.casino.org/casinoscores/it/crazy-time/"
SCRAPER_VERSION = "2026-04-01-v4"
SCRAPE_WORKER = Path(__file__).resolve().parent / "scrape_worker.py"
WORKER_PYTHON = Path(__file__).resolve().parent.parent / ".venv" / "Scripts" / "python.exe"
MAX_ALLOWED_SOURCE_LAG_SECONDS = 20
SCRAPE_RETRY_ATTEMPTS = 1


def _run_scrape_worker(limit: int = 60) -> Dict[str, Any]:
    python_bin = str(WORKER_PYTHON) if WORKER_PYTHON.exists() else sys.executable
    cmd = [
        python_bin,
        str(SCRAPE_WORKER),
        "--limit",
        str(limit),
        "--screenshot-prefix",
        "cronologia",
    ]
    # Render can be slower with Playwright startup/network; avoid killing the worker too early.
    timeout_sec = 90 if limit <= 120 else 120
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"worker rc={proc.returncode}")
    payload = json.loads(proc.stdout)
    debug_stderr = (proc.stderr or "").strip()
    if debug_stderr:
        payload["_worker_debug"] = debug_stderr[-2000:]
    return payload


def _run_scrape_worker_fresh(limit: int) -> Dict[str, Any]:
    """
    Esegue lo scrape e, se la sorgente e' in ritardo oltre soglia, riprova subito
    scegliendo il payload con lag migliore.
    """
    # 1) Prima prova con worker Playwright (tabella reale => mapping esito piu accurato).
    best_payload: Optional[Dict[str, Any]] = None
    best_rows: List[Dict[str, Any]] = []
    best_lag: Optional[int] = None

    last_worker_error: Optional[str] = None
    for _ in range(max(1, SCRAPE_RETRY_ATTEMPTS)):
        try:
            payload = _run_scrape_worker(limit=limit)
        except Exception as exc:
            last_worker_error = f"{type(exc).__name__}: {str(exc)}"
            payload = {"rows": [], "screenshot": None, "_worker_debug": last_worker_error}
        rows = payload.get("rows") or []
        lag = _time_lag_seconds(rows)

        current = lag if lag is not None else 10**9
        best = best_lag if best_lag is not None else 10**9
        if rows and (best_payload is None or current < best):
            best_payload, best_rows, best_lag = payload, rows, lag

        if lag is not None and lag <= MAX_ALLOWED_SOURCE_LAG_SECONDS:
            return payload

    if best_payload is None:
        diag = "No rows from Playwright worker"
        if last_worker_error:
            diag += f" | worker={last_worker_error}"
        return {"rows": [], "_worker_debug": diag}

    # Keep diagnostics even when payload is empty so API can expose root cause.
    if not (best_payload.get("rows") or []):
        diag = str(best_payload.get("_worker_debug") or "").strip()
        if not diag:
            parts: List[str] = []
            if last_worker_error:
                parts.append(f"worker={last_worker_error}")
            diag = " | ".join(parts)
        if diag:
            best_payload["_worker_debug"] = diag
    return best_payload


def _time_lag_seconds(rows: List[Dict[str, Any]]) -> Optional[int]:
    if not rows:
        return None
    t = str(rows[0].get("time") or "")
    m = re.match(r"^(\d{1,2}):(\d{2})$", t)
    if not m:
        return None
    row_min = int(m.group(1)) * 60 + int(m.group(2))
    now = datetime.now()
    now_min = now.hour * 60 + now.minute
    lag_min = now_min - row_min
    if lag_min < 0:
        lag_min += 24 * 60
    return lag_min * 60


def _rows_latest_first(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def key(r: Dict[str, Any]) -> int:
        t = str(r.get("time") or "")
        m = re.match(r"^(\d{1,2}):(\d{2})$", t)
        if not m:
            return -1
        return int(m.group(1)) * 60 + int(m.group(2))
    return sorted(rows, key=key, reverse=True)


def _rows_oldest_first(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return list(reversed(_rows_latest_first(rows)))


# ============================================================================
# SESSION STORAGE (In-memory per semplicità, usare Redis in produzione)
# ============================================================================

# Store sessioni attive: {user_id: BrainEngine}
active_sessions: Dict[int, BrainEngine] = {}
auto_state: Dict[int, Dict[str, Any]] = {}
PUBLIC_GUEST_ID = 0

# Public autopoll cache: keep responses fast even at 1s refresh.
_public_cache: Dict[str, Any] = {"ts": 0.0, "payload": None}
_public_lock = threading.Lock()
_public_inflight = False
_public_state_lock = threading.Lock()
_public_bootstrapped = False
_public_refresh_lock = threading.Lock()
_public_ingestion_task: Optional[asyncio.Task] = None


async def refresh_public_cache_once() -> None:
    """
    Esegue un refresh della cache/stato pubblico come fa l'endpoint /auto-brain-public,
    ma utilizzabile anche da un loop in background (startup).
    """
    user_id = PUBLIC_GUEST_ID
    brain = get_or_create_session(user_id)
    if not brain.session_active:
        brain.start_session(100.0)

    state = auto_state.setdefault(
        user_id,
        {"last_poll": datetime.utcnow() - timedelta(seconds=3), "seen": set(), "rows": []}
    )

    # Evita refresh concorrenti
    if not _public_refresh_lock.acquire(blocking=False):
        return

    try:
        is_bootstrap = len(state.get("seen") or set()) == 0
        worker_limit = 40 if is_bootstrap else 25
        payload = await asyncio.to_thread(_run_scrape_worker_fresh, worker_limit)
        fetched_rows = payload.get("rows") or []
        lag_seconds = _time_lag_seconds(fetched_rows)
        parsed_rows = _clean_rows(fetched_rows)

        source_ok_local = True
        source_error_local: Optional[str] = None
        new_count_local = 0

        with _public_state_lock:
            state["last_screenshot"] = payload.get("screenshot")
            state["rows"] = parsed_rows
            state["last_poll"] = datetime.utcnow()

            if not parsed_rows:
                source_ok_local = False
                worker_dbg = str(payload.get("_worker_debug") or "").strip()
                base_msg = "Nessuna riga trovata nella tabella (Cronologia Giocate)"
                source_error_local = f"{base_msg}. Worker: {worker_dbg}" if worker_dbg else base_msg
            else:
                source_error_local = None if (lag_seconds is None or lag_seconds <= MAX_ALLOWED_SOURCE_LAG_SECONDS) else f"Dati in ritardo: ~{lag_seconds}s"

            for row in _rows_oldest_first(parsed_rows):
                dt = str(row.get("datetime_text") or row.get("time") or "").strip().lower()
                slot = str(row.get("slot_result") or "").strip().lower()
                wheel = str(row.get("wheel_result") or "").strip().lower()
                mults = row.get("top_slot_multipliers") or []
                mult_sig = ",".join(str(x) for x in mults)
                key = f"{dt}|{slot}|{wheel}|{mult_sig}"
                if key in state["seen"]:
                    continue
                wheel_seg = row.get("wheel_segment") or row.get("segment")
                slot_seg = row.get("slot_segment")

                if wheel_seg in ALL_SEGMENTS:
                    top = row.get("top_slot_multipliers") or []
                    bonus_data: Dict[str, Any] = {
                        "slot_result": row.get("slot_result"),
                        "wheel_result": row.get("wheel_result"),
                        "slot_segment": slot_seg,
                        "wheel_segment": wheel_seg,
                        "top_slot_multipliers": top,
                    }
                    multiplier_to_send: Optional[int] = None
                    if str(wheel_seg).isdigit():
                        base = int(wheel_seg)
                        bonus_data["base_wheel"] = base
                        multiplier_to_send = max(top) if top else base
                    else:
                        multiplier_to_send = max(top) if top else None

                    if multiplier_to_send is not None:
                        brain.add_spin(segment=wheel_seg, multiplier=multiplier_to_send, mult_segment=wheel_seg, bonus_data=bonus_data)
                    else:
                        brain.add_spin(segment=wheel_seg, bonus_data=bonus_data)

                state["seen"].add(key)
                new_count_local += 1

        # Persist + cache payload
        try:
            existing = _load_public_history()
            existing_keys = {str(x.get("key")) for x in existing if isinstance(x, dict)}
            now_ts = time.time()
            for row in parsed_rows:
                dt = str(row.get("datetime_text") or row.get("time") or "").strip().lower()
                slot = str(row.get("slot_result") or "").strip().lower()
                wheel = str(row.get("wheel_result") or "").strip().lower()
                mults = row.get("top_slot_multipliers") or []
                mult_sig = ",".join(str(x) for x in mults)
                k2 = f"{dt}|{slot}|{wheel}|{mult_sig}"
                if k2 in existing_keys:
                    continue
                existing.append({"key": k2, "observed_at": now_ts, "row": row})
                existing_keys.add(k2)
            _save_public_history(existing)
        except Exception:
            pass

        try:
            _save_public_patterns(brain.pattern_engine.export_patterns())
        except Exception:
            pass

        # Build payload using the same logic as endpoint.
        def _build_payload_local(source_ok: bool, source_error: Optional[str], new_rows_added: int) -> Dict[str, Any]:
            hot_signals = brain.get_best_signals(4)
            next_pick = hot_signals[0] if hot_signals else None
            mini_brains = brain.get_all_brains_status()
            rows_latest = _rows_latest_first(state["rows"])[:600]
            saved_rows = len(_load_public_history())
            chrono = _rows_oldest_first(state.get("rows") or [])
            live_statistics = compute_live_window_stats(chrono, ALL_SEGMENTS, THEORETICAL_PROBS)
            live_statistics["brain_spins_recorded"] = brain.spin_count
            live_statistics["persisted_file_rows"] = saved_rows
            return {
                "scraper_version": SCRAPER_VERSION,
                "debug_now": datetime.utcnow().isoformat(),
                "auto_mode": True,
                "public_mode": True,
                "poll_interval_seconds": 1,
                "source_url": CRAZY_TIME_SOURCE_URL,
                "source_ok": source_ok,
                "source_error": source_error,
                "source_lag_seconds": _time_lag_seconds(state.get("rows") or []),
                "scraper_last_error": getattr(scraper, "last_error", None),
                "scraper_last_rows_count": getattr(scraper, "last_rows_count", None),
                "scraper_module": getattr(scraper, "__class__", type(scraper)).__module__,
                "scraper_rows_count": len(state["rows"]),
                "history_saved_6h_rows": saved_rows,
                "history_saved_rows": saved_rows,
                "last_poll": state["last_poll"].isoformat(),
                "last_screenshot": state.get("last_screenshot"),
                "new_rows_added": new_rows_added,
                "tracked_rows": len(state["seen"]),
                "latest_rows": rows_latest,
                "source_latest_time": (rows_latest[0].get("time") if rows_latest else None),
                "next_hot_signal": next_pick,
                "hot_signals": hot_signals,
                "mini_brains": mini_brains,
                "prediction_accuracy": brain.get_prediction_accuracy(),
                "session": brain.get_session_status(),
                "live_statistics": live_statistics,
            }

        payload_out_local = _build_payload_local(source_ok_local, source_error_local, new_count_local)
        if new_count_local > 0:
            try:
                await notify_hot_signals(payload_out_local.get("hot_signals") or [], source="public")
            except Exception:
                pass
        with _public_lock:
            _public_cache["payload"] = payload_out_local
            _public_cache["ts"] = time.time()
    except Exception as e:
        # Non far crashare il loop, ma esponi l'errore nel payload
        try:
            state_last_poll = None
            try:
                state_last_poll = state.get("last_poll").isoformat() if isinstance(state.get("last_poll"), datetime) else None
            except Exception:
                state_last_poll = None
            err_payload: Dict[str, Any] = {
                "scraper_version": SCRAPER_VERSION,
                "debug_now": datetime.utcnow().isoformat(),
                "auto_mode": True,
                "public_mode": True,
                "poll_interval_seconds": 1,
                "source_url": CRAZY_TIME_SOURCE_URL,
                "source_ok": False,
                "source_error": f"{type(e).__name__}: {str(e)}",
                "source_lag_seconds": None,
                "scraper_last_error": getattr(scraper, "last_error", None),
                "scraper_last_rows_count": getattr(scraper, "last_rows_count", None),
                "scraper_module": getattr(scraper, "__class__", type(scraper)).__module__,
                "scraper_rows_count": len((state.get("rows") or []) if isinstance(state.get("rows"), list) else []),
                "history_saved_6h_rows": len(_load_public_history()),
                "history_saved_rows": len(_load_public_history()),
                "last_poll": state_last_poll or datetime.utcnow().isoformat(),
                "last_screenshot": state.get("last_screenshot") if isinstance(state, dict) else None,
                "new_rows_added": 0,
                "tracked_rows": len(state.get("seen") or set()) if isinstance(state.get("seen"), set) else 0,
                "latest_rows": _rows_latest_first(state.get("rows") or [])[:60] if isinstance(state.get("rows"), list) else [],
                "source_latest_time": None,
                "next_hot_signal": None,
                "hot_signals": [],
                "mini_brains": brain.get_all_brains_status() if brain else {},
                "prediction_accuracy": brain.get_prediction_accuracy() if brain else {},
                "session": brain.get_session_status() if brain else {},
                "live_statistics": {},
            }
            with _public_lock:
                _public_cache["payload"] = err_payload
                _public_cache["ts"] = time.time()
        except Exception:
            pass
    finally:
        try:
            _public_refresh_lock.release()
        except Exception:
            pass


async def _public_ingestion_loop(initial_delay_seconds: float = 0.0) -> None:
    if initial_delay_seconds > 0:
        try:
            await asyncio.sleep(initial_delay_seconds)
        except asyncio.CancelledError:
            return
    while True:
        try:
            await refresh_public_cache_once()
        except asyncio.CancelledError:
            break
        except Exception:
            pass
        await asyncio.sleep(1.0)


def start_public_ingestion_loop(initial_delay_seconds: float = 0.0) -> None:
    global _public_ingestion_task
    if _public_ingestion_task and not _public_ingestion_task.done():
        return
    _public_ingestion_task = asyncio.create_task(_public_ingestion_loop(initial_delay_seconds))
    try:
        def _on_done(t: asyncio.Task) -> None:
            try:
                exc = t.exception()
            except asyncio.CancelledError:
                logger.info("public ingestion loop cancelled")
                return
            except BaseException:
                logger.exception("public ingestion loop done callback failed")
                return
            if exc is not None:
                logger.exception("public ingestion loop crashed", exc_info=exc)
            else:
                logger.info("public ingestion loop finished")
        _public_ingestion_task.add_done_callback(_on_done)
    except Exception:
        logger.exception("failed attaching ingestion loop callback")


async def stop_public_ingestion_loop() -> None:
    global _public_ingestion_task
    t = _public_ingestion_task
    _public_ingestion_task = None
    if not t:
        return
    t.cancel()
    try:
        await t
    except Exception:
        pass

PUBLIC_HISTORY_FILE = Path(__file__).resolve().parent / "public_history.json"
PUBLIC_PATTERNS_FILE = Path(__file__).resolve().parent / "public_patterns.json"
PUBLIC_HISTORY_MAX_ITEMS = 300


def _keep_last_300(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(items, list):
        return []
    # Mantieni l'ordine (oldest->newest) e tieni solo le ultime N.
    return items[-PUBLIC_HISTORY_MAX_ITEMS:]


def _load_public_history() -> List[Dict[str, Any]]:
    try:
        if not PUBLIC_HISTORY_FILE.exists():
            return []
        raw = PUBLIC_HISTORY_FILE.read_text(encoding="utf-8")
        data = json.loads(raw)
        items = data.get("items") if isinstance(data, dict) else []
        if not isinstance(items, list):
            return []
        return _keep_last_300(items)
    except Exception:
        return []


def _save_public_history(items: List[Dict[str, Any]]) -> None:
    try:
        items2 = _keep_last_300(items)
        PUBLIC_HISTORY_FILE.write_text(
            json.dumps({"saved_at": time.time(), "items": items2}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def _load_public_patterns() -> Dict[str, Any]:
    try:
        if not PUBLIC_PATTERNS_FILE.exists():
            return {}
        raw = PUBLIC_PATTERNS_FILE.read_text(encoding="utf-8")
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_public_patterns(patterns: Dict[str, Any]) -> None:
    try:
        if not isinstance(patterns, dict):
            return
        PUBLIC_PATTERNS_FILE.write_text(
            json.dumps({"saved_at": time.time(), "patterns": patterns}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def get_or_create_session(user_id: int) -> BrainEngine:
    """Recupera o crea sessione BrainEngine per utente"""
    if user_id not in active_sessions:
        brain = BrainEngine(username=f"user_{user_id}")
        # Dashboard pubblica: 1 previsione/giro (max EV) per statistiche più stabili (più tentativi).
        if user_id == PUBLIC_GUEST_ID:
            brain.enable_continuous_prediction_stats = True
        active_sessions[user_id] = brain
    return active_sessions[user_id]


def clear_session(user_id: int):
    """Cancella sessione utente"""
    if user_id in active_sessions:
        del active_sessions[user_id]


def _normalize_segment(raw_text: str) -> Optional[str]:
    t = raw_text.lower().strip()
    t_norm = re.sub(r"[\s_\-]+", "", t)
    # Bonus: gestisce varianti testo + nomi file icone (es. crazytime.png, cashhunt.svg, pachiko.png)
    if "cash hunt" in t or "cashhunt" in t_norm:
        return "CH"
    if "coin flip" in t or "coinflip" in t_norm:
        return "CF"
    if "pachinko" in t or "pachiko" in t or "pachinko" in t_norm or "pachiko" in t_norm:
        return "PA"
    if "crazy time" in t or "crazytime" in t_norm:
        return "CT"
    for n in ("10", "5", "2", "1"):
        if re.search(rf"(^|\D){n}x?($|\D)", t):
            return n
    return None


def _clean_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cleaned: List[Dict[str, Any]] = []
    for row in rows:
        slot = str(row.get("slot_result") or "").strip()
        slot_icon = str(row.get("slot_icon") or "").strip()
        wheel = str(row.get("wheel_result") or "").strip()
        wheel_icon = str(row.get("wheel_icon") or "").strip()
        # Per robustezza: per la ruota prioritizza i campi visuali (wheel_icon/wheel_result),
        # poi fallback ai campi legacy che in alcuni casi possono essere sporchi.
        wheel_visual_seg = _normalize_segment(wheel_icon) or _normalize_segment(wheel)
        wheel_legacy_seg = _normalize_segment(str(row.get("wheel_segment") or "")) or _normalize_segment(str(row.get("segment") or ""))
        wheel_seg = wheel_visual_seg or wheel_legacy_seg
        # For "Pachinko + Perso" cases, slot_result may be "Perso" but icon tells the real segment.
        slot_seg = _normalize_segment(slot_icon) or _normalize_segment(slot) or _normalize_segment(str(row.get("slot_segment") or ""))
        seg = wheel_seg or slot_seg
        top = row.get("top_slot_multipliers") or []
        final_mult: Optional[int] = None
        if top:
            final_mult = max(top)
        elif wheel_seg and str(wheel_seg).isdigit():
            final_mult = int(wheel_seg)
        cleaned.append(
            {
                "time": row.get("time"),
                "datetime_text": row.get("datetime_text") or row.get("time"),
                "segment": seg,  # per compat UI (prefer wheel)
                "wheel_segment": wheel_seg,
                "slot_segment": slot_seg,
                "slot_result": slot,
                "slot_icon": slot_icon or None,
                "wheel_result": wheel,
                "wheel_icon": wheel_icon or None,
                "top_slot_multipliers": top,
                "final_multiplier": final_mult,
            }
        )
    return cleaned


def _extract_rows_from_html(html: str) -> List[Dict[str, Any]]:
    """Parser HTML focalizzato su sezione Cronologia Giocate."""
    rows: List[Dict[str, Any]] = []

    compact = re.sub(r"\s+", " ", html, flags=re.MULTILINE)

    low = compact.lower()
    start_idx = low.find("cronologia giocate")
    end_idx = low.find("ultimi top moltiplicatori")
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        compact = compact[start_idx:end_idx]

    times = list(re.finditer(r"\b\d{1,2}:\d{2}\b", compact))

    for m in times:
        start = max(0, m.start() - 240)
        end = min(len(compact), m.end() + 320)
        window = compact[start:end]

        segment = _normalize_segment(window)
        if not segment:
            continue

        multipliers = [int(x) for x in re.findall(r"\b(\d{1,4})x\b", window, flags=re.IGNORECASE)]
        top_slot = multipliers if multipliers else []
        entry = {
            "time": m.group(0),
            "segment": segment,
            "slot_result": segment,
            "wheel_result": segment,
            "top_slot_multipliers": top_slot,
            "raw": window[:220],
        }
        rows.append(entry)

    # Dedup by time+segment and keep latest
    unique: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        key = f"{r['time']}-{r['segment']}"
        unique[key] = r
    return list(unique.values())[-60:]


async def _fetch_live_rows() -> List[Dict[str, Any]]:
    # Lettura diretta HTML: evita blocchi Playwright su Windows.
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=headers) as client:
        response = await client.get(CRAZY_TIME_SOURCE_URL)
        response.raise_for_status()
        html = response.text
    return _extract_rows_from_html(html)


def _fetch_live_rows_sync() -> List[Dict[str, Any]]:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    with httpx.Client(timeout=12, follow_redirects=True, headers=headers) as client:
        response = client.get(CRAZY_TIME_SOURCE_URL)
        response.raise_for_status()
        html = response.text
    return _extract_rows_from_html(html)


# ============================================================================
# ACCESS CONTROL MIDDLEWARE
# ============================================================================

async def verify_tool_access(
    user_id: int,
    db: AsyncSession,
    redirect: bool = False
) -> User:
    """
    Verifica rigorosa accesso al tool.
    BLOCCA accesso se:
    - Utente non ha pagato e trial scaduto
    - Abbonamento scaduto
    - Account inattivo
    
    PERMETTE accesso se:
    - Admin
    - VIP
    - Abbonamento attivo
    - Trial attivo (primi 100 utenti)
    """
    user = await get_user_by_id(db, user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Utente non trovato"
        )
    
    # Admin e VIP sempre accesso
    if user.role in ["admin", "vip"]:
        return user
    
    # Verifica account attivo
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": "Account disattivato",
                "redirect": "/account-disabled",
                "can_access": False
            }
        )
    
    # Verifica accesso
    can_access = user.can_access_tool()
    
    if not can_access:
        # Determina messaggio appropriato
        if user.subscription_status == "none":
            message = "Per utilizzare il tool devi attivare un abbonamento"
            redirect_url = "/pricing"
        elif user.subscription_status == "expired":
            message = "Il tuo abbonamento è scaduto. Rinnova per continuare."
            redirect_url = "/pricing"
        elif user.subscription_status == "cancelled":
            message = "Abbonamento cancellato. Riattiva per continuare."
            redirect_url = "/pricing"
        else:
            message = "Accesso negato. Abbonamento richiesto."
            redirect_url = "/pricing"
        
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": message,
                "redirect": redirect_url,
                "can_access": False,
                "subscription_status": user.subscription_status,
                "trial_end": user.trial_end.isoformat() if user.trial_end else None
            }
        )
    
    return user


# ============================================================================
# SCHEMAS
# ============================================================================

class StartSessionRequest(BaseModel):
    bankroll: float = Field(..., gt=0, description="Bankroll iniziale")


class AddSpinRequest(BaseModel):
    segment: str = Field(..., description="Segmento uscito (1,2,5,10,CF,CH,PA,CT)")
    multiplier: Optional[int] = Field(None, description="Moltiplicatore Top Slot")
    mult_segment: Optional[str] = Field(None, description="Segmento del moltiplicatore")
    bonus_data: Optional[Dict[str, Any]] = Field(None, description="Dati bonus")


class UpdateBankrollRequest(BaseModel):
    amount: float = Field(..., description="Importo vincita (+) o perdita (-)")


class SessionResponse(BaseModel):
    active: bool
    spin_count: int
    bankroll_start: float
    bankroll_current: float
    profit: float
    profit_percent: float
    warning: Optional[str]
    stop: bool


class DecisionResponse(BaseModel):
    action: str
    segment: Optional[str]
    confidence: float
    ev: float
    suggested_stake: float
    risk_level: str
    reason: str
    alternatives: List[Dict]


# ============================================================================
# ROUTES
# ============================================================================

@router.get("/access-status")
async def check_access_status(
    request: Request,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Verifica stato accesso al tool"""
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Utente non trovato")
    
    return {
        "can_access": user.can_access_tool(),
        "role": user.role,
        "subscription_status": user.subscription_status,
        "is_trial_active": user.is_trial_active(),
        "trial_end": user.trial_end.isoformat() if user.trial_end else None,
        "subscription_end": user.subscription_current_period_end.isoformat() if user.subscription_current_period_end else None,
    }


@router.get("/casino-source")
async def get_casino_source_data(
    request: Request,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Recupera e sintetizza i dati pubblici dalla pagina Crazy Time."""
    await verify_tool_access(user_id, db)

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(CRAZY_TIME_SOURCE_URL)
        response.raise_for_status()
        html = response.text

    clean_text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
    clean_text = re.sub(r"<style[\s\S]*?</style>", " ", clean_text, flags=re.IGNORECASE)
    clean_text = re.sub(r"<[^>]+>", " ", clean_text)
    clean_text = re.sub(r"\s+", " ", clean_text).strip()

    def extract_block(keyword: str, span: int = 420) -> str:
        idx = clean_text.lower().find(keyword.lower())
        if idx == -1:
            return ""
        return clean_text[idx: idx + span].strip()

    return {
        "source_url": CRAZY_TIME_SOURCE_URL,
        "fetched_at": datetime.utcnow().isoformat(),
        "summary": {
            "intro": extract_block("Crazy Time è un gioco dal vivo"),
            "history": extract_block("Cronologia Giocate"),
            "top_slot": extract_block("Top Slot Abbinata Risultato Ruota"),
            "bonus_coin_flip": extract_block("Coin flip"),
            "bonus_cash_hunt": extract_block("Cash Hunt"),
            "bonus_pachinko": extract_block("Pachinko"),
            "bonus_crazy_time": extract_block("Crazy Time Gioco Bonus"),
            "faq": extract_block("Statistiche Crazy Time FAQs", span=650),
        }
    }


@router.get("/auto-brain")
async def auto_brain_status(
    request: Request,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Modalità automatica:
    - ogni 2 secondi legge la pagina sorgente
    - aggiunge nuovi spin nel BrainEngine
    - restituisce segnali caldi e ultime righe cronologia
    """
    await verify_tool_access(user_id, db)
    brain = get_or_create_session(user_id)

    if not brain.session_active:
        brain.start_session(100.0)

    state = auto_state.setdefault(
        user_id,
        {"last_poll": datetime.utcnow() - timedelta(seconds=3), "seen": set(), "rows": []}
    )

    now = datetime.utcnow()
    # Se non abbiamo ancora righe, poll immediatamente (bootstrap UI + segnali).
    should_poll = (not state.get("rows")) or (now - state["last_poll"]).total_seconds() >= 2
    parsed_rows: List[Dict[str, Any]] = state["rows"]
    new_count = 0
    source_ok = True
    source_error = None

    if should_poll:
        try:
            payload = await asyncio.to_thread(_run_scrape_worker_fresh, 80)
            fetched_rows = payload.get("rows") or []
            lag_seconds = _time_lag_seconds(fetched_rows)
            parsed_rows = _clean_rows(fetched_rows)
            state["last_screenshot"] = payload.get("screenshot")
            state["rows"] = parsed_rows
            state["last_poll"] = now
            if not parsed_rows:
                source_ok = False
                worker_dbg = str(payload.get("_worker_debug") or "").strip()
                base_msg = "Nessuna riga trovata nella tabella (Cronologia Giocate)"
                source_error = f"{base_msg}. Worker: {worker_dbg}" if worker_dbg else base_msg
            else:
                source_error = None if (lag_seconds is None or lag_seconds <= MAX_ALLOWED_SOURCE_LAG_SECONDS) else f"Dati in ritardo: ~{lag_seconds}s"
        except Exception as exc:
            source_ok = False
            source_error = str(exc)

        for row in parsed_rows:
            # Dedup robusto: la stessa "ora" può ripetersi (es. 14:48) -> includiamo contenuto della riga.
            dt = str(row.get("datetime_text") or row.get("time") or "").strip().lower()
            slot = str(row.get("slot_result") or "").strip().lower()
            wheel = str(row.get("wheel_result") or "").strip().lower()
            mults = row.get("top_slot_multipliers") or []
            mult_sig = ",".join(str(x) for x in mults)
            key = f"{dt}|{slot}|{wheel}|{mult_sig}"
            if key in state["seen"]:
                continue
            wheel_seg = row.get("wheel_segment") or row.get("segment")
            slot_seg = row.get("slot_segment")
            slot_raw = str(row.get("slot_result") or "").strip().lower()

            # Regole (come richiesto):
            # - Esito ruota arriva sempre (wheel_seg).
            # - Per NUMERI (1/2/5/10): il valore finale lo prendiamo DIRETTAMENTE dalla colonna "Moltip." della pagina.
            #   Il sito fa già il calcolo (es. ruota=10 -> Moltip.=10X; se top slot coincide -> Moltip.=20X ecc.).
            # - Per BONUS: i moltiplicatori li prendiamo dalla pagina (range/lista); usiamo max(top) come valore da inviare,
            #   e salviamo min/max/lista in bonus_data.
            if wheel_seg in ALL_SEGMENTS:
                top = row.get("top_slot_multipliers") or []
                bonus_data: Dict[str, Any] = {
                    "slot_result": row.get("slot_result"),
                    "wheel_result": row.get("wheel_result"),
                    "slot_segment": slot_seg,
                    "wheel_segment": wheel_seg,
                    "top_slot_multipliers": top,
                }

                multiplier_to_send: Optional[int] = None

                if str(wheel_seg).isdigit():
                    base = int(wheel_seg)
                    bonus_data["base_wheel"] = base
                    if top:
                        bonus_data["min_multiplier"] = min(top)
                        bonus_data["max_multiplier"] = max(top)
                        bonus_data["final_multiplier"] = max(top)
                        multiplier_to_send = max(top)
                    else:
                        # fallback se la pagina non mostra Moltip. per qualche motivo
                        bonus_data["final_multiplier"] = base
                        multiplier_to_send = base
                else:
                    # bonus
                    if top:
                        bonus_data["min_multiplier"] = min(top)
                        bonus_data["max_multiplier"] = max(top)
                        bonus_data["final_multiplier"] = max(top)
                        multiplier_to_send = max(top)
                    else:
                        bonus_data["final_multiplier"] = None
                        multiplier_to_send = None

                if multiplier_to_send is not None:
                    brain.add_spin(segment=wheel_seg, multiplier=multiplier_to_send, mult_segment=wheel_seg, bonus_data=bonus_data)
                else:
                    brain.add_spin(segment=wheel_seg, bonus_data=bonus_data)
            state["seen"].add(key)
            new_count += 1

    hot_signals = brain.get_best_signals(4)
    next_pick = hot_signals[0] if hot_signals else None

    return {
        "scraper_version": SCRAPER_VERSION,
        "debug_now": datetime.utcnow().isoformat(),
        "auto_mode": True,
        "poll_interval_seconds": 2,
        "source_url": CRAZY_TIME_SOURCE_URL,
        "source_ok": source_ok,
        "source_error": source_error,
        "source_lag_seconds": _time_lag_seconds(state.get("rows") or []),
        "scraper_last_error": getattr(scraper, "last_error", None),
        "scraper_last_rows_count": getattr(scraper, "last_rows_count", None),
        "scraper_module": getattr(scraper, "__class__", type(scraper)).__module__,
        "last_poll": state["last_poll"].isoformat(),
        "last_screenshot": state.get("last_screenshot"),
        "new_rows_added": new_count,
        "tracked_rows": len(state["seen"]),
        "latest_rows": _rows_latest_first(state["rows"])[:24],
        "source_latest_time": (_rows_latest_first(state["rows"])[0].get("time") if state.get("rows") else None),
        "next_hot_signal": next_pick,
        "hot_signals": hot_signals,
        "session": brain.get_session_status(),
    }


@router.get("/auto-brain-public")
async def auto_brain_public():
    """
    Versione pubblica senza login (solo uso locale/dimostrativo).
    """
    user_id = PUBLIC_GUEST_ID
    brain = get_or_create_session(user_id)

    if not brain.session_active:
        brain.start_session(100.0)

    state = auto_state.setdefault(
        user_id,
        {"last_poll": datetime.utcnow() - timedelta(seconds=3), "seen": set(), "rows": []}
    )

    # Bootstrap from persisted last-6h history (gives confidence immediately after restart).
    global _public_bootstrapped
    if not _public_bootstrapped:
        pat = _load_public_patterns()
        if isinstance(pat, dict) and isinstance(pat.get("patterns"), dict):
            try:
                brain.pattern_engine.import_patterns(pat.get("patterns") or {})
            except Exception:
                pass
        persisted = _load_public_history()
        if persisted:
            # Rebuild state rows and brain spins oldest->newest.
            with _public_state_lock:
                state["rows"] = [it.get("row") for it in persisted if isinstance(it.get("row"), dict)]
                state["seen"] = set(
                    str(it.get("key")) for it in persisted if isinstance(it.get("key"), str) and it.get("key")
                )
                state["last_poll"] = datetime.utcnow()
            # Feed brain with the stored rows (oldest first).
            for it in persisted:
                row = it.get("row")
                if not isinstance(row, dict):
                    continue
                wheel_seg = row.get("wheel_segment") or row.get("segment")
                if wheel_seg not in ALL_SEGMENTS:
                    continue
                top = row.get("top_slot_multipliers") or []
                bonus_data: Dict[str, Any] = {
                    "slot_result": row.get("slot_result"),
                    "wheel_result": row.get("wheel_result"),
                    "slot_segment": row.get("slot_segment"),
                    "wheel_segment": wheel_seg,
                    "top_slot_multipliers": top,
                }
                mult: Optional[int] = None
                if str(wheel_seg).isdigit():
                    base = int(wheel_seg)
                    bonus_data["base_wheel"] = base
                    mult = max(top) if top else base
                else:
                    mult = max(top) if top else None
                if mult is not None:
                    brain.add_spin(segment=wheel_seg, multiplier=mult, mult_segment=wheel_seg, bonus_data=bonus_data)
                else:
                    brain.add_spin(segment=wheel_seg, bonus_data=bonus_data)
        _public_bootstrapped = True

    def _build_payload(source_ok: bool, source_error: Optional[str], new_rows_added: int) -> Dict[str, Any]:
        hot_signals = brain.get_best_signals(4)
        next_pick = hot_signals[0] if hot_signals else None
        mini_brains = brain.get_all_brains_status()
        # Return full 6h history (capped for UI/perf).
        rows_latest = _rows_latest_first(state["rows"])[:600]
        saved_rows = len(_load_public_history())
        chrono = _rows_oldest_first(state.get("rows") or [])
        live_statistics = compute_live_window_stats(chrono, ALL_SEGMENTS, THEORETICAL_PROBS)
        live_statistics["brain_spins_recorded"] = brain.spin_count
        live_statistics["persisted_file_rows"] = saved_rows
        return {
            "scraper_version": SCRAPER_VERSION,
            "debug_now": datetime.utcnow().isoformat(),
            "auto_mode": True,
            "public_mode": True,
            "poll_interval_seconds": 1,
            "source_url": CRAZY_TIME_SOURCE_URL,
            "source_ok": source_ok,
            "source_error": source_error,
            "source_lag_seconds": _time_lag_seconds(state.get("rows") or []),
            "scraper_last_error": getattr(scraper, "last_error", None),
            "scraper_last_rows_count": getattr(scraper, "last_rows_count", None),
            "scraper_module": getattr(scraper, "__class__", type(scraper)).__module__,
            "scraper_rows_count": len(state["rows"]),
            # Backward compatibility key (old name), and new generic key.
            "history_saved_6h_rows": saved_rows,
            "history_saved_rows": saved_rows,
            "last_poll": state["last_poll"].isoformat(),
            "last_screenshot": state.get("last_screenshot"),
            "new_rows_added": new_rows_added,
            "tracked_rows": len(state["seen"]),
            "latest_rows": rows_latest,
            "source_latest_time": (rows_latest[0].get("time") if rows_latest else None),
            "next_hot_signal": next_pick,
            "hot_signals": hot_signals,
            "mini_brains": mini_brains,
            "prediction_accuracy": brain.get_prediction_accuracy(),
            "session": brain.get_session_status(),
            "live_statistics": live_statistics,
        }

    # Always return cached payload immediately if present.
    with _public_lock:
        cached = _public_cache.get("payload")
        cached_ts = float(_public_cache.get("ts") or 0.0)

    now = datetime.utcnow()
    should_poll = (not state.get("rows")) or (now - state["last_poll"]).total_seconds() >= 1
    can_refresh = _public_refresh_lock.acquire(blocking=False) if should_poll else False

    if should_poll and can_refresh:
        async def _refresh_public_once():
            source_ok_local = True
            source_error_local: Optional[str] = None
            new_count_local = 0
            try:
                is_bootstrap = len(state.get("seen") or set()) == 0
                worker_limit = 40 if is_bootstrap else 25
                payload = await asyncio.to_thread(_run_scrape_worker_fresh, worker_limit)
                fetched_rows = payload.get("rows") or []
                lag_seconds = _time_lag_seconds(fetched_rows)
                parsed_rows = _clean_rows(fetched_rows)

                with _public_state_lock:
                    state["last_screenshot"] = payload.get("screenshot")
                    state["rows"] = parsed_rows
                    state["last_poll"] = datetime.utcnow()

                    if not parsed_rows:
                        source_ok_local = False
                        worker_dbg = str(payload.get("_worker_debug") or "").strip()
                        base_msg = "Nessuna riga trovata nella tabella (Cronologia Giocate)"
                        source_error_local = f"{base_msg}. Worker: {worker_dbg}" if worker_dbg else base_msg
                    else:
                        source_error_local = None if (lag_seconds is None or lag_seconds <= MAX_ALLOWED_SOURCE_LAG_SECONDS) else f"Dati in ritardo: ~{lag_seconds}s"

                    for row in _rows_oldest_first(parsed_rows):
                        dt = str(row.get("datetime_text") or row.get("time") or "").strip().lower()
                        slot = str(row.get("slot_result") or "").strip().lower()
                        wheel = str(row.get("wheel_result") or "").strip().lower()
                        mults = row.get("top_slot_multipliers") or []
                        mult_sig = ",".join(str(x) for x in mults)
                        key = f"{dt}|{slot}|{wheel}|{mult_sig}"
                        if key in state["seen"]:
                            continue
                        wheel_seg = row.get("wheel_segment") or row.get("segment")
                        slot_seg = row.get("slot_segment")

                        if wheel_seg in ALL_SEGMENTS:
                            top = row.get("top_slot_multipliers") or []
                            bonus_data: Dict[str, Any] = {
                                "slot_result": row.get("slot_result"),
                                "wheel_result": row.get("wheel_result"),
                                "slot_segment": slot_seg,
                                "wheel_segment": wheel_seg,
                                "top_slot_multipliers": top,
                            }
                            multiplier_to_send: Optional[int] = None
                            if str(wheel_seg).isdigit():
                                base = int(wheel_seg)
                                bonus_data["base_wheel"] = base
                                multiplier_to_send = max(top) if top else base
                            else:
                                multiplier_to_send = max(top) if top else None

                            if multiplier_to_send is not None:
                                brain.add_spin(segment=wheel_seg, multiplier=multiplier_to_send, mult_segment=wheel_seg, bonus_data=bonus_data)
                            else:
                                brain.add_spin(segment=wheel_seg, bonus_data=bonus_data)

                        state["seen"].add(key)
                        new_count_local += 1

                    try:
                        existing = _load_public_history()
                        existing_keys = {str(x.get("key")) for x in existing if isinstance(x, dict)}
                        now_ts = time.time()
                        for row in parsed_rows:
                            dt = str(row.get("datetime_text") or row.get("time") or "").strip().lower()
                            slot = str(row.get("slot_result") or "").strip().lower()
                            wheel = str(row.get("wheel_result") or "").strip().lower()
                            mults = row.get("top_slot_multipliers") or []
                            mult_sig = ",".join(str(x) for x in mults)
                            k2 = f"{dt}|{slot}|{wheel}|{mult_sig}"
                            if k2 in existing_keys:
                                continue
                            existing.append({"key": k2, "observed_at": now_ts, "row": row})
                            existing_keys.add(k2)
                        _save_public_history(existing)
                    except Exception:
                        pass

                    try:
                        _save_public_patterns(brain.pattern_engine.export_patterns())
                    except Exception:
                        pass

                    payload_out_local = _build_payload(source_ok_local, source_error_local, new_count_local)
                    if new_count_local > 0:
                        try:
                            await notify_hot_signals(payload_out_local.get("hot_signals") or [], source="public")
                        except Exception:
                            pass
                    with _public_lock:
                        _public_cache["payload"] = payload_out_local
                        _public_cache["ts"] = time.time()
            except Exception as e:
                payload_out_local = _build_payload(False, str(e), 0)
                with _public_lock:
                    _public_cache["payload"] = payload_out_local
                    _public_cache["ts"] = time.time()
            finally:
                _public_refresh_lock.release()

        asyncio.create_task(_refresh_public_once())

    if cached:
        # Evita di servire cache vecchia quando la sorgente e' vuota/stale.
        cache_age = time.time() - cached_ts
        has_rows = bool((cached or {}).get("latest_rows"))
        # Se abbiamo righe, serviamo la cache; se non abbiamo righe, serviamo comunque la cache
        # perché contiene lo stato più recente (inclusi eventuali errori di scrape).
        if has_rows or cache_age <= 2.0:
            return cached
        return cached

    # No cached data yet: return fast “empty but valid” payload; background thread will fill it.
    # Importante: se non abbiamo righe, non segnare la fonte come OK.
    # Mostra un messaggio utile in UI mentre il refresh in background prova a riempire la cache.
    fallback_err = getattr(scraper, "last_error", None) or "Inizializzazione sorgente in corso..."
    return _build_payload(False, fallback_err, 0)


@router.post("/session/start")
async def start_session(
    request: Request,
    session_data: StartSessionRequest,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Avvia nuova sessione di gioco.
    Richiede abbonamento attivo o trial valido.
    """
    # Verifica accesso rigorosa
    user = await verify_tool_access(user_id, db)
    
    # Crea o resetta sessione
    brain = get_or_create_session(user_id)
    brain.start_session(session_data.bankroll)
    
    return {
        "message": "Sessione avviata",
        "session": brain.get_session_status()
    }


@router.post("/session/end")
async def end_session(
    request: Request,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Termina sessione e restituisce statistiche"""
    # Verifica accesso
    user = await verify_tool_access(user_id, db)
    
    brain = get_or_create_session(user_id)
    stats = brain.end_session()
    
    # Cancella sessione
    clear_session(user_id)
    
    return {
        "message": "Sessione terminata",
        "statistics": stats
    }


@router.get("/session/status")
async def get_session_status(
    request: Request,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
) -> SessionResponse:
    """Restituisce stato sessione corrente"""
    # Verifica accesso
    user = await verify_tool_access(user_id, db)
    
    brain = get_or_create_session(user_id)
    status_data = brain.get_session_status()
    
    return SessionResponse(**status_data)


@router.post("/spin")
async def add_spin(
    request: Request,
    spin_data: AddSpinRequest,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Registra un nuovo giro e ottiene decisione.
    Richiede sessione attiva.
    """
    # Verifica accesso
    user = await verify_tool_access(user_id, db)
    
    # Validazione segmento
    if spin_data.segment not in ALL_SEGMENTS:
        raise HTTPException(
            status_code=400,
            detail=f"Segmento non valido. Valori: {', '.join(ALL_SEGMENTS)}"
        )
    
    brain = get_or_create_session(user_id)
    
    try:
        result = brain.add_spin(
            segment=spin_data.segment,
            multiplier=spin_data.multiplier,
            mult_segment=spin_data.mult_segment,
            bonus_data=spin_data.bonus_data
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/bankroll/update")
async def update_bankroll(
    request: Request,
    update_data: UpdateBankrollRequest,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Aggiorna bankroll (vincita o perdita)"""
    # Verifica accesso
    user = await verify_tool_access(user_id, db)
    
    brain = get_or_create_session(user_id)
    brain.bankroll_engine.update_bankroll(update_data.amount)
    
    return {
        "message": "Bankroll aggiornata",
        "session": brain.get_session_status()
    }


@router.get("/decision", response_model=DecisionResponse)
async def get_decision(
    request: Request,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Ottiene decisione corrente del MetaBrain"""
    # Verifica accesso
    user = await verify_tool_access(user_id, db)
    
    brain = get_or_create_session(user_id)
    decision = brain.get_meta_decision()
    
    return DecisionResponse(**decision)


@router.get("/signals")
async def get_signals(
    request: Request,
    top_n: int = 3,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Restituisce migliori segnali attivi"""
    # Verifica accesso
    user = await verify_tool_access(user_id, db)
    
    brain = get_or_create_session(user_id)
    signals = brain.get_best_signals(top_n)
    
    return {"signals": signals}


@router.get("/brains")
async def get_all_brains_status(
    request: Request,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Restituisce stato di tutti i MiniBrains"""
    # Verifica accesso
    user = await verify_tool_access(user_id, db)
    
    brain = get_or_create_session(user_id)
    statuses = brain.get_all_brains_status()
    
    return {"brains": statuses}


@router.get("/brain/{segment}")
async def get_brain_status(
    request: Request,
    segment: str,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Restituisce stato di un MiniBrain specifico"""
    # Verifica accesso
    user = await verify_tool_access(user_id, db)
    
    if segment not in ALL_SEGMENTS:
        raise HTTPException(status_code=400, detail="Segmento non valido")
    
    brain = get_or_create_session(user_id)
    status = brain.get_brain_status(segment)
    
    return {"brain": status}


@router.get("/history")
async def get_spin_history(
    request: Request,
    count: int = 20,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Restituisce storico spin"""
    # Verifica accesso
    user = await verify_tool_access(user_id, db)
    
    brain = get_or_create_session(user_id)
    history = brain.get_last_spins(count)
    
    return {"history": history}


@router.get("/patterns")
async def get_learned_patterns(
    request: Request,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Restituisce pattern appresi"""
    # Verifica accesso
    user = await verify_tool_access(user_id, db)
    
    brain = get_or_create_session(user_id)
    patterns = brain.get_learned_patterns()
    
    return {"patterns": patterns}


@router.get("/ev/{segment}")
async def calculate_ev(
    request: Request,
    segment: str,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Calcola EV per un segmento"""
    # Verifica accesso
    user = await verify_tool_access(user_id, db)
    
    if segment not in ALL_SEGMENTS:
        raise HTTPException(status_code=400, detail="Segmento non valido")
    
    brain = get_or_create_session(user_id)
    ev = brain.calculate_ev(segment)
    
    return {"segment": segment, "ev": ev}


@router.get("/stakes/{segment}")
async def calculate_stakes(
    request: Request,
    segment: str,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Calcola stakes progressivi per un segmento"""
    # Verifica accesso
    user = await verify_tool_access(user_id, db)
    
    if segment not in ALL_SEGMENTS:
        raise HTTPException(status_code=400, detail="Segmento non valido")
    
    brain = get_or_create_session(user_id)
    stakes = brain.calculate_stakes(segment)
    
    return {"segment": segment, "stakes": stakes}
