"""
Jarvis Desktop - Internal Event Bus
Barramento reativo desacoplado para eventos locais:
- vision.gesture, vision.presence
- audio.started, audio.stopped
- clipboard.changed
- window.changed
- system.telemetry
- openclaw.connected, openclaw.disconnected
"""

import time
import threading
from typing import Callable, Dict, List, Any
from collections import deque

class EventBus:
    def __init__(self, history_limit: int = 100):
        self._subscribers: Dict[str, List[Callable[[Dict[str, Any]], None]]] = {}
        self._lock = threading.Lock()
        self._history = deque(maxlen=history_limit)

    def subscribe(self, event_type: str, callback: Callable[[Dict[str, Any]], None]):
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            if callback not in self._subscribers[event_type]:
                self._subscribers[event_type].append(callback)

    def unsubscribe(self, event_type: str, callback: Callable[[Dict[str, Any]], None]):
        with self._lock:
            if event_type in self._subscribers and callback in self._subscribers[event_type]:
                self._subscribers[event_type].remove(callback)

    def emit(self, event_type: str, data: Dict[str, Any] = None):
        if data is None:
            data = {}
        
        event = {
            "type": event_type,
            "timestamp": time.time(),
            "data": data
        }

        with self._lock:
            self._history.append(event)
            # Lista de callbacks exatos + wildcard "*"
            callbacks = list(self._subscribers.get(event_type, [])) + list(self._subscribers.get("*", []))

        # Notifica inscritos de forma assíncrona / não-bloqueante
        for cb in callbacks:
            try:
                cb(event)
            except Exception as e:
                print(f"[EventBus] Erro ao disparar callback para '{event_type}': {e}")

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._history)[-limit:]
