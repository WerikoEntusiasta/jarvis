import os
import json
import threading
from typing import Dict, Any, Optional

DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "vision_config.json")

class VisionConfig:
    """Thread-safe configuration manager for Jarvis Vision Subsystem."""
    
    def __init__(self, config_path: str = DEFAULT_CONFIG_PATH):
        self.config_path = config_path
        self._lock = threading.Lock()
        self._data: Dict[str, Any] = {}
        self.load()

    def load(self) -> Dict[str, Any]:
        with self._lock:
            if os.path.exists(self.config_path):
                try:
                    with open(self.config_path, "r", encoding="utf-8") as f:
                        self._data = json.load(f)
                        return self._data
                except Exception as e:
                    print(f"[VisionConfig] Erro ao carregar {self.config_path}: {e}")
            
            # Fallback padrão
            self._data = {
                "camera": {
                    "device_index": 0,
                    "width": 640,
                    "height": 480,
                    "fps_target": 30,
                    "enabled_by_default": True
                },
                "detection": {
                    "min_gesture_confidence": 0.60,
                    "min_presence_confidence": 0.60,
                    "gesture_cooldown_seconds": 1.5,
                    "presence_cooldown_seconds": 3.0,
                    "swipe_threshold_pixels": 70,
                    "swipe_max_frames": 18
                },
                "gestures_to_actions": {
                    "thumbs_up": {"action": "confirm", "risk_level": "low"},
                    "open_hand": {"action": "play_pause", "risk_level": "low"},
                    "fist": {"action": "minimize_all", "risk_level": "low"},
                    "point_up": {"action": "volume_up", "risk_level": "low"},
                    "point_down": {"action": "volume_down", "risk_level": "low"},
                    "swipe_right": {"action": "next_track", "risk_level": "low"},
                    "swipe_left": {"action": "prev_track", "risk_level": "low"},
                    "peace_sign": {"action": "open_app", "target": "chrome", "risk_level": "low"},
                    "three_fingers": {"action": "open_app", "target": "code", "risk_level": "low"}
                },
                "security": {
                    "require_confirmation_for": [
                        "delete_file", "format_disk", "kill_system_process", "exec_admin_script", "reboot_system"
                    ]
                }
            }
            return self._data

    def save(self):
        with self._lock:
            try:
                with open(self.config_path, "w", encoding="utf-8") as f:
                    json.dump(self._data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"[VisionConfig] Erro ao salvar config: {e}")

    def get(self, *keys, default=None):
        with self._lock:
            curr = self._data
            for k in keys:
                if isinstance(curr, dict) and k in curr:
                    curr = curr[k]
                else:
                    return default
            return curr

    def set(self, *keys, value=None):
        if not keys:
            return
        with self._lock:
            curr = self._data
            for k in keys[:-1]:
                if k not in curr or not isinstance(curr[k], dict):
                    curr[k] = {}
                curr = curr[k]
            curr[keys[-1]] = value
        self.save()

    def get_action_for_gesture(self, gesture: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            mappings = self._data.get("gestures_to_actions", {})
            return mappings.get(gesture)

    def set_action_for_gesture(self, gesture: str, action: str, target: str = "", risk_level: str = "low"):
        with self._lock:
            if "gestures_to_actions" not in self._data:
                self._data["gestures_to_actions"] = {}
            self._data["gestures_to_actions"][gesture] = {
                "action": action,
                "target": target,
                "risk_level": risk_level
            }
        self.save()

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._data))
