"""
Configurações Globais do J.A.R.V.I.S. Windows v2
100% Independente do ZimaOS: o HUD e as APIs rodam localmente no Windows.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ROOT_ENV = BASE_DIR.parent / ".env"

def _load_env_file(path: Path):
    if not path.exists():
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k not in os.environ:
                os.environ[k] = v

_load_env_file(ROOT_ENV)

# Servidor Local 100% Independente
LOCAL_PORT = int(os.environ.get("JARVIS_LOCAL_PORT", "8085"))
CORE_URL = f"http://127.0.0.1:{LOCAL_PORT}"

# URL remota do ZimaOS (usada apenas para telemetria/sincronismo secundário quando online)
REMOTE_ZIMA_URL = os.environ.get("JARVIS_CORE_URL", "https://jarvis.werikspace.xyz").rstrip("/")
BRIDGE_SECRET = os.environ.get("BRIDGE_SECRET", "q48dvmeLKT3L32qHSDLClwLu9MbmiPi0P_c8p-7ThFs")
NODE_ID = os.environ.get("JARVIS_NODE_ID", "jarvis-windows-primary")

POLL_INTERVAL_SEC = 1.0
HEARTBEAT_INTERVAL_SEC = 5.0
MUTEX_NAME = "Local\\JARVIS_WINDOWS_V2_MUTEX"
IPC_PORT = 49160

# Hotkey global: VK_SPACE com MOD_CONTROL (Ctrl+Espaço) ou Win+Shift+J
HOTKEY_MODIFIERS = 0x0002  # MOD_CONTROL
HOTKEY_VK = 0x20           # VK_SPACE
HOTKEY_ID = 9001
