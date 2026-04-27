"""
API Brain Engine - Crazy Time Tool (local-only).
"""
from fastapi import APIRouter
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, timezone
import time
import re
import httpx
import json
import asyncio
import subprocess
import sys
from pathlib import Path
from live_scraper import scraper
import threading
import os
import logging

from brain_engine import BrainEngine, ALL_SEGMENTS, THEORETICAL_PROBS
from live_window_stats import compute_live_window_stats
from live_data_pipeline import (
    apply_brain_spin,
    row_dedupe_key,
    row_valid_for_brain,
    rows_newest_first,
    rows_oldest_first,
    time_lag_seconds as pipeline_time_lag_seconds,
)

router = APIRouter(prefix="/brain", tags=["Crazy Time Tool"])
logger = logging.getLogger(__name__)
CRAZY_TIME_SOURCE_URL = "https://www.casino.org/casinoscores/it/crazy-time/"
SCRAPER_VERSION = "2026-04-11-v5-pipeline-utc"
_public_cached_payload: Optional[Dict[str, Any]] = None
_public_cached_ts: float = 0.0


def public_cache_load() -> tuple[Optional[Dict[str, Any]], float]:
    return _public_cached_payload, _public_cached_ts


def public_cache_store(payload: Optional[Dict[str, Any]], ts: Optional[float] = None) -> None:
    global _public_cached_payload, _public_cached_ts
    _public_cached_payload = payload
    _public_cached_ts = float(time.time() if ts is None else ts)


def _iso_utc_z(dt: Optional[datetime] = None) -> str:
    """ISO-8601 UTC con suffisso Z (evita ambiguità nel browser)."""
    if dt is None:
        dt = datetime.now(timezone.utc)
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")
SCRAPE_WORKER = Path(__file__).resolve().parent / "scrape_worker.py"
WORKER_PYTHON = Path(__file__).resolve().parent.parent / ".venv" / "Scripts" / "python.exe"
MAX_ALLOWED_SOURCE_LAG_SECONDS = 20
# Modalità low-latency: un solo tentativo per ciclo (evita accumulo ritardi lunghi).
SCRAPE_RETRY_ATTEMPTS = 1
SOURCE_FAILURE_THRESHOLD = 3
_evolution_blocked_until: Optional[datetime] = None


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = (os.getenv(name, str(default)) or "").strip()
    try:
        value = int(raw)
    except Exception:
        value = default
    return max(minimum, min(value, maximum))


# File storico / pattern (usati anche da reset avvio)
PUBLIC_HISTORY_FILE = Path(__file__).resolve().parent / "public_history.json"
PUBLIC_PATTERNS_FILE = Path(__file__).resolve().parent / "public_patterns.json"

# Finestra sul disco: default 4000 righe (minimo richiesto utente); solo le piu' recenti dalla pagina.
PUBLIC_HISTORY_MAX_ITEMS = max(4000, min(int(os.getenv("PUBLIC_HISTORY_MAX_ITEMS", "4000")), 20000))

# Bootstrap: prendi sempre almeno tanto quanto la finestra disco (di solito 5000 righe scrape).
PUBLIC_BOOTSTRAP_WORKER_LIMIT = _env_int(
    "PUBLIC_BOOTSTRAP_WORKER_LIMIT",
    max(5000, PUBLIC_HISTORY_MAX_ITEMS),
    max(4000, PUBLIC_HISTORY_MAX_ITEMS),
    20000,
)
PUBLIC_LIVE_WORKER_LIMIT = _env_int("PUBLIC_LIVE_WORKER_LIMIT", 120, 20, 5000)
PUBLIC_DEEP_BACKFILL_INTERVAL_SECONDS = _env_int("PUBLIC_DEEP_BACKFILL_INTERVAL_SECONDS", 90, 10, 900)
EVOLUTION_BLOCK_COOLDOWN_SECONDS = _env_int("EVOLUTION_BLOCK_COOLDOWN_SECONDS", 3600, 60, 86400)
PUBLIC_BOOTSTRAP_WARMUP_LIMIT = _env_int("PUBLIC_BOOTSTRAP_WARMUP_LIMIT", 800, 200, 2000)
# Snapshot su disco solo se lo scrape ha davvero riempito la tabella (evita wipe con ~30 righe da API/HTML).
PUBLIC_HISTORY_SNAPSHOT_MIN_ROWS = _env_int(
    "PUBLIC_HISTORY_SNAPSHOT_MIN_ROWS",
    max(600, PUBLIC_HISTORY_MAX_ITEMS // 8),
    80,
    min(15000, PUBLIC_HISTORY_MAX_ITEMS),
)


def _run_scrape_worker(limit: int = 60, hours_override: Optional[int] = None) -> Dict[str, Any]:
    python_bin = str(WORKER_PYTHON) if WORKER_PYTHON.exists() else sys.executable
    cmd = [
        python_bin,
        str(SCRAPE_WORKER),
        "--limit",
        str(limit),
        "--screenshot-prefix",
        "cronologia",
    ]
    if hours_override and int(hours_override) > 0:
        cmd += ["--hours", str(int(hours_override))]
    # Per limiti alti (storico profondo) Playwright richiede più tempo.
    if limit <= 120:
        timeout_sec = 90
    elif limit <= 1000:
        timeout_sec = 150
    else:
        # Storico profondo: scroll lungo sul sito (possono servire molti minuti).
        timeout_sec = max(900, int(os.getenv("SCRAPER_DEEP_TIMEOUT_SECONDS", "1200")))
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"worker rc={proc.returncode}")
    payload = json.loads(proc.stdout)
    debug_stderr = (proc.stderr or "").strip()
    if debug_stderr:
        payload["_worker_debug"] = debug_stderr[-2000:]
    return payload


def _scrape_hours_for_phase(is_bootstrap: bool) -> int:
    """
    Boot iniziale con finestra lunga, poi finestra più corta e reattiva.
    - SCRAPER_CRONOLOGIA_HOURS_BOOTSTRAP (default 72)
    - SCRAPER_CRONOLOGIA_HOURS_LIVE (default 6)
    """
    key = "SCRAPER_CRONOLOGIA_HOURS_BOOTSTRAP" if is_bootstrap else "SCRAPER_CRONOLOGIA_HOURS_LIVE"
    raw = (os.getenv(key) or os.getenv("SCRAPER_CRONOLOGIA_HOURS") or ("72" if is_bootstrap else "6")).strip()
    try:
        hours = int(raw)
    except ValueError:
        hours = 72 if is_bootstrap else 6
    if hours not in (1, 6, 12, 24, 48, 72):
        hours = 72 if is_bootstrap else 6
    return hours


def _run_scrape_worker_fresh(
    limit: int,
    *,
    is_bootstrap: bool = False,
    force_playwright: bool = False,
) -> Dict[str, Any]:
    """
    Esegue lo scrape e, se la sorgente e' in ritardo oltre soglia, riprova subito
    scegliendo il payload con lag migliore.

    Ordine: 1) API JSON Evolution; 2) worker Playwright (se abilitato).
    force_playwright: salta Evolution (es. storico disco ancora vuoto: l'API spesso resta ~30 righe).
    """
    last_worker_error: Optional[str] = None

    global _evolution_blocked_until
    evo_enabled = os.getenv("SCRAPER_USE_EVOLUTION_API", "0").strip().lower() not in ("0", "false", "no")
    evo_blocked = isinstance(_evolution_blocked_until, datetime) and datetime.utcnow() < _evolution_blocked_until
    if force_playwright:
        evo_enabled = False
    if evo_enabled and not evo_blocked:
        try:
            from crazytime_api import fetch_evolution_crazytime_rows

            api_rows = fetch_evolution_crazytime_rows(limit=limit)
            if api_rows:
                return {
                    "rows": api_rows,
                    "screenshot": None,
                    "_worker_debug": "source=evolution-api (api-cs.casino.org)",
                }
        except Exception as exc:
            last_worker_error = f"evolution-api: {type(exc).__name__}: {exc}"
            # Se la sorgente risponde 403, sospendi Evolution per un po' e usa Playwright.
            if "403" in str(exc):
                _evolution_blocked_until = datetime.utcnow() + timedelta(seconds=EVOLUTION_BLOCK_COOLDOWN_SECONDS)
    elif evo_enabled and evo_blocked:
        wait_s = int((_evolution_blocked_until - datetime.utcnow()).total_seconds()) if _evolution_blocked_until else 0
        last_worker_error = f"evolution-api: temporarily disabled after 403 ({max(0, wait_s)}s remaining)"

    pw_ok = os.getenv("SCRAPER_PLAYWRIGHT_FALLBACK", "1").strip().lower() not in ("0", "false", "no")
    if not pw_ok:
        diag = "Playwright fallback disabilitato (usare Evolution API e/o Redis worker)"
        if last_worker_error:
            diag += f" | {last_worker_error}"
        return {"rows": [], "screenshot": None, "_worker_debug": diag}

    best_payload: Optional[Dict[str, Any]] = None
    best_rows: List[Dict[str, Any]] = []
    best_lag: Optional[int] = None

    hours_override = _scrape_hours_for_phase(is_bootstrap)
    for _ in range(max(1, SCRAPE_RETRY_ATTEMPTS)):
        try:
            payload = _run_scrape_worker(limit=limit, hours_override=hours_override)
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


def _public_history_ready_flag(saved_rows: int) -> bool:
    return saved_rows >= PUBLIC_HISTORY_MAX_ITEMS


def _select_public_worker_limit(state: Dict[str, Any]) -> int:
    """
    Backfill a step per non restare minuti con UI a 0:
    - fase warmup: limite ridotto per ottenere prime centinaia di righe rapidamente
    - fase intermedia: limite medio
    - fase finale: limite bootstrap pieno fino a raggiungere capienza su disco
    """
    try:
        saved_rows = len(_load_public_history())
    except Exception:
        saved_rows = 0
    if saved_rows <= 0:
        state["last_deep_backfill_at"] = datetime.utcnow()
        return min(PUBLIC_BOOTSTRAP_WORKER_LIMIT, PUBLIC_BOOTSTRAP_WARMUP_LIMIT)
    mid_target = min(PUBLIC_HISTORY_MAX_ITEMS, max(PUBLIC_BOOTSTRAP_WARMUP_LIMIT * 2, 1500))
    if saved_rows < mid_target:
        state["last_deep_backfill_at"] = datetime.utcnow()
        return min(PUBLIC_BOOTSTRAP_WORKER_LIMIT, 2000)
    if saved_rows < PUBLIC_HISTORY_MAX_ITEMS:
        state["last_deep_backfill_at"] = datetime.utcnow()
        return PUBLIC_BOOTSTRAP_WORKER_LIMIT
    return PUBLIC_LIVE_WORKER_LIMIT


def _time_lag_seconds(rows: List[Dict[str, Any]]) -> Optional[int]:
    lag = pipeline_time_lag_seconds(rows)
    if lag is not None:
        return lag
    # Se non abbiamo timestamp UTC affidabile, non stimare il lag da sola HH:MM:
    # puo' produrre falsi ritardi enormi (timezone/giorno diverso).
    return None


def _rows_latest_first(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if any(r.get("settled_at_utc") for r in rows):
        return rows_newest_first(rows)
    def key(r: Dict[str, Any]) -> int:
        t = str(r.get("time") or "")
        m = re.match(r"^(\d{1,2}):(\d{2})$", t)
        if not m:
            return -1
        return int(m.group(1)) * 60 + int(m.group(2))
    return sorted(rows, key=key, reverse=True)


def _rows_oldest_first(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if any(r.get("settled_at_utc") for r in rows):
        return rows_oldest_first(rows)
    return list(reversed(_rows_latest_first(rows)))


# ============================================================================
# SESSION STORAGE (In-memory per semplicità, usare Redis in produzione)
# ============================================================================

# Store sessioni attive: {user_id: BrainEngine}
active_sessions: Dict[int, BrainEngine] = {}
auto_state: Dict[int, Dict[str, Any]] = {}
PUBLIC_GUEST_ID = 0

# Public autopoll cache: keep responses fast even at 1s refresh.
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
        {
            "last_poll": datetime.utcnow() - timedelta(seconds=3),
            "seen": set(),
            "rows": [],
            "consecutive_failures": 0,
            "last_deep_backfill_at": datetime.utcnow() - timedelta(seconds=PUBLIC_DEEP_BACKFILL_INTERVAL_SECONDS),
        }
    )

    # Evita refresh concorrenti
    if not _public_refresh_lock.acquire(blocking=False):
        return

    try:
        is_bootstrap = len(state.get("seen") or set()) == 0
        worker_limit = _select_public_worker_limit(state)
        try:
            saved_rows_hint = len(_load_public_history())
        except Exception:
            saved_rows_hint = 0
        force_pw = saved_rows_hint < PUBLIC_HISTORY_MAX_ITEMS
        payload = await asyncio.to_thread(
            _run_scrape_worker_fresh,
            worker_limit,
            is_bootstrap=is_bootstrap,
            force_playwright=force_pw,
        )
        fetched_rows = payload.get("rows") or []
        lag_seconds = _time_lag_seconds(fetched_rows)
        parsed_rows = _clean_rows(fetched_rows)

        source_ok_local = True
        source_error_local: Optional[str] = None
        new_count_local = 0

        with _public_state_lock:
            state["last_screenshot"] = payload.get("screenshot")
            state["last_poll"] = datetime.utcnow()

            if not parsed_rows:
                state["consecutive_failures"] = int(state.get("consecutive_failures") or 0) + 1
                worker_dbg = str(payload.get("_worker_debug") or "").strip()
                base_msg = "Nessuna riga trovata nella tabella (Cronologia Giocate)"
                if state.get("rows") and state["consecutive_failures"] < SOURCE_FAILURE_THRESHOLD:
                    source_ok_local = True
                    source_error_local = (
                        f"Fonte intermittente: fallimento {state['consecutive_failures']}/{SOURCE_FAILURE_THRESHOLD-1}, uso ultimo buffer valido."
                    )
                else:
                    source_ok_local = False
                    source_error_local = f"{base_msg}. Worker: {worker_dbg}" if worker_dbg else base_msg
            else:
                state["rows"] = parsed_rows
                state["consecutive_failures"] = 0
                source_error_local = None if (lag_seconds is None or lag_seconds <= MAX_ALLOWED_SOURCE_LAG_SECONDS) else f"Dati in ritardo: ~{lag_seconds}s"

            for row in _rows_oldest_first(parsed_rows):
                key = row_dedupe_key(row)
                if key in state["seen"]:
                    continue
                wheel_seg = row.get("wheel_segment") or row.get("segment")
                slot_seg = row.get("slot_segment")
                if not row_valid_for_brain(row, wheel_seg):
                    logger.warning("public ingest: scarto riga non valida per brain wheel_seg=%s", wheel_seg)
                    state["seen"].add(key)
                    continue
                apply_brain_spin(brain, str(wheel_seg), slot_seg, row)
                state["seen"].add(key)
                new_count_local += 1

        # Persist + cache payload (finestra fresca dopo scrape profondo)
        try:
            _persist_public_history(parsed_rows, worker_limit)
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
                "debug_now": _iso_utc_z(),
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
                "public_history_max_items": PUBLIC_HISTORY_MAX_ITEMS,
                "public_history_ready": _public_history_ready_flag(saved_rows),
                "scraper_cronologia_hours_hint": int(os.getenv("SCRAPER_CRONOLOGIA_HOURS", "6") or 6),
                "last_poll": _iso_utc_z(state["last_poll"]),
                "last_screenshot": state.get("last_screenshot"),
                "new_rows_added": new_rows_added,
                "tracked_rows": len(state["seen"]),
                "latest_rows": rows_latest,
                "source_latest_time": (rows_latest[0].get("time") if rows_latest else None),
                "source_latest_settled_utc": (rows_latest[0].get("settled_at_utc") if rows_latest else None),
                "source_consecutive_failures": int(state.get("consecutive_failures") or 0),
                "next_hot_signal": next_pick,
                "hot_signals": hot_signals,
                "mini_brains": mini_brains,
                "prediction_accuracy": brain.get_prediction_accuracy(),
                "session": brain.get_session_status(),
                "live_statistics": live_statistics,
            }

        payload_out_local = _build_payload_local(source_ok_local, source_error_local, new_count_local)
        public_cache_store(payload_out_local)
    except Exception as e:
        # Non far crashare il loop, ma esponi l'errore nel payload
        try:
            state_last_poll = None
            try:
                state_last_poll = _iso_utc_z(state.get("last_poll")) if isinstance(state.get("last_poll"), datetime) else None
            except Exception:
                state_last_poll = None
            try:
                _saved_err = len(_load_public_history())
            except Exception:
                _saved_err = 0
            err_payload: Dict[str, Any] = {
                "scraper_version": SCRAPER_VERSION,
                "debug_now": _iso_utc_z(),
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
                "history_saved_6h_rows": _saved_err,
                "history_saved_rows": _saved_err,
                "public_history_max_items": PUBLIC_HISTORY_MAX_ITEMS,
                "public_history_ready": _public_history_ready_flag(_saved_err),
                "last_poll": state_last_poll or _iso_utc_z(),
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
            public_cache_store(err_payload)
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
        # Evita di accodare scrape troppo ravvicinati (RAM su Render Free).
        await asyncio.sleep(3.0)


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


def _snapshot_public_history_items(parsed_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Ultime PUBLIC_HISTORY_MAX_ITEMS righe (piu' recenti), ordine cronologico sul disco."""
    if not parsed_rows:
        return []
    newest_first = _rows_latest_first(parsed_rows)
    newest_slice = newest_first[:PUBLIC_HISTORY_MAX_ITEMS]
    oldest_first = list(reversed(newest_slice))
    ts = time.time()
    out: List[Dict[str, Any]] = []
    for row in oldest_first:
        out.append({"key": row_dedupe_key(row), "observed_at": ts, "row": row})
    return out


def _persist_public_history(parsed_rows: List[Dict[str, Any]], worker_limit: int) -> None:
    """
    Scrape profondo: rimpiazza il file con lo snapshot fresco dalla pagina (finestra N).
    Aggiornamenti live piccoli: merge + trim (non cancellare migliaia di righe per un poll da 120/240).
    """
    if not parsed_rows:
        return
    wants_deep = worker_limit >= max(PUBLIC_BOOTSTRAP_WORKER_LIMIT // 2, 2000) or len(parsed_rows) >= (
        PUBLIC_HISTORY_MAX_ITEMS - 500
    )
    # Sostituisci il file solo se abbiamo abbastanza righe; altrimenti merge (evita erase con ~26–40 righe).
    deep_fetch = wants_deep and len(parsed_rows) >= PUBLIC_HISTORY_SNAPSHOT_MIN_ROWS
    if deep_fetch:
        _save_public_history(_snapshot_public_history_items(parsed_rows))
        return
    try:
        existing = _load_public_history()
        existing_keys = {str(x.get("key")) for x in existing if isinstance(x, dict)}
        now_ts = time.time()
        for row in parsed_rows:
            k2 = row_dedupe_key(row)
            if k2 in existing_keys:
                continue
            existing.append({"key": k2, "observed_at": now_ts, "row": row})
            existing_keys.add(k2)
        _save_public_history(existing)
    except Exception:
        pass


def reset_persistent_public_store_on_startup() -> None:
    """
    Ad ogni riavvio: svuota solo public_history.json (giri ruota). I pattern restano sempre su disco:
    il cervello li aggiorna/scarta quando sono obsoleti — non si cancellano qui.
    """
    global _public_bootstrapped
    reset_h = os.getenv("PUBLIC_RESET_HISTORY_ON_START", "1").strip().lower() in {"1", "true", "yes", "on"}
    if reset_h:
        try:
            PUBLIC_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            PUBLIC_HISTORY_FILE.write_text(
                json.dumps({"saved_at": time.time(), "items": [], "reset_on_startup": True}, ensure_ascii=False),
                encoding="utf-8",
            )
            logger.info("public_history.json azzerato all'avvio (solo storico giri; pattern preservati)")
        except Exception:
            logger.exception("reset public_history.json fallito")
        _public_bootstrapped = False


def _keep_last_public_history(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not isinstance(items, list):
        return []
    # Finestra scorrevole: ordine oldest->newest; ogni salvataggio tiene solo le ultime N (le nuove restano, le vecchie cadono).
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
        return _keep_last_public_history(items)
    except Exception:
        return []


def _save_public_history(items: List[Dict[str, Any]]) -> None:
    try:
        items2 = _keep_last_public_history(items)
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
    # Crazy Bonus (Top Slot) non è il numero in "x5"
    if "crazy bonus" in t or "crazybonus" in t_norm:
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
        moltip_chain = row.get("moltip_chain")
        max_m = row.get("max_multiplier")
        top_only = row.get("top_slot_multiplier")
        # Colonna "Moltip.": Evolution espone maxMultiplier; dalla tabella HTML spesso compaiono piu "Nx"
        # nella stessa cella (es. boost slot + finale): per allinearsi al sito usiamo l'ultimo, non il max.
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

        # Moltip.: da evolution-api arriva gia moltip_chain / maxMultiplier (match Top Slot incluso).
        # Senza moltip_chain (DOM): usa i molti dalla cella o, se vuota, base esito numerico.
        moltip_display: List[Any]
        if moltip_chain is not None:
            moltip_display = list(moltip_chain)
        else:
            moltip_display = list(top)
        if moltip_chain is None and wheel_seg in ("1", "2", "5", "10") and not moltip_display:
            try:
                moltip_display = [int(wheel_seg)]
            except (TypeError, ValueError):
                pass

        cleaned.append(
            {
                "event_id": row.get("event_id") or "",
                "settled_at_utc": row.get("settled_at_utc") or "",
                "time": row.get("time"),
                "datetime_text": row.get("datetime_text") or row.get("time"),
                "segment": seg,  # per compat UI (prefer wheel)
                "wheel_segment": wheel_seg,
                "slot_segment": slot_seg,
                "slot_result": slot,
                "slot_icon": slot_icon or None,
                "wheel_result": wheel,
                "wheel_icon": wheel_icon or None,
                "moltip_chain": moltip_display,
                "top_slot_multipliers": moltip_display,
                "top_slot_multiplier": top_only if top_only is not None else None,
                "max_multiplier": int(max_m) if max_m is not None else None,
                "final_multiplier": final_mult,
                "data_source": row.get("data_source") or "legacy",
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


@router.get("/auto-brain-public")
async def auto_brain_public():
    """
    Versione pubblica locale (solo uso locale/dimostrativo).
    """
    user_id = PUBLIC_GUEST_ID
    brain = get_or_create_session(user_id)

    if not brain.session_active:
        brain.start_session(100.0)

    state = auto_state.setdefault(
        user_id,
        {
            "last_poll": datetime.utcnow() - timedelta(seconds=3),
            "seen": set(),
            "rows": [],
            "consecutive_failures": 0,
            "last_deep_backfill_at": datetime.utcnow() - timedelta(seconds=PUBLIC_DEEP_BACKFILL_INTERVAL_SECONDS),
        }
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
                raw_hist = [it.get("row") for it in persisted if isinstance(it.get("row"), dict)]
                state["rows"] = _clean_rows(raw_hist)
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
                slot_seg = row.get("slot_segment")
                if not row_valid_for_brain(row, wheel_seg):
                    continue
                apply_brain_spin(brain, str(wheel_seg), slot_seg, row)
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
            "debug_now": _iso_utc_z(),
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
            "public_history_max_items": PUBLIC_HISTORY_MAX_ITEMS,
            "public_history_ready": _public_history_ready_flag(saved_rows),
            "scraper_cronologia_hours_hint": int(os.getenv("SCRAPER_CRONOLOGIA_HOURS", "6") or 6),
            "last_poll": _iso_utc_z(state["last_poll"]),
            "last_screenshot": state.get("last_screenshot"),
            "new_rows_added": new_rows_added,
            "tracked_rows": len(state["seen"]),
            "latest_rows": rows_latest,
            "source_latest_time": (rows_latest[0].get("time") if rows_latest else None),
            "source_latest_settled_utc": (rows_latest[0].get("settled_at_utc") if rows_latest else None),
            "source_consecutive_failures": int(state.get("consecutive_failures") or 0),
            "next_hot_signal": next_pick,
            "hot_signals": hot_signals,
            "mini_brains": mini_brains,
            "prediction_accuracy": brain.get_prediction_accuracy(),
            "session": brain.get_session_status(),
            "live_statistics": live_statistics,
        }

    # Always return cached payload immediately if present.
    cached, cached_ts = public_cache_load()

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
                worker_limit = _select_public_worker_limit(state)
                try:
                    saved_rows_hint = len(_load_public_history())
                except Exception:
                    saved_rows_hint = 0
                force_pw = saved_rows_hint < PUBLIC_HISTORY_MAX_ITEMS
                payload = await asyncio.to_thread(
                    _run_scrape_worker_fresh,
                    worker_limit,
                    is_bootstrap=is_bootstrap,
                    force_playwright=force_pw,
                )
                fetched_rows = payload.get("rows") or []
                lag_seconds = _time_lag_seconds(fetched_rows)
                parsed_rows = _clean_rows(fetched_rows)

                with _public_state_lock:
                    state["last_screenshot"] = payload.get("screenshot")
                    state["last_poll"] = datetime.utcnow()

                    if not parsed_rows:
                        state["consecutive_failures"] = int(state.get("consecutive_failures") or 0) + 1
                        worker_dbg = str(payload.get("_worker_debug") or "").strip()
                        base_msg = "Nessuna riga trovata nella tabella (Cronologia Giocate)"
                        if state.get("rows") and state["consecutive_failures"] < SOURCE_FAILURE_THRESHOLD:
                            source_ok_local = True
                            source_error_local = (
                                f"Fonte intermittente: fallimento {state['consecutive_failures']}/{SOURCE_FAILURE_THRESHOLD-1}, uso ultimo buffer valido."
                            )
                        else:
                            source_ok_local = False
                            source_error_local = f"{base_msg}. Worker: {worker_dbg}" if worker_dbg else base_msg
                    else:
                        state["rows"] = parsed_rows
                        state["consecutive_failures"] = 0
                        source_error_local = None if (lag_seconds is None or lag_seconds <= MAX_ALLOWED_SOURCE_LAG_SECONDS) else f"Dati in ritardo: ~{lag_seconds}s"

                    for row in _rows_oldest_first(parsed_rows):
                        key = row_dedupe_key(row)
                        if key in state["seen"]:
                            continue
                        wheel_seg = row.get("wheel_segment") or row.get("segment")
                        slot_seg = row.get("slot_segment")
                        if not row_valid_for_brain(row, wheel_seg):
                            logger.warning("auto_brain_public refresh: scarto riga wheel_seg=%s", wheel_seg)
                            state["seen"].add(key)
                            continue
                        apply_brain_spin(brain, str(wheel_seg), slot_seg, row)
                        state["seen"].add(key)
                        new_count_local += 1

                    try:
                        _persist_public_history(parsed_rows, worker_limit)
                    except Exception:
                        pass

                    try:
                        _save_public_patterns(brain.pattern_engine.export_patterns())
                    except Exception:
                        pass

                    payload_out_local = _build_payload(source_ok_local, source_error_local, new_count_local)
                    public_cache_store(payload_out_local)
            except Exception as e:
                payload_out_local = _build_payload(False, str(e), 0)
                public_cache_store(payload_out_local)
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

    # No cached data yet: se abbiamo gia' righe in memoria (bootstrap da file), usale subito.
    if state.get("rows"):
        return _build_payload(True, None, 0)

    # Se non abbiamo righe, mostra un messaggio utile mentre il refresh prova a riempire la cache.
    fallback_err = getattr(scraper, "last_error", None) or (
        "Avvio: cache pubblica in caricamento (pochi secondi). "
        "Se resta vuoto, controlla log API (Playwright/timeout). "
        f"Ora server UTC: {_iso_utc_z()}"
    )
    return _build_payload(False, fallback_err, 0)

