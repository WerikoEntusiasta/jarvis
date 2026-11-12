"""
J.A.R.V.I.S. Computer Vision Subsystem
Multimodal Edge Vision Engine with MediaPipe, OpenCV, Real-time Gesture Detection and Windows Control.
"""

import threading
from typing import Optional

from .config import VisionConfig
from .camera import CameraCapture
from .gestures import GestureDetector
from .events import VisionEventBus, VisionEvent
from .actions import WindowsActions
from .engine import VisionEngine

_VISION_INSTANCE: Optional[VisionEngine] = None
_VISION_LOCK = threading.Lock()

def get_vision_engine():
    """Retorna instância singleton segura do VisionEngine com fallback resiliente."""
    global _VISION_INSTANCE
    with _VISION_LOCK:
        if _VISION_INSTANCE is None:
            try:
                engine = VisionEngine()
                def _broadcast_to_hud(payload):
                    try:
                        from core.local_server import broadcast_hud_event
                        broadcast_hud_event("vision_event", payload)
                    except Exception:
                        pass
                engine.on_hud_broadcast = _broadcast_to_hud
                # Câmera inicia em standby seguro (0% de CPU até ser acionada)
                engine.start()
                engine.disable_camera()
                _VISION_INSTANCE = engine
            except Exception as e:
                class ResilientDummyVision:
                    def get_status(self):
                        return {
                            "enabled": False, "fps": 0.0, "camera_device": "Standby Seguro",
                            "resolution": "640x480", "gesture": "none", "gesture_pt": "Nenhum",
                            "action_pt": "Nenhuma ação", "gesture_emoji": "", "confidence": 0.0,
                            "confidence_pct": 0, "hand": "Nenhuma"
                        }
                    def toggle_camera(self):
                        return False
                    def is_camera_enabled(self):
                        return False
                    def enable_camera(self):
                        pass
                    def disable_camera(self):
                        pass
                    def stop(self):
                        pass
                _VISION_INSTANCE = ResilientDummyVision()
        return _VISION_INSTANCE

__all__ = [
    "VisionConfig",
    "CameraCapture",
    "GestureDetector",
    "VisionEventBus",
    "VisionEvent",
    "WindowsActions",
    "VisionEngine",
    "get_vision_engine"
]
