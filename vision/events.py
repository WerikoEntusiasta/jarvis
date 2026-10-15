import time
import threading
from typing import Dict, Any, List, Callable, Optional
from dataclasses import dataclass, asdict

@dataclass
class VisionEvent:
    type: str # "vision.gesture" | "vision.presence"
    timestamp: float
    confidence: float
    gesture: Optional[str] = None
    hand: Optional[str] = None
    present: Optional[bool] = None
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "type": self.type,
            "timestamp": self.timestamp,
            "confidence": round(self.confidence, 2)
        }
        if self.gesture is not None:
            d["gesture"] = self.gesture
        if self.hand is not None:
            d["hand"] = self.hand
        if self.present is not None:
            d["present"] = self.present
        if self.metadata:
            d["metadata"] = self.metadata
        return d

    def to_semantic_string(self) -> str:
        """Gera descrição em linguagem natural compreensível para o OpenClaw."""
        t_str = time.strftime("%H:%M:%S", time.localtime(self.timestamp))
        if self.type == "vision.gesture":
            hand_pt = "direita" if self.hand == "right" else ("esquerda" if self.hand == "left" else "")
            hand_info = f" com a mão {hand_pt}" if hand_pt else ""
            return f"[{t_str}] Evento Visual: Gesto '{self.gesture}' detectado{hand_info} (confiança: {int(self.confidence*100)}%)."
        elif self.type == "vision.presence":
            status = "presente" if self.present else "ausente"
            return f"[{t_str}] Percepção de Presença: Usuário está {status} diante da estação."
        return f"[{t_str}] Evento de Visão: {self.type}"

class VisionEventBus:
    """
    Decoupled Event Bus for normalized Vision Events.
    - Manages intelligent debounce and per-gesture cooldowns.
    - Dispatches to subscribers (HUD SSE, OpenClaw, Windows Actions, Logger).
    - Stores structured event audit trail.
    """

    def __init__(self, gesture_cooldown_sec: float = 3.0, presence_cooldown_sec: float = 4.0, global_cooldown_sec: float = 2.5):
        self.gesture_cooldown_sec = gesture_cooldown_sec
        self.presence_cooldown_sec = presence_cooldown_sec
        self.global_cooldown_sec = global_cooldown_sec
        
        self._listeners: List[Callable[[VisionEvent], None]] = []
        self._lock = threading.Lock()
        
        self._last_gesture_time: Dict[str, float] = {}
        self._global_last_gesture_time: float = 0.0
        self._last_presence_state: Optional[bool] = None
        self._last_presence_emit_time: float = 0.0
        
        self._event_history: List[Dict[str, Any]] = []
        self._max_history = 60

    def subscribe(self, callback: Callable[[VisionEvent], None]):
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def unsubscribe(self, callback: Callable[[VisionEvent], None]):
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    def publish_gesture(self, gesture: str, confidence: float, hand: str = "right", metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Publica um gesto detectado aplicando cooldown/debounce global e individual.
        Retorna True se o evento foi aceito e emitido, False se foi bloqueado por cooldown.
        """
        if not gesture or gesture == "none":
            return False

        now = time.time()
        with self._lock:
            # Trava global para impedir múltiplos disparos em cadeia
            if (now - self._global_last_gesture_time) < self.global_cooldown_sec:
                return False

            last_time = self._last_gesture_time.get(gesture, 0.0)
            if (now - last_time) < self.gesture_cooldown_sec:
                # Bloqueado por cooldown do gesto específico
                return False

            self._last_gesture_time[gesture] = now
            self._global_last_gesture_time = now
            event = VisionEvent(
                type="vision.gesture",
                gesture=gesture,
                confidence=confidence,
                hand=hand,
                timestamp=now,
                metadata=metadata
            )
            self._record_and_dispatch(event)
            return True

    def publish_presence(self, is_present: bool, confidence: float = 0.95) -> bool:
        """
        Publica mudança no estado de presença diante da câmera.
        """
        now = time.time()
        with self._lock:
            # Só emite se o estado mudou ou se já passou o tempo de heartbeat
            state_changed = (self._last_presence_state != is_present)
            time_elapsed = (now - self._last_presence_emit_time) >= self.presence_cooldown_sec

            if not state_changed and not time_elapsed:
                return False

            self._last_presence_state = is_present
            self._last_presence_emit_time = now
            
            event = VisionEvent(
                type="vision.presence",
                present=is_present,
                confidence=confidence,
                timestamp=now
            )
            self._record_and_dispatch(event)
            return True

    def _record_and_dispatch(self, event: VisionEvent):
        # Registra no log de histórico
        ed = event.to_dict()
        self._event_history.append(ed)
        if len(self._event_history) > self._max_history:
            self._event_history.pop(0)

        # Log estruturado no console
        t_fmt = time.strftime("%H:%M:%S", time.localtime(event.timestamp))
        print(f"[VISION EVENT BUS] {t_fmt} | {event.type} -> {event.gesture or ('Present' if event.present else 'Absent')} (conf: {event.confidence})")

        # Dispara para todos os listeners registrados
        for listener in list(self._listeners):
            try:
                listener(event)
            except Exception as e:
                print(f"[VisionEventBus] Erro no listener {listener}: {e}")

    def get_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._lock:
            return list(reversed(self._event_history[-limit:]))
