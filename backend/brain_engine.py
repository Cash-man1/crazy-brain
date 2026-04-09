"""
Brain Engine - Crazy Time Analysis Tool
Adattato per backend FastAPI
"""
import json
import math
import os
import random
import statistics
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple, Any, Set
from collections import deque, defaultdict
from datetime import datetime
from enum import Enum, auto
import copy


# =============================================================================
# CONFIGURAZIONE CRAZY TIME
# =============================================================================

class SegmentType(Enum):
    NUMERO = "numero"
    BONUS = "bonus"

class Phase(Enum):
    APPRENDIMENTO = "apprendimento"
    ATTENZIONE = "attenzione"
    ATTACCO = "attacco"
    CONFERMATO = "confermato"
    STOP = "stop"
    SUCCESSO = "successo"

class SignalType(Enum):
    NESSUNO = "nessuno"
    OSSERVA = "osserva"
    ATTENZIONE = "attenzione"
    ENTRA = "entra"
    HOT = "hot"
    STOP = "stop"
    SUCCESSO = "successo"

# Configurazione segmenti Crazy Time (pesi reali)
SEGMENT_CONFIG = {
    "1": {"type": SegmentType.NUMERO, "weight": 21, "payout": 1, "color": "#4FC3F7"},
    "2": {"type": SegmentType.NUMERO, "weight": 13, "payout": 2, "color": "#FFD54F"},
    "5": {"type": SegmentType.NUMERO, "weight": 7, "payout": 5, "color": "#EF5350"},
    "10": {"type": SegmentType.NUMERO, "weight": 4, "payout": 10, "color": "#AB47BC"},
    "CH": {"type": SegmentType.BONUS, "weight": 2, "payout": 0, "color": "#66BB6A", "name": "Cash Hunt"},
    "CF": {"type": SegmentType.BONUS, "weight": 4, "payout": 0, "color": "#42A5F5", "name": "Coin Flip"},
    "PA": {"type": SegmentType.BONUS, "weight": 2, "payout": 0, "color": "#CE93D8", "name": "Pachinko"},
    "CT": {"type": SegmentType.BONUS, "weight": 1, "payout": 0, "color": "#D32F2F", "name": "Crazy Time"},
}

ALL_SEGMENTS = list(SEGMENT_CONFIG.keys())
NUM_SEGMENTS = ["1", "2", "5", "10"]
BONUS_SEGMENTS = ["CH", "CF", "PA", "CT"]

# Pesi e payout estratti
WEIGHTS = {seg: data["weight"] for seg, data in SEGMENT_CONFIG.items()}
PAYOUTS = {seg: data["payout"] for seg, data in SEGMENT_CONFIG.items()}
TOTAL_WEIGHT = sum(WEIGHTS.values())

# Probabilità teoriche
THEORETICAL_PROBS = {seg: w / TOTAL_WEIGHT for seg, w in WEIGHTS.items()}
EXPECTED_GAPS = {seg: 1 / p for seg, p in THEORETICAL_PROBS.items()}

MINI_BRAIN_LEARNED_FILENAME = "mini_brain_learned.json"
# Peso dei campioni vecchi nella media per il range (half-life in numero di colpi nella finestra).
RANGE_LEARN_HALF_LIFE_SAMPLES = 6.0


def mini_brain_learned_default_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), MINI_BRAIN_LEARNED_FILENAME)


def weighted_mean_spins(samples: List[int], max_take: int = 15, half_life: float = RANGE_LEARN_HALF_LIFE_SAMPLES) -> float:
    """Media pesata: i colpi piu recenti pesano di piu (decadimento esponenziale)."""
    if not samples:
        return 0.0
    recent = samples[-max_take:]
    n = len(recent)
    wsum = 0.0
    tsum = 0.0
    for i, x in enumerate(recent):
        age = (n - 1 - i)
        w = 0.5 ** (age / half_life)
        wsum += w * float(x)
        tsum += w
    return wsum / tsum if tsum > 0 else float(statistics.mean(recent))


def wilson_ci_95(successes: int, attempts: int) -> Optional[Tuple[float, float]]:
    """Intervallo Wilson al 95% per proporzione (None se attempts==0)."""
    if attempts <= 0:
        return None
    z = 1.96
    p = successes / attempts
    denom = 1.0 + z * z / attempts
    center = (p + z * z / (2 * attempts)) / denom
    margin = z * math.sqrt(max(0.0, p * (1 - p) / attempts + z * z / (4 * attempts * attempts))) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def calibration_attack_vs_independent_spins(
    segment: str,
    attempts: int,
    successes: int,
    range_max: int,
    n_sims: int = 400,
) -> Dict[str, Any]:
    """
    Modello nullo: ogni 'attacco' = fino a R spin indipendenti con p teorica del segmento.
    MC leggero (solo se attempts non enorme) + z-score binomiale.
    """
    p = float(THEORETICAL_PROBS.get(segment, 0) or 0)
    R = max(1, min(int(range_max) if range_max else 9, 20))
    p_win = 1.0 - (1.0 - p) ** R if p < 1.0 else 1.0
    out: Dict[str, Any] = {
        "segment": segment,
        "attempts": attempts,
        "successes": successes,
        "range_used": R,
        "p_win_null": round(p_win, 6),
        "observed_rate": None,
        "null_expected_rate": round(p_win, 4),
        "z_score_vs_null": None,
        "mc_p_ge_observed": None,
        "label": "pochi dati",
    }
    if attempts < 1:
        return out
    obs = successes / attempts
    out["observed_rate"] = round(obs, 4)
    if attempts < 3:
        return out
    mu = attempts * p_win
    var = max(1e-12, attempts * p_win * (1.0 - p_win))
    z = (successes - mu) / math.sqrt(var)
    out["z_score_vs_null"] = round(z, 3)
    rng = random.Random((hash(segment) & 0xFFFFFFFF) ^ (attempts << 8) ^ successes)
    sim_cap = min(max(200, n_sims), 320)
    att_mc = min(attempts, 28)
    if att_mc >= 1:
        succ_thr = successes if att_mc == attempts else min(
            att_mc, max(0, (successes * att_mc + attempts // 2) // attempts)
        )
        ge = 0
        for _ in range(sim_cap):
            w = sum(1 for _ in range(att_mc) if rng.random() < p_win)
            if w >= succ_thr:
                ge += 1
        out["mc_p_ge_observed"] = round(ge / sim_cap, 4)
    else:
        out["mc_p_ge_observed"] = None
    pge = out["mc_p_ge_observed"]
    if attempts < 5:
        out["label"] = "pochi dati"
    elif z < 0.5 and (pge is None or pge > 0.22):
        out["label"] = "compatibile con caso"
    elif z < 1.5:
        out["label"] = "debole"
    elif z < 2.5:
        out["label"] = "moderato"
    else:
        out["label"] = "sopra il caso"
    return out


def mini_brain_effective_confidence(state: "MiniBrainState") -> float:
    """Riduce la confidence mostrata/usata se mancano dati (anti overconfidence)."""
    raw = float(state.confidence)
    n_att = int(state.attempts)
    n_lr = len(state.learned_hit_spins)
    cap = 0.40 + 0.55 * min(1.0, n_att / 12.0) * min(1.0, n_lr / 8.0)
    cap = min(0.92, max(0.28, cap))
    return round(min(raw, cap), 4)


def meta_dynamic_min_confidence(state: "MiniBrainState") -> float:
    """Soglia minima piu alta con pochi tentativi o pochi campioni sul range."""
    base = 0.30
    if state.attempts < 5:
        base += 0.06
    if len(state.learned_hit_spins) < 4:
        base += 0.05
    return min(0.52, base)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class SpinRecord:
    """Record di un singolo giro (NON persistente)"""
    giro: int
    segment: str
    timestamp: datetime
    multiplier: Optional[int] = None
    mult_segment: Optional[str] = None
    bonus_data: Optional[Dict] = None
    valore_reale: Optional[float] = None


@dataclass
class PatternData:
    """Dati pattern statistici (PERSISTENTI)"""
    transition_matrix: Dict[str, Dict[str, int]] = field(default_factory=lambda: defaultdict(lambda: defaultdict(int)))
    sequence_counts: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    total_transitions: int = 0
    bigram_probs: Dict[str, Dict[str, float]] = field(default_factory=dict)
    trigram_counts: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    pattern_strength: Dict[str, float] = field(default_factory=dict)
    last_update: Optional[datetime] = None


@dataclass
class MiniBrainState:
    """Stato volatile di un MiniBrain (resetta a sessione)"""
    segment: str
    battery: float = 0.0
    phase: Phase = Phase.APPRENDIMENTO
    confidence: float = 0.0
    gap_current: int = 0
    gap_history: List[int] = field(default_factory=list)
    last_seen: int = 0
    cooldown: float = 0.0
    heat: float = 0.0
    pressure: float = 0.0
    z_score: float = 0.0
    attempts: int = 0
    successes: int = 0
    top_slot_hits: int = 0
    top_slot_multiplier: float = 1.0
    signal: SignalType = SignalType.OSSERVA
    ev_current: float = 0.0
    range_max: int = 0
    range_current: int = 0
    attack_start_spin: int = 0
    # Giri dall'inizio attacco all'uscita del segmento (solo hit in fase attacco/confermato), per adattare il range.
    learned_hit_spins: List[int] = field(default_factory=list)
    learned_last_update: Optional[str] = None


@dataclass
class MetaDecision:
    """Decisione finale del MetaBrain"""
    action: str  # "PLAY", "NO_PLAY", "WAIT"
    segment: Optional[str] = None
    confidence: float = 0.0
    ev: float = 0.0
    suggested_stake: float = 0.0
    risk_level: str = "low"  # low, medium, high
    reason: str = ""
    alternatives: List[Dict] = field(default_factory=list)


@dataclass
class SessionState:
    """Stato sessione (NON persistente)"""
    bankroll_start: float = 0.0
    bankroll_current: float = 0.0
    profit: float = 0.0
    spin_count: int = 0
    start_time: Optional[datetime] = None
    risk_exposure: float = 0.0
    active_signals: int = 0


# =============================================================================
# PATTERN RECOGNITION ENGINE
# =============================================================================

class PatternRecognitionEngine:
    """
    Motore di riconoscimento pattern basato su probabilità condizionali reali.
    Apprende automaticamente pattern ricorrenti senza hardcoding.
    """
    
    MIN_SAMPLES = 50  # Minimo campioni per validare pattern
    SIGNIFICANCE_THRESHOLD = 1.5  # Deviazione significativa dalla teorica
    
    def __init__(self):
        self.data = PatternData()
        self.recent_sequence: deque = deque(maxlen=10)
    
    def record_transition(self, from_seg: str, to_seg: str):
        """Registra una transizione tra segmenti"""
        # Defensive against deserialized plain dicts (after import) that may miss defaultdict behavior.
        if from_seg not in self.data.transition_matrix or not isinstance(self.data.transition_matrix[from_seg], dict):
            self.data.transition_matrix[from_seg] = defaultdict(int)
        if to_seg not in self.data.transition_matrix[from_seg]:
            self.data.transition_matrix[from_seg][to_seg] = 0
        self.data.transition_matrix[from_seg][to_seg] += 1
        self.data.total_transitions += 1
        self.recent_sequence.append(to_seg)
        self._update_probabilities()
        self._detect_sequences()
    
    def _update_probabilities(self):
        """Aggiorna probabilità condizionali P(A|B)"""
        if self.data.total_transitions < self.MIN_SAMPLES:
            return
        new_strength: Dict[str, float] = {}
        for from_seg in ALL_SEGMENTS:
            row_obj = self.data.transition_matrix.get(from_seg, {})
            if not isinstance(row_obj, dict):
                row_obj = {}
            total_from = sum(int(v) for v in row_obj.values() if isinstance(v, (int, float)))
            if total_from > 0:
                self.data.bigram_probs[from_seg] = {}
                for to_seg in ALL_SEGMENTS:
                    count = int(row_obj.get(to_seg, 0))
                    empirical_prob = count / total_from
                    theoretical_prob = THEORETICAL_PROBS[to_seg]
                    
                    # Calcola deviazione significativa
                    if theoretical_prob > 0:
                        deviation = empirical_prob / theoretical_prob
                        if deviation > self.SIGNIFICANCE_THRESHOLD:
                            strength = min(1.0, (deviation - 1) / 2)
                            pattern_key = f"{from_seg}->{to_seg}"
                            new_strength[pattern_key] = strength
                        
                        self.data.bigram_probs[from_seg][to_seg] = empirical_prob
        # Rebuild completo: i pattern non piu significativi vengono rimossi.
        self.data.pattern_strength = new_strength
    
    def _detect_sequences(self):
        """Rileva sequenze di lunghezza 2-3"""
        seq_list = list(self.recent_sequence)
        if len(seq_list) >= 2:
            bigram = "->".join(seq_list[-2:])
            self.data.sequence_counts[bigram] += 1
        
        if len(seq_list) >= 3:
            trigram = "->".join(seq_list[-3:])
            self.data.trigram_counts[trigram] += 1
    
    def get_pattern_influence(self, last_segment: str, target_segment: str) -> float:
        """
        Restituisce influenza del pattern sulla probabilità del target.
        Range: 0-1 (0 = nessuna influenza, 1 = forte influenza)
        """
        if self.data.total_transitions < self.MIN_SAMPLES:
            return 0.0
        
        pattern_key = f"{last_segment}->{target_segment}"
        return self.data.pattern_strength.get(pattern_key, 0.0)
    
    def get_conditional_prob(self, last_segment: str, target_segment: str) -> float:
        """Restituisce P(target | last) se disponibile, altrimenti teorica"""
        if last_segment in self.data.bigram_probs:
            return self.data.bigram_probs[last_segment].get(target_segment, THEORETICAL_PROBS[target_segment])
        return THEORETICAL_PROBS[target_segment]
    
    def export_patterns(self) -> Dict:
        """Esporta pattern per persistenza"""
        return {
            "transition_matrix": dict(self.data.transition_matrix),
            "bigram_probs": self.data.bigram_probs,
            "pattern_strength": self.data.pattern_strength,
            "total_transitions": self.data.total_transitions,
            "last_update": datetime.now().isoformat()
        }
    
    def import_patterns(self, data: Dict):
        """Importa pattern da persistenza"""
        self.data.transition_matrix = defaultdict(lambda: defaultdict(int), data.get("transition_matrix", {}))
        self.data.bigram_probs = data.get("bigram_probs", {})
        self.data.pattern_strength = data.get("pattern_strength", {})
        self.data.total_transitions = data.get("total_transitions", 0)


# =============================================================================
# TOP SLOT ENGINE
# =============================================================================

class TopSlotEngine:
    """
    Gestisce l'impatto dei moltiplicatori Top Slot sulle decisioni.
    Un moltiplicatore che colpisce aumenta significativamente EV e influenza pattern.
    """
    
    def __init__(self):
        self.last_top_slot: Optional[Tuple[str, int]] = None
        self.top_slot_history: List[Dict] = []
    
    def process_top_slot(self, segment: str, multiplier: int) -> Dict:
        """
        Processa un moltiplicatore Top Slot.
        Restituisce impatto sul sistema.
        """
        self.last_top_slot = (segment, multiplier)
        
        impact = {
            "segment": segment,
            "multiplier": multiplier,
            "effective_payout": self._calculate_effective_payout(segment, multiplier),
            "cooldown_boost": min(5, multiplier / 10),  # Cooldown aumenta con moltiplicatore
            "confidence_boost": min(0.3, multiplier / 100),  # Boost confidence
            "ev_multiplier": multiplier if segment in NUM_SEGMENTS else 1.0
        }
        
        self.top_slot_history.append({
            **impact,
            "timestamp": datetime.now().isoformat()
        })
        
        return impact
    
    def _calculate_effective_payout(self, segment: str, multiplier: int) -> float:
        """Calcola payout effettivo considerando moltiplicatore"""
        base_payout = PAYOUTS.get(segment, 0)
        if segment in NUM_SEGMENTS:
            return base_payout * multiplier
        return multiplier  # Per bonus, il moltiplicatore è il payout
    
    def get_top_slot_influence(self, segment: str) -> float:
        """
        Restituisce influenza del last top slot sul segmento.
        Se il top slot ha colpito questo segmento, influenza è alta.
        """
        if not self.last_top_slot:
            return 0.0
        
        last_seg, mult = self.last_top_slot
        if last_seg == segment:
            return min(1.0, mult / 50)  # Influenza proporzionale al moltiplicatore
        return 0.0


# =============================================================================
# EV ENGINE
# =============================================================================

class EVEngine:
    """
    Calcola Expected Value reale per ogni segmento.
    EV = P(win) * payout - (1 - P(win))
    """
    
    def __init__(self, pattern_engine: PatternRecognitionEngine, top_slot_engine: TopSlotEngine):
        self.pattern_engine = pattern_engine
        self.top_slot_engine = top_slot_engine
    
    def calculate_ev(self, segment: str, mini_brain: MiniBrainState, 
                     last_segment: Optional[str] = None) -> float:
        """
        Calcola EV per un segmento considerando tutti i fattori.
        """
        # Probabilità base
        base_prob = THEORETICAL_PROBS[segment]
        
        # Aggiusta probabilità con pattern
        if last_segment:
            pattern_prob = self.pattern_engine.get_conditional_prob(last_segment, segment)
            pattern_influence = self.pattern_engine.get_pattern_influence(last_segment, segment)
            # Media ponderata tra prob base e pattern
            adjusted_prob = base_prob * (1 - pattern_influence) + pattern_prob * pattern_influence
        else:
            adjusted_prob = base_prob
        
        # Aggiusta con confidence del mini brain (versione conservativa con pochi dati)
        confidence_factor = mini_brain_effective_confidence(mini_brain)
        adjusted_prob = adjusted_prob * (1 + confidence_factor * 0.5)
        
        # Cap probabilità a valori ragionevoli
        adjusted_prob = min(0.95, adjusted_prob)
        
        # Payout effettivo
        base_payout = PAYOUTS[segment]
        
        # Se c'è stato un top slot su questo segmento
        top_slot_influence = self.top_slot_engine.get_top_slot_influence(segment)
        if top_slot_influence > 0 and self.top_slot_engine.last_top_slot:
            _, mult = self.top_slot_engine.last_top_slot
            effective_payout = base_payout * mult if segment in NUM_SEGMENTS else mult
        else:
            effective_payout = base_payout
        
        # Formula EV
        ev = (adjusted_prob * effective_payout) - (1 - adjusted_prob)
        
        return round(ev, 4)
    
    def filter_positive_ev(self, evs: Dict[str, float]) -> Dict[str, float]:
        """Filtra solo EV positivi, ordinati per valore"""
        positive = {k: v for k, v in evs.items() if v > 0}
        return dict(sorted(positive.items(), key=lambda x: x[1], reverse=True))


# =============================================================================
# BANKROLL ENGINE
# =============================================================================

class BankrollEngine:
    """
    Gestione professionale bankroll con risk management integrato.
    """
    
    MAX_RISK_PERCENT = 0.30  # Max 30% bankroll a rischio
    MAX_SPIN_PERCENT = 0.10  # Max 10% per spin
    PROGRESSION_FACTOR = 1.25  # Progressione 25%
    
    def __init__(self):
        self.session = SessionState()
    
    def start_session(self, bankroll: float):
        """Avvia nuova sessione"""
        self.session = SessionState(
            bankroll_start=bankroll,
            bankroll_current=bankroll,
            start_time=datetime.now()
        )
    
    def update_bankroll(self, amount: float):
        """Aggiorna bankroll (positivo = vincita)"""
        self.session.bankroll_current += amount
        self.session.profit = self.session.bankroll_current - self.session.bankroll_start
    
    def calculate_stakes(self, segment: str, ev: float, range_estimate: int) -> List[float]:
        """
        Calcola stakes progressivi per un segmento.
        Considera payout, EV, range stimato.
        """
        if self.session.bankroll_current <= 0:
            return []

        # Defensive: avoid division by zero / invalid ranges.
        try:
            range_estimate = int(range_estimate)
        except Exception:
            range_estimate = 1
        if range_estimate <= 0:
            range_estimate = 1
        
        bankroll = self.session.bankroll_current
        max_risk = bankroll * self.MAX_RISK_PERCENT
        max_spin = bankroll * self.MAX_SPIN_PERCENT
        
        # Payout-aware base stake
        payout = PAYOUTS.get(segment, 0)
        if payout > 0:
            # Per numeri, stake inversamente proporzionale al payout
            base_unit = max_risk / (range_estimate * payout)
        else:
            # Per bonus, stake più conservativo
            base_unit = max_risk / (range_estimate * 2)
        
        # EV adjustment
        ev_factor = max(0.5, min(2.0, 1 + ev))
        base_unit *= ev_factor
        
        steps = min(max(range_estimate, 1), 8)
        stakes = []
        current = base_unit
        
        for i in range(steps):
            stake = min(current, max_spin)
            stakes.append(round(stake, 2))
            current *= self.PROGRESSION_FACTOR
        
        return stakes
    
    def get_risk_exposure(self, active_stakes: List[float] = None) -> float:
        """Calcola esposizione rischio totale"""
        if not active_stakes:
            return 0.0
        total = sum(active_stakes)
        return total / self.session.bankroll_current if self.session.bankroll_current > 0 else 1.0
    
    def check_limits(self) -> Dict:
        """Controlla limiti di sessione"""
        if self.session.bankroll_start == 0:
            return {"warning": None, "stop": False}
        
        profit_pct = (self.session.profit / self.session.bankroll_start) * 100
        
        warning = None
        stop = False
        
        if profit_pct <= -50:
            stop = True
            warning = "STOP: Perdita capitale 50%. Sessione terminata."
        elif profit_pct <= -30:
            warning = "WARNING: Perdita 30%. Ridurre esposizione."
        elif profit_pct >= 30:
            warning = "PROFIT: Obiettivo 30% raggiunto. Considerare stop."
        
        return {
            "profit_percent": round(profit_pct, 2),
            "warning": warning,
            "stop": stop
        }


# =============================================================================
# MINI BRAIN
# =============================================================================

class MiniBrain:
    """
    Cervello individuale per un segmento.
    Gestisce metriche statistiche, fasi, confidence.
    """
    
    BATTERY_CHARGE_BASE = 2.0
    BATTERY_CHARGE_PRESSURE = 3.0
    BATTERY_CHARGE_GAP = 5.0
    BATTERY_DECAY_ATTACK = 8.0
    
    def __init__(self, segment: str):
        self.segment = segment
        self.state = MiniBrainState(segment=segment)
        self.expected_gap = EXPECTED_GAPS[segment]
        self.weight = WEIGHTS[segment]
        self.payout = PAYOUTS[segment]
    
    def record_spin(self, is_hit: bool, spin_count: int, 
                    top_slot_impact: Optional[Dict] = None):
        """Registra un giro per questo segmento"""
        if is_hit:
            self._handle_hit(spin_count, top_slot_impact)
        else:
            self._handle_miss(spin_count)
    
    def _handle_hit(self, spin_count: int, top_slot_impact: Optional[Dict]):
        """Gestisce uscita del segmento"""
        # Calcola gap
        if self.state.last_seen > 0:
            gap = spin_count - self.state.last_seen
            self.state.gap_history.append(gap)
            if len(self.state.gap_history) > 50:
                self.state.gap_history.pop(0)
        
        self.state.last_seen = spin_count
        self.state.gap_current = 0
        
        # Cooldown post-hit
        base_cooldown = 5.0
        if top_slot_impact:
            base_cooldown += top_slot_impact.get("cooldown_boost", 0)
        self.state.cooldown = base_cooldown
        
        # Se era in attacco, registra successo
        if self.state.phase in [Phase.ATTACCO, Phase.CONFERMATO]:
            self.state.successes += 1
            self.state.signal = SignalType.SUCCESSO
            # Impara quanti giri sono serviti (range_current = miss dopo ingresso; +1 include il giro di hit).
            spins_to_hit = self.state.range_current + 1
            if 1 <= spins_to_hit <= 30:
                self.state.learned_hit_spins.append(spins_to_hit)
                if len(self.state.learned_hit_spins) > 40:
                    self.state.learned_hit_spins = self.state.learned_hit_spins[-40:]
                self.state.learned_last_update = datetime.now().isoformat()
        
        # Reset fase
        self.state.phase = Phase.APPRENDIMENTO
        self.state.range_current = 0
        self.state.attack_start_spin = 0
        self.state.battery = max(20, self.state.battery - 30)  # Scarica dopo hit
    
    def _handle_miss(self, spin_count: int):
        """Gestisce mancata uscita"""
        self.state.gap_current = spin_count - self.state.last_seen if self.state.last_seen > 0 else spin_count
        self.state.cooldown = max(0, self.state.cooldown - 1)
        
        # Carica battery
        charge = self.BATTERY_CHARGE_BASE
        
        # Bonus per pressure
        pressure_ratio = self.state.gap_current / self.expected_gap
        if pressure_ratio > 0.7:
            charge += self.BATTERY_CHARGE_PRESSURE
        if pressure_ratio > 1.0:
            charge += self.BATTERY_CHARGE_GAP
        
        self.state.battery = min(100, self.state.battery + charge)
        
        # Gestione fasi
        self._update_phase(spin_count)
    
    def _update_phase(self, spin_count: int):
        """Aggiorna fase in base alle condizioni"""
        if self.state.phase == Phase.APPRENDIMENTO:
            if self.state.battery >= 60 and self.state.cooldown <= 0:
                self.state.phase = Phase.ATTENZIONE
                self.state.signal = SignalType.ATTENZIONE
        
        elif self.state.phase == Phase.ATTENZIONE:
            if self.state.battery >= 80 and self.state.confidence > 0.4:
                self._enter_attack(spin_count)
        
        elif self.state.phase in [Phase.ATTACCO, Phase.CONFERMATO]:
            self.state.range_current += 1
            self.state.battery = max(0, self.state.battery - self.BATTERY_DECAY_ATTACK)
            
            if self.state.range_current >= self.state.range_max or self.state.battery <= 20:
                self.state.phase = Phase.STOP
                self.state.signal = SignalType.STOP
    
    def _base_range_max(self) -> int:
        return 6 if self.segment == "CT" else 9

    def _adapt_range_max_from_learning(self) -> int:
        """Abbassa (o rialza dentro il tetto) il range in base alla media dei giri fino all'hit in attacco."""
        base = self._base_range_max()
        samples = self.state.learned_hit_spins
        if len(samples) < 3:
            return base
        mean_spins = weighted_mean_spins(samples, max_take=15, half_life=RANGE_LEARN_HALF_LIFE_SAMPLES)
        # Piccolo margine sopra la media osservata (non stringere troppo al primo colpo).
        target = int(math.ceil(mean_spins + 0.75))
        floor_r = 3 if self.segment == "CT" else 4
        return max(floor_r, min(base, target))

    def _enter_attack(self, spin_count: int):
        """Entra in fase di attacco"""
        self.state.phase = Phase.ATTACCO
        self.state.signal = SignalType.ENTRA
        self.state.range_current = 0
        self.state.range_max = self._adapt_range_max_from_learning()
        self.state.attack_start_spin = spin_count
        self.state.attempts += 1
        
        # Verifica se diventa CONFERMATO
        if self.state.attempts >= 3:
            success_rate = self.state.successes / self.state.attempts
            if success_rate >= 0.4:
                self.state.phase = Phase.CONFERMATO
    
    def update_metrics(self, spin_count: int, last30: deque):
        """Aggiorna metriche statistiche"""
        # Heat (frequenza ultimi 30)
        self.state.heat = list(last30).count(self.segment) / 30 if len(last30) > 0 else 0
        
        # Pressure
        self.state.pressure = min(100, (self.state.gap_current / self.expected_gap) * 50)
        
        # Z-score
        if len(self.state.gap_history) >= 5:
            mean_gap = statistics.mean(self.state.gap_history)
            std_gap = statistics.stdev(self.state.gap_history) if len(self.state.gap_history) > 1 else 1
            if std_gap > 0:
                self.state.z_score = abs((self.state.gap_current - mean_gap) / std_gap)
            else:
                self.state.z_score = 0
        
        # Confidence
        self._calculate_confidence()
    
    def _calculate_confidence(self):
        """Calcola confidence combinando tutti i fattori"""
        # Gap ratio
        gap_ratio = self.state.gap_current / self.expected_gap if self.expected_gap > 0 else 0
        gap_score = min(1.0, gap_ratio / 1.5) * 0.25
        
        # Pressure
        pressure_score = (self.state.pressure / 100) * 0.25
        
        # Heat (inverso - meno uscite recenti = più confidence)
        heat_score = (1 - self.state.heat) * 0.15
        
        # Z-score
        z_score = min(1.0, self.state.z_score / 3) * 0.15
        
        # Cooldown (inverso)
        cooldown_score = (1 - min(1.0, self.state.cooldown / 5)) * 0.10
        
        # Battery
        battery_score = (self.state.battery / 100) * 0.10
        
        # Somma pesata
        confidence = gap_score + pressure_score + heat_score + z_score + cooldown_score + battery_score
        
        # Boost per fase avanzata
        if self.state.phase == Phase.CONFERMATO:
            confidence = min(1.0, confidence * 1.2)
        
        self.state.confidence = round(confidence, 4)
    
    def get_status(self) -> Dict:
        """Restituisce stato completo"""
        att = int(self.state.attempts)
        succ = int(self.state.successes)
        n_lr = len(self.state.learned_hit_spins)
        eff_conf = mini_brain_effective_confidence(self.state)
        ci = wilson_ci_95(succ, att) if att > 0 else None
        cal = calibration_attack_vs_independent_spins(
            self.segment, att, succ, self.state.range_max or self._base_range_max()
        )
        return {
            "segment": self.segment,
            "phase": self.state.phase.value,
            "confidence": eff_conf,
            "confidence_raw": self.state.confidence,
            "battery": round(self.state.battery, 2),
            "gap_current": self.state.gap_current,
            "expected_gap": round(self.expected_gap, 2),
            "pressure": round(self.state.pressure, 2),
            "heat": round(self.state.heat, 3),
            "z_score": round(self.state.z_score, 3),
            "cooldown": round(self.state.cooldown, 2),
            "range": f"{self.state.range_current}/{self.state.range_max}",
            "success_rate": round(succ / att, 3) if att > 0 else 0,
            "attack_attempts": att,
            "attack_successes": succ,
            "attack_success_ci95": [round(ci[0], 3), round(ci[1], 3)] if ci else None,
            "attack_data_sparse": att < 5,
            "range_samples_n": n_lr,
            "learned_last_update": self.state.learned_last_update,
            "calibration_vs_null": cal,
            "signal": self.state.signal.value,
            "ev": self.state.ev_current
        }


# =============================================================================
# META BRAIN
# =============================================================================

class MetaBrain:
    """
    Decisore ufficiale del sistema.
    Legge tutti i MiniBrains, calcola EV, gestisce rischio, decide azione.
    """
    
    EV_THRESHOLD = 0.0  # Solo EV > 0
    MIN_CONFIDENCE = 0.3  # Confidence minima per giocare
    MAX_EXPOSURE = 0.30  # Max esposizione rischio
    
    def __init__(self, mini_brains: Dict[str, MiniBrain], 
                 ev_engine: EVEngine, 
                 bankroll_engine: BankrollEngine,
                 pattern_engine: PatternRecognitionEngine):
        self.mini_brains = mini_brains
        self.ev_engine = ev_engine
        self.bankroll_engine = bankroll_engine
        self.pattern_engine = pattern_engine
        self.last_segment: Optional[str] = None
        self.evs: Dict[str, float] = {}
    
    def evaluate(self, spin_count: int) -> MetaDecision:
        """
        Valuta tutti i segmenti e restituisce decisione finale.
        """
        # Calcola EV per tutti i segmenti
        self.evs = {}
        for seg, brain in self.mini_brains.items():
            ev = self.ev_engine.calculate_ev(seg, brain.state, self.last_segment)
            brain.state.ev_current = ev
            self.evs[seg] = ev
        
        # Filtra EV positivi
        positive_ev = self.ev_engine.filter_positive_ev(self.evs)
        
        # Se nessun EV positivo, non giocare
        if not positive_ev:
            return MetaDecision(
                action="NO_PLAY",
                reason="Nessun EV positivo disponibile",
                ev=0.0,
                confidence=0.0
            )
        
        # Filtra per confidence minima (soglia dinamica + confidence efficace)
        candidates = []
        for seg, ev in positive_ev.items():
            brain = self.mini_brains[seg]
            eff_c = mini_brain_effective_confidence(brain.state)
            need = max(self.MIN_CONFIDENCE, meta_dynamic_min_confidence(brain.state))
            if eff_c >= need:
                candidates.append({
                    "segment": seg,
                    "ev": ev,
                    "confidence": eff_c,
                    "phase": brain.state.phase,
                    "range_max": brain.state.range_max
                })
        
        if not candidates:
            return MetaDecision(
                action="WAIT",
                reason="EV positivi ma confidence insufficiente",
                ev=max(positive_ev.values()),
                confidence=max(
                    mini_brain_effective_confidence(self.mini_brains[s].state) for s in positive_ev.keys()
                )
            )
        
        # Ordina con score composito (piu stabile/preciso): EV + confidence + fase.
        phase_bonus = {
            Phase.CONFERMATO: 0.15,
            Phase.ATTACCO: 0.10,
            Phase.ATTENZIONE: 0.03,
            Phase.APPRENDIMENTO: 0.0,
            Phase.STOP: -0.10,
            Phase.SUCCESSO: 0.05,
        }
        for c in candidates:
            seg = c["segment"]
            pattern_bonus = 0.0
            if self.last_segment:
                pattern_bonus = self.pattern_engine.get_pattern_influence(self.last_segment, seg) * 0.12
            c["score"] = (
                (c["ev"] * 0.7)
                + (c["confidence"] * 0.3)
                + phase_bonus.get(c["phase"], 0.0)
                + pattern_bonus
            )
        candidates.sort(key=lambda x: (x["score"], x["ev"], x["confidence"]), reverse=True)
        best = candidates[0]
        
        # Calcola stakes
        stakes = self.bankroll_engine.calculate_stakes(
            best["segment"], 
            best["ev"], 
            best["range_max"]
        )
        
        # Valuta rischio
        risk_exposure = self.bankroll_engine.get_risk_exposure(stakes)
        risk_level = "low" if risk_exposure < 0.15 else "medium" if risk_exposure < 0.25 else "high"
        
        # Se esposizione troppo alta, riduci o non giocare
        if risk_exposure > self.MAX_EXPOSURE:
            return MetaDecision(
                action="NO_PLAY",
                reason=f"Esposizione rischio troppo alta ({risk_exposure:.1%})",
                ev=best["ev"],
                confidence=best["confidence"]
            )
        
        # Prepara alternative
        alternatives = candidates[1:3] if len(candidates) > 1 else []
        
        return MetaDecision(
            action="PLAY",
            segment=best["segment"],
            ev=best["ev"],
            confidence=best["confidence"],
            suggested_stake=stakes[0] if stakes else 0.0,
            risk_level=risk_level,
            reason=f"EV positivo {best['ev']:.3f} con confidence {best['confidence']:.1%}",
            alternatives=alternatives
        )
    
    def update_last_segment(self, segment: str):
        """Aggiorna ultimo segmento uscito"""
        self.last_segment = segment


# =============================================================================
# BRAIN ENGINE PRINCIPALE (FACADE)
# =============================================================================

class BrainEngine:
    """
    Facade principale del sistema.
    Coordina tutti i componenti e fornisce API pubblica.
    """
    
    def __init__(self, username: str = "player", mini_brain_learned_path: Optional[str] = None):
        self.username = username
        self._mini_brain_learned_path = mini_brain_learned_path or mini_brain_learned_default_path()
        
        # Componenti persistenti (pattern)
        self.pattern_engine = PatternRecognitionEngine()
        self.top_slot_engine = TopSlotEngine()
        
        # Componenti volatili (reset a sessione)
        self.mini_brains: Dict[str, MiniBrain] = {}
        self.ev_engine: Optional[EVEngine] = None
        self.bankroll_engine = BankrollEngine()
        self.meta_brain: Optional[MetaBrain] = None
        
        # Stato sessione
        self.spin_count = 0
        self.history: deque = deque(maxlen=1000)
        self.last30: deque = deque(maxlen=30)
        self.session_active = False
        # Statistiche "selettive": solo hot in attacco / meta PLAY, con finestra a range (tentativi pochi).
        self.prediction_stats: Dict[str, Dict[str, int]] = {
            seg: {"attempts": 0, "hits": 0} for seg in ALL_SEGMENTS
        }
        # Statistiche "continue": ogni giro una sola previsione top (max EV) → ~1 tentativo per giro, stima più rapida.
        self.prediction_stats_continuous: Dict[str, Dict[str, int]] = {
            seg: {"attempts": 0, "hits": 0} for seg in ALL_SEGMENTS
        }
        # Se True, get_prediction_accuracy usa by_segment dalle stats continue; sempre esposte anche quelle selettive.
        self.enable_continuous_prediction_stats: bool = False
        # Predizione "attiva": conta 1 tentativo per chiamata (range), non per giro.
        # {segment: str, expires_spin: int} dove expires_spin è incluso (>= spin_count) per cui la chiamata è valida.
        self._pending_prediction: Optional[Dict[str, Any]] = None

        # Inizializza MiniBrains
        self._init_mini_brains()
        self._load_mini_brain_learned()
    
    def _init_mini_brains(self):
        """Inizializza i 8 MiniBrains"""
        for seg in ALL_SEGMENTS:
            self.mini_brains[seg] = MiniBrain(seg)
        
        self.ev_engine = EVEngine(self.pattern_engine, self.top_slot_engine)
        self.meta_brain = MetaBrain(
            self.mini_brains,
            self.ev_engine,
            self.bankroll_engine,
            self.pattern_engine
        )

    def _load_mini_brain_learned(self):
        """Ripristina solo i campioni per il range adattivo (persistenza tra riavvii)."""
        path = self._mini_brain_learned_path
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return
        segs = data.get("segments") or {}
        for seg, brain in self.mini_brains.items():
            row = segs.get(seg)
            if not isinstance(row, dict):
                continue
            lh = row.get("learned_hit_spins")
            if isinstance(lh, list):
                cleaned: List[int] = []
                for x in lh[-40:]:
                    try:
                        xi = int(x)
                        if 1 <= xi <= 30:
                            cleaned.append(xi)
                    except Exception:
                        pass
                brain.state.learned_hit_spins = cleaned
            lu = row.get("learned_last_update")
            if isinstance(lu, str):
                brain.state.learned_last_update = lu

    def _persist_mini_brain_learned(self):
        path = self._mini_brain_learned_path
        payload: Dict[str, Any] = {
            "version": 1,
            "saved_at": datetime.utcnow().isoformat(),
            "segments": {},
        }
        for seg, brain in self.mini_brains.items():
            payload["segments"][seg] = {
                "learned_hit_spins": list(brain.state.learned_hit_spins),
                "learned_last_update": brain.state.learned_last_update,
            }
        tmp = path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            os.replace(tmp, path)
        except Exception:
            try:
                if os.path.isfile(tmp):
                    os.remove(tmp)
            except Exception:
                pass
    
    # =========================================================================
    # API SESSIONE
    # =========================================================================
    
    def start_session(self, bankroll: float):
        """Avvia nuova sessione (resetta dati volatili)"""
        self.spin_count = 0
        self.history.clear()
        self.last30.clear()
        self.session_active = True
        self.prediction_stats = {seg: {"attempts": 0, "hits": 0} for seg in ALL_SEGMENTS}
        self.prediction_stats_continuous = {seg: {"attempts": 0, "hits": 0} for seg in ALL_SEGMENTS}
        self._pending_prediction = None

        # Reset MiniBrains (ma mantieni pattern); ripristina campioni range da disco
        self._init_mini_brains()
        self._load_mini_brain_learned()
        
        # Start bankroll
        self.bankroll_engine.start_session(bankroll)
    
    def end_session(self) -> Dict:
        """Termina sessione e restituisce statistiche"""
        self.session_active = False
        
        return {
            "spin_count": self.spin_count,
            "bankroll_start": self.bankroll_engine.session.bankroll_start,
            "bankroll_end": self.bankroll_engine.session.bankroll_current,
            "profit": self.bankroll_engine.session.profit,
            "profit_percent": round(
                (self.bankroll_engine.session.profit / self.bankroll_engine.session.bankroll_start * 100), 2
            ) if self.bankroll_engine.session.bankroll_start > 0 else 0,
            "patterns_learned": len(self.pattern_engine.data.pattern_strength)
        }
    
    def _continuous_best_segment(self) -> Optional[str]:
        """Una previsione per giro: segmento con EV massima (stato pre-esito)."""
        if not self.meta_brain:
            return None
        self.meta_brain.evaluate(self.spin_count)
        evs = getattr(self.meta_brain, "evs", None) or {}
        if not evs:
            return None
        best_seg = max(evs.items(), key=lambda kv: (kv[1], kv[0]))[0]
        return best_seg if best_seg in ALL_SEGMENTS else None

    # =========================================================================
    # API SPIN
    # =========================================================================
    
    def add_spin(self, 
                 segment: str,
                 multiplier: Optional[int] = None,
                 mult_segment: Optional[str] = None,
                 bonus_data: Optional[Dict] = None) -> Dict:
        """
        Registra un nuovo giro completo.
        Restituisce decisione del MetaBrain.
        """
        if not self.session_active:
            raise ValueError("Sessione non attiva. Chiama start_session() prima.")

        predicted_top: Optional[str] = None
        predicted_range: Optional[int] = None
        if self.meta_brain:
            hot = self.get_best_signals(1)
            if hot:
                predicted_top = hot[0].get("segment")
                try:
                    predicted_range = int(hot[0].get("range_remaining")) if hot[0].get("range_remaining") is not None else None
                except Exception:
                    predicted_range = None
            else:
                pre_dec = self.meta_brain.evaluate(self.spin_count)
                if pre_dec.action == "PLAY" and pre_dec.segment:
                    predicted_top = pre_dec.segment
                    predicted_range = None

        pred_continuous: Optional[str] = None
        if self.enable_continuous_prediction_stats:
            pred_continuous = self._continuous_best_segment()

        self.spin_count += 1

        if pred_continuous and pred_continuous in ALL_SEGMENTS:
            self.prediction_stats_continuous[pred_continuous]["attempts"] += 1

        # Scadenza chiamata precedente (se il range è finito, azzera).
        if self._pending_prediction and isinstance(self._pending_prediction.get("expires_spin"), int):
            if self.spin_count > int(self._pending_prediction["expires_spin"]):
                self._pending_prediction = None

        # Se la previsione è cambiata (o non c'era), apri una nuova "chiamata" e conta 1 tentativo.
        # Nota: range_remaining = 2 significa valida per questo giro e i prossimi 2 giri => expires = spin_count + 2
        if predicted_top and predicted_top in ALL_SEGMENTS:
            current_seg = (self._pending_prediction or {}).get("segment")
            if current_seg != predicted_top:
                self.prediction_stats[predicted_top]["attempts"] += 1
                expires_spin = self.spin_count + max(int(predicted_range or 0), 0)
                self._pending_prediction = {"segment": predicted_top, "expires_spin": expires_spin}
        
        # Processa Top Slot se presente
        top_slot_impact = None
        if mult_segment and multiplier:
            top_slot_impact = self.top_slot_engine.process_top_slot(mult_segment, multiplier)
        
        # Registra transizione per pattern
        if self.meta_brain.last_segment:
            self.pattern_engine.record_transition(self.meta_brain.last_segment, segment)
        
        # Aggiorna last30
        self.last30.append(segment)
        
        # Crea record
        valore_reale = None
        if mult_segment == segment and multiplier:
            if segment in NUM_SEGMENTS:
                valore_reale = PAYOUTS[segment] * multiplier
            else:
                valore_reale = multiplier
        
        record = SpinRecord(
            giro=self.spin_count,
            segment=segment,
            timestamp=datetime.now(),
            multiplier=multiplier,
            mult_segment=mult_segment,
            bonus_data=bonus_data,
            valore_reale=valore_reale
        )
        self.history.append(record)
        
        # Aggiorna tutti i MiniBrains
        for seg, brain in self.mini_brains.items():
            is_hit = (seg == segment)
            brain.record_spin(is_hit, self.spin_count, top_slot_impact if is_hit else None)
        
        # Aggiorna metriche
        for brain in self.mini_brains.values():
            brain.update_metrics(self.spin_count, self.last30)
        
        # Aggiorna MetaBrain
        self.meta_brain.update_last_segment(segment)
        
        # Ottieni decisione
        decision = self.meta_brain.evaluate(self.spin_count)

        # Se c'è una chiamata attiva e il segmento esce dentro il range => 1 hit e chiudi la chiamata.
        if self._pending_prediction and self._pending_prediction.get("segment") == segment:
            if segment in self.prediction_stats:
                self.prediction_stats[segment]["hits"] += 1
            self._pending_prediction = None

        if pred_continuous and pred_continuous == segment and pred_continuous in self.prediction_stats_continuous:
            self.prediction_stats_continuous[pred_continuous]["hits"] += 1
        
        self._persist_mini_brain_learned()
        
        return {
            "spin": self.spin_count,
            "result": segment,
            "meta_decision": {
                "action": decision.action,
                "segment": decision.segment,
                "ev": decision.ev,
                "confidence": decision.confidence,
                "suggested_stake": decision.suggested_stake,
                "risk_level": decision.risk_level,
                "reason": decision.reason
            },
            "all_evs": self.meta_brain.evs
        }
    
    # =========================================================================
    # API QUERY
    # =========================================================================
    
    def get_meta_decision(self) -> Dict:
        """Restituisce decisione corrente del MetaBrain"""
        if not self.session_active:
            return {"error": "Sessione non attiva"}
        
        decision = self.meta_brain.evaluate(self.spin_count)
        return {
            "action": decision.action,
            "segment": decision.segment,
            "confidence": decision.confidence,
            "ev": decision.ev,
            "suggested_stake": decision.suggested_stake,
            "risk_level": decision.risk_level,
            "reason": decision.reason,
            "alternatives": decision.alternatives
        }
    
    def get_prediction_accuracy(self) -> Dict[str, Any]:
        """Per ogni segmento: tentativi/indovinati; modalità continua = 1 pick/giro (max EV), selettiva = hot/meta."""
        def _pack(stats: Dict[str, Dict[str, int]]) -> Dict[str, Any]:
            out: Dict[str, Any] = {}
            for seg in ALL_SEGMENTS:
                a = int(stats[seg]["attempts"])
                h = int(stats[seg]["hits"])
                out[seg] = {
                    "attempts": a,
                    "hits": h,
                    "rate": (h / a) if a else None,
                }
            return out

        primary = self.prediction_stats_continuous if self.enable_continuous_prediction_stats else self.prediction_stats
        return {
            "by_segment": _pack(primary),
            "by_segment_selective": _pack(self.prediction_stats),
            "spin_count": self.spin_count,
            "primary_mode": "continuous" if self.enable_continuous_prediction_stats else "selective",
        }

    def get_best_signals(self, top_n: int = 3) -> List[Dict]:
        """Restituisce i migliori segnali attivi"""
        signals = []
        
        for seg, brain in self.mini_brains.items():
            if brain.state.phase in [Phase.ATTACCO, Phase.CONFERMATO]:
                if brain.state.attack_start_spin > 0:
                    elapsed = max(0, self.spin_count - brain.state.attack_start_spin)
                    progress = max(brain.state.range_current, elapsed)
                else:
                    progress = brain.state.range_current
                remaining = max(0, brain.state.range_max - progress)
                stakes = self.bankroll_engine.calculate_stakes(seg, brain.state.ev_current, brain.state.range_max)
                
                eff_c = mini_brain_effective_confidence(brain.state)
                signals.append({
                    "segment": seg,
                    "phase": brain.state.phase.value,
                    "confidence": eff_c,
                    "confidence_raw": brain.state.confidence,
                    "ev": brain.state.ev_current,
                    "range_remaining": remaining,
                    "battery": brain.state.battery,
                    "suggested_stakes": stakes[:3] if stakes else []
                })
        
        signals.sort(key=lambda x: (x["ev"], x["confidence"]), reverse=True)
        return signals[:top_n]
    
    def calculate_ev(self, segment: str) -> float:
        """Calcola EV per un segmento specifico"""
        if segment not in self.mini_brains:
            return 0.0
        brain = self.mini_brains[segment]
        return self.ev_engine.calculate_ev(segment, brain.state, self.meta_brain.last_segment)
    
    def calculate_stakes(self, segment: str) -> List[float]:
        """Calcola stakes progressivi per un segmento"""
        if segment not in self.mini_brains:
            return []
        brain = self.mini_brains[segment]
        return self.bankroll_engine.calculate_stakes(segment, brain.state.ev_current, brain.state.range_max)
    
    def get_brain_status(self, segment: str) -> Dict:
        """Restituisce stato completo di un MiniBrain"""
        if segment not in self.mini_brains:
            return {"error": "Segmento non valido"}
        return self.mini_brains[segment].get_status()
    
    def get_all_brains_status(self) -> Dict[str, Dict]:
        """Restituisce stato di tutti i MiniBrains"""
        return {seg: brain.get_status() for seg, brain in self.mini_brains.items()}
    
    def get_session_status(self) -> Dict:
        """Restituisce stato sessione con warning"""
        limits = self.bankroll_engine.check_limits()
        
        return {
            "active": self.session_active,
            "spin_count": self.spin_count,
            "bankroll_start": self.bankroll_engine.session.bankroll_start,
            "bankroll_current": round(self.bankroll_engine.session.bankroll_current, 2),
            "profit": round(self.bankroll_engine.session.profit, 2),
            "profit_percent": limits["profit_percent"],
            "warning": limits["warning"],
            "stop": limits["stop"],
            "risk_exposure": self.bankroll_engine.get_risk_exposure()
        }
    
    def get_learned_patterns(self) -> Dict:
        """Restituisce pattern appresi (PERSISTENTI)"""
        return {
            "total_transitions": self.pattern_engine.data.total_transitions,
            "pattern_count": len(self.pattern_engine.data.pattern_strength),
            "strong_patterns": dict(sorted(
                self.pattern_engine.data.pattern_strength.items(),
                key=lambda x: x[1],
                reverse=True
            )[:10]),
            "conditional_probs": self.pattern_engine.data.bigram_probs
        }
    
    def get_last_spins(self, count: int = 20) -> List[Dict]:
        """Restituisce ultimi spin"""
        spins = list(self.history)[-count:]
        return [asdict(spin) for spin in spins]
