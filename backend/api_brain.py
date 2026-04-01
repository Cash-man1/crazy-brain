"""
API Brain Engine - Crazy Time Tool
Accesso controllato rigorosamente lato backend
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import re
import httpx
from live_scraper import scraper

from database import get_db, User, get_user_by_id
from security import get_current_user_id, get_client_ip, limiter
from brain_engine import BrainEngine, ALL_SEGMENTS

router = APIRouter(prefix="/brain", tags=["Crazy Time Tool"])
CRAZY_TIME_SOURCE_URL = "https://www.casino.org/casinoscores/it/crazy-time/"
SCRAPER_VERSION = "2026-04-01-v4"


# ============================================================================
# SESSION STORAGE (In-memory per semplicità, usare Redis in produzione)
# ============================================================================

# Store sessioni attive: {user_id: BrainEngine}
active_sessions: Dict[int, BrainEngine] = {}
auto_state: Dict[int, Dict[str, Any]] = {}
PUBLIC_GUEST_ID = 0


def get_or_create_session(user_id: int) -> BrainEngine:
    """Recupera o crea sessione BrainEngine per utente"""
    if user_id not in active_sessions:
        active_sessions[user_id] = BrainEngine(username=f"user_{user_id}")
    return active_sessions[user_id]


def clear_session(user_id: int):
    """Cancella sessione utente"""
    if user_id in active_sessions:
        del active_sessions[user_id]


def _normalize_segment(raw_text: str) -> Optional[str]:
    t = raw_text.lower()
    if "cash hunt" in t:
        return "CH"
    if "coin flip" in t:
        return "CF"
    if "pachinko" in t:
        return "PA"
    if "crazy time" in t:
        return "CT"
    for n in ("10", "5", "2", "1"):
        if re.search(rf"(^|\D){n}x?($|\D)", t):
            return n
    return None


def _clean_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cleaned: List[Dict[str, Any]] = []
    for row in rows:
        slot = str(row.get("slot_result") or "")
        wheel = str(row.get("wheel_result") or "")
        seg = row.get("segment") or _normalize_segment(wheel) or _normalize_segment(slot)
        if seg not in ALL_SEGMENTS:
            continue
        cleaned.append(
            {
                "time": row.get("time"),
                "segment": seg,
                "slot_result": seg,
                "wheel_result": seg,
                "top_slot_multipliers": row.get("top_slot_multipliers") or [],
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
    - ogni 6 secondi legge la pagina sorgente
    - aggiunge nuovi spin nel BrainEngine
    - restituisce segnali caldi e ultime righe cronologia
    """
    await verify_tool_access(user_id, db)
    brain = get_or_create_session(user_id)

    if not brain.session_active:
        brain.start_session(100.0)

    state = auto_state.setdefault(
        user_id,
        {"last_poll": datetime.utcnow() - timedelta(seconds=7), "seen": set(), "rows": []}
    )

    now = datetime.utcnow()
    should_poll = (now - state["last_poll"]).total_seconds() >= 6
    parsed_rows: List[Dict[str, Any]] = state["rows"]
    new_count = 0
    source_ok = True
    source_error = None

    if should_poll:
        try:
            fetched_rows = await _fetch_live_rows()
            parsed_rows = _clean_rows(fetched_rows)
            state["rows"] = parsed_rows
            state["last_poll"] = now
            if parsed_rows:
                source_error = None
        except Exception as exc:
            source_ok = False
            source_error = str(exc)

        for row in parsed_rows:
            key = f"{row.get('time')}-{row.get('segment')}"
            if key in state["seen"]:
                continue
            seg = row.get("segment")
            if seg not in ALL_SEGMENTS:
                continue

            top = row.get("top_slot_multipliers") or []
            if top:
                brain.add_spin(segment=seg, multiplier=max(top), mult_segment=seg)
            else:
                brain.add_spin(segment=seg)
            state["seen"].add(key)
            new_count += 1

    hot_signals = brain.get_best_signals(4)
    next_pick = hot_signals[0] if hot_signals else None

    return {
        "scraper_version": SCRAPER_VERSION,
        "debug_now": datetime.utcnow().isoformat(),
        "auto_mode": True,
        "poll_interval_seconds": 6,
        "source_url": CRAZY_TIME_SOURCE_URL,
        "source_ok": source_ok,
        "source_error": source_error,
        "last_poll": state["last_poll"].isoformat(),
        "new_rows_added": new_count,
        "tracked_rows": len(state["seen"]),
        "latest_rows": list(reversed(state["rows"][-12:])),
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
        {"last_poll": datetime.utcnow() - timedelta(seconds=7), "seen": set(), "rows": []}
    )

    now = datetime.utcnow()
    should_poll = (now - state["last_poll"]).total_seconds() >= 6
    parsed_rows: List[Dict[str, Any]] = state["rows"]
    new_count = 0
    source_ok = True
    source_error = None

    if should_poll:
        try:
            fetched_rows = await _fetch_live_rows()
            parsed_rows = _clean_rows(fetched_rows)
            state["rows"] = parsed_rows
            state["last_poll"] = now
            if parsed_rows:
                source_error = None
        except Exception as exc:
            source_ok = False
            source_error = str(exc)

        for row in parsed_rows:
            key = f"{row.get('time')}-{row.get('segment')}"
            if key in state["seen"]:
                continue
            seg = row.get("segment")
            if seg not in ALL_SEGMENTS:
                continue

            top = row.get("top_slot_multipliers") or []
            if top:
                brain.add_spin(segment=seg, multiplier=max(top), mult_segment=seg)
            else:
                brain.add_spin(segment=seg)
            state["seen"].add(key)
            new_count += 1

    hot_signals = brain.get_best_signals(4)
    next_pick = hot_signals[0] if hot_signals else None
    mini_brains = brain.get_all_brains_status()

    return {
        "scraper_version": SCRAPER_VERSION,
        "debug_now": datetime.utcnow().isoformat(),
        "auto_mode": True,
        "public_mode": True,
        "poll_interval_seconds": 6,
        "source_url": CRAZY_TIME_SOURCE_URL,
        "source_ok": source_ok,
        "source_error": source_error,
        "scraper_rows_count": len(state["rows"]),
        "last_poll": state["last_poll"].isoformat(),
        "new_rows_added": new_count,
        "tracked_rows": len(state["seen"]),
        "latest_rows": list(reversed(state["rows"][-12:])),
        "next_hot_signal": next_pick,
        "hot_signals": hot_signals,
        "mini_brains": mini_brains,
        "session": brain.get_session_status(),
    }


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
