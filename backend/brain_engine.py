"""
Brain Engine - Crazy Time Analysis Tool
Adattato per backend FastAPI
"""
import json
import math
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
        self.data.transition_matrix[from_seg][to_seg] += 1
        self.data.total_transitions += 1
        self.recent_sequence.append(to_seg)
        self._update_probabilities()
        self._detect_sequences()
    
    def _update_probabilities(self):
        """Aggiorna probabilità condizionali P(A|B)"""
        if self.data.total_transitions < self.MIN_SAMPLES:
            return
        
        for from_seg in ALL_SEGMENTS:
            total_from = sum(self.data.transition_matrix[from_seg].values())
            if total_from > 0:
                self.data.bigram_probs[from_seg] = {}
                for to_seg in ALL_SEGMENTS:
                    count = self.data.transition_matrix[from_seg][to_seg]
                    empirical_prob = count / total_from
                    theoretical_prob = THEORETICAL_PROBS[to_seg]
                    
                    # Calcola deviazione significativa
                    if theoretical_prob > 0:
                        deviation = empirical_prob / theoretical_prob
                        if deviation > self.SIGNIFICANCE_THRESHOLD:
                            strength = min(1.0, (deviation - 1) / 2)
                            pattern_key = f"{from_seg}->{to_seg}"
                            self.data.pattern_strength[pattern_key] = strength
                        
                        self.data.bigram_probs[from_seg][to_seg] = empirical_prob
    
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
        
        # Aggiusta con confidence del mini brain
        confidence_factor = mini_brain.confidence
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
        
        bankroll = self.session.bankroll_current
        max_risk = bankroll * self.MAX_RISK_PERCENT
        max_spin = bankroll * self.MAX_SPIN_PERCENT
        
        # Payout-aware base stake
        payout = PAYOUTS[segment]
        if payout > 0:
            # Per numeri, stake inversamente proporzionale al payout
            base_unit = max_risk / (range_estimate * payout)
        else:
            # Per bonus, stake più conservativo
            base_unit = max_risk / (range_estimate * 2)
        
        # EV adjustment
        ev_factor = max(0.5, min(2.0, 1 + ev))
        base_unit *= ev_factor
        
        steps = min(range_estimate, 8)
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
        
        # Reset fase
        self.state.phase = Phase.APPRENDIMENTO
        self.state.range_current = 0
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
        self._update_phase()
    
    def _update_phase(self):
        """Aggiorna fase in base alle condizioni"""
        if self.state.phase == Phase.APPRENDIMENTO:
            if self.state.battery >= 60 and self.state.cooldown <= 0:
                self.state.phase = Phase.ATTENZIONE
                self.state.signal = SignalType.ATTENZIONE
        
        elif self.state.phase == Phase.ATTENZIONE:
            if self.state.battery >= 80 and self.state.confidence > 0.4:
                self._enter_attack()
        
        elif self.state.phase in [Phase.ATTACCO, Phase.CONFERMATO]:
            self.state.range_current += 1
            self.state.battery = max(0, self.state.battery - self.BATTERY_DECAY_ATTACK)
            
            if self.state.range_current >= self.state.range_max or self.state.battery <= 20:
                self.state.phase = Phase.STOP
                self.state.signal = SignalType.STOP
    
    def _enter_attack(self):
        """Entra in fase di attacco"""
        self.state.phase = Phase.ATTACCO
        self.state.signal = SignalType.ENTRA
        self.state.range_current = 0
        self.state.range_max = 6 if self.segment == "CT" else 9
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
        return {
            "segment": self.segment,
            "phase": self.state.phase.value,
            "confidence": self.state.confidence,
            "battery": round(self.state.battery, 2),
            "gap_current": self.state.gap_current,
            "expected_gap": round(self.expected_gap, 2),
            "pressure": round(self.state.pressure, 2),
            "heat": round(self.state.heat, 3),
            "z_score": round(self.state.z_score, 3),
            "cooldown": round(self.state.cooldown, 2),
            "range": f"{self.state.range_current}/{self.state.range_max}",
            "success_rate": round(self.state.successes / self.state.attempts, 3) if self.state.attempts > 0 else 0,
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
        
        # Filtra per confidence minima
        candidates = []
        for seg, ev in positive_ev.items():
            brain = self.mini_brains[seg]
            if brain.state.confidence >= self.MIN_CONFIDENCE:
                candidates.append({
                    "segment": seg,
                    "ev": ev,
                    "confidence": brain.state.confidence,
                    "phase": brain.state.phase,
                    "range_max": brain.state.range_max
                })
        
        if not candidates:
            return MetaDecision(
                action="WAIT",
                reason="EV positivi ma confidence insufficiente",
                ev=max(positive_ev.values()),
                confidence=max(self.mini_brains[s].state.confidence for s in positive_ev.keys())
            )
        
        # Ordina per EV (principale) e confidence (secondario)
        candidates.sort(key=lambda x: (x["ev"], x["confidence"]), reverse=True)
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
    
    def __init__(self, username: str = "player"):
        self.username = username
        
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
        
        # Inizializza MiniBrains
        self._init_mini_brains()
    
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
    
    # =========================================================================
    # API SESSIONE
    # =========================================================================
    
    def start_session(self, bankroll: float):
        """Avvia nuova sessione (resetta dati volatili)"""
        self.spin_count = 0
        self.history.clear()
        self.last30.clear()
        self.session_active = True
        
        # Reset MiniBrains (ma mantieni pattern)
        self._init_mini_brains()
        
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
        
        self.spin_count += 1
        
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
    
    def get_best_signals(self, top_n: int = 3) -> List[Dict]:
        """Restituisce i migliori segnali attivi"""
        signals = []
        
        for seg, brain in self.mini_brains.items():
            if brain.state.phase in [Phase.ATTACCO, Phase.CONFERMATO]:
                remaining = brain.state.range_max - brain.state.range_current
                stakes = self.bankroll_engine.calculate_stakes(seg, brain.state.ev_current, brain.state.range_max)
                
                signals.append({
                    "segment": seg,
                    "phase": brain.state.phase.value,
                    "confidence": brain.state.confidence,
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
