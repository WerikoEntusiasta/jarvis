"""
Jarvis Desktop - Config Manager
Centraliza todas as configurações do aplicativo local Windows,
conexão remota com o OpenClaw Gateway na VPS, permissões e capacidades.
"""

import os
import json
import platform
import socket
from typing import Dict, Any, List

CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "jarvis_desktop_config.json")

DEFAULT_CONFIG: Dict[str, Any] = {
    "version": "1.0.0",
    "node": {
        "node_id": f"jarvis-pc-{socket.gethostname().lower().replace(' ', '-').replace('_', '-')}",
        "device_name": f"PC {socket.gethostname()}",
        "platform": "windows",
        "os_version": platform.platform(),
        "arch": platform.machine()
    },
    "gateway": {
        "bridge_url": os.environ.get("JARVIS_CORE_URL", "https://jarvis.werikspace.xyz"),
        "backup_ip": os.environ.get("ZIMA_IP", os.environ.get("ZIMA_IP", "127.0.0.1")),
        "port": int(os.environ.get("JARVIS_NODE_PORT", "18789")),
        "token": os.environ.get("JARVIS_NODE_TOKEN", ""),
        "use_tls": True,
        "reconnect_interval_seconds": 5,
        "heartbeat_interval_seconds": 15,
        "timeout_seconds": 10
    },
    "capabilities": [
        "camera",
        "microphone",
        "screen",
        "keyboard",
        "mouse",
        "windows",
        "applications",
        "audio",
        "clipboard",
        "notifications",
        "system",
        "vision_local",
        "power",
        "wake_confirmation"
    ],
    "security": {
        "allow_low_risk": True,
        "allow_medium_risk": True,
        "require_confirmation_for_high": False,
        "auto_confirm_high_risk": True,
        "blocked_commands": [
            "format",
            "rmdir /s",
            "del /f /s /q c:",
            "reg delete"
        ]
    },
    "vision": {
        "enabled": False,
        "fps": 24,
        "confidence_threshold": 0.60,
        "debounce_seconds": 1.2
    },
    "audio": {
        "enabled": True,
        "sample_rate": 16000,
        "vad_silence_timeout_ms": 1500
    },
    "screen": {
        "enabled": True,
        "max_width": 1920,
        "max_height": 1080
    },
    "clipboard": {
        "watch": True,
        "poll_interval_seconds": 1.0
    },
    "system_monitor": {
        "poll_interval_seconds": 3.0
    },
    "ui": {
        "tray_enabled": True,
        "hud_enabled": True,
        "auto_start_with_windows": True
    }
}

class DesktopConfig:
    def __init__(self, filepath: str = CONFIG_FILE):
        self.filepath = filepath
        self.data: Dict[str, Any] = {}
        self.load()

    def load(self) -> Dict[str, Any]:
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    self.data = self._deep_merge(DEFAULT_CONFIG, saved)
            except Exception as e:
                print(f"[DesktopConfig] Erro ao carregar {self.filepath}: {e}. Usando padrões.")
                self.data = DEFAULT_CONFIG.copy()
        else:
            self.data = DEFAULT_CONFIG.copy()
            self.save()
        return self.data

    def save(self):
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[DesktopConfig] Erro ao salvar {self.filepath}: {e}")

    def get(self, *keys, default=None):
        curr = self.data
        for k in keys:
            if isinstance(curr, dict) and k in curr:
                curr = curr[k]
            else:
                return default
        return curr

    def set(self, *keys, value=None):
        if not keys:
            return
        curr = self.data
        for k in keys[:-1]:
            if k not in curr or not isinstance(curr[k], dict):
                curr[k] = {}
            curr = curr[k]
        curr[keys[-1]] = value
        self.save()

    def _deep_merge(self, base: dict, override: dict) -> dict:
        result = base.copy()
        for k, v in override.items():
            if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = self._deep_merge(result[k], v)
            else:
                result[k] = v
        return result
