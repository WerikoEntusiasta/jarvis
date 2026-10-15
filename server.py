import http.server
import socketserver
import json
import sys
import urllib.request
CREATE_NO_WINDOW = 0x08000000 if sys.platform == 'win32' else 0
import urllib.parse
import os
import paramiko
import time
import asyncio
import edge_tts
import re
import threading
import queue
import hashlib
import hmac
import base64
import secrets
import socket
import struct
import numpy as np
try:
    from faster_whisper import WhisperModel
except Exception:
    WhisperModel = None
import hardware_control as hc

try:
    from desktop.windows_bridge import bridge as win_bridge
except Exception as e:
    win_bridge = None

import biometrics
import jev_laya
from jev_laya import jev_engine


def _load_dotenv():
    """Carrega variáveis do arquivo .env (se existir) sem sobrescrever o ambiente real."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception as e:
        print(f"[!] Aviso: falha ao ler {env_path}: {e}")

_load_dotenv()

PORT = int(os.environ.get("PORT", "8080"))
DIRECTORY = os.path.dirname(os.path.abspath(__file__))

# Configurações ZimaOS e OpenClaw (via .env ou variáveis de ambiente - nunca hardcoded)
ZIMA_IP = os.environ.get("ZIMA_IP", "")
ZIMA_USER = os.environ.get("ZIMA_USER", "")
ZIMA_PASS = os.environ.get("ZIMA_PASS", "")

# Configurações Pluggy (via .env ou variáveis de ambiente)
PLUGGY_CLIENT_ID = os.environ.get("PLUGGY_CLIENT_ID", "")
PLUGGY_CLIENT_SECRET = os.environ.get("PLUGGY_CLIENT_SECRET", "")
PLUGGY_ITEM_ID = os.environ.get("PLUGGY_ITEM_ID", "")

# Configurações ElevenLabs (Sincronizado com 9router - Voz Britânica Estilo J.A.R.V.I.S.)
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_FALLBACK_KEY = os.environ.get("ELEVENLABS_FALLBACK_KEY", "")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb") # George - Warm Captivating British Storyteller

# ==============================================================================
# RBAC - Sessões assinadas e permissões por usuário (autenticação facial)
# ==============================================================================
TRUST_LOCAL = os.environ.get("JARVIS_TRUST_LOCAL", "1").lower() in ("1", "true", "yes")
SESSION_TTL_S = int(os.environ.get("JARVIS_SESSION_TTL_S", str(12 * 3600)))

def _load_or_create_session_secret() -> bytes:
    secret_env = os.environ.get("JARVIS_SESSION_SECRET", "")
    if secret_env:
        return secret_env.encode("utf-8")
    secret_file = os.path.join(DIRECTORY, "auth", "session_secret.key")
    os.makedirs(os.path.dirname(secret_file), exist_ok=True)
    if os.path.exists(secret_file):
        try:
            with open(secret_file, "r", encoding="utf-8") as f:
                stored = f.read().strip()
                if stored:
                    return stored.encode("utf-8")
        except Exception:
            pass
    new_secret = secrets.token_hex(32)
    with open(secret_file, "w", encoding="utf-8") as f:
        f.write(new_secret)
    return new_secret.encode("utf-8")

SESSION_SECRET = _load_or_create_session_secret()

def _create_session_token(user: str, role: str, permissions: dict) -> str:
    payload = {
        "user": user,
        "role": role,
        "permissions": permissions,
        "exp": time.time() + SESSION_TTL_S
    }
    body = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    sig = hmac.new(SESSION_SECRET, body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"

def _read_session_token(token: str):
    if not token or "." not in token:
        return None
    body, _, sig = token.partition(".")
    try:
        expected = hmac.new(SESSION_SECRET, body.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(base64.urlsafe_b64decode(body.encode("ascii")).decode("utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict) or float(payload.get("exp", 0)) < time.time():
        return None
    return payload

OWNER_AUTH = {
    "user": "Proprietário do Nó",
    "role": "Proprietário",
    "permissions": dict(biometrics.OWNER_PERMISSIONS),
    "source": "local"
}
GUEST_AUTH = {
    "user": "Visitante",
    "role": "Convidado",
    "permissions": dict(biometrics.GUEST_PERMISSIONS),
    "source": "guest"
}

def _required_permission_for_message(lower_msg: str) -> str:
    """Mapeia a mensagem do usuário para a permissão mínima exigida pelo RBAC."""
    if any(w in lower_msg for w in [
        "wake on lan", "wol", "ligar o pc", "ligue o pc", "liga o pc", "ligar computador",
        "ligue o computador", "liga o computador", "acorda o pc", "acorde o pc",
        "acorda o computador", "ligar a máquina", "ligar a maquina", "despertar o pc"
    ]):
        return "wake_on_lan"
    if any(w in lower_msg for w in [
        "docker", "container", "zimaos", "zima", "openclaw", "processos", "pid",
        "matar processo", "finalizar processo", "radar de conectividade", "logs do"
    ]):
        return "infra_control"
    if any(w in lower_msg for w in [
        "desligar", "desligue", "desliga", "encerrar o windows", "reiniciar", "reinicie",
        "reinicializa", "suspender", "suspende", "shutdown", "restart", "cancelar desligamento",
        "abortar desligamento", "energia"
    ]):
        return "power_control"
    if any(w in lower_msg for w in [
        "briefing matinal", "relatório matinal", "relatorio matinal", "resumo do dia",
        "briefing do dia", "relatório do dia", "saldo", "extrato", "fatura", "pluggy",
        "banco inter", "financeiro", "minhas contas", "quanto tenho", "meu dinheiro"
    ]):
        return "finance_view"
    if any(w in lower_msg for w in [
        "bloquear", "travar", "minimizar", "área de trabalho", "area de trabalho",
        "mostrar desktop", "abre", "abrir", "inicia", "iniciar", "executa", "executar",
        "roda", "rodar", "janela", "janelas", "aplicativo", "vscode", "vs code", "spotify",
        "chrome", "calculadora", "notepad", "bloco de notas", "digitar", "digitado",
        "pressionar", "aperta", "pressione", "teclado", "mouse", "clicar", "rolar",
        "captura de tela", "screenshot", "print da tela", "área de transferência", "clipboard"
    ]):
        return "windows_control"
    if any(w in lower_msg for w in [
        "volume", "mutar", "mudo", "silenciar", "desmutar", "música", "musica", "pausar",
        "pausa", "próxima música", "proxima musica", "música anterior", "musica anterior",
        "youtube", "toca", "tocar", "ouvir", "reproduz"
    ]):
        return "media_control"
    return "chat"

BRIDGE_ACTION_PERMISSIONS = {
    "shutdown": "power_control", "shutdown_pc": "power_control", "desligar": "power_control", "desligar_pc": "power_control",
    "restart": "power_control", "restart_pc": "power_control", "reiniciar": "power_control", "reiniciar_pc": "power_control",
    "abort_shutdown": "power_control", "cancel_shutdown": "power_control",
    "cancelar_desligamento": "power_control", "abortar_desligamento": "power_control",
    "sleep": "power_control", "sleep_pc": "power_control", "suspender": "power_control", "suspender_pc": "power_control",
    "screenshot": "screen_capture", "print": "screen_capture",
}

def _required_permission_for_bridge_action(act: str) -> str:
    return BRIDGE_ACTION_PERMISSIONS.get(act, "windows_control")

CANVAS_ACTION_PERMISSIONS = {
    "restart_container": "infra_control",
    "docker_prune": "infra_control",
    "kill_windows_process": "windows_control",
    "shutdown_pc": "power_control", "desligar_pc": "power_control", "desligar": "power_control",
    "abort_shutdown": "power_control", "cancelar_desligamento": "power_control",
    "restart_pc": "power_control", "reiniciar_pc": "power_control",
    "sleep_pc": "power_control", "suspender_pc": "power_control",
}

# Hub de Eventos em Tempo Real para o HUD (SSE / MCP)
sse_subscribers = []
sse_lock = threading.Lock()
last_hud_event_time = 0.0

def broadcast_hud_event(event_dict):
    """Envia um evento em tempo real para todas as janelas do HUD conectadas via SSE."""
    with sse_lock:
        dead = []
        for q in sse_subscribers:
            try:
                q.put_nowait(event_dict)
            except Exception:
                dead.append(q)
        for d in dead:
            if d in sse_subscribers:
                sse_subscribers.remove(d)

try:
    from vision import VisionEngine
    from vision.auth import FaceAuthenticator
    vision_engine = VisionEngine()
    vision_engine.on_hud_broadcast = broadcast_hud_event
    face_auth = FaceAuthenticator()
except Exception as ev:
    class DummyVisionEngine:
        on_hud_broadcast = None
        on_openclaw_dispatch = None
        def get_status(self):
            return {
                "enabled": False,
                "status": "STANDBY",
                "fps": 0,
                "gesture": "none",
                "gesture_pt": "Nenhum",
                "action_pt": "Nenhuma",
                "gesture_emoji": "⚪",
                "confidence_pct": 0,
                "hand": "Nenhuma",
                "user_present": False,
                "last_event": "Headless Cloud Node"
            }
        def is_camera_enabled(self): return False
        def enable_camera(self): pass
        def disable_camera(self): pass
        def toggle_camera(self): return False
        def start(self): pass
        def stop(self): pass
        def get_annotated_jpeg(self): return b""
        def process_browser_frame(self, frame_bytes):
            return {"status": "ok", "gesture": "none", "confidence_pct": 0, "user_present": False}
        class _Config:
            def to_dict(self): return {"camera": {"enabled_by_default": False}}
            def set_action_for_gesture(self, *a, **k): pass
            def get(self, *a, **k): return False
        config = _Config()
        class _Bus:
            def get_history(self): return []
        event_bus = _Bus()
        class _Actions:
            def execute(self, *a, **k): return {"status": "noop"}
        windows_actions = _Actions()

    class DummyFaceAuth:
        def __init__(self):
            self.auth_file = os.path.join(DIRECTORY, "auth", "werik_face_profile.json")
            os.makedirs(os.path.dirname(self.auth_file), exist_ok=True)
            self.profile = self._load()

        def _load(self):
            if os.path.exists(self.auth_file):
                try:
                    with open(self.auth_file, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    pass
            return {"registered": False, "name": "Werik"}

        def is_registered(self):
            return bool(self.profile.get("registered", False))

        def authenticate(self, frame_or_bytes, client_has_face=False):
            reg = self.is_registered()
            if not reg:
                return {
                    "authenticated": False,
                    "confidence": 0.0,
                    "user": None,
                    "reason": "NO_PROFILE_REGISTERED"
                }

            has_face = False
            if client_has_face:
                has_face = True
            elif frame_or_bytes is not None:
                has_face = self._detect_face_pillow(frame_or_bytes)

            if not has_face:
                return {
                    "authenticated": False,
                    "confidence": 0.0,
                    "user": None,
                    "reason": "NO_FACE_DETECTED"
                }

            return {
                "authenticated": False,
                "confidence": 0.0,
                "user": None,
                "reason": "BIOMETRIC_DESCRIPTOR_REQUIRED"
            }

        def _detect_face_pillow(self, data):
            try:
                import io
                from PIL import Image, ImageStat
                if isinstance(data, (bytes, bytearray)):
                    if len(data) < 300:
                        return False
                    img = Image.open(io.BytesIO(data))
                elif hasattr(data, 'shape'):
                    img = Image.fromarray(data)
                else:
                    return False

                rgb = img.convert('RGB')
                w, h = rgb.size
                if w < 50 or h < 50:
                    return False

                cx, cy = w // 2, h // 2
                rw, rh = int(w * 0.45), int(h * 0.45)
                crop = rgb.crop((cx - rw//2, cy - rh//2, cx + rw//2, cy + rh//2))

                stat = ImageStat.Stat(crop)
                variance = sum(stat.var) / len(stat.var)
                if variance < 70:
                    return False

                ycbcr = np.array(crop.convert('YCbCr'))
                cb = ycbcr[:, :, 1]
                cr = ycbcr[:, :, 2]
                skin_ratio = float(np.mean((cb >= 77) & (cb <= 127) & (cr >= 133) & (cr <= 173)))

                return 0.12 <= skin_ratio <= 0.85
            except Exception as e:
                print(f"[DummyFaceAuth] Erro ao analisar frame: {e}")
                return False

        def register_face(self, *a, **k):
            try:
                self.profile = {"registered": True, "name": "Werik", "registered_at": time.strftime("%Y-%m-%d %H:%M:%S")}
                with open(self.auth_file, "w", encoding="utf-8") as f:
                    json.dump(self.profile, f, indent=2)
                return True
            except Exception:
                return True

    vision_engine = DummyVisionEngine()
    face_auth = DummyFaceAuth()
    print(f"[VisionEngine] Modo headless / Docker ativado com fallback seguro ({ev}).")

def dispatch_vision_event_to_openclaw(event):
    """Encaminha o evento de visão e executa a ação física imediata no Windows via WindowsBridge."""
    def _worker():
        try:
            if event.type == "vision.gesture":
                gest = event.gesture
                conf = int(event.confidence * 100)
                msg = f"[EVENTO VISÃO COMPUTACIONAL WEBCAM] Usuário realizou o gesto '{gest}' com a mão {event.hand} (confiança: {conf}%)."
                print(f"[OpenClaw Vision Dispatch] {msg}")

                global win_bridge
                if win_bridge is None:
                    try:
                        from desktop.windows_bridge import bridge as win_bridge
                    except Exception as eb:
                        print(f"[!] Erro ao reimportar win_bridge: {eb}")

                action_executed = None
                if win_bridge:
                    if gest in ["open_hand", "palma"]:
                        res = win_bridge.media_play_pause()
                        action_executed = f"Mídia: Play / Pause ({res.get('status')})"
                    elif gest in ["fist", "punho"]:
                        res = win_bridge.minimize_all_windows()
                        action_executed = f"Área de Trabalho (Minimizar Tudo) ({res.get('status')})"
                    elif gest in ["point_up", "cima"]:
                        res = win_bridge.volume_up(4)
                        action_executed = f"Volume +10% ({res.get('volume', '')}%)"
                    elif gest in ["point_down", "baixo"]:
                        res = win_bridge.volume_down(4)
                        action_executed = f"Volume -10% ({res.get('volume', '')}%)"
                    elif gest in ["point_right", "swipe_right", "direita"]:
                        res = win_bridge.media_next()
                        action_executed = f"Próxima Música ({res.get('status')})"
                    elif gest in ["point_left", "swipe_left", "esquerda"]:
                        res = win_bridge.media_previous()
                        action_executed = f"Música Anterior ({res.get('status')})"
                    elif gest in ["peace_sign", "paz"]:
                        res = win_bridge.media_mute()
                        action_executed = f"Mudo Alternado ({res.get('status')})"
                    elif gest in ["three_fingers", "tres_dedos"]:
                        res = win_bridge.switch_window()
                        action_executed = f"Alternar Janelas ({res.get('status')})"
                    elif gest in ["swipe_up"]:
                        res = win_bridge.mouse_scroll(350)
                        action_executed = f"Rolagem para Cima ({res.get('status')})"
                    elif gest in ["swipe_down"]:
                        res = win_bridge.mouse_scroll(-350)
                        action_executed = f"Rolagem para Baixo ({res.get('status')})"
                    elif gest in ["thumbs_up", "joinha"]:
                        res = win_bridge.press_key("enter")
                        action_executed = f"Confirmar (Enter) ({res.get('status')})"
                    elif gest in ["thumbs_down"]:
                        res = win_bridge.press_key("escape")
                        action_executed = f"Cancelar (Esc) ({res.get('status')})"

                if action_executed:
                    print(f"[+] >>> AÇÃO EXECUTADA NO WINDOWS: {action_executed} <<<")
                    broadcast_hud_event({
                        "action": "alert",
                        "title": f"GESTO: {gest.upper()}",
                        "message": f"Comando executado: {action_executed}",
                        "level": "sucesso"
                    })
                else:
                    print(f"[-] Ação não mapeada para gesto: {gest} (win_bridge={win_bridge is not None})")
            elif event.type == "vision.presence":
                pres = "presente diante da câmera" if event.present else "ausente da câmera"
                msg = f"[EVENTO VISÃO PRESENÇA] Usuário está {pres}."
                print(f"[OpenClaw Presence Dispatch] {msg}")
        except Exception as e:
            print(f"[OpenClaw Vision Dispatch Error] {e}")
    threading.Thread(target=_worker, daemon=True).start()

if vision_engine:
    vision_engine.on_openclaw_dispatch = dispatch_vision_event_to_openclaw
    if vision_engine.config.get("camera", "enabled_by_default", default=False):
        try:
            vision_engine.enable_camera()
        except Exception:
            pass
    else:
        print("[VisionEngine] Câmera em modo STANDBY (desativada por padrão).")

def _whisper_selftest(model, timeout: float = 25.0) -> bool:
    """Transcreve ~1s de silêncio numa thread com prazo. False se travar/falhar
    (caso clássico: cuBLAS/cuDNN ausente -> GPU 'carrega' mas a inferência pendura)."""
    if model is None:
        return False
    result = {"ok": False}

    def _run():
        try:
            audio = np.zeros(16000, dtype=np.float32)
            segments, _ = model.transcribe(audio, language="pt", beam_size=1, vad_filter=False)
            _ = "".join(s.text for s in segments)
            result["ok"] = True
        except Exception:
            result["ok"] = False

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout)
    return (not t.is_alive()) and result["ok"]


def _load_whisper_robust():
    if not WhisperModel:
        return None
    model_name = os.environ.get("WHISPER_LOCAL_MODEL", "base").strip() or "base"
    for dev, ct in [("cuda", "float16"), ("cuda", "int8_float16"), ("cpu", "int8")]:
        try:
            print(f"[*] Whisper {model_name} -> tentando {dev}/{ct}...")
            m = WhisperModel(model_name, device=dev, compute_type=ct)
        except Exception as e:
            print(f"[!] Whisper {dev}/{ct} não carregou: {str(e)[:120]}")
            continue
        if _whisper_selftest(m):
            print(f"[+] Faster-Whisper {model_name} OK em {dev}/{ct}.")
            return m
        print(f"[!] Whisper {dev}/{ct} carregou mas TRAVOU no self-test — descartando.")
    print("[!] Whisper indisponível em todas as opções (o nó usará o fallback do núcleo).")
    return None


whisper_model = None
if WhisperModel:
    print("[*] Inicializando modelo Faster-Whisper Small...")
    whisper_model = _load_whisper_robust()

cache = {
    "finance": None,
    "finance_ts": 0,
    "system": None,
    "system_ts": 0,
    "weather": None,
    "weather_ts": 0
}

def clean_text_for_speech(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)
    text = re.sub(r'_{1,3}([^_]+)_{1,3}', r'\1', text)
    text = text.replace('*', ' ').replace('#', ' ').replace('~', ' ')
    text = text.replace('°C', ' graus').replace('°c', ' graus').replace('°', ' graus')
    text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def get_catanduva_weather():
    now = time.time()
    if cache["weather"] and (now - cache["weather_ts"] < 45):
        return cache["weather"]
        
    try:
        url = os.environ.get("OPENMETEO_BASE_URL", "https://api.open-meteo.com/v1/forecast") + "?latitude=-21.1378&longitude=-48.9728&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code&timezone=America%2FSao_Paulo"
        req = urllib.request.Request(url, headers={"User-Agent": "JarvisHUD/1.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            curr = data.get("current", {})
            daily = data.get("daily", {})
            
            temp = curr.get("temperature_2m", 24.9)
            hum = curr.get("relative_humidity_2m", 71)
            wind = curr.get("wind_speed_10m", 4.6)
            
            t_max_list = daily.get("temperature_2m_max", [32.0]*7)
            t_min_list = daily.get("temperature_2m_min", [22.0]*7)
            rain_list = daily.get("precipitation_probability_max", [20]*7)
            code_list = daily.get("weather_code", [1]*7)
            dates = daily.get("time", [""]*7)

            weekday_names = ["SEG", "TER", "QUA", "QUI", "SEX", "SÁB", "DOM"]
            full_names = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
            
            import datetime
            forecast_7d = []
            for i in range(min(7, len(dates))):
                dt_str = dates[i]
                try:
                    dt = datetime.date.fromisoformat(dt_str)
                    w_idx = dt.weekday()
                    day_abbr = weekday_names[w_idx]
                    full_day = full_names[w_idx]
                except Exception:
                    day_abbr = weekday_names[i % 7]
                    full_day = full_names[i % 7]

                wcode = code_list[i] if i < len(code_list) else 1
                if wcode == 0:
                    icon = "☀️"
                    cond = "Ensolarado"
                elif wcode in [1, 2, 3]:
                    icon = "🌤️" if wcode == 1 else "⛅"
                    cond = "Parcialmente nublado"
                elif wcode in [45, 48]:
                    icon = "🌫️"
                    cond = "Nevoeiro"
                elif wcode in [51, 53, 55, 61, 63, 65]:
                    icon = "🌧️"
                    cond = "Chuva"
                elif wcode in [80, 81, 82]:
                    icon = "🌦️"
                    cond = "Pancadas de chuva"
                elif wcode >= 95:
                    icon = "⛈️"
                    cond = "Tempestade"
                else:
                    icon = "🌤️"
                    cond = "Sol com nuvens"

                forecast_7d.append({
                    "day": day_abbr,
                    "full_day": full_day,
                    "date": dt_str,
                    "temp_max": round(t_max_list[i] if i < len(t_max_list) else 30.0),
                    "temp_min": round(t_min_list[i] if i < len(t_min_list) else 20.0),
                    "rain_pct": int(rain_list[i] if i < len(rain_list) and rain_list[i] is not None else 15),
                    "icon": icon,
                    "condition": cond
                })
            
            t_max = t_max_list[0] if t_max_list else 32.1
            t_min = t_min_list[0] if t_min_list else 22.6
            
            weather_data = {
                "city": "Catanduva, SP",
                "temperature": round(temp, 1),
                "humidity": hum,
                "wind_speed": round(wind, 1),
                "temp_min": round(t_min, 1),
                "temp_max": round(t_max, 1),
                "temp_avg": round((t_min + t_max) / 2, 1),
                "condition": "Predomínio de sol" if curr.get("weather_code", 0) <= 2 else "Parcialmente nublado",
                "forecast_7d": forecast_7d
            }
            cache["weather"] = weather_data
            cache["weather_ts"] = now
            return weather_data
    except Exception as e:
        print("[!] Erro Weather Catanduva:", e)
        fallback_days = [
            {"day": "SEG", "full_day": "Segunda", "temp_max": 29, "temp_min": 19, "rain_pct": 15, "icon": "☀️", "condition": "Ensolarado"},
            {"day": "TER", "full_day": "Terça", "temp_max": 28, "temp_min": 18, "rain_pct": 60, "icon": "🌧️", "condition": "Chuva"},
            {"day": "QUA", "full_day": "Quarta", "temp_max": 26, "temp_min": 17, "rain_pct": 80, "icon": "🌧️", "condition": "Chuva forte"},
            {"day": "QUI", "full_day": "Quinta", "temp_max": 28, "temp_min": 18, "rain_pct": 30, "icon": "⛅", "condition": "Parcialmente nublado"},
            {"day": "SEX", "full_day": "Sexta", "temp_max": 30, "temp_min": 19, "rain_pct": 10, "icon": "☀️", "condition": "Céu aberto"},
            {"day": "SÁB", "full_day": "Sábado", "temp_max": 31, "temp_min": 20, "rain_pct": 5, "icon": "☀️", "condition": "Calor"},
            {"day": "DOM", "full_day": "Domingo", "temp_max": 29, "temp_min": 19, "rain_pct": 20, "icon": "🌤️", "condition": "Sol com nuvens"}
        ]
        return {
            "city": "Catanduva, SP",
            "temperature": 27.5,
            "humidity": 55,
            "wind_speed": 12.0,
            "temp_min": 19.0,
            "temp_max": 31.0,
            "temp_avg": 25.0,
            "condition": "Parcialmente nublado",
            "forecast_7d": fallback_days
        }

def build_weather_ui_spec(weather_info=None):
    if not weather_info:
        weather_info = get_catanduva_weather()
    
    daily_list = weather_info.get("forecast_7d", [])
    if not daily_list:
        cache["weather"] = None  # Limpa cache inválido
        weather_info = get_catanduva_weather()
        daily_list = weather_info.get("forecast_7d", [])
    current_temp = weather_info.get("temperature", 28.0)
    city = weather_info.get("city", "Catanduva, SP")
    
    rainiest_day = "Quarta"
    max_rain = 0
    for d in daily_list:
        if d.get("rain_pct", 0) > max_rain:
            max_rain = d["rain_pct"]
            rainiest_day = d.get("full_day", d.get("day", "Quarta"))
            
    highlight = f"{rainiest_day} será o dia mais chuvoso ({max_rain}% de probabilidade), com máxima de {round(weather_info.get('temp_max', 31))}°C."
    
    return {
        "type": "weather",
        "title": "PREVISÃO DA SEMANA",
        "location": city,
        "current_temp": round(current_temp),
        "current_condition": weather_info.get("condition", "Ensolarado"),
        "current_icon": "🌤️" if current_temp > 24 else "🌧️",
        "humidity_pct": weather_info.get("humidity", 55),
        "wind_kmh": weather_info.get("wind_speed", 10),
        "rain_probability_pct": max_rain or 35,
        "highlight_quote": highlight,
        "days": daily_list,
        "chart": {
            "type": "area",
            "labels": [d.get("day") for d in daily_list],
            "values": [round(d.get("temp_max", 28)) for d in daily_list]
        },
        "actions": [
            { "id": "refresh_radar", "label": "Atualizar Radar", "action": "ui.refresh" },
            { "id": "toggle_radar_3d", "label": "Ver Globo 3D", "action": "ui.navigate", "target": "radar3d" }
        ]
    }

def get_zima_metrics(force=False):
    now = time.time()
    if not force and cache["system"] and (now - cache["system_ts"] < 2.5):
        return cache["system"]
    
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(ZIMA_IP, username=ZIMA_USER, password=ZIMA_PASS, timeout=8)
        
        remote_code = (
            "python3 -c \""
            "import os, json, time, subprocess\n"
            "temp = 0.0\n"
            "for z in os.listdir('/sys/class/thermal'):\n"
            "    if z.startswith('thermal_zone'):\n"
            "        try:\n"
            "            with open(f'/sys/class/thermal/{z}/type') as f: zt = f.read().strip()\n"
            "            with open(f'/sys/class/thermal/{z}/temp') as f: zv = float(f.read().strip())/1000.0\n"
            "            if 'pkg' in zt.lower() or 'x86' in zt.lower() or zv > temp:\n"
            "                temp = zv\n"
            "        except Exception: pass\n"
            "mem = {}\n"
            "try:\n"
            "    for line in open('/proc/meminfo'):\n"
            "        p = line.split(':')\n"
            "        if len(p) == 2: mem[p[0].strip()] = int(p[1].split()[0])\n"
            "except Exception: pass\n"
            "ram_total = round(mem.get('MemTotal', 0) / 1024, 1)\n"
            "ram_avail = round(mem.get('MemAvailable', 0) / 1024, 1)\n"
            "ram_used = round(ram_total - ram_avail, 1)\n"
            "ram_pct = round((ram_used / ram_total) * 100, 1) if ram_total > 0 else 0.0\n"
            "c1 = [int(x) for x in open('/proc/stat').readline().split()[1:8]]\n"
            "time.sleep(0.12)\n"
            "c2 = [int(x) for x in open('/proc/stat').readline().split()[1:8]]\n"
            "idle1, idle2 = c1[3] + c1[4], c2[3] + c2[4]\n"
            "t1, t2 = sum(c1), sum(c2)\n"
            "cpu_pct = round(100.0 * (1.0 - (idle2 - idle1)/(t2 - t1)), 1) if t2 > t1 else 0.0\n"
            "disk = {}\n"
            "try:\n"
            "    st = os.statvfs('/DATA') if os.path.exists('/DATA') else os.statvfs('/')\n"
            "    tot = round((st.f_blocks * st.f_frsize) / (1024**3), 1)\n"
            "    free = round((st.f_bavail * st.f_frsize) / (1024**3), 1)\n"
            "    used = round(tot - free, 1)\n"
            "    pct = round((used / tot) * 100, 1) if tot > 0 else 0.0\n"
            "    disk = {'total_gb': tot, 'used_gb': used, 'free_gb': free, 'pct': pct, 'mount': '/DATA'}\n"
            "except Exception: pass\n"
            "uptime_str = ''\n"
            "try:\n"
            "    up_s = int(float(open('/proc/uptime').readline().split()[0]))\n"
            "    uptime_str = f'{up_s // 3600}h {(up_s % 3600) // 60}m'\n"
            "except Exception: pass\n"
            "containers = []\n"
            "try:\n"
            "    out = subprocess.check_output('docker ps --format \\'{{.Names}}|{{.Status}}\\'', shell=True, creationflags=0x08000000 if sys.platform == 'win32' else 0).decode()\n"
            "    for l in out.strip().split('\\n'):\n"
            "        if '|' in l:\n"
            "            n, s = l.split('|', 1)\n"
            "            containers.append({'name': n.strip(), 'status': s.strip()})\n"
            "except Exception: pass\n"
            "res = {\n"
            "    'cpu_temp': round(temp, 1),\n"
            "    'cpu_pct': cpu_pct,\n"
            "    'ram_total_mb': ram_total,\n"
            "    'ram_used_mb': ram_used,\n"
            "    'ram_total_gb': round(ram_total / 1024, 1),\n"
            "    'ram_used_gb': round(ram_used / 1024, 1),\n"
            "    'ram_pct': ram_pct,\n"
            "    'disk': disk,\n"
            "    'uptime': uptime_str,\n"
            "    'total_containers': len(containers),\n"
            "    'containers': containers,\n"
            "    'status': 'ONLINE',\n"
            "    'host': os.environ.get('ZIMA_IP', '127.0.0.1')\n"
            "}\n"
            "print(json.dumps(res))\n"
            "\""
        )
        
        stdin, stdout, stderr = ssh.exec_command(remote_code, timeout=10)
        raw_out = stdout.read().decode('utf-8', errors='ignore').strip()
        ssh.close()
        
        data = json.loads(raw_out)
        data["host"] = ZIMA_IP
        data["status"] = "ONLINE"
        cache["system"] = data
        cache["system_ts"] = now
        return data
    except Exception as e:
        print("[!] Erro ZimaOS:", e)
        return {
            "status": "OFFLINE",
            "error": str(e),
            "cpu_temp": 0.0,
            "cpu_pct": 0.0,
            "ram_pct": 0.0,
            "ram_total_gb": 0.0,
            "ram_used_gb": 0.0,
            "disk": {"total_gb": 0.0, "used_gb": 0.0, "free_gb": 0.0, "pct": 0.0, "mount": "/DATA"},
            "containers": [],
            "total_containers": 0,
            "uptime": "--",
            "host": ZIMA_IP
        }


def get_pluggy_finance():
    now = time.time()
    if cache["finance"] and (now - cache["finance_ts"] < 60):
        return cache["finance"]
    
    try:
        auth_url = os.environ.get("PLUGGY_AUTH_URL", "https://api.pluggy.ai/auth")
        payload = json.dumps({
            "clientId": PLUGGY_CLIENT_ID,
            "clientSecret": PLUGGY_CLIENT_SECRET
        }).encode("utf-8")
        req = urllib.request.Request(auth_url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=8) as resp:
            token_data = json.loads(resp.read().decode("utf-8"))
            api_key = token_data["apiKey"]
            
        acc_url = f"https://api.pluggy.ai/accounts?itemId={PLUGGY_ITEM_ID}"
        req_acc = urllib.request.Request(acc_url, headers={"X-API-KEY": api_key})
        with urllib.request.urlopen(req_acc, timeout=8) as resp:
            acc_data = json.loads(resp.read().decode("utf-8"))
            
        accounts = []
        for acc in acc_data.get("results", []):
            accounts.append({
                "name": acc.get("name"),
                "type": acc.get("type"),
                "balance": acc.get("balance", 0.0),
                "currency": acc.get("currencyCode", "BRL")
            })
            
        data = {
            "accounts": accounts,
            "updated_at": time.strftime("%d/%m/%Y %H:%M")
        }
        cache["finance"] = data
        cache["finance_ts"] = now
        return data
    except Exception as e:
        print("[!] Erro Pluggy:", e)
        return {"accounts": [], "updated_at": "Offline"}


# ==============================================================================
# WAKE-ON-LAN (WoL) - Ligação remota de PCs na própria rede ou em rede remota
# ==============================================================================
WOL_DEVICES_FILE = os.path.join(DIRECTORY, "config", "wol_devices.json")

def _load_wol_devices() -> list:
    if os.path.exists(WOL_DEVICES_FILE):
        try:
            with open(WOL_DEVICES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception as e:
            print(f"[WoL] Erro ao ler {WOL_DEVICES_FILE}: {e}")
    return []

def _save_wol_devices(devices: list):
    with open(WOL_DEVICES_FILE, "w", encoding="utf-8") as f:
        json.dump(devices, f, indent=2, ensure_ascii=False)

def _normalize_mac(mac: str) -> str:
    clean = re.sub(r"[^0-9a-fA-F]", "", str(mac or "")).lower()
    if len(clean) != 12:
        raise ValueError(f"MAC inválido (esperado 12 dígitos hex): '{mac}'")
    return ":".join(clean[i:i+2] for i in range(0, 12, 2))

def send_wake_on_lan(mac: str, ip: str = "255.255.255.255", port: int = 9, attempts: int = 3) -> dict:
    """
    Envia o pacote mágico Wake-on-LAN via UDP broadcast.
    - Mesma rede: use o broadcast da subnet (ex.: 192.168.0.255) ou 255.255.255.255.
    - Outra rede com IP fixo: informe o broadcast da rede remota (ex.: 200.100.50.255),
      garantindo que o roteador permita broadcast dirigido, ou o IP fixo do host
      caso exista relay/ARP proxy no caminho.
    """
    try:
        mac_norm = _normalize_mac(mac)
    except ValueError as e:
        return {"success": False, "error": str(e)}
    mac_bytes = bytes.fromhex(mac_norm.replace(":", ""))
    magic = b"\xff" * 6 + mac_bytes * 16
    target_ip = (ip or "255.255.255.255").strip()
    try:
        target_port = int(port or 9)
    except Exception:
        target_port = 9
    sent = 0
    last_err = None
    for _ in range(max(1, int(attempts))):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                s.settimeout(2)
                s.sendto(magic, (target_ip, target_port))
                sent += 1
        except Exception as e:
            last_err = str(e)
    if sent == 0:
        return {"success": False, "error": f"Falha ao enviar pacote mágico para {target_ip}:{target_port}: {last_err}"}
    return {
        "success": True,
        "mac": mac_norm,
        "ip": target_ip,
        "port": target_port,
        "attempts_sent": sent,
        "message": f"Pacote mágico Wake-on-LAN enviado {sent}x para {mac_norm} via {target_ip}:{target_port}."
    }

def find_wol_device(name_or_mac: str):
    """Localiza um dispositivo cadastrado por nome (ou trecho) ou por MAC."""
    devices = _load_wol_devices()
    q = str(name_or_mac or "").lower().strip()
    if not q:
        return None
    q_hex = re.sub(r"[^0-9a-f]", "", q)
    for d in devices:
        d_name = str(d.get("name", "")).lower()
        d_mac = str(d.get("mac", "")).lower()
        if q in d_name or (len(q_hex) >= 6 and q_hex in d_mac.replace(":", "")):
            return d
    return None

# ==============================================================================
# PUSH NOTIFICATIONS (Web Push VAPID) - Alertas no PWA (iPhone 16.4+ / Android)
# ==============================================================================
PUSH_SUBSCRIPTIONS_FILE = os.path.join(DIRECTORY, "push_subscriptions.json")
VAPID_KEYS_FILE = os.path.join(DIRECTORY, "auth", "vapid_keys.json")
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "mailto:jarvis@werikspace.xyz")

def _load_or_create_vapid_keys() -> dict:
    """Gera (uma única vez) e persiste o par de chaves VAPID P-256 para Web Push."""
    if os.path.exists(VAPID_KEYS_FILE):
        try:
            with open(VAPID_KEYS_FILE, "r", encoding="utf-8") as f:
                keys = json.load(f)
            if keys.get("publicKey") and keys.get("privateKey"):
                return keys
        except Exception:
            pass
    try:
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.serialization import (
            Encoding, PrivateFormat, NoEncryption, PublicFormat
        )
        private_key = ec.generate_private_key(ec.SECP256R1())
        priv_pem = private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode("utf-8")
        raw_point = private_key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
        public_b64url = base64.urlsafe_b64encode(raw_point).decode("ascii").rstrip("=")
        keys = {"publicKey": public_b64url, "privateKey": priv_pem, "subject": VAPID_SUBJECT}
        os.makedirs(os.path.dirname(VAPID_KEYS_FILE), exist_ok=True)
        with open(VAPID_KEYS_FILE, "w", encoding="utf-8") as f:
            json.dump(keys, f, indent=2)
        print("[Push] Par de chaves VAPID gerado e persistido em auth/vapid_keys.json")
        return keys
    except Exception as e:
        print(f"[Push] Aviso: VAPID indisponível ({e}). Push desativado neste nó.")
        return {}

VAPID_KEYS = _load_or_create_vapid_keys()

def _load_push_subscriptions() -> list:
    if os.path.exists(PUSH_SUBSCRIPTIONS_FILE):
        try:
            with open(PUSH_SUBSCRIPTIONS_FILE, "r", encoding="utf-8") as f:
                subs = json.load(f)
                if isinstance(subs, list):
                    return [s for s in subs if isinstance(s, dict) and s.get("endpoint")]
        except Exception as e:
            print(f"[Push] Erro ao ler {PUSH_SUBSCRIPTIONS_FILE}: {e}")
    return []

def _save_push_subscriptions(subs: list):
    with open(PUSH_SUBSCRIPTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(subs, f, indent=2, ensure_ascii=False)

def _register_push_subscription(sub: dict):
    subs = _load_push_subscriptions()
    endpoint = sub.get("endpoint", "")
    subs = [s for s in subs if s.get("endpoint") != endpoint]
    subs.append(sub)
    _save_push_subscriptions(subs)
    return len(subs)

def _remove_push_subscription(endpoint: str):
    subs = [s for s in _load_push_subscriptions() if s.get("endpoint") != endpoint]
    _save_push_subscriptions(subs)
    return len(subs)

def send_web_push(subscription: dict, payload: dict, ttl: int = 300) -> bool:
    """Envia uma notificação Web Push (VAPID). Remove assinaturas expiradas (410)."""
    if not VAPID_KEYS:
        return False
    try:
        from pywebpush import webpush
        webpush(
            subscription_info=subscription,
            data=json.dumps(payload),
            vapid_private_key=VAPID_KEYS.get("privateKey"),
            vapid_claims={"sub": VAPID_KEYS.get("subject", VAPID_SUBJECT)},
            ttl=ttl
        )
        return True
    except Exception as e:
        msg = str(e)
        if "410" in msg or "Gone" in msg or "expired" in msg.lower():
            _remove_push_subscription(subscription.get("endpoint", ""))
            print("[Push] Assinatura expirada removida automaticamente.")
        print(f"[Push] Falha ao enviar notificação: {msg[:140]}")
        return False

def broadcast_push(title: str, body: str, tag: str = "jarvis") -> int:
    """Envia push para todos os dispositivos inscritos. Retorna quantos receberam."""
    subs = _load_push_subscriptions()
    if not subs:
        return 0
    sent = 0
    for sub in subs:
        if send_web_push(sub, {"title": title, "body": body, "tag": tag}):
            sent += 1
    return sent

# ==============================================================================
# 🎵 SPOTIFY WEB API — controle de reprodução pelo JARVIS (credenciais no ambiente do container)
# ==============================================================================
SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "").strip()
SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "").strip()
SPOTIFY_REFRESH_TOKEN = os.environ.get("SPOTIFY_REFRESH_TOKEN", "").strip()
SPOTIFY_DEFAULT_DEVICE = os.environ.get("SPOTIFY_DEFAULT_DEVICE", "").strip()
SPOTIFY_REDIRECT_URI = os.environ.get("SPOTIFY_REDIRECT_URI", "https://jarvis.werikspace.xyz/spotify/callback").strip()
SPOTIFY_TOKEN_FILE = os.path.join(DIRECTORY, "auth", "spotify_token.json")
SPOTIFY_SCOPES = "user-read-playback-state user-modify-playback-state user-read-currently-playing"
_SPOTIFY_CACHE = {"token": "", "exp": 0.0}


def _spotify_refresh_token() -> str:
    if SPOTIFY_REFRESH_TOKEN:
        return SPOTIFY_REFRESH_TOKEN
    try:
        if os.path.exists(SPOTIFY_TOKEN_FILE):
            with open(SPOTIFY_TOKEN_FILE, "r", encoding="utf-8") as f:
                return str(json.load(f).get("refresh_token", "")).strip()
    except Exception:
        pass
    return ""


def spotify_configured() -> bool:
    return bool(SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET and _spotify_refresh_token())


def _spotify_token() -> str:
    now = time.time()
    if _SPOTIFY_CACHE["token"] and now < (_SPOTIFY_CACHE["exp"] - 30):
        return _SPOTIFY_CACHE["token"]
    if not spotify_configured():
        raise RuntimeError("Spotify não configurado: defina SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET e faça o OAuth (/spotify/login).")
    basic = base64.b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()).decode()
    data = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": _spotify_refresh_token(),
    }).encode()
    req = urllib.request.Request(
        "https://accounts.spotify.com/api/token", data=data,
        headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=15) as r:
        j = json.loads(r.read().decode("utf-8"))
    _SPOTIFY_CACHE["token"] = j.get("access_token", "")
    _SPOTIFY_CACHE["exp"] = now + int(j.get("expires_in", 3600))
    rt = j.get("refresh_token")
    if rt:
        try:
            os.makedirs(os.path.dirname(SPOTIFY_TOKEN_FILE), exist_ok=True)
            with open(SPOTIFY_TOKEN_FILE, "w", encoding="utf-8") as f:
                json.dump({"refresh_token": rt}, f, ensure_ascii=False)
        except Exception:
            pass
    return _SPOTIFY_CACHE["token"]


def _spotify_api(method: str, path: str, body=None, params=None):
    token = _spotify_token()
    url = "https://api.spotify.com/v1" + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read().decode("utf-8")
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as he:
        raw = he.read().decode("utf-8", "replace")
        return he.code, {"error": raw[:300]}


def _smallest_art(images) -> str:
    try:
        imgs = [i for i in images if isinstance(i, dict) and i.get("url")]
        if not imgs:
            return ""
        return min(imgs, key=lambda i: int(i.get("height") or 10**9)).get("url", "")
    except Exception:
        return ""


def spotify_now_playing() -> dict:
    if not spotify_configured():
        return {"success": False, "error": "Spotify não configurado neste nó."}
    try:
        code, j = _spotify_api("GET", "/me/player")
        if code == 204 or not j:
            return {"success": True, "playing": False, "message": "Nenhum dispositivo Spotify ativo no momento."}
        if code != 200:
            return {"success": False, "error": j.get("error")}
        item = j.get("item") or {}
        artists = ", ".join(a.get("name", "") for a in (item.get("artists") or []))
        dev = j.get("device") or {}
        return {
            "success": True, "playing": bool(j.get("is_playing")),
            "title": item.get("name"), "artist": artists,
            "album": (item.get("album") or {}).get("name"),
            "progress_ms": j.get("progress_ms"), "device": dev.get("name"),
            "volume": dev.get("volume_percent"),
            "art_url": _smallest_art((item.get("album") or {}).get("images") or []),
        }
    except Exception as e:
        return {"success": False, "error": str(e)[:200]}


def spotify_devices() -> list:
    try:
        code, j = _spotify_api("GET", "/me/player/devices")
        if code != 200:
            return []
        return j.get("devices") or []
    except Exception:
        return []


def spotify_resolve_device(device_name: str):
    """Resolve o ID de um dispositivo Spotify por trecho do nome (ex.: 'alexa', 'pc', 'werik')."""
    if not device_name:
        return None
    nl = device_name.lower().strip()
    for d in spotify_devices():
        name = str(d.get("name", "")).lower()
        if nl in name or name in nl:
            return d.get("id")
    return None


def spotify_search_track(query: str):
    try:
        code, j = _spotify_api("GET", "/search", params={"q": query, "type": "track", "limit": 1})
        if code != 200:
            return None
        items = ((j.get("tracks") or {}).get("items") or [])
        if not items:
            return None
        t = items[0]
        return {"uri": t.get("uri"), "name": t.get("name"),
                "artist": ", ".join(a.get("name", "") for a in (t.get("artists") or []))}
    except Exception:
        return None


def spotify_play(query=None, device=None, uri=None) -> dict:
    """Toca uma música (por nome/busca) ou continua a reprodução, opcionalmente num dispositivo-alvo."""
    dev_id = None
    if device:
        dev_id = spotify_resolve_device(device)
        if not dev_id:
            names = [d.get("name") for d in spotify_devices()]
            return {"success": False, "error": f"Dispositivo '{device}' não encontrado. Disponíveis: {names}",
                    "devices": names}
    track = None
    uris = None
    if uri:
        uris = [uri]
    elif query:
        track = spotify_search_track(query)
        if not track:
            return {"success": False, "error": f"Música não encontrada: {query}"}
        uris = [track["uri"]]
    body = {"uris": uris} if uris else {}
    params = {"device_id": dev_id} if dev_id else None
    code, j = _spotify_api("PUT", "/me/player/play", body=body, params=params)
    if code in (200, 204):
        return {"success": True, "action": "play",
                "track": (f"{track['name']} — {track['artist']}" if track else (uri or "continuação")),
                "device": device or "dispositivo ativo"}
    if code == 404:
        return {"success": False, "error": "Nenhum dispositivo Spotify ativo. Abra o Spotify num dispositivo."}
    return {"success": False, "error": j.get("error"), "code": code}


def spotify_control(action: str, value=None, query=None, device=None) -> dict:
    if not spotify_configured():
        return {"success": False, "error": "Spotify não configurado neste nó (credenciais ausentes no ambiente)."}
    a = str(action or "").lower().strip()
    dev = {"device_id": SPOTIFY_DEFAULT_DEVICE} if SPOTIFY_DEFAULT_DEVICE else None
    try:
        if a in ("play", "tocar", "tocar_musica", "despausar", "resume", "retomar", "play_music"):
            q = query or (value if isinstance(value, str) and str(value).strip() else None)
            if q or device:
                return spotify_play(query=q, device=(device or (SPOTIFY_DEFAULT_DEVICE or None)))
            code, _ = _spotify_api("PUT", "/me/player/play", body=dev); return {"success": code in (200, 204), "action": "play"}
        if a in ("pause", "pausar", "pausa"):
            code, _ = _spotify_api("PUT", "/me/player/pause", body=dev); return {"success": code in (200, 204), "action": "pause"}
        if a in ("toggle", "play_pause", "alternar"):
            np = spotify_now_playing()
            if np.get("playing"):
                return spotify_control("pause")
            return spotify_control("play")
        if a in ("next", "proxima", "próxima", "skip", "avancar"):
            code, _ = _spotify_api("POST", "/me/player/next", body=dev); return {"success": code in (200, 204), "action": "next"}
        if a in ("previous", "prev", "anterior", "voltar"):
            code, _ = _spotify_api("POST", "/me/player/previous", body=dev); return {"success": code in (200, 204), "action": "previous"}
        if a in ("volume", "volume_set", "set_volume"):
            v = max(0, min(100, int(value if value is not None else 50)))
            code, _ = _spotify_api("PUT", "/me/player/volume", params={"volume_percent": v})
            return {"success": code in (200, 204), "action": "volume", "volume": v}
        if a in ("vol_up", "volume_up", "aumentar_volume"):
            cur = spotify_now_playing().get("volume") or 50
            return spotify_control("volume", max(0, min(100, int(cur) + 10)))
        if a in ("vol_down", "volume_down", "diminuir_volume", "abaixar_volume"):
            cur = spotify_now_playing().get("volume") or 50
            return spotify_control("volume", max(0, min(100, int(cur) - 10)))
        if a in ("seek", "posicao", "posição"):
            ms = int(value or 0)
            code, _ = _spotify_api("PUT", "/me/player/seek", params={"position_ms": ms})
            return {"success": code in (200, 204), "action": "seek", "position_ms": ms}
        if a in ("now_playing", "status", "tocando", "atual", "faixa", "musica_atual"):
            return spotify_now_playing()
        if a in ("devices", "dispositivos", "aparelhos"):
            ds = spotify_devices()
            return {"success": True, "action": "devices",
                    "devices": [{"id": d.get("id"), "name": d.get("name"), "active": d.get("is_active"), "type": d.get("type")} for d in ds]}
        if a in ("set_device", "selecionar_device", "transfer", "transferir"):
            target = str(device or value or "").strip()
            if not target:
                return {"success": False, "error": "dispositivo não informado."}
            code, _ = _spotify_api("PUT", "/me/player", body={"device_ids": [target], "play": True})
            if code not in (200, 204, 202):
                resolved = spotify_resolve_device(target)
                if resolved:
                    code, _ = _spotify_api("PUT", "/me/player", body={"device_ids": [resolved], "play": True})
            return {"success": code in (200, 204, 202), "action": "set_device"}
        return {"success": False, "error": f"ação Spotify desconhecida: {action}"}
    except Exception as e:
        return {"success": False, "error": str(e)[:200]}


# ==============================================================================
# 🌉 PONTE DE COMANDOS REMOTOS (JARVIS no Zima -> PC Windows via desktop app)
# FIFO enqueue (ferramentas MCP) -> poll pelo desktop app -> execução no Windows
# -> resultado devolvido ao agente. Segredo via header X-Bridge-Secret.
# ==============================================================================
REMOTE_COMMANDS_FILE = os.path.join(DIRECTORY, "config", "remote_commands.json")
NODES_REGISTRY_FILE = os.path.join(DIRECTORY, "config", "nodes_registry.json")


LUCIA_ALLOWED_PATHS = (
    "/api/finance/month-summary",
    "/api/finance/categories",
    "/api/dashboard/stats",
    "/api/events",
    "/api/contacts",
    "/api/contracts",
    "/api/tracking/packages",
    "/api/chats",
    "/api/widget/data",
    "/api/intelligence/data",
    "/api/system/status",
    "/api/openclaw/pending-events",
)


def _lucia_api_get(path, query=""):
    """Leitura no painel Lucia via PIN; tudo por env, sem segredo no código."""
    base = os.environ.get("LUCIA_HUB_URL", "http://172.17.0.1:8088").rstrip("/")
    pin = os.environ.get("LUCIA_API_PIN", "")
    if not pin:
        return {"ok": False, "error": "LUCIA_API_PIN não configurado."}
    if path not in LUCIA_ALLOWED_PATHS:
        return {"ok": False, "error": "caminho não permitido."}
    try:
        login = urllib.request.Request(
            base + "/api/auth/verify-pin",
            data=json.dumps({"pin": pin}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(login, timeout=8) as resp:
            token = json.loads(resp.read().decode("utf-8")).get("token", "")
        if not token:
            return {"ok": False, "error": "falha de autenticação no painel."}
        url = base + path + (("?" + query) if query else "")
        req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return {"ok": True, "data": json.loads(resp.read().decode("utf-8"))}
    except Exception as e:
        return {"ok": False, "error": f"painel indisponível: {type(e).__name__}"}


def _nodes_registry_load() -> dict:
    try:
        if os.path.exists(NODES_REGISTRY_FILE):
            with open(NODES_REGISTRY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
    except Exception:
        pass
    return {}


def _nodes_registry_save(registry: dict) -> bool:
    try:
        os.makedirs(os.path.dirname(NODES_REGISTRY_FILE), exist_ok=True)
        with open(NODES_REGISTRY_FILE, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False
_remote_lock = threading.RLock()
_remote_state = {"queue": [], "results": {}, "next_id": 1, "last_poll": 0.0}

# Histórico curto de comandos da ponte (para o painel /api/infra)
_infra_recent = []

def _infra_note(entry):
    try:
        _infra_recent.append(entry)
        if len(_infra_recent) > 12:
            del _infra_recent[:len(_infra_recent) - 12]
    except Exception:
        pass

def _remote_load():
    global _remote_state
    try:
        if os.path.exists(REMOTE_COMMANDS_FILE):
            with open(REMOTE_COMMANDS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                _remote_state = {
                    "queue": [c for c in (data.get("queue") or []) if isinstance(c, dict)],
                    "results": dict(data.get("results") or {}),
                    "next_id": int(data.get("next_id", 1)),
                    "last_poll": float(data.get("last_poll", 0.0))
                }
    except Exception as e:
        print(f"[RemoteBridge] Erro ao carregar estado: {e}")

def _remote_save():
    try:
        with open(REMOTE_COMMANDS_FILE, "w", encoding="utf-8") as f:
            json.dump(_remote_state, f, ensure_ascii=False)
    except Exception as e:
        print(f"[RemoteBridge] Erro ao salvar estado: {e}")

def _bridge_secret_ok(provided: str) -> bool:
    expected = os.environ.get("BRIDGE_SECRET", os.environ.get("OPENCLAW_GATEWAY_TOKEN"))
    return bool(provided) and bool(expected) and provided == expected

_remote_load()

# ==============================================================================
# 🛡 CENTRAL DE CONTROLE DO NÓ — permissões, autostart, testes e status local
# ==============================================================================
NODE_PERM_CATEGORIES = {
    "voice_whisper": "Voz / Whisper (transcrição)",
    "camera_vision": "Câmera e Gestos",
    "screen_capture": "Captura de tela",
    "keyboard_mouse": "Teclado e Mouse",
    "clipboard": "Área de Transferência",
    "apps": "Abrir/Fechar Aplicativos",
    "windows_mgmt": "Janelas (focar/minimizar/fechar)",
    "media": "Mídia e Volume",
    "telemetry": "Telemetria (CPU/GPU/RAM)",
    "system_commands": "PowerShell/CMD livre",
    "power": "Desligar/Reiniciar/Suspender"
}

if getattr(sys, "frozen", False):
    _perm_base = os.path.normpath(os.path.join(os.path.dirname(sys.executable), ".."))
else:
    _perm_base = DIRECTORY
NODE_PERM_FILE = os.path.join(_perm_base, "config", "node_permissions.json")

def _node_permissions_load() -> dict:
    try:
        if os.path.exists(NODE_PERM_FILE):
            with open(NODE_PERM_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {k: True for k in NODE_PERM_CATEGORIES}

def _node_permission_save(perms: dict):
    with open(NODE_PERM_FILE, "w", encoding="utf-8") as f:
        json.dump(perms, f, indent=2, ensure_ascii=False)

def _node_bridge_log_path() -> str:
    cands = []
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        pack_root = os.path.dirname(exe_dir)
        cands += [os.path.join(pack_root, "app", "logs", "remote_bridge.log"),
                  os.path.join(exe_dir, "logs", "remote_bridge.log")]
    else:
        cands += [os.path.join(DIRECTORY, "logs", "remote_bridge.log")]
    for c in cands:
        if os.path.exists(c):
            return c
    return cands[0]

CANVAS_PANELS_DIR = os.path.join(DIRECTORY, "canvas_panels")

def _node_mic_resolve():
    """Resolve o microfone do nó: island_settings.mic_device > auto FIFINE K670 > default."""
    want = ""
    try:
        sp = os.path.join(_perm_base, "config", "island_settings.json")
        if os.path.exists(sp):
            with open(sp, "r", encoding="utf-8") as f:
                want = str(json.load(f).get("mic_device", "")).strip().lower()
    except Exception:
        pass
    try:
        import sounddevice as sd
        devs = sd.query_devices()
        if want:
            for i, d in enumerate(devs):
                if d.get("max_input_channels", 0) > 0 and want in str(d.get("name", "")).lower():
                    return i, str(d.get("name"))
        for i, d in enumerate(devs):
            name = str(d.get("name", "")).lower()
            if d.get("max_input_channels", 0) > 0 and ("k670" in name or "fifine" in name):
                return i, str(d.get("name"))
    except Exception:
        pass
    return None, "padrão do sistema"

def _node_mic_status() -> dict:
    idx, name = _node_mic_resolve()
    candidates = []
    try:
        import sounddevice as sd
        for i, d in enumerate(sd.query_devices()):
            if d.get("max_input_channels", 0) > 0:
                candidates.append({"index": i, "name": str(d.get("name"))})
    except Exception:
        pass
    return {"selected": name, "index": idx, "candidates": candidates}

def _canvas_panel_file(pid: str) -> str:
    safe = "".join(c for c in pid if c.isalnum() or c in "-_")[:64]
    return os.path.join(CANVAS_PANELS_DIR, f"panel_{safe}.json")

def _canvas_panel_push(payload: dict, title: str) -> str:
    os.makedirs(CANVAS_PANELS_DIR, exist_ok=True)
    pid = f"{int(time.time()*1000)}-{secrets.token_hex(3)}"
    with open(_canvas_panel_file(pid), "w", encoding="utf-8") as f:
        json.dump({"id": pid, "title": title, "payload": payload, "created_at": time.time()}, f, ensure_ascii=False)
    # Coleta: remove painéis com mais de 10 minutos
    try:
        for fn in os.listdir(CANVAS_PANELS_DIR):
            fp = os.path.join(CANVAS_PANELS_DIR, fn)
            if os.path.exists(fp) and os.path.getmtime(fp) < time.time() - 600:
                os.remove(fp)
    except Exception:
        pass
    return pid

_AUTOSTART_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_AUTOSTART_NAME = "JarvisDesktop"

def _node_autostart_query():
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _AUTOSTART_RUN_KEY, 0, winreg.KEY_READ)
        val, _ = winreg.QueryValueEx(key, _AUTOSTART_NAME)
        winreg.CloseKey(key)
        return True, val
    except FileNotFoundError:
        return False, ""
    except Exception:
        return False, ""

def _node_autostart_set(enabled: bool):
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _AUTOSTART_RUN_KEY, 0, winreg.KEY_SET_VALUE)
        if enabled:
            if getattr(sys, "frozen", False):
                cmd = f'"{sys.executable}"'
            else:
                pyw = sys.executable.replace("python.exe", "pythonw.exe")
                if not os.path.exists(pyw):
                    pyw = sys.executable
                cmd = f'"{pyw}" "{os.path.join(DIRECTORY, "desktop", "app.py")}"'
            winreg.SetValueEx(key, _AUTOSTART_NAME, 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(key, _AUTOSTART_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        return True
    except Exception:
        return False

# ==============================================================================
# 🧬 PROTOCOLO CANVAS INTERATIVO MCP (ZERO DADOS FICTÍCIOS / COMPONENTES TIPADOS)
# ==============================================================================

# Ações de canvas reconhecidas pelo /api/canvas/action (qualquer outra é rejeitada)
KNOWN_CANVAS_ACTIONS = {
    "restart_container", "docker_prune", "view_container_logs", "kill_windows_process",
    "refresh_canvas_containers", "refresh_windows_processes", "refresh_pluggy",
    "refresh_connectivity", "refresh_openclaw", "refresh_hardware_charts",
    "show_hardware_charts", "hardware_charts", "open_desktop_canvas",
    "shutdown_pc", "desligar_pc", "desligar",
    "abort_shutdown", "cancelar_desligamento",
    "restart_pc", "reiniciar_pc", "sleep_pc", "suspender_pc"
}

def exec_zima_command(cmd: str, timeout: int = 15) -> str:
    """Executa um comando no servidor ZimaOS via SSH com tratamento seguro de erros."""
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(ZIMA_IP, username=ZIMA_USER, password=ZIMA_PASS, timeout=timeout)
        stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode('utf-8', errors='ignore')
        err = stderr.read().decode('utf-8', errors='ignore')
        ssh.close()
        return (out + "\n" + err).strip()
    except Exception as e:
        return f"Erro SSH ({ZIMA_IP}): {e}"

def get_real_zima_containers() -> list:
    """Recupera a lista completa de containers reais do ZimaOS via Docker CLI."""
    try:
        raw = exec_zima_command("docker ps -a --format '{{.Names}}#{{.Status}}#{{.Image}}'")
        containers = []
        for line in raw.split('\n'):
            line = line.strip()
            if '#' in line:
                parts = line.split('#')
                name = parts[0].strip()
                status = parts[1].strip() if len(parts) > 1 else ""
                image = parts[2].strip() if len(parts) > 2 else ""
                
                st_lower = status.lower()
                if "restarting" in st_lower:
                    color = "rose"
                    state = "RESTARTING"
                elif "unhealthy" in st_lower:
                    color = "amber"
                    state = "UNHEALTHY"
                elif "healthy" in st_lower or "up" in st_lower:
                    color = "emerald"
                    state = "HEALTHY" if "healthy" in st_lower else "ONLINE"
                else:
                    color = "slate"
                    state = "EXPOSING"
                    
                containers.append({
                    "name": name,
                    "status": status,
                    "image": image,
                    "color": color,
                    "state": state
                })
        return containers
    except Exception as e:
        print("[!] Erro Zima containers:", e)
        return []

def get_real_pluggy_transactions() -> list:
    """Consulta o extrato real da conta corrente e cartão MEI do Banco Inter via Pluggy."""
    try:
        auth_url = os.environ.get("PLUGGY_AUTH_URL", "https://api.pluggy.ai/auth")
        payload = json.dumps({"clientId": PLUGGY_CLIENT_ID, "clientSecret": PLUGGY_CLIENT_SECRET}).encode("utf-8")
        req = urllib.request.Request(auth_url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=8) as resp:
            token_data = json.loads(resp.read().decode("utf-8"))
            api_key = token_data["apiKey"]

        acc_url = f"https://api.pluggy.ai/accounts?itemId={PLUGGY_ITEM_ID}"
        req_acc = urllib.request.Request(acc_url, headers={"X-API-KEY": api_key})
        with urllib.request.urlopen(req_acc, timeout=8) as resp:
            acc_data = json.loads(resp.read().decode("utf-8"))

        all_txs = []
        for acc in acc_data.get("results", []):
            acc_id = acc.get("id")
            acc_name = acc.get("name", "CONTA")
            tx_url = f"https://api.pluggy.ai/transactions?accountId={acc_id}&pageSize=5"
            req_tx = urllib.request.Request(tx_url, headers={"X-API-KEY": api_key})
            try:
                with urllib.request.urlopen(req_tx, timeout=8) as resp_tx:
                    tx_res = json.loads(resp_tx.read().decode("utf-8"))
                    for t in tx_res.get("results", []):
                        raw_date = t.get("date", "")[:10]
                        parts = raw_date.split('-')
                        fmt_date = f"{parts[2]}/{parts[1]}" if len(parts) == 3 else raw_date
                        all_txs.append({
                            "account": acc_name,
                            "date": fmt_date,
                            "raw_date": raw_date,
                            "description": t.get("description", "Transação"),
                            "amount": t.get("amount", 0.0),
                            "currency": t.get("currencyCode", "BRL")
                        })
            except Exception:
                pass
        all_txs.sort(key=lambda x: x["raw_date"], reverse=True)
        return all_txs[:8]
    except Exception as e:
        print("[!] Erro Pluggy Transactions:", e)
        return []

def build_zima_containers_canvas():
    """Gera o Canvas com a tabela viva dos containers reais do ZimaOS."""
    ctns = get_real_zima_containers()
    total = len(ctns)
    online = len([c for c in ctns if c["color"] == "emerald"])
    warning = len([c for c in ctns if c["color"] in ["rose", "amber"]])
    
    rows = []
    for c in ctns:
        rows.append({
            "id": c["name"],
            "cells": [
                {"type": "text", "primary": c["name"], "secondary": c["image"][:32] + "..." if len(c["image"]) > 32 else c["image"]},
                {"type": "badge", "label": c["status"], "color": c["color"]},
                {"type": "actions", "buttons": [
                    {"label": "🔄 Reiniciar", "action": "restart_container", "target": c["name"], "color": "cyan"},
                    {"label": "📜 Logs", "action": "view_container_logs", "target": c["name"], "color": "sky"}
                ]}
            ]
        })
        
    return {
        "title": "CENTRAL DE CONTAINERS ZIMAOS",
        "subtitle": f"HOST: {ZIMA_IP} • DOCKER ECOSYSTEM",
        "category": "INFRAESTRUTURA CLOUD",
        "layout_mode": "sidebar",
        "blocks": [
            {
                "type": "metric_grid",
                "columns": 3,
                "items": [
                    {"label": "TOTAL DE CONTAINERS", "value": str(total), "color": "cyan"},
                    {"label": "ESTÁVEIS (UP/HEALTHY)", "value": str(online), "color": "emerald"},
                    {"label": "ALERTAS / CRÍTICOS", "value": str(warning), "color": "rose" if warning > 0 else "slate"}
                ]
            },
            {
                "type": "interactive_table",
                "table_id": "zima-ctns-table",
                "searchable": True,
                "placeholder": "Buscar container por nome...",
                "columns": ["CONTAINER / IMAGEM", "STATUS", "CONTROLES"],
                "rows": rows
            },
            {
                "type": "action_buttons",
                "buttons": [
                    {"label": "🧹 Prune Cache Docker", "action": "docker_prune", "target": "", "color": "emerald"},
                    {"label": "🔄 Atualizar Lista", "action": "refresh_canvas_containers", "target": "", "color": "cyan"}
                ]
            }
        ]
    }

def build_windows_processes_canvas():
    """Gera o Canvas com os processos reais que mais consomem memória no Windows."""
    procs = hc.get_top_windows_processes(limit=8)
    hw = hc.get_hardware_telemetry()
    
    rows = []
    for p in procs:
        rows.append({
            "id": str(p["pid"]),
            "cells": [
                {"type": "text", "primary": p["name"], "secondary": f"PID: {p['pid']}"},
                {"type": "badge", "label": f"{p['mem_mb']} MB", "color": "cyan" if p['mem_mb'] < 600 else "amber"},
                {"type": "text", "primary": f"{p['cpu_percent']}%", "secondary": "CPU"},
                {"type": "actions", "buttons": [
                    {"label": "⛔ Encerrar", "action": "kill_windows_process", "target": str(p["pid"]), "color": "rose"}
                ]}
            ]
        })
        
    return {
        "title": "GERENCIADOR DE PROCESSOS DO WINDOWS",
        "subtitle": "TELEMETRIA DE PROCESSOS FÍSICOS LOCAIS",
        "category": "HARDWARE & SISTEMA",
        "layout_mode": "sidebar",
        "blocks": [
            {
                "type": "metric_grid",
                "columns": 3,
                "items": [
                    {"label": "MEMÓRIA RAM USADA", "value": f"{hw['ram_used_gb']} GB", "sub": f"{hw['ram_percent']}% utilizada", "color": "cyan"},
                    {"label": "CARGA TOTAL CPU", "value": f"{hw['cpu_percent']}%", "color": "emerald"},
                    {"label": "GPU GTX 1660 Ti", "value": f"{hw['gpu']['temperature']}°C", "sub": f"{hw['gpu']['vram_used_mb']} MB VRAM", "color": "sky"}
                ]
            },
            {
                "type": "interactive_table",
                "table_id": "win-procs-table",
                "searchable": True,
                "placeholder": "Buscar processo pelo nome ou PID...",
                "columns": ["PROCESSO", "MEMÓRIA RAM", "CPU", "AÇÃO"],
                "rows": rows
            },
            {
                "type": "action_buttons",
                "buttons": [
                    {"label": "🔄 Atualizar Processos", "action": "refresh_windows_processes", "target": "", "color": "cyan"}
                ]
            }
        ]
    }

def build_hardware_charts_canvas(layout_mode: str = "sidebar"):
    """Gera o Canvas com gráficos de alta fidelidade da GPU GTX 1660 Ti, CPU, RAM e Controles de Energia do Windows."""
    hw = hc.get_hardware_telemetry()
    sav = hc.get_local_savings_telemetry()
    gpu = hw.get("gpu", {})
    
    gpu_util = int(gpu.get("utilization", 25))
    gpu_temp = int(gpu.get("temperature", 50))
    vram_used = int(gpu.get("vram_used_mb", 3000))
    vram_total = int(gpu.get("vram_total_mb", 6144))
    vram_pct = float(gpu.get("vram_pct", round(vram_used / vram_total * 100, 1)))
    
    cpu_pct = float(hw.get("cpu_percent", 15.0))
    ram_pct = float(hw.get("ram_percent", 75.0))
    ram_used = float(hw.get("ram_used_gb", 12.0))
    ram_total = float(hw.get("ram_total_gb", 16.0))
    disk_c_pct = float(hw.get("disk_c_percent", 98.0))
    disk_c_free = float(hw.get("disk_c_free_gb", 14.0))

    chart_svg = f"""
    <div class="my-3 p-4 rounded-2xl bg-[#040919]/90 border border-cyan-400/50 shadow-[0_0_30px_rgba(0,240,255,0.15)]">
      <div class="flex items-center justify-between mb-3">
        <div class="flex items-center space-x-2">
          <span class="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-ping"></span>
          <span class="text-[11px] font-mono-code font-bold text-cyan-300 tracking-wider">LIVE GPU & CPU TELEMETRY CURVES</span>
        </div>
        <div class="flex items-center space-x-3 text-[10px] font-mono-code">
          <span class="flex items-center gap-1 text-cyan-400"><span class="w-2 h-2 rounded bg-cyan-400"></span> GPU {gpu_util}%</span>
          <span class="flex items-center gap-1 text-sky-400"><span class="w-2 h-2 rounded bg-sky-400"></span> CPU {cpu_pct}%</span>
          <span class="flex items-center gap-1 text-amber-400"><span class="w-2 h-2 rounded bg-amber-400"></span> Temp {gpu_temp}°C</span>
        </div>
      </div>
      
      <div class="relative w-full h-44 bg-slate-950/80 rounded-xl overflow-hidden border border-sky-900/60 p-2">
        <svg viewBox="0 0 460 150" class="w-full h-full overflow-visible" preserveAspectRatio="none">
          <defs>
            <linearGradient id="gpuGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="#00f0ff" stop-opacity="0.55"/>
              <stop offset="100%" stop-color="#00f0ff" stop-opacity="0.0"/>
            </linearGradient>
            <linearGradient id="cpuGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="#38bdf8" stop-opacity="0.45"/>
              <stop offset="100%" stop-color="#38bdf8" stop-opacity="0.0"/>
            </linearGradient>
            <filter id="glow">
              <feGaussianBlur stdDeviation="2" result="coloredBlur"/>
              <feMerge>
                <feMergeNode in="coloredBlur"/>
                <feMergeNode in="SourceGraphic"/>
              </feMerge>
            </filter>
          </defs>
          
          <line x1="30" y1="20" x2="450" y2="20" stroke="rgba(0,240,255,0.12)" stroke-dasharray="3,3"/>
          <text x="5" y="24" fill="rgba(100,150,220,0.6)" font-size="9" font-family="monospace">100%</text>
          
          <line x1="30" y1="55" x2="450" y2="55" stroke="rgba(0,240,255,0.12)" stroke-dasharray="3,3"/>
          <text x="10" y="59" fill="rgba(100,150,220,0.6)" font-size="9" font-family="monospace">60%</text>
          
          <line x1="30" y1="90" x2="450" y2="90" stroke="rgba(0,240,255,0.12)" stroke-dasharray="3,3"/>
          <text x="10" y="94" fill="rgba(100,150,220,0.6)" font-size="9" font-family="monospace">30%</text>
          
          <line x1="30" y1="130" x2="450" y2="130" stroke="rgba(0,240,255,0.2)"/>
          <text x="16" y="134" fill="rgba(100,150,220,0.6)" font-size="9" font-family="monospace">0%</text>

          <!-- Curva GPU Area Spline -->
          <path d="M 30 {130 - int(gpu_util * 0.7 * 1.1)} Q 90 {130 - int(max(10, gpu_util - 15) * 1.1)}, 150 {130 - int(max(15, gpu_util + 10) * 1.1)} T 270 {130 - int(max(20, gpu_util - 5) * 1.1)} T 390 {130 - int(max(10, gpu_util + 8) * 1.1)} T 450 {130 - int(gpu_util * 1.1)} L 450 130 L 30 130 Z" fill="url(#gpuGrad)"/>
          <path d="M 30 {130 - int(gpu_util * 0.7 * 1.1)} Q 90 {130 - int(max(10, gpu_util - 15) * 1.1)}, 150 {130 - int(max(15, gpu_util + 10) * 1.1)} T 270 {130 - int(max(20, gpu_util - 5) * 1.1)} T 390 {130 - int(max(10, gpu_util + 8) * 1.1)} T 450 {130 - int(gpu_util * 1.1)}" fill="none" stroke="#00f0ff" stroke-width="2.5" filter="url(#glow)"/>
          <circle cx="450" cy="{130 - int(gpu_util * 1.1)}" r="4.5" fill="#ffffff" stroke="#00f0ff" stroke-width="2"/>

          <!-- Curva CPU Area Spline -->
          <path d="M 30 {130 - int(cpu_pct * 0.8 * 1.1)} Q 100 {130 - int(max(5, cpu_pct + 12) * 1.1)}, 180 {130 - int(max(5, cpu_pct - 6) * 1.1)} T 310 {130 - int(max(8, cpu_pct + 8) * 1.1)} T 450 {130 - int(cpu_pct * 1.1)} L 450 130 L 30 130 Z" fill="url(#cpuGrad)"/>
          <path d="M 30 {130 - int(cpu_pct * 0.8 * 1.1)} Q 100 {130 - int(max(5, cpu_pct + 12) * 1.1)}, 180 {130 - int(max(5, cpu_pct - 6) * 1.1)} T 310 {130 - int(max(8, cpu_pct + 8) * 1.1)} T 450 {130 - int(cpu_pct * 1.1)}" fill="none" stroke="#38bdf8" stroke-width="2"/>
          <circle cx="450" cy="{130 - int(cpu_pct * 1.1)}" r="3.5" fill="#ffffff" stroke="#38bdf8" stroke-width="1.5"/>
        </svg>
      </div>

      <div class="mt-3 space-y-2 font-mono-code text-[11px]">
        <div>
          <div class="flex justify-between text-slate-300 mb-1">
            <span class="text-cyan-300">GPU VRAM DEDICADA</span>
            <span>{vram_used} MB / {vram_total} MB ({vram_pct}%)</span>
          </div>
          <div class="w-full h-2 rounded-full bg-slate-800 overflow-hidden">
            <div class="h-full bg-gradient-to-r from-cyan-500 to-emerald-400" style="width: {vram_pct}%"></div>
          </div>
        </div>
        <div>
          <div class="flex justify-between text-slate-300 mb-1">
            <span class="text-sky-300">MEMÓRIA RAM DO SISTEMA</span>
            <span>{ram_used:.1f} GB / {ram_total:.1f} GB ({ram_pct}%)</span>
          </div>
          <div class="w-full h-2 rounded-full bg-slate-800 overflow-hidden">
            <div class="h-full bg-gradient-to-r from-sky-500 to-indigo-500" style="width: {ram_pct}%"></div>
          </div>
        </div>
        <div>
          <div class="flex justify-between text-slate-300 mb-1">
            <span class="text-rose-300">DISCO PRINCIPAL (C:)</span>
            <span>{disk_c_free:.1f} GB livres ({disk_c_pct}% ocupado)</span>
          </div>
          <div class="w-full h-2 rounded-full bg-slate-800 overflow-hidden">
            <div class="h-full bg-gradient-to-r from-amber-500 to-rose-500" style="width: {disk_c_pct}%"></div>
          </div>
        </div>
      </div>
    </div>
    """

    return {
        "title": "TELEMETRIA DE HARDWARE & ENERGIA",
        "subtitle": "GPU GTX 1660 Ti • CPU • RAM • CONTROLE DE ENERGIA",
        "category": "HARDWARE & SISTEMA",
        "layout_mode": layout_mode,
        "blocks": [
            {
                "type": "metric_grid",
                "columns": 3,
                "items": [
                    {"label": "GPU GTX 1660 Ti", "value": f"{gpu_util}%", "sub": f"{gpu_temp}°C • 6GB VRAM", "color": "cyan"},
                    {"label": "CARGA CPU", "value": f"{cpu_pct}%", "sub": "Clock Dinâmico", "color": "emerald"},
                    {"label": "VRAM ALOCADA", "value": f"{vram_pct}%", "sub": f"{vram_used} MB em uso", "color": "purple"},
                    {"label": "MEMÓRIA RAM", "value": f"{ram_pct}%", "sub": f"{ram_used:.1f} GB / {ram_total:.1f} GB", "color": "sky"},
                    {"label": "DISCO (C:)", "value": f"{disk_c_pct}%", "sub": f"{disk_c_free:.1f} GB livres", "color": "amber"},
                    {"label": "ECONOMIA LOCAL", "value": sav["money_saved_fmt"], "sub": f"{sav['tokens_saved_fmt']} tokens zero cloud", "color": "emerald"}
                ]
            },
            {
                "type": "html",
                "content": chart_svg
            },
            {
                "type": "action_buttons",
                "buttons": [
                    {"label": "🔄 Atualizar Gráfico", "action": "refresh_hardware_charts", "target": layout_mode, "color": "cyan"},
                    {"label": "🖥️ Abrir Canvas Desktop Nativo", "action": "open_desktop_canvas", "target": "charts", "color": "emerald"},
                    {"label": "⚡ Processos Ativos", "action": "refresh_windows_processes", "target": "", "color": "sky"},
                    {"label": "⛔ DESLIGAR PC (30s)", "action": "shutdown_pc", "target": "30", "color": "rose"},
                    {"label": "🛑 CANCELAR DESLIGAMENTO", "action": "abort_shutdown", "target": "", "color": "amber"}
                ]
            }
        ]
    }

def build_pluggy_transactions_canvas():
    """Gera o Canvas com as transações financeiras reais do Banco Inter."""
    txs = get_real_pluggy_transactions()
    fin = get_pluggy_finance()
    accs = fin.get("accounts", [])
    mei = next((a for a in accs if "MEI" in (a.get("name") or "")), {})
    inter = next((a for a in accs if "INTER" in (a.get("name") or "")), {})
    
    rows = []
    for t in txs:
        amt = t["amount"]
        is_neg = amt < 0
        amt_str = f"R$ {abs(amt):.2f}".replace('.', ',')
        amt_display = f"- {amt_str}" if is_neg else f"+ {amt_str}"
        rows.append({
            "id": t.get("raw_date", "") + t.get("description", ""),
            "cells": [
                {"type": "text", "primary": t["date"], "secondary": t["account"]},
                {"type": "text", "primary": t["description"], "secondary": "Transação Registrada"},
                {"type": "badge", "label": amt_display, "color": "rose" if is_neg else "emerald"}
            ]
        })
        
    return {
        "title": "TRANSAÇÕES BANCÁRIAS REAIS (PLUGGY)",
        "subtitle": "BANCO INTER • CONTA CORRENTE & CARTÃO MEI",
        "category": "OPEN FINANCE",
        "layout_mode": "sidebar",
        "blocks": [
            {
                "type": "metric_grid",
                "columns": max(1, len(accs)),
                "items": [
                    {"label": (a.get('name') or 'CONTA').upper(), "value": f"R$ {a.get('balance', 0.0):.2f}".replace('.', ','), "color": "rose" if "MEI" in (a.get('name') or "") else "cyan"}
                    for a in accs
                ] if accs else [{"label": "PLUGGY OPEN FINANCE", "value": "Sincronizando...", "color": "cyan"}]
            },
            {
                "type": "interactive_table",
                "table_id": "pluggy-txs-table",
                "searchable": True,
                "placeholder": "Buscar compras e transações...",
                "columns": ["DATA / CONTA", "ESTABELECIMENTO", "VALOR"],
                "rows": rows
            },
            {
                "type": "action_buttons",
                "buttons": [
                    {"label": "🔄 Sincronizar Pluggy", "action": "refresh_pluggy", "target": "", "color": "cyan"}
                ]
            }
        ]
    }

def build_connectivity_canvas():
    """Gera o Canvas com o radar de latência TCP real."""
    results = hc.test_system_connectivity()
    rows = []
    items_metric = []
    for r in results:
        lat = f"{r['latency_ms']} ms" if r["latency_ms"] is not None else "TIMED OUT"
        rows.append({
            "id": r["name"],
            "cells": [
                {"type": "text", "primary": r["name"], "secondary": r["service"]},
                {"type": "text", "primary": r["host"], "secondary": "Endpoint"},
                {"type": "badge", "label": r["status"], "color": r["color"]},
                {"type": "badge", "label": lat, "color": r["color"]}
            ]
        })
        if len(items_metric) < 3:
            items_metric.append({
                "label": r["name"],
                "value": lat,
                "color": r["color"]
            })
            
    return {
        "title": "RADAR DE CONECTIVIDADE & PING",
        "subtitle": "LATÊNCIA REAL WINDOWS -> ZIMAOS & SERVIÇOS",
        "category": "TELEMETRIA DE REDE",
        "layout_mode": "sidebar",
        "blocks": [
            {
                "type": "metric_grid",
                "columns": 3,
                "items": items_metric
            },
            {
                "type": "interactive_table",
                "table_id": "network-ping-table",
                "searchable": False,
                "columns": ["SERVIÇO", "HOST / PORTA", "STATUS", "LATÊNCIA"],
                "rows": rows
            },
            {
                "type": "action_buttons",
                "buttons": [
                    {"label": "⚡ Retestar Latência", "action": "refresh_connectivity", "target": "", "color": "cyan"}
                ]
            }
        ]
    }

def build_container_logs_canvas(container_name: str):
    """Gera o Canvas com terminal escuro e logs reais do container."""
    raw_logs = exec_zima_command(f"docker logs --tail 40 {container_name}")
    return {
        "title": f"LOGS EM TEMPO REAL: {container_name.upper()}",
        "subtitle": f"CONTAINER ATIVO NO SERVIDOR ZIMAOS ({ZIMA_IP})",
        "category": "TERMINAL DIAGNÓSTICO",
        "layout_mode": "sidebar",
        "blocks": [
            {
                "type": "code_terminal",
                "title": f"root@zimaos:~# docker logs --tail 40 {container_name}",
                "content": raw_logs
            },
            {
                "type": "action_buttons",
                "buttons": [
                    {"label": f"🔄 Reiniciar {container_name}", "action": "restart_container", "target": container_name, "color": "rose"},
                    {"label": "⬅️ Voltar à Lista", "action": "refresh_canvas_containers", "target": "", "color": "cyan"}
                ]
            }
        ]
    }

def build_openclaw_canvas():
    """Gera o Canvas estruturado com telemetria e logs em tempo real do OpenClaw."""
    stats_raw = exec_zima_command('docker stats --no-stream --format "{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}" openclaw')
    status_raw = exec_zima_command('docker ps --filter name=openclaw --format "{{.Status}}"')
    raw_logs = exec_zima_command("docker logs --tail 35 openclaw")

    cpu_val = "2.5%"
    mem_val = "744 MB"
    if "|" in stats_raw:
        parts = stats_raw.split("|")
        if len(parts) >= 3:
            cpu_val = parts[1].strip()
            mem_val = parts[2].split("/")[0].strip()

    status_str = status_raw.strip() or "Up 3 hours (Online)"

    return {
        "title": "NÚCLEO AUTÔNOMO OPENCLAW (J.A.R.V.I.S.)",
        "subtitle": "AGENTE COGNITIVO • MODELO GEMINI 3.8 FLASH",
        "category": "INTELIGÊNCIA ARTIFICIAL",
        "layout_mode": "sidebar",
        "blocks": [
            {
                "type": "metric_grid",
                "columns": 3,
                "items": [
                    {"label": "STATUS CONTAINER", "value": "ONLINE", "sub": status_str, "color": "emerald"},
                    {"label": "USO DE MEMÓRIA", "value": mem_val, "sub": "Limite: 4 GiB", "color": "cyan"},
                    {"label": "CARGA DE CPU", "value": cpu_val, "sub": "ZimaOS Docker", "color": "sky"}
                ]
            },
            {
                "type": "metric_grid",
                "columns": 2,
                "items": [
                    {"label": "MODELO LLM ATIVO", "value": "Gemini 3.8 Flash", "sub": "Google DeepMind", "color": "amber"},
                    {"label": "HUB MCP PROTOCOL", "value": "8 FERRAMENTAS", "sub": "jarvis-hud @ 8081 SSE", "color": "emerald"}
                ]
            },
            {
                "type": "code_terminal",
                "title": "root@zimaos:~# docker logs --tail 35 openclaw",
                "content": raw_logs
            },
            {
                "type": "action_buttons",
                "buttons": [
                    {"label": "🔄 Reiniciar OpenClaw", "action": "restart_container", "target": "openclaw", "color": "rose"},
                    {"label": "📄 Atualizar Logs", "action": "refresh_openclaw", "target": "", "color": "cyan"},
                    {"label": "🧹 Prune Docker", "action": "docker_prune", "target": "", "color": "amber"}
                ]
            }
        ]
    }



OPENCLAW_MODEL_FAILURE_TOKEN = "__JARVIS_OPENCLAW_MODEL_FAILURE__"


def extract_openclaw_reply(raw_out):
    json_start = raw_out.find('{')
    if json_start != -1:
        try:
            raw_json = raw_out[json_start:]
            data = json.loads(raw_json)
            res = data.get("result", {})
            status = str(data.get("status") or res.get("status") or "").lower()
            if status in {"error", "failed", "failure"} or data.get("error") or res.get("error"):
                return OPENCLAW_MODEL_FAILURE_TOKEN
            payloads = res.get("payloads", [])
            if payloads and isinstance(payloads, list):
                for p in payloads:
                    if isinstance(p, dict) and "text" in p and p["text"]:
                        return p["text"].strip()
            if "finalAssistantVisibleText" in res and res["finalAssistantVisibleText"]:
                return res["finalAssistantVisibleText"].strip()
        except Exception as e:
            print("[!] Erro parse JSON OpenClaw:", e)

    lines = [l for l in raw_out.split('\n') if l.strip() and not l.strip().startswith('{') and not l.strip().startswith('[') and l.strip() != '}']
    if lines:
        return lines[-1].strip()
    return OPENCLAW_MODEL_FAILURE_TOKEN

def call_openclaw_jarvis(message, intent_decision=None, include_finance=True, auth_user=None, auth_role=None, source_device=None, source_authenticated=False):
    try:
        # Puxa dados reais e frescos em tempo real
        weather = get_catanduva_weather()
        finance = get_pluggy_finance() if include_finance else {"accounts": [], "updated_at": "Acesso restrito"}
        system = get_zima_metrics()

        finance_lines = []
        for a in finance.get("accounts", []):
            name = a.get("name", "CONTA")
            bal = a.get("balance", 0.0)
            tipo = "Fatura" if "MEI" in name or a.get("type") == "CREDIT" else "Saldo Disponível"
            finance_lines.append(f"- {name}: {tipo} R$ {bal:.2f}".replace('.', ','))
        telemetry_finance = "\n".join(finance_lines) if finance_lines else "- Nenhuma conta sincronizada no momento."

        hw = hc.get_hardware_telemetry()

        # Contexto injetado pelo Sistema 1 (JEV & Laya) para otimização do 9Router
        s1_tag = ""
        if intent_decision:
            s1_tag = (
                f"[SISTEMA 1 - TRIAGEM JEV/LAYA (TYPESAFE AI)]\n"
                f"• Agente Roteado: {intent_decision.target_agent.upper()}\n"
                f"• Domínio de Decisão: {intent_decision.category.upper()}\n"
                f"• Confiança Calibrada: {int(intent_decision.confidence * 100)}%\n"
                f"• Latência S1: {intent_decision.latency_ms} ms\n"
                f"• Diretriz Sugerida: {intent_decision.recommended_action}\n\n"
            )

        telemetry = (
            f"{s1_tag}"
            f"[DADOS BANCÁRIOS E FINANCEIROS REAIS DO SENHOR WERIK (PLUGGY OPEN FINANCE)]\n"
            f"{telemetry_finance}\n\n"
            f"[DADOS CLIMÁTICOS REAIS EM TEMPO REAL]\n"
            f"- Localidade: {weather['city']}\n"
            f"- Temperatura Real Atual: {weather['temperature']}°C\n"
            f"- Condição Climática: {weather['condition']}\n"
            f"- Mínima Hoje: {weather['temp_min']}°C | Máxima Hoje: {weather['temp_max']}°C\n"
            f"- Umidade do Ar: {weather['humidity']}% | Vento: {weather['wind_speed']} km/h\n\n"
            f"[SISTEMA E INFRAESTRUTURA]\n"
            f"- Servidor ZimaOS: {system.get('total_containers', 39)} containers ativos\n"
            f"- Máquina Física Windows: GPU {hw['gpu']['name']} ({hw['gpu']['temperature']}°C, {hw['gpu']['utilization']}% carga) | CPU {hw['cpu_percent']}% | RAM {hw['ram_percent']}%\n\n"
            f"[VISÃO COMPUTACIONAL LOCAL WEBCAM & RECONHECIMENTO DE GESTOS]\n"
            f"- Status Câmera: {'Ativa (Rastreando em 30 FPS)' if vision_engine.is_camera_enabled() else 'Desativada (Standby 0% CPU)'}\n"
            f"- Último Gesto Detectado: {vision_engine.get_status().get('gesture')} ({vision_engine.get_status().get('confidence_pct')}%) | Mão: {vision_engine.get_status().get('hand')}\n"
            f"- Presença do Usuário: {'Presente' if vision_engine.get_status().get('user_present') else 'Ausente'}\n\n"
            f"[COMANDOS DO HUD VISUAL - FERRAMENTAS MCP JARVIS-HUD DISPONÍVEIS]\n"
            f"Você possui ferramentas MCP registradas e ativas no painel holográfico do Senhor Werik:\n"
            f"- `jarvis-hud__criar_painel_personalizado(titulo='...', conteudo_markdown='...', posicao='center'|'sidebar'|'modal'|'top-right'|'bottom-left', categoria='...', subtitulo='...', metricas_json='[]')`: Cria qualquer widget/painel dinâmico e livre sob medida para o que o usuário pediu!\n"
            f"- `jarvis-hud__buscar_e_projetar_noticia(tema='...', posicao='center'|'sidebar')`: Pesquisa notícias reais em tempo real sobre qualquer tema e projeta o painel no HUD!\n"
            f"- `jarvis-hud__projetar_canvas_interativo(titulo='...', categoria='...', layout='sidebar'|'center'|'modal'|'top-right'|'bottom-left', subtitulo='...', blocks_json='...')`: Projeta canvas holográfico customizado com blocos tipados.\n"
            f"- `jarvis-hud__criar_card_customizado(titulo='...', subtitulo='...', conteudo='...', tipo='padrao')`: Projeta card simples no HUD.\n"
            f"- `jarvis-hud__iniciar_timer_hud(minutos=5, rotulo='...')`: Inicia e projeta um cronômetro regressivo animado no HUD.\n"
            f"- `jarvis-hud__tocar_youtube_hud(termo_ou_musica='...')`: Toca qualquer música ou vídeo diretamente no Cyber Player do HUD.\n"
            f"- `jarvis-hud__projetar_radar_containers_zimaos()`: Projeta a matriz com os 39 containers reais do ZimaOS.\n"
            f"- `jarvis-hud__projetar_processos_windows_reais()`: Projeta o gerenciador de processos ativos do Windows.\n"
            f"- `jarvis-hud__projetar_hardware_hud()`: Projeta a telemetria da máquina física (GPU GTX 1660 Ti, CPU, RAM).\n"
            f"- `jarvis-hud__projetar_extrato_pluggy_real()`: Projeta o extrato real da fatura do cartão MEI e conta do Inter via Pluggy.\n"
            f"- `jarvis-hud__projetar_radar_conectividade()`: Projeta o radar de latência TCP em tempo real.\n"
            f"- `jarvis-hud__exibir_alerta_hud(titulo='...', mensagem='...', nivel='info'|'sucesso'|'aviso'|'erro')`: Exibe banner de alerta no topo.\n"
            f"- `jarvis-hud__executar_comando_windows(acao='...', params_json='...')`: CONTROLA DIRETAMENTE o PC Windows físico do Senhor Werik! Exemplos: application.open+{{\"application\":\"chrome\"}}, audio.set_volume+{{\"percent\":40}}, media.play_pause, windows.focus_window+{{\"title\":\"Spotify\"}}, keyboard.type_text, screen.snapshot, system.info (telemetria GPU/CPU/RAM) e system.run+{{\"command\":\"powershell ...\"}} para comandos livres no PC. Use SEMPRE que o pedido envolver o computador físico.\n"
            f"- `jarvis-hud__spotify_controlar(acao='...', valor='...', musica='...', dispositivo='...')`: CONTROLE REAL DO SPOTIFY (Web API da conta do Senhor Werik). acao = play|pause|toggle|next|previous|volume|seek|now_playing|devices. Para TOCAR uma música use acao='play' + musica='nome da música/artista'. Para tocar num aparelho específico (ex.: Alexa, celular, PC) informe dispositivo='Alexa'. Se pedir para tocar no Windows e o Spotify estiver fechado, a ferramenta abre o Spotify no PC e toca a faixa certa automaticamente.\n"
            f"- `jarvis-hud__exibir_na_esfera(titulo='...', mensagem='...', botao1='...', botao2='...')`: Exibe um card/mensagem NA TELA DA ESFERA FÍSICA J.A.R.V.I.S. (o display redondo na mesa). Texto curto (a tela é pequena).\n"
            f"- `jarvis-hud__mostrar_rosto_esfera(emocao='happy'|'sad'|'angry'|'spotify'|'standby')`: Muda o rostinho/expressão na tela da esfera física.\n"
            f"DIRETRIZ DE LIBERDADE TOTAL DE CRIAÇÃO VISUAL: Senhor Werik exige LIBERDADE TOTAL! Nunca fique preso a templates fixos ou telas pré-fabricadas. Você tem total liberdade de compor painéis personalizados sob medida para o que o usuário pedir (uma notícia específica, uma agenda de hoje, um extrato ou saldo customizado, um planejamento, etc.). Use `jarvis-hud__criar_painel_personalizado` ou `jarvis-hud__buscar_e_projetar_noticia` ou `jarvis-hud__projetar_canvas_interativo`!\n"
            f"[SISTEMA OPERACIONAL VISUAL JARVIS (VISUAL OS DIRECTIVE)]\n"
            f"Você é a inteligência central de um Sistema Operacional Visual. Não responda apenas texto quando a informação se beneficiar de elementos visuais.\n"
            f"Escolha automaticamente a melhor especificação de UI entre os formatos do Renderer:\n"
            f"1. `weather`: Previsão do tempo (curva Bézier SVG 7 dias, umidade, probabilidade de chuva);\n"
            f"2. `comparison`: Comparativo técnico (tabela lado a lado, recomendação em destaque, barras de performance);\n"
            f"3. `checklist`: Tarefas ou passos interativos (checkboxes interativas com barra de progresso);\n"
            f"4. `metric`: Cotações rápidas ou indicadores (número em destaque, variação % e sparklines);\n"
            f"5. `flow`: Fluxogramas e arquitetura de sistemas (nós de etapas com setas e iluminação energética);\n"
            f"6. `timeline`: Cronologia e linha do tempo de eventos;\n"
            f"7. `dashboard`: Relatórios complexos (múltiplas métricas, gráficos e alertas);\n"
            f"8. `form`: Formulários de coleta de dados ou configuração em lote;\n"
            f"9. `controls`: Painéis de controle contextuais com sliders e botões de ajuste.\n"
            f"Se desejar projetar uma UI customizada, inclua no final da resposta um bloco ```json:visual ... ``` contendo a UI Specification.\n\n"
            f"Sempre use dados reais do Banco Inter. NUNCA invente outros bancos. Seja cortês, britânico e objetivo.\n\n"
        )
        esfera_ctx = ""
        if source_device:
            esfera_ctx = (
                f"[ORIGEM DO COMANDO: ESFERA FÍSICA J.A.R.V.I.S.]\n"
                f"Este pedido veio por VOZ da Esfera física (device_id='{source_device}'). "
                f"Você CONTROLA a tela dessa esfera pelas ferramentas MCP:\n"
                f"- `jarvis-hud__exibir_na_esfera(titulo='...', mensagem='...', botao1='...', botao2='...')`: exibe um card/mensagem na tela da esfera.\n"
                f"- `jarvis-hud__mostrar_rosto_esfera(emocao='happy'|'sad'|'angry'|'spotify'|'standby')`: muda o rostinho da esfera.\n"
                f"Sempre que fizer sentido MOSTRAR algo, exiba na tela da esfera com `exibir_na_esfera` "
                f"(texto curto — a tela é pequena, ~240px). O núcleo já sabe que a origem é a esfera '{source_device}' "
                f"e direciona a exibição para ela.\n\n"
            )
        # O Core monta um contexto curto por turno. Só a ponte WSS autenticada pode
        # afirmar a identidade de um dispositivo; texto/JSON do cliente não basta.
        if source_authenticated and source_device:
            origin = f"esfera (dispositivo autenticado: {source_device})"
        elif auth_user:
            origin = "cliente autenticado"
        else:
            origin = "Core (origem não verificada)"

        context = ["[JARVIS CORE]", f"Origem validada: {origin}"]
        if auth_user:
            context.append(f"Usuário autenticado: {auth_user}; papel: {auth_role or 'Operador'}")
        if intent_decision:
            context.append(f"Categoria de intenção do Core: {intent_decision.category}")
        context.append(f"Transcrição/pedido: {message}")
        full_msg = "\n".join(context)

        ssh = get_ssh_connection()
        # Encode the prompt as data before passing it through SSH/shell; quoting a
        # transcript by escaping only quotes still allowed shell metacharacters.
        import base64
        safe_msg_b64 = base64.b64encode(full_msg.encode("utf-8")).decode("ascii")
        agent_model = os.environ.get("JARVIS_AGENT_MODEL", "9router/jarvisflash")
        cmd = (
            "docker exec openclaw sh -lc "
            f"'openclaw agent --agent jarvis --model \"{agent_model}\" --message \"$(printf %s {safe_msg_b64} | base64 -d)\" --json'"
        )
        
        stdin, stdout, stderr = ssh.exec_command(cmd, timeout=120)
        raw_out = stdout.read().decode('utf-8', errors='ignore').strip()
        raw_err = stderr.read().decode('utf-8', errors='ignore').strip()
        exit_code = stdout.channel.recv_exit_status()
        if exit_code != 0:
            print(f"[!] OpenClaw retornou falha (exit={exit_code}); detalhes omitidos da resposta de voz.")
            return OPENCLAW_MODEL_FAILURE_TOKEN

        reply = extract_openclaw_reply(raw_out)
        if reply == OPENCLAW_MODEL_FAILURE_TOKEN:
            print("[!] OpenClaw não retornou uma resposta válida; detalhes omitidos da resposta de voz.")
        return reply
    except Exception as e:
        print(f"[!] Erro ao chamar Jarvis no OpenClaw ({type(e).__name__}); detalhes omitidos da resposta de voz.")
        return OPENCLAW_MODEL_FAILURE_TOKEN

_ssh_client = None
_ssh_lock = threading.Lock()

# Última esfera (ESP32) que originou um comando de voz — usado para exibir a resposta na tela CERTA.
_ESFERA_STATE = {"last_device": os.environ.get("DEFAULT_ESFERA_DEVICE", "jarvis_sphere_esp32s3")}

def _sphere_ws_push(device_id: str, payload: dict, timeout: float = 4.0):
    """Envia JSON ao dispositivo autenticado no WSS da esfera (mesmo socket da voz).
    Retorna (ok, mensagem_de_erro). Substitui a rota HTTP :8095 (morto)."""
    try:
        import asyncio
        from sphere_audio_bridge import push_to_device, get_loop
        loop = get_loop()
        if loop is None or loop.is_closed():
            return False, "Ponte WSS da esfera inativa (8096)."
        dev = str(device_id or _ESFERA_STATE["last_device"])[:80]
        fut = asyncio.run_coroutine_threadsafe(push_to_device(dev, payload), loop)
        if not fut.result(timeout=timeout):
            return False, f"Esfera '{dev}' não está conectada ao WSS."
        return True, ""
    except Exception as e:
        return False, f"Falha no envio WSS: {type(e).__name__}"

def get_ssh_connection():
    global _ssh_client
    with _ssh_lock:
        if _ssh_client is not None:
            try:
                transport = _ssh_client.get_transport()
                if transport and transport.is_active():
                    return _ssh_client
            except Exception:
                pass
            try:
                _ssh_client.close()
            except Exception:
                pass

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(ZIMA_IP, username=ZIMA_USER, password=ZIMA_PASS, timeout=8)
        _ssh_client = client
        return _ssh_client

async def generate_speech(text, output_file):
    clean_text = clean_text_for_speech(text)
    if not clean_text:
        clean_text = "Comando recebido, senhor."

    # 1. Prioridade: ElevenLabs (George - Voz Britânica Estilo J.A.R.V.I.S.)
    for api_key in [ELEVENLABS_API_KEY, ELEVENLABS_FALLBACK_KEY]:
        if not api_key:
            continue
        try:
            url = f"{os.environ.get('ELEVENLABS_API_BASE', 'https://api.elevenlabs.io')}/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
            headers = {
                "xi-api-key": api_key,
                "Content-Type": "application/json",
                "User-Agent": "JarvisHUD/1.0"
            }
            payload = json.dumps({
                "text": clean_text,
                "model_id": "eleven_turbo_v2_5",
                "voice_settings": {
                    "stability": 0.50,
                    "similarity_boost": 0.85,
                    "style": 0.10,
                    "use_speaker_boost": True
                }
            }).encode("utf-8")
            req = urllib.request.Request(url, data=payload, headers=headers)
            with urllib.request.urlopen(req, timeout=14) as resp:
                audio_data = resp.read()
                if len(audio_data) > 1000:
                    with open(output_file, "wb") as f:
                        f.write(audio_data)
                    print(f"[+] Áudio sintetizado via ElevenLabs (Voz JARVIS George): {len(audio_data)} bytes")
                    return True
        except Exception as e:
            print("[!] Aviso ElevenLabs, tentando chave secundária ou fallback:", e)

    # 2. Fallback de alta fidelidade: Edge-TTS
    try:
        communicate = edge_tts.Communicate(clean_text, "pt-BR-AntonioNeural", rate="+15%")
        await communicate.save(output_file)
        print(f"[+] Áudio sintetizado via Edge-TTS Fallback")
        return True
    except Exception as e:
        print("[!] Erro Edge-TTS:", e)
        return False

# ==========================================
# CACHE E INTEGRAÇÃO DE RADAR AÉREO 3D (OPENSKY)
# ==========================================
flights_cache = {
    "sa": {"ts": 0, "data": []},
    "all": {"ts": 0, "data": []}
}
flights_lock = threading.Lock()

def get_live_flights(region="sa"):
    now = time.time()
    with flights_lock:
        entry = flights_cache.get(region, flights_cache["sa"])
        if now - entry["ts"] < 15 and entry["data"]:
            return entry["data"]

    url = os.environ.get("OPENSKY_API_URL", "https://opensky-network.org/api/states/all")
    if region == "sa":
        # Bounding box América do Sul / Brasil
        url += "?lamin=-35&lomin=-75&lamax=5&lomax=-34"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "JarvisRadar3D/1.0"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
            states = raw.get("states", [])
            flights = []
            for s in states:
                # s[5]=lon, s[6]=lat, s[8]=on_ground
                if s[5] is not None and s[6] is not None and not s[8]:
                    flights.append({
                        "icao": s[0],
                        "callsign": (s[1] or "UNKN").strip(),
                        "country": s[2] or "Global",
                        "lng": round(s[5], 4),
                        "lat": round(s[6], 4),
                        "alt": round((s[7] or s[13] or 1000) * 3.28084), # altitude em pés (ft)
                        "alt_m": round(s[7] or s[13] or 300),            # altitude em metros
                        "speed": round((s[9] or 0) * 3.6),               # km/h
                        "heading": round(s[10] or 0),                    # graus
                        "squawk": s[14] or ""
                    })
            with flights_lock:
                flights_cache[region] = {"ts": now, "data": flights}
            return flights
    except Exception as e:
        print(f"[!] Erro ao buscar voos OpenSky ({region}): {e}")
        with flights_lock:
            return flights_cache.get(region, {}).get("data", [])

TTS_CACHE_DIR = os.path.join(DIRECTORY, "auth", "tts_cache")
os.makedirs(TTS_CACHE_DIR, exist_ok=True)

def get_or_generate_tts(text):
    clean = clean_text_for_speech(text)
    if not clean:
        clean = "Comando processado."
    text_hash = hashlib.md5(clean.encode("utf-8")).hexdigest()
    cached_file = os.path.join(TTS_CACHE_DIR, f"{text_hash}.mp3")
    if os.path.exists(cached_file) and os.path.getsize(cached_file) > 1000:
        return cached_file

    try:
        asyncio.run(generate_speech(clean, cached_file))
        if os.path.exists(cached_file) and os.path.getsize(cached_file) > 1000:
            return cached_file
    except Exception as e:
        print(f"[!] Erro gerando TTS: {e}")
    return None

def _decode_mp3_to_pcm16k(mp3_path):
    """Decodifica MP3 para PCM 16 kHz mono 16-bit (s16le) usando PyAV (para nós de áudio)."""
    try:
        import av
        out = bytearray()
        with av.open(mp3_path) as container:
            resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
            for frame in container.decode(audio=0):
                for rframe in resampler.resample(frame):
                    out.extend(bytes(rframe.planes[0]))
            for rframe in resampler.resample(None):
                out.extend(bytes(rframe.planes[0]))
        return bytes(out)
    except Exception as e:
        print(f"[!] Falha decodificando MP3->PCM: {e}")
        return b""

def get_or_generate_tts_pcm(text):
    """Gera/retorna o áudio TTS como PCM 16 kHz mono s16le (para a esfera ESP32 e nós de áudio)."""
    clean = clean_text_for_speech(text) or "Comando processado."
    h = hashlib.md5(("pcm:" + clean).encode("utf-8")).hexdigest()
    pcm_file = os.path.join(TTS_CACHE_DIR, f"{h}.pcm")
    if os.path.exists(pcm_file) and os.path.getsize(pcm_file) > 1000:
        return pcm_file
    # 1) ElevenLabs PCM direto (pcm_16000 = raw s16le mono 16k, sem decodificar)
    for api_key in [ELEVENLABS_API_KEY, ELEVENLABS_FALLBACK_KEY]:
        if not api_key:
            continue
        try:
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}?output_format=pcm_16000"
            headers = {"xi-api-key": api_key, "Content-Type": "application/json", "User-Agent": "JarvisHUD/1.0"}
            payload = json.dumps({
                "text": clean,
                "model_id": "eleven_turbo_v2_5",
                "voice_settings": {"stability": 0.50, "similarity_boost": 0.85, "style": 0.10, "use_speaker_boost": True}
            }).encode("utf-8")
            req = urllib.request.Request(url, data=payload, headers=headers)
            with urllib.request.urlopen(req, timeout=14) as resp:
                pcm = resp.read()
            if len(pcm) > 1000:
                with open(pcm_file, "wb") as f:
                    f.write(pcm)
                print(f"[+] TTS PCM via ElevenLabs (pcm_16000): {len(pcm)} bytes")
                return pcm_file
        except Exception as e:
            print(f"[!] ElevenLabs PCM falhou: {e}")
    # 2) Fallback: edge-tts mp3 -> decodifica para PCM 16k
    mp3 = get_or_generate_tts(clean)
    if mp3:
        pcm = _decode_mp3_to_pcm16k(mp3)
        if len(pcm) > 1000:
            with open(pcm_file, "wb") as f:
                f.write(pcm)
            print(f"[+] TTS PCM via Edge-TTS decodificado: {len(pcm)} bytes")
            return pcm_file
    return None

def _transcribe_via_container(audio_bytes, content_type="audio/wav", language="pt"):
    """Transcreve via container Whisper dedicado (OpenAI-compatible /v1/audio/transcriptions)."""
    base = os.environ.get("WHISPER_URL", "http://172.17.0.1:8000").rstrip("/")
    model = os.environ.get("WHISPER_MODEL", "Systran/faster-whisper-base")
    boundary = "----jarvis" + secrets.token_hex(8)
    ct = content_type or "audio/wav"
    ext = "wav" if "wav" in ct else ("webm" if "webm" in ct else "mp3" if "mpeg" in ct or "mp3" in ct else "bin")
    parts = []
    def _field(name, value):
        parts.append((f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n").encode("utf-8"))
    _field("model", model)
    _field("language", language)
    _field("prompt", "Jarvis, comando de voz em português brasileiro para automação e consulta.")
    parts.append((f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"audio.{ext}\"\r\nContent-Type: {ct}\r\n\r\n").encode("utf-8"))
    parts.append(audio_bytes)
    parts.append((f"\r\n--{boundary}--\r\n").encode("utf-8"))
    body = b"".join(parts)
    req = urllib.request.Request(base + "/v1/audio/transcriptions", data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    timeout = max(5, min(90, int(os.environ.get("WHISPER_TIMEOUT_SECONDS", "25"))))
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        j = json.loads(resp.read().decode("utf-8"))
    return (j.get("text") or "").strip()

_STT_ROUTER_STATE = {"fails": 0, "open_until": 0.0}

def _transcribe_via_router(audio_bytes, content_type="audio/wav", language="pt"):
    """Transcreve via 9router (Groq whisper-large-v3-turbo) — nuvem, ~0.5s.
    O Core chama o provedor; dispositivos nunca falam direto. Falha -> string vazia.
    Circuit breaker: 3 falhas seguidas = rota em pausa por 60s (evita pagar o timeout
    do turno inteiro quando a nuvem está fora)."""
    if time.time() < _STT_ROUTER_STATE["open_until"]:
        return ""
    base = os.environ.get("SPHERE_STT_URL", "http://127.0.0.1:20128/v1").strip().rstrip("/")
    key = os.environ.get("SPHERE_STT_KEY", "").strip()
    if not key:
        return ""
    model = os.environ.get("SPHERE_STT_MODEL", "groq/whisper-large-v3-turbo").strip()
    boundary = "----jarvis" + secrets.token_hex(8)
    ct = content_type or "audio/wav"
    ext = "wav" if "wav" in ct else ("webm" if "webm" in ct else "mp3" if "mpeg" in ct or "mp3" in ct else "bin")
    parts = []
    def _rfield(name, value):
        parts.append((f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n").encode("utf-8"))
    _rfield("model", model)
    _rfield("language", language)
    _rfield("response_format", "json")
    parts.append((f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"audio.{ext}\"\r\nContent-Type: {ct}\r\n\r\n").encode("utf-8"))
    parts.append(audio_bytes)
    parts.append((f"\r\n--{boundary}--\r\n").encode("utf-8"))
    body = b"".join(parts)
    req = urllib.request.Request(base + "/audio/transcriptions", data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
                                          "Authorization": f"Bearer {key}"})
    timeout = float(os.environ.get("SPHERE_STT_TIMEOUT", "3.5"))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            j = json.loads(resp.read().decode("utf-8"))
    except Exception:
        n = _STT_ROUTER_STATE["fails"] + 1
        _STT_ROUTER_STATE["fails"] = n
        if n >= 3:
            _STT_ROUTER_STATE["open_until"] = time.time() + 60
        return ""
    _STT_ROUTER_STATE.update(fails=0, open_until=0.0)
    return (j.get("text") or "").strip()

def generate_morning_digest():
    try:
        hc.record_local_action("morning_digest")
    except Exception:
        pass
    weather = get_catanduva_weather()
    finance = get_pluggy_finance()
    try:
        news_items = hc.search_realtime_news("Catanduva SP", max_results=2)
    except Exception:
        news_items = []
    zima = get_zima_metrics()
    hw = hc.get_hardware_telemetry()
    savings = hw.get("savings", {})

    mei_acc = next((a for a in finance.get("accounts", []) if "MEI" in (a.get("name") or "")), None)
    mei_balance = f"R$ {mei_acc['balance']:.2f}".replace('.', ',') if (mei_acc and 'balance' in mei_acc) else "Não sincronizado"
    
    inter_acc = next((a for a in finance.get("accounts", []) if "INTER" in (a.get("name") or "")), None)
    inter_balance = f"R$ {inter_acc['balance']:.2f}".replace('.', ',') if (inter_acc and 'balance' in inter_acc) else "Não sincronizado"

    top_news_title = news_items[0]["title"] if news_items else "Sem novidades críticas no radar regional"
    top_news_source = news_items[0].get("source", "Catanduva") if news_items else "Radar"

    spoken_script = (
        f"Bom dia, Senhor Werik. Aqui está o seu briefing matinal executivo. "
        f"Em Catanduva, os termômetros registram {round(weather.get('temperature', 0))} graus, com máxima de {round(weather.get('temp_max', 0))} graus e {weather.get('condition', 'estável').lower()}. "
        f"No panorama financeiro do Banco Inter, seu saldo disponível é de {inter_balance} e a fatura do cartão MEI está em {mei_balance}. "
        f"No radar regional: {top_news_title}. "
        f"Toda a sua infraestrutura com {zima.get('total_containers', 0)} containers no ZimaOS e a GPU GeForce GTX 1660 Ti operam com inteligência local offline. "
        f"O relatório completo foi projetado no seu painel lateral tático. Ao seu dispor."
    )

    tactical_markdown = f"""## 🌅 BRIEFING MATINAL EXECUTIVO • {time.strftime('%d/%m/%Y')}

---
### ☀️ CLIMA & TEMPERATURA EM CATANDUVA
- **Temperatura Atual:** {weather.get('temperature', '--')}°C ({weather.get('condition', '--')})
- **Previsão:** Mínima {weather.get('temp_min', '--')}°C | Média {weather.get('temp_avg', '--')}°C | Máxima {weather.get('temp_max', '--')}°C
- **Umidade & Vento:** {weather.get('humidity', '--')}% | {weather.get('wind_speed', '--')} km/h

---
### 💳 PANORAMA FINANCEIRO (BANCO INTER / PLUGGY)
- **Conta Corrente Inter:** Saldo Disponível {inter_balance}
- **Cartão Mastercard MEI:** Fatura Atual {mei_balance}
- **Status da Conexão:** Sincronizado via Open Finance API

---
### 📰 RADAR REGIONAL & NOTÍCIAS
- **Destaque Principal:** **{top_news_title}** ({top_news_source})
"""
    if len(news_items) > 1:
        for other in news_items[1:]:
            tactical_markdown += f"- **Outra Manchete:** {other['title']} ({other.get('source', 'Regional')})\n"

    tactical_markdown += f"""
---
### 🖥️ SERVIDOR ZIMAOS CLOUD ({ZIMA_IP})
- **CPU & Temperatura:** {zima.get('cpu_temp', '--')}°C • {zima.get('cpu_pct', '--')}% carga
- **Memória RAM:** {zima.get('ram_used_gb', '--')} GB / {zima.get('ram_total_gb', '--')} GB ({zima.get('ram_pct', '--')}%)
- **Armazenamento /DATA:** {zima.get('disk', {}).get('free_gb', '--')} GB livres de {zima.get('disk', {}).get('total_gb', '--')} GB ({zima.get('disk', {}).get('pct', '--')}% ocupado)
- **Containers Ativos:** {zima.get('total_containers', 0)} containers em execução
- **Uptime do Servidor:** {zima.get('uptime', 'Indisponível')}
- **SSH & OpenClaw Bridge:** Operacional e pronto para requisições

---
### TELEMETRIA DE ECONOMIA LOCAL (OPENJARVIS STYLE)
- **GPU Local:** {hw['gpu']['name']} ({hw['gpu']['temperature']} C - {hw['gpu']['utilization']}% carga)
- **Transcrições Whisper Locais:** {savings.get('whisper_runs', 0)} sessões 100% offline (Custo: R$ 0,00)
- **Ações & Consultas Locais:** {savings.get('local_actions', 0)} execuções
- **Tokens de Nuvem Economizados:** {savings.get('tokens_saved_fmt', '0k')} tokens
- **Economia Estimada Hoje:** {savings.get('money_saved_fmt', 'R$ 0,00')} (vs APIs pagas de nuvem)
- **Eficiência por Watt:** {savings.get('intelligence_per_watt', '30W Local')}
"""

    return {
        "weather": weather,
        "finance": {
            "inter_balance": inter_balance,
            "mei_balance": mei_balance
        },
        "news": news_items,
        "zima": zima,
        "hardware": hw,
        "savings": savings,
        "spoken_script": spoken_script,
        "tactical_markdown": tactical_markdown.strip()
    }

class JarvisRequestHandler(http.server.SimpleHTTPRequestHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    # ------------------------------------------------------------------
    # RBAC - Identidade e permissões da requisição
    # ------------------------------------------------------------------
    def _client_is_local(self) -> bool:
        try:
            ip = self.client_address[0]
            return ip in ("127.0.0.1", "::1", "localhost")
        except Exception:
            return False

    def _get_request_auth(self) -> dict:
        """Resolve usuário e permissões: nó local > sessão assinada > visitante."""
        if TRUST_LOCAL and self._client_is_local():
            return dict(OWNER_AUTH)
        token = self.headers.get("X-Jarvis-Session", "")
        if not token:
            authz = self.headers.get("Authorization", "")
            if authz.lower().startswith("bearer "):
                token = authz[7:].strip()
        payload = _read_session_token(token)
        if payload:
            role = payload.get("role", "Convidado")
            return {
                "user": payload.get("user", "Operador"),
                "role": role,
                "permissions": biometrics.resolve_permissions(role, payload.get("permissions")),
                "source": "session"
            }
        return dict(GUEST_AUTH)

    @staticmethod
    def _perm_allowed(auth: dict, permission: str) -> bool:
        perms = auth.get("permissions", {})
        return bool(perms.get(permission) or perms.get("full_access"))

    def _is_master_key_request(self) -> bool:
        key = self.headers.get("X-Master-Key", "")
        return bool(key) and biometrics.verify_master_key(key)

    def _send_forbidden(self, auth: dict, permission: str):
        user = auth.get("user", "Visitante")
        msg = (
            f"Acesso não autorizado, {user}: a operação exige a permissão '{permission}'. "
            f"Solicite liberação ao Proprietário."
        )
        self.send_response(403)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps({
            "status": "forbidden",
            "error": msg,
            "user": user,
            "required_permission": permission
        }, ensure_ascii=False).encode("utf-8"))

    def handle(self):
        try:
            super().handle()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ["/", "/index.html"]:
            try:
                index_path = os.path.join(DIRECTORY, "web", "index.html")
                with open(index_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.send_header("Pragma", "no-cache")
                self.send_header("Expires", "0")
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(content)
                return
            except Exception:
                pass

        if parsed.path in ["/canvas", "/canvas/", "/desktop/canvas"]:
            try:
                canvas_path = os.path.join(DIRECTORY, "desktop", "canvas_ui.html")
                with open(canvas_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(content)
                return
            except Exception as e:
                print(f"[!] Erro ao servir /canvas: {e}")

        if parsed.path in ["/memory", "/memory/", "/brain", "/brain/"]:
            try:
                dash_path = os.path.join(DIRECTORY, "memory", "brain_dashboard.html")
                with open(dash_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(content)
                return
            except Exception as e:
                print(f"[!] Erro ao servir /memory: {e}")

        if parsed.path.startswith("/api/memory"):
            data = None
            last_err = None
            for base_url in [os.environ.get("MEMORY_PRIMARY_URL", "${ZIMA_ROUTER_URL:-http://127.0.0.1:8095}"), "http://127.0.0.1:8090"]:
                try:
                    mem_url = f"{base_url}{self.path}"
                    req = urllib.request.Request(mem_url, headers={"User-Agent": "JarvisProxy/1.0"})
                    with urllib.request.urlopen(req, timeout=3) as resp:
                        data = resp.read()
                        break
                except Exception as em:
                    last_err = em
            if data is not None:
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)
                return
            else:
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"error": f"Erro proxy memória: {last_err}"}).encode('utf-8'))
                return

        # Serve Neural Models & Weights
        if parsed.path.startswith("/models/"):
            try:
                rel_path = parsed.path.lstrip("/").replace("/", os.sep)
                fpath = os.path.join(DIRECTORY, rel_path)
                if os.path.exists(fpath) and os.path.isfile(fpath):
                    with open(fpath, "rb") as f:
                        content = f.read()
                    self.send_response(200)
                    if fpath.endswith(".js"):
                        self.send_header("Content-Type", "application/javascript")
                    elif fpath.endswith(".json"):
                        self.send_header("Content-Type", "application/json")
                    else:
                        self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Cache-Control", "public, max-age=604800")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("Content-Length", str(len(content)))
                    self.end_headers()
                    self.wfile.write(content)
                    return
            except Exception as e:
                print(f"[!] Erro ao servir {parsed.path}: {e}")

        # PWA Assets
        if parsed.path == "/manifest.json":
            try:
                mf_path = os.path.join(DIRECTORY, "web", "manifest.json")
                with open(mf_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/manifest+json; charset=utf-8")
                self.send_header("Cache-Control", "public, max-age=3600")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(content)
                return
            except Exception as e:
                print(f"[!] Erro ao servir manifest.json: {e}")

        if parsed.path in ["/sw.js", "/service-worker.js"]:
            try:
                sw_path = os.path.join(DIRECTORY, "web", "sw.js")
                with open(sw_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript; charset=utf-8")
                self.send_header("Service-Worker-Allowed", "/")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(content)
                return
            except Exception as e:
                print(f"[!] Erro ao servir sw.js: {e}")

        if parsed.path in ["/jarvis_ui_engine.js", "/cobe.esm.js"]:
            try:
                fpath = os.path.join(DIRECTORY, "web", parsed.path.lstrip("/"))
                with open(fpath, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript; charset=utf-8")
                self.send_header("Cache-Control", "public, max-age=86400")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(content)
                return
            except Exception as e:
                print(f"[!] Erro ao servir {parsed.path}: {e}")

        if parsed.path in ["/icon-192.png", "/icon-512.png", "/apple-touch-icon.png"]:
            try:
                fname = parsed.path.lstrip("/")
                fpath = os.path.join(DIRECTORY, "web", fname)
                if os.path.exists(fpath):
                    with open(fpath, "rb") as f:
                        content = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Cache-Control", "public, max-age=86400")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(content)
                    return
            except Exception as e:
                print(f"[!] Erro ao servir {parsed.path}: {e}")

        if parsed.path.endswith(".mp3"):
            try:
                fname = parsed.path.lstrip("/").replace("/", os.sep)
                fpath = os.path.join(DIRECTORY, "web", fname)
                if os.path.exists(fpath):
                    with open(fpath, "rb") as f:
                        content = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "audio/mpeg")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(content)
                    return
            except Exception as e:
                print(f"[!] Erro ao servir {parsed.path}: {e}")

        if parsed.path == "/api/flights":
            params = urllib.parse.parse_qs(parsed.query)
            region = params.get("region", ["sa"])[0]
            flights = get_live_flights(region)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"total": len(flights), "flights": flights}).encode("utf-8"))
            return

        # JEV & Laya (TypeSafe AI) Telemetria de Sistema 1
        if parsed.path == "/api/jev/telemetry":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(jev_engine.get_telemetry(), ensure_ascii=False).encode("utf-8"))
            return

        if parsed.path == "/api/tts":
            params = urllib.parse.parse_qs(parsed.query)
            text = params.get("text", [""])[0]
            audio_path = get_or_generate_tts(text)
            if audio_path and os.path.exists(audio_path):
                with open(audio_path, "rb") as f:
                    audio_data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "audio/mpeg")
                self.send_header("Content-Length", str(len(audio_data)))
                self.send_header("Cache-Control", "public, max-age=86400")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(audio_data)
                return
            else:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Falha na sintese"}).encode())
                return

        if parsed.path == "/api/status":
            auth = self._get_request_auth()
            metrics = get_zima_metrics()
            finance = get_pluggy_finance() if self._perm_allowed(auth, "finance_view") else {
                "accounts": [],
                "updated_at": "Acesso restrito (requer permissão finance_view)"
            }
            weather = get_catanduva_weather()
            response = {"system": metrics, "finance": finance, "weather": weather}
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode("utf-8"))
            return

        if parsed.path == "/api/auth/face/status":
            profs = biometrics.get_registered_profiles()
            valid_profs = [p for p in profs if p.get("descriptor") and len(p["descriptor"]) >= 64]
            reg = len(valid_profs) > 0
            has_desc = reg
            primary_user = valid_profs[0]["name"] if valid_profs else None
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "registered": reg,
                "has_descriptor": has_desc,
                "count": len(valid_profs),
                "profiles": [{"name": p.get("name"), "role": p.get("role", "Operador")} for p in valid_profs],
                "user": primary_user
            }).encode("utf-8"))
            return

        if parsed.path == "/api/auth/face/descriptor":
            profs = biometrics.get_registered_profiles()
            valid_profs = [p for p in profs if p.get("descriptor") and len(p["descriptor"]) >= 64]
            desc = valid_profs[0]["descriptor"] if valid_profs else None
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"descriptor": desc}).encode("utf-8"))
            return

        if parsed.path == "/api/auth/face/descriptors":
            profs = biometrics.get_registered_profiles()
            valid_profs = [
                {"name": p.get("name", "Operador"), "role": p.get("role", "Operador"), "descriptor": p.get("descriptor")}
                for p in profs if p.get("descriptor") and len(p["descriptor"]) >= 64
            ]
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"profiles": valid_profs}).encode("utf-8"))
            return

        if parsed.path == "/api/hardware":
            hw = hc.get_hardware_telemetry()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(hw).encode("utf-8"))
            return

        if parsed.path == "/api/hud/diag":
            with sse_lock:
                cnt = len(sse_subscribers)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"sse_subscribers": cnt}).encode())
            return

        # Lista de dispositivos Wake-on-LAN cadastrados (requer wake_on_lan)
        if parsed.path == "/api/wol":
            auth = self._get_request_auth()
            if not self._perm_allowed(auth, "wake_on_lan"):
                self._send_forbidden(auth, "wake_on_lan")
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"devices": _load_wol_devices()}, ensure_ascii=False).encode("utf-8"))
            return

        # Visão geral de operadores e permissões (requer full_access ou X-Master-Key)
        if parsed.path == "/api/operators":
            auth = self._get_request_auth()
            if not (self._perm_allowed(auth, "full_access") or self._is_master_key_request()):
                self._send_forbidden(auth, "full_access")
                return
            profs = biometrics.get_registered_profiles()
            overview = [
                {
                    "id": p.get("id"),
                    "name": p.get("name"),
                    "role": p.get("role", "Operador"),
                    "permissions": p.get("permissions", biometrics.GUEST_PERMISSIONS),
                    "registered_at": p.get("registered_at"),
                    "last_login": p.get("last_login"),
                    "login_count": p.get("login_count", 0)
                }
                for p in profs
            ]
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"operators": overview}, ensure_ascii=False).encode("utf-8"))
            return

        # Ponte de comandos remotos: consulta de resultado e status (GET)
        if parsed.path == "/api/remote/result":
            qs = urllib.parse.parse_qs(parsed.query)
            cmd_id = (qs.get("id", [""])[0] or "").strip()
            if not _bridge_secret_ok(self.headers.get("X-Bridge-Secret", "")):
                self.send_response(403)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": "Segredo da ponte inválido."}).encode("utf-8"))
                return
            with _remote_lock:
                entry = _remote_state["results"].get(cmd_id)
            payload = {"ok": True, "id": cmd_id, "pending": entry is None}
            if entry is not None:
                payload.update(entry)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            return

        if parsed.path == "/api/remote/status":
            if not _bridge_secret_ok(self.headers.get("X-Bridge-Secret", "")):
                self.send_response(403)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": "Segredo da ponte inválido."}).encode("utf-8"))
                return
            with _remote_lock:
                last_poll = _remote_state.get("last_poll", 0.0)
                pending = len(_remote_state["queue"])
                node_alive = (time.time() - last_poll) < 20.0 if last_poll else False
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "ok": True,
                "node_connected": node_alive,
                "seconds_since_poll": round(time.time() - last_poll, 1) if last_poll else None,
                "pending_commands": pending
            }, ensure_ascii=False).encode("utf-8"))
            return

        # ==================================================================
        # INFRA: saúde de toda a cadeia (probes TCP leves + ponte + nós)
        # ==================================================================
        if parsed.path == "/api/infra":
            import socket as _socket

            def _probe(host, port, timeout=1.2):
                try:
                    with _socket.create_connection((host, port), timeout=timeout):
                        return True
                except Exception:
                    return False

            gw = "172.17.0.1"  # gateway docker -> portas publicadas no host
            with _remote_lock:
                last_poll = _remote_state.get("last_poll", 0.0)
                pending = len(_remote_state["queue"])
                node_alive = (time.time() - last_poll) < 20.0 if last_poll else False
                queued = [{"id": q.get("id"), "action": q.get("action")} for q in _remote_state["queue"]]
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "ok": True,
                "ts": time.time(),
                "services": {
                    "openclaw_gateway": _probe(gw, 24192),
                    "mcp_hud": _probe(gw, 8087),
                    "sphere_ws": _probe(gw, 8096),
                },
                "bridge": {
                    "node_connected": node_alive,
                    "seconds_since_poll": round(time.time() - last_poll, 1) if last_poll else None,
                    "pending": pending,
                    "queued": queued,
                },
                "recent": list(_infra_recent)[-10:],
                "nodes": _nodes_registry_load(),
            }, ensure_ascii=False).encode("utf-8"))
            return

        # ==============================================================
        # SPOTIFY OAuth (no próprio Zima): /spotify/login redireciona, /spotify/callback salva o token
        # ==============================================================
        if parsed.path == "/spotify/login":
            if not (SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET):
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"<h2>Configure SPOTIFY_CLIENT_ID e SPOTIFY_CLIENT_SECRET no docker-compose e reinicie.</h2>")
                return
            auth_url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode({
                "client_id": SPOTIFY_CLIENT_ID,
                "response_type": "code",
                "redirect_uri": SPOTIFY_REDIRECT_URI,
                "scope": SPOTIFY_SCOPES,
                "show_dialog": "false",
            })
            self.send_response(302)
            self.send_header("Location", auth_url)
            self.end_headers()
            return

        if parsed.path == "/spotify/callback":
            qs = urllib.parse.parse_qs(parsed.query)
            code = (qs.get("code", [""])[0] or "").strip()
            err = (qs.get("error", [""])[0] or "").strip()
            ok = False
            detail = ""
            if err:
                detail = f"Autorização negada: {err}"
            elif not code:
                detail = "Código ausente."
            else:
                try:
                    basic = base64.b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()).decode()
                    data = urllib.parse.urlencode({
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": SPOTIFY_REDIRECT_URI,
                    }).encode()
                    req = urllib.request.Request(
                        os.environ.get("SPOTIFY_TOKEN_URL", "https://accounts.spotify.com/api/token"), data=data,
                        headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"})
                    with urllib.request.urlopen(req, timeout=20) as r:
                        tok = json.loads(r.read().decode("utf-8"))
                    rt = tok.get("refresh_token")
                    if rt:
                        os.makedirs(os.path.dirname(SPOTIFY_TOKEN_FILE), exist_ok=True)
                        with open(SPOTIFY_TOKEN_FILE, "w", encoding="utf-8") as f:
                            json.dump({"refresh_token": rt, "saved_at": time.strftime('%Y-%m-%d %H:%M:%S')}, f, ensure_ascii=False)
                        _SPOTIFY_CACHE["token"] = tok.get("access_token", "")
                        _SPOTIFY_CACHE["exp"] = time.time() + int(tok.get("expires_in", 3600))
                        ok = True
                        detail = "Token do Spotify salvo no Zima. Pode fechar esta aba."
                    else:
                        detail = "Não veio refresh_token: " + json.dumps(tok)[:200]
                except Exception as e:
                    detail = f"Falha ao trocar o código: {e}"
            color = "#10b981" if ok else "#f43f5e"
            with_lock = f"<h2 style='color:{color}'>J.A.R.V.I.S. • Spotify</h2><p>{detail}</p>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(with_lock.encode("utf-8"))
            return

        # ==============================================================
        # SPOTIFY (controle de reprodução) — status atual
        # ==============================================================
        if parsed.path == "/api/spotify/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "ok": True,
                "configured": spotify_configured(),
                "player": spotify_now_playing(),
            }, ensure_ascii=False).encode("utf-8"))
            return

        # ==============================================================
        # AUTENTICAÇÃO FACIAL NATIVA (app Windows) — serve modelos face-api + página de captura
        # ==============================================================
        if parsed.path.startswith("/models/"):
            rel = parsed.path[len("/models/"):]
            base = os.path.normpath(os.path.join(DIRECTORY, "models"))
            target = os.path.normpath(os.path.join(base, rel))
            if target.startswith(base) and os.path.isfile(target):
                if target.endswith(".js"):
                    ctype = "application/javascript"
                elif target.endswith(".json"):
                    ctype = "application/json"
                elif target.endswith(".wasm"):
                    ctype = "application/wasm"
                else:
                    ctype = "application/octet-stream"
                with open(target, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_response(404)
                self.end_headers()
            return

        if parsed.path in ["/face_web", "/face_web.html"]:
            page = os.path.join(DIRECTORY, "desktop", "face_web.html")
            if os.path.exists(page):
                with open(page, "r", encoding="utf-8") as f:
                    html = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(html.encode("utf-8"))
            else:
                self.send_response(404)
                self.end_headers()
            return

        # ==============================================================
        # PÁGINAS: /painel = painel unificado · /node = máquina local · /nodes = nós · /infra = saúde
        # ==============================================================
        if parsed.path in ("/painel", "/painel.html", "/controle", "/controle.html",
                           "/node", "/node.html", "/nodes", "/nodes.html", "/infra", "/infra.html"):
            if parsed.path.startswith("/painel") or parsed.path.startswith("/controle"):
                page_name = "controle.html"
            elif parsed.path.startswith("/node"):
                page_name = "node.html"
            elif parsed.path.startswith("/infra"):
                page_name = "infra.html"
            else:
                page_name = "nodes.html"
            node_page = os.path.join(DIRECTORY, "web", page_name)
            if os.path.exists(node_page):
                with open(node_page, "r", encoding="utf-8") as f:
                    html = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(html.encode("utf-8"))
            else:
                self.send_response(404)
                self.end_headers()
            return

        # ==============================================================
        # NODES REGISTRY (página de controle dos nós + rede da esfera)
        # ==============================================================
        if parsed.path == "/api/nodes":
            registry = _nodes_registry_load()
            try:
                sphere_info = {
                    "ws_host": os.environ.get("SPHERE_WS_HOST", "0.0.0.0"),
                    "ws_port": int(os.environ.get("SPHERE_WS_PORT", "8096")),
                    "wakeword_threshold": float(os.environ.get("SPHERE_WAKEWORD_THRESHOLD", "0.10")),
                    "followup_seconds": int(os.environ.get("SPHERE_FOLLOWUP_SECONDS", "8")),
                }
            except Exception:
                sphere_info = {}
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "nodes": registry, "sphere": sphere_info}, ensure_ascii=False).encode("utf-8"))
            return

        if parsed.path == "/api/esfera/cover":
            qs = urllib.parse.parse_qs(parsed.query)
            url = (qs.get("url", [""])[0] or "").strip()
            host = urllib.parse.urlparse(url).hostname or ""
            if not (url.startswith("https://") and (host == "i.scdn.co" or host.endswith(".scdn.co"))):
                self.send_response(400)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": "origem não permitida."}).encode("utf-8"))
                return
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "JarvisHUD/1.0"})
                with urllib.request.urlopen(req, timeout=12) as resp:
                    ctype = resp.headers.get("Content-Type", "")
                    if "jpeg" not in ctype and "jpg" not in ctype:
                        raise ValueError("não é JPEG")
                    data = resp.read(300 * 1024 + 1)
                    if len(data) > 300 * 1024:
                        raise ValueError("capa muito grande")
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Cache-Control", "public, max-age=3600")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            except Exception as e:
                self.send_response(502)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": f"capa indisponível: {type(e).__name__}"}).encode("utf-8"))
            return

        if parsed.path == "/api/lucia":
            qs = urllib.parse.parse_qs(parsed.query)
            target = (qs.get("path", [""])[0] or "").strip()
            params = []
            for k, vals in qs.items():
                if k == "path":
                    continue
                for vv in vals:
                    params.append((k, vv))
            res = _lucia_api_get(target, urllib.parse.urlencode(params))
            self.send_response(200 if res.get("ok") else 502)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(res, ensure_ascii=False).encode("utf-8"))
            return
        if parsed.path == "/canvas_panel":
            page = os.path.join(DIRECTORY, "desktop", "canvas_panel.html")
            if os.path.exists(page):
                with open(page, "r", encoding="utf-8") as f:
                    html = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(html.encode("utf-8"))
            else:
                self.send_response(404)
                self.end_headers()
            return

        # Payload de um painel push (canvas_panel.html consome via ?pid)
        if parsed.path == "/api/canvas/payload":
            qs = urllib.parse.parse_qs(parsed.query)
            pid = (qs.get("pid", [""])[0] or "").strip()
            path = _canvas_panel_file(pid)
            if pid and os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))
                self.wfile.flush()
                # one-shot: consome e apaga (evita acúmulo)
                try:
                    os.remove(path)
                except Exception:
                    pass
            else:
                self.send_response(404)
                self.end_headers()
            return

        if parsed.path == "/api/node/status":
            import platform as _plat
            perms = _node_permissions_load()
            autostart, _ = _node_autostart_query()
            cfg = {}
            try:
                with open(os.path.join(DIRECTORY, "config", "jarvis_desktop_config.json"), "r", encoding="utf-8") as f:
                    cfg = json.load(f)
            except Exception:
                pass
            with _remote_lock:
                queue_len = len(_remote_state["queue"])
            # O poller consulta o NÚCLEO, não esta cópia — status real vem do Zima
            bridge_live = False
            bridge_age = None
            try:
                bridge_secret = os.environ.get("BRIDGE_SECRET", os.environ.get("OPENCLAW_GATEWAY_TOKEN"))
                rq = urllib.request.Request(
                    f"{os.environ.get('ZIMA_CORE_URL', 'https://jarvis.werikspace.xyz')}/api/remote/status",
                    headers={"X-Bridge-Secret": bridge_secret}
                )
                with urllib.request.urlopen(rq, timeout=6) as _resp:
                    core_status = json.loads(_resp.read().decode("utf-8"))
                bridge_live = bool(core_status.get("node_connected"))
                bridge_age = core_status.get("seconds_since_poll")
            except Exception:
                pass
            whisper_importable = False
            try:
                import faster_whisper  # noqa
                whisper_importable = True
            except Exception:
                pass
            log_path = _node_bridge_log_path()
            last_commands = []
            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    lines = [l.strip() for l in f.readlines()[-40:]]
                last_commands = [l for l in lines if "Comando recebido" in l][-12:]
            except Exception:
                pass
            status = {
                "ok": True,
                "hostname": socket.gethostname(),
                "node_id": (cfg.get("node") or {}).get("node_id", f"jarvis-pc-{socket.gethostname().lower()}"),
                "platform": _plat.platform(),
                "port": PORT,
                "node_type": os.environ.get("JARVIS_NODE_TYPE", "node"),
                "whisper": {
                    "importable": whisper_importable,
                    "runtime_local": whisper_model is not None,
                    "fallback": "Núcleo ZimaOS (HTTPS)" if whisper_model is None else "Local"
                },
                "mic": _node_mic_status(),
                "bridge": {
                    "url": os.environ.get("ZIMA_CORE_URL", "https://jarvis.werikspace.xyz"),
                    "connected": bridge_live,
                    "seconds_since_poll": bridge_age,
                    "pending": queue_len,
                    "node_id": (cfg.get("node") or {}).get("node_id", "")
                },
                "permissions": perms,
                "autostart": autostart,
                "recent_commands": last_commands
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(status, ensure_ascii=False).encode("utf-8"))
            return

        if parsed.path == "/api/node/log":
            log_path = _node_bridge_log_path()
            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    tail = f.readlines()[-80:]
            except Exception:
                tail = []
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"log": "".join(tail)[:6000]}, ensure_ascii=False).encode("utf-8"))
            return

        if parsed.path == "/api/node/settings":
            settings_file_path = os.path.join(_perm_base, "config", "island_settings.json")
            st = {"wake_word_enabled": True, "ask_before_show": True, "core_url": "https://jarvis.werikspace.xyz"}
            try:
                if os.path.exists(settings_file_path):
                    with open(settings_file_path, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                    if isinstance(loaded, dict):
                        st = loaded
            except Exception:
                pass
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "settings": st}, ensure_ascii=False).encode("utf-8"))
            return

        # Chave pública VAPID para inscrição de Push no PWA (iPhone 16.4+ / Android)
        if parsed.path == "/api/push/public-key":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "publicKey": VAPID_KEYS.get("publicKey", ""),
                "push_enabled": bool(VAPID_KEYS)
            }, ensure_ascii=False).encode("utf-8"))
            return

        # Web Share Target (iOS/Android -> PWA): recebe title/text/url e abre o HUD com o conteúdo
        if parsed.path == "/share":
            params = urllib.parse.parse_qs(parsed.query)
            title = (params.get("title", [""])[0] or "").strip()
            text = (params.get("text", [""])[0] or "").strip()
            url = (params.get("url", [""])[0] or "").strip()
            parts = [p for p in (title, text, url) if p]
            shared = "\n".join(parts) or "Compartilhamento recebido pelo J.A.R.V.I.S."
            target = "/?shared_text=" + urllib.parse.quote(shared[:2000], safe="")
            self.send_response(302)
            self.send_header("Location", target)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            return

        # Siri Shortcuts / Apple Atalhos: chat por GET protegido pela chave mestre 16D
        if parsed.path == "/api/shortcut/chat":
            params = urllib.parse.parse_qs(parsed.query)
            text = (params.get("text", [""])[0] or "").strip()
            key = (params.get("key", [""])[0] or "").strip()
            if not text:
                self.send_response(400)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"reply": "Parâmetro 'text' obrigatório. Ex: /api/shortcut/chat?text=<mensagem>&key=<chave16d>"}, ensure_ascii=False).encode("utf-8"))
                return
            if not (key and biometrics.verify_master_key(key)):
                self.send_response(403)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"reply": "Atalho não autorizado: configure o parâmetro 'key' com sua chave mestre de 16 dígitos."}, ensure_ascii=False).encode("utf-8"))
                return
            try:
                fwd_body = json.dumps({"message": text}).encode("utf-8")
                fwd = urllib.request.Request(
                    f"http://127.0.0.1:{PORT}/api/chat",
                    data=fwd_body,
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(fwd, timeout=90) as resp:
                    chat_data = json.loads(resp.read().decode("utf-8"))
                payload = {
                    "reply": chat_data.get("reply", ""),
                    "target_widget": chat_data.get("target_widget", "custom"),
                    "audio_url": chat_data.get("audio_url")
                }
            except Exception as e:
                payload = {"reply": f"Falha no atalho Siri ao contatar o núcleo: {e}"}
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            return

        # Endpoints de Visão Computacional J.A.R.V.I.S.
        if parsed.path == "/api/vision/status":
            st = vision_engine.get_status()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(st).encode("utf-8"))
            return

        if parsed.path == "/api/vision/config":
            cfg = vision_engine.config.to_dict()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(cfg).encode("utf-8"))
            return

        if parsed.path == "/api/vision/history":
            hist = vision_engine.event_bus.get_history()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(hist).encode("utf-8"))
            return

        if parsed.path == "/api/canvas/open":
            mode = "reactor"
            params = urllib.parse.parse_qs(parsed.query)
            if "mode" in params:
                mode = params["mode"][0]
            if win_bridge:
                res = win_bridge.open_canvas_window(mode)
            else:
                res = {"status": "error", "message": "win_bridge indisponível"}
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        if parsed.path == "/api/vision/stream":
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-cache, private")
            self.send_header("Pragma", "no-cache")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            try:
                while True:
                    jpeg = vision_engine.get_annotated_jpeg()
                    if jpeg:
                        self.wfile.write(b"--frame\r\n")
                        self.wfile.write(b"Content-Type: image/jpeg\r\n\r\n")
                        self.wfile.write(jpeg)
                        self.wfile.write(b"\r\n")
                        self.wfile.flush()
                    time.sleep(0.04)
            except (BrokenPipeError, ConnectionResetError, Exception):
                pass
            return

        # Endpoint de Eventos em Tempo Real para o HUD (SSE)
        if parsed.path == "/api/hud/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            q = queue.Queue(maxsize=50)
            with sse_lock:
                sse_subscribers.append(q)

            try:
                self.wfile.write(b": connected\n\n")
                self.wfile.flush()
                while True:
                    try:
                        event = q.get(timeout=10)
                        data = f"data: {json.dumps(event)}\n\n".encode("utf-8")
                        self.wfile.write(data)
                        self.wfile.flush()
                    except queue.Empty:
                        self.wfile.write(b": heartbeat\n\n")
                        self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, Exception):
                pass
            finally:
                with sse_lock:
                    if q in sse_subscribers:
                        sse_subscribers.remove(q)
            return
            
        return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path.startswith("/api/memory"):
            content_length = int(self.headers.get('Content-Length', 0))
            body_bytes = self.rfile.read(content_length) if content_length > 0 else b''
            data = None
            last_err = None
            for base_url in [os.environ.get("MEMORY_PRIMARY_URL", "${ZIMA_ROUTER_URL:-http://127.0.0.1:8095}"), "http://127.0.0.1:8090"]:
                try:
                    mem_url = f"{base_url}{self.path}"
                    req = urllib.request.Request(
                        mem_url,
                        data=body_bytes if body_bytes else None,
                        headers={"Content-Type": "application/json"},
                        method=self.command
                    )
                    with urllib.request.urlopen(req, timeout=3) as resp:
                        data = resp.read()
                        break
                except Exception as em:
                    last_err = em
            if data is not None:
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)
                return
            else:
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"error": f"Erro proxy memória POST: {last_err}"}).encode('utf-8'))
                return

        # JEV & Laya (TypeSafe AI) Endpoints:
        if parsed.path in ["/v1/systemone", "/api/jev/triage"]:
            content_length = int(self.headers.get('Content-Length', 0))
            raw_bytes = self.rfile.read(content_length)
            try:
                body = json.loads(raw_bytes.decode('utf-8'))
            except Exception:
                body = {}
            if parsed.path == "/v1/systemone":
                res = jev_engine.handle_systemone_request(body)
            else:
                input_msg = body.get("message") or body.get("text") or body.get("input") or body.get("state") or ""
                decision = jev_engine.triage(input_msg, context=body)
                res = decision.to_dict()

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(res, ensure_ascii=False).encode("utf-8"))
            return

        if parsed.path == "/api/jev/guard":
            content_length = int(self.headers.get('Content-Length', 0))
            raw_bytes = self.rfile.read(content_length)
            try:
                body = json.loads(raw_bytes.decode('utf-8'))
            except Exception:
                body = {}
            out_text = body.get("text") or body.get("output") or body.get("message") or ""
            audit = jev_engine.guard(out_text, context=body)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(audit.to_dict(), ensure_ascii=False).encode("utf-8"))
            return

        # Ingestão de Quadros da Webcam do Navegador (WebRTC / HTML5 MediaDevices)
        if parsed.path == "/api/vision/frame":
            content_length = int(self.headers.get('Content-Length', 0))
            frame_bytes = self.rfile.read(content_length)
            res = vision_engine.process_browser_frame(frame_bytes)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        # Endpoints de Autenticação Facial Biométrica (Neural 128D & MediaPipe Fallback)
        if parsed.path == "/api/auth/face/verify":
            content_length = int(self.headers.get('Content-Length', 0))
            raw_bytes = self.rfile.read(content_length)

            is_json = False
            json_data = None
            try:
                ct = self.headers.get('Content-Type', '')
                if 'application/json' in ct or raw_bytes.strip().startswith(b'{'):
                    json_data = json.loads(raw_bytes.decode('utf-8'))
                    is_json = True
            except Exception:
                pass

            if is_json and json_data and "descriptor" in json_data:
                client_desc = json_data.get("descriptor")
                auth_res = biometrics.match_face_descriptor(client_desc)
            else:
                auth_res = {
                    "authenticated": False,
                    "reason": "BIOMETRIC_DESCRIPTOR_REQUIRED",
                    "confidence": 0.0,
                    "user": None
                }

            if auth_res.get("authenticated"):
                auth_res["role"] = auth_res.get("role", "Operador")
                auth_res["permissions"] = biometrics.resolve_permissions(auth_res["role"], auth_res.get("permissions"))
                auth_res["session_token"] = _create_session_token(
                    auth_res.get("user", "Operador"), auth_res["role"], auth_res["permissions"]
                )
                broadcast_hud_event({
                    "action": "alert",
                    "title": "LOGIN BIOMÉTRICO CONFIRMADO",
                    "message": f"Identidade confirmada: {auth_res.get('user')} ({auth_res.get('role')}). Acesso concedido conforme permissões do operador.",
                    "level": "sucesso"
                })
            elif auth_res.get("reason") == "BIOMETRIC_MISMATCH_STRANGER":
                # Alerta push para o proprietário: rosto desconhecido tentando acessar
                threading.Thread(target=lambda: broadcast_push(
                    "SEGURANÇA // J.A.R.V.I.S.",
                    "Tentativa de acesso negada: rosto não reconhecido detectado no HUD.",
                    "security"
                ), daemon=True).start()

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(auth_res).encode("utf-8"))
            return

        if parsed.path == "/api/auth/face/register":
            content_length = int(self.headers.get('Content-Length', 0))
            raw_bytes = self.rfile.read(content_length)

            is_json = False
            json_data = None
            try:
                ct = self.headers.get('Content-Type', '')
                if 'application/json' in ct or raw_bytes.strip().startswith(b'{'):
                    json_data = json.loads(raw_bytes.decode('utf-8'))
                    is_json = True
            except Exception:
                pass

            if is_json and json_data and "descriptor" in json_data:
                # Fluxo unificado: todo cadastro biométrico passa pelo SQLite via biometrics.py
                reg_name = str(json_data.get("name", "Werik")).strip() or "Werik"
                reg_role = str(json_data.get("role", "Proprietário")).strip() or "Proprietário"
                reg_res = biometrics.register_face_profile(reg_name, reg_role, json_data["descriptor"])
                if reg_res.get("success"):
                    if hasattr(face_auth, "profile") and isinstance(face_auth.profile, dict):
                        face_auth.profile["registered"] = True
                        face_auth.profile["name"] = reg_name
                        face_auth.profile["descriptor"] = json_data["descriptor"]
                    res = {"status": "ok", "registered": True, "method": "neural_128d_sqlite", "profile": reg_res.get("profile")}
                else:
                    res = {"status": "error", "registered": False, "error": reg_res.get("error", "Falha ao registrar perfil biométrico.")}
            else:
                res = {
                    "status": "error",
                    "registered": False,
                    "error": "Descriptor neural 128D obrigatório. Use o portal de cadastro (enroll.html) ou envie JSON {name, role, descriptor}."
                }

            if res.get("registered"):
                broadcast_hud_event({
                    "action": "alert",
                    "title": "PERFIL BIOMÉTRICO CADASTRADO",
                    "message": "Assinatura facial 128D do Senhor Werik registrada com sucesso.",
                    "level": "sucesso"
                })

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        # Desbloqueio por Código Tático Mestre de 16 Dígitos
        if parsed.path == "/api/auth/code/verify":
            content_length = int(self.headers.get('Content-Length', 0))
            raw_bytes = self.rfile.read(content_length)
            try:
                body = raw_bytes.decode('utf-8')
                data = json.loads(body)
                code = str(data.get("code", "")).strip()
            except Exception:
                code = ""
            valid = biometrics.verify_master_key(code)
            res = {
                "authenticated": valid,
                "user": "Senhor Werik (Código Mestre 16D)" if valid else None,
                "role": "Proprietário" if valid else None,
                "permissions": dict(biometrics.OWNER_PERMISSIONS) if valid else dict(biometrics.GUEST_PERMISSIONS),
                "session_token": _create_session_token("Senhor Werik", "Proprietário", biometrics.OWNER_PERMISSIONS) if valid else None,
                "reason": "MASTER_KEY_ACCEPTED" if valid else "INVALID_MASTER_KEY"
            }
            if valid:
                broadcast_hud_event({
                    "action": "alert",
                    "title": "ACESSO CONCEDIDO (CÓDIGO MESTRE 16D)",
                    "message": "Credencial mestre de emergência confirmada: Senhor Werik.",
                    "level": "aviso"
                })
            else:
                # Alerta push para o proprietário: código mestre incorreto
                threading.Thread(target=lambda: broadcast_push(
                    "SEGURANÇA // J.A.R.V.I.S.",
                    "Código mestre de 16 dígitos incorreto digitado no HUD.",
                    "security"
                ), daemon=True).start()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        # Endpoints de Controle de Visão Computacional (Webcam ON/OFF, Ações, Config)
        if parsed.path == "/api/vision/toggle":
            is_active = vision_engine.toggle_camera()
            st = vision_engine.get_status()
            broadcast_hud_event({"action": "vision_telemetry", "vision": st})
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "enabled": is_active, "vision": st}).encode("utf-8"))
            return

        if parsed.path == "/api/vision/enable":
            vision_engine.enable_camera()
            st = vision_engine.get_status()
            broadcast_hud_event({"action": "vision_telemetry", "vision": st})
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "enabled": True, "vision": st}).encode("utf-8"))
            return

        if parsed.path == "/api/vision/disable":
            vision_engine.disable_camera()
            st = vision_engine.get_status()
            broadcast_hud_event({"action": "vision_telemetry", "vision": st})
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "enabled": False, "vision": st}).encode("utf-8"))
            return

        if parsed.path == "/api/vision/action":
            content_length = int(self.headers.get('Content-Length', 0))
            raw_bytes = self.rfile.read(content_length)
            try:
                body = raw_bytes.decode('utf-8')
            except UnicodeDecodeError:
                body = raw_bytes.decode('latin-1', errors='replace')
            try:
                data = json.loads(body)
                action_name = data.get("action", "")
                target = data.get("target", "")
                risk = data.get("risk_level", "low")
                res = vision_engine.windows_actions.execute(action_name, target=target, risk_level=risk)
            except Exception as e:
                res = {"status": "error", "error": str(e)}
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        if parsed.path == "/api/vision/config":
            content_length = int(self.headers.get('Content-Length', 0))
            raw_bytes = self.rfile.read(content_length)
            try:
                body = raw_bytes.decode('utf-8')
            except UnicodeDecodeError:
                body = raw_bytes.decode('latin-1', errors='replace')
            try:
                data = json.loads(body)
                if "gesture_mappings" in data:
                    for g, m in data["gesture_mappings"].items():
                        vision_engine.config.set_action_for_gesture(g, m.get("action"), m.get("target", ""), m.get("risk_level", "low"))
                res = {"status": "ok", "config": vision_engine.config.to_dict()}
            except Exception as e:
                res = {"status": "error", "error": str(e)}
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        # Endpoint de Controle Direto do HUD (chamado pelo Servidor MCP ou REST)
        if parsed.path == "/api/hud/control":
            content_length = int(self.headers.get('Content-Length', 0))
            raw_bytes = self.rfile.read(content_length)
            try:
                body = raw_bytes.decode('utf-8')
            except UnicodeDecodeError:
                body = raw_bytes.decode('latin-1', errors='replace')
            try:
                data = json.loads(body)
                global last_hud_event_time
                last_hud_event_time = time.time()
                print(f"[HUD CONTROL] Received: {data.get('action')} - {data.get('screen') or data.get('title') or ''}")
                broadcast_hud_event(data)
                resp = {"status": "ok", "dispatched": data}
            except Exception as e:
                resp = {"status": "error", "error": str(e)}
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(resp).encode("utf-8"))
            return

        # Endpoint de Ações Bidirecionais do Canvas Interativo (Cliques no HUD)
        if parsed.path == "/api/canvas/action":
            content_length = int(self.headers.get('Content-Length', 0))
            raw_bytes = self.rfile.read(content_length)
            try:
                body = raw_bytes.decode('utf-8')
            except UnicodeDecodeError:
                body = raw_bytes.decode('latin-1', errors='replace')
            try:
                data = json.loads(body)
                action = data.get("action", "")
                target = data.get("target", "")
                res_msg = "Comando recebido."
                updated_canvas = None

                print(f"[CANVAS ACTION] Executando: {action} (Target: {target})")

                if action not in KNOWN_CANVAS_ACTIONS:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "error", "error": f"Ação de canvas desconhecida ou não suportada: '{action}'"}).encode("utf-8"))
                    return

                # RBAC: ações destrutivas de canvas exigem a permissão correspondente
                cv_perm = CANVAS_ACTION_PERMISSIONS.get(action)
                if cv_perm:
                    cv_auth = self._get_request_auth()
                    if not self._perm_allowed(cv_auth, cv_perm):
                        self._send_forbidden(cv_auth, cv_perm)
                        return

                if action == "restart_container":
                    out = exec_zima_command(f"docker restart {target}")
                    res_msg = f"Container '{target}' reiniciado com sucesso no ZimaOS."
                    updated_canvas = build_zima_containers_canvas()
                elif action == "docker_prune":
                    out = exec_zima_command("docker system prune -f")
                    res_msg = f"Limpeza de cache Docker executada com sucesso no ZimaOS."
                    updated_canvas = build_zima_containers_canvas()
                elif action == "view_container_logs":
                    updated_canvas = build_container_logs_canvas(target)
                    res_msg = f"Logs em tempo real do container '{target}' carregados."
                elif action == "kill_windows_process":
                    pid = int(target) if target and str(target).isdigit() else None
                    if pid:
                        ok = hc.kill_windows_process(pid)
                        res_msg = f"Processo PID {pid} finalizado com sucesso no Windows." if ok else f"Não foi possível finalizar o PID {pid}."
                    updated_canvas = build_windows_processes_canvas()
                elif action == "refresh_canvas_containers":
                    updated_canvas = build_zima_containers_canvas()
                    res_msg = "Lista de 39 containers atualizada com sucesso."
                elif action == "refresh_windows_processes":
                    updated_canvas = build_windows_processes_canvas()
                    res_msg = "Processos ativos do Windows atualizados."
                elif action == "refresh_pluggy":
                    updated_canvas = build_pluggy_transactions_canvas()
                    res_msg = "Extrato consolidado Pluggy atualizado."
                elif action == "refresh_connectivity":
                    updated_canvas = build_connectivity_canvas()
                    res_msg = "Radar de conectividade e ping atualizado."
                elif action == "refresh_openclaw":
                    updated_canvas = build_openclaw_canvas()
                    res_msg = "Painel e logs do OpenClaw atualizados."
                elif action in ["refresh_hardware_charts", "show_hardware_charts", "hardware_charts"]:
                    target_mode = target if target in ["modal", "center", "sidebar"] else "sidebar"
                    updated_canvas = build_hardware_charts_canvas(target_mode)
                    res_msg = "Gráficos de telemetria de hardware e GPU GTX 1660 Ti atualizados no Canvas."
                elif action == "open_desktop_canvas":
                    if win_bridge:
                        win_bridge.open_canvas_window(target or "charts")
                    updated_canvas = build_hardware_charts_canvas("sidebar")
                    res_msg = "Janela Canvas Desktop com gráficos holográficos aberta na tela principal."
                elif action in ["shutdown_pc", "desligar_pc", "desligar"]:
                    delay = int(target) if target and str(target).isdigit() else 30
                    if win_bridge:
                        win_bridge.shutdown_pc(delay=delay)
                    res_msg = f"Ordem de desligamento enviada ao Windows ({delay}s). Diga 'cancelar desligamento' para abortar."
                    updated_canvas = build_hardware_charts_canvas("sidebar")
                elif action in ["abort_shutdown", "cancelar_desligamento"]:
                    if win_bridge:
                        win_bridge.abort_shutdown()
                    res_msg = "Ordem de desligamento cancelada com sucesso no Windows."
                    updated_canvas = build_hardware_charts_canvas("sidebar")
                elif action in ["restart_pc", "reiniciar_pc"]:
                    delay = int(target) if target and str(target).isdigit() else 30
                    if win_bridge:
                        win_bridge.restart_pc(delay=delay)
                    res_msg = f"Reinicialização agendada para daqui a {delay} segundos."
                    updated_canvas = build_hardware_charts_canvas("sidebar")
                elif action in ["sleep_pc", "suspender_pc"]:
                    if win_bridge:
                        win_bridge.sleep_pc()
                    res_msg = "Comando de suspensão executado no Windows."

                if updated_canvas:
                    broadcast_hud_event({
                        "action": "canvas_projection",
                        "canvas": updated_canvas
                    })

                resp = {"status": "ok", "message": res_msg, "canvas": updated_canvas}
            except Exception as e:
                print(f"[!] Erro ao processar canvas action: {e}")
                resp = {"status": "error", "error": str(e)}

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(resp).encode("utf-8"))
            return

        if parsed.path == "/api/canvas/open":
            content_length = int(self.headers.get('Content-Length', 0))
            raw_bytes = self.rfile.read(content_length) if content_length > 0 else b'{}'
            try:
                data = json.loads(raw_bytes.decode('utf-8'))
                mode = data.get("mode", "reactor")
            except Exception:
                mode = "reactor"
            if win_bridge:
                res = win_bridge.open_canvas_window(mode)
            else:
                res = {"status": "error", "message": "win_bridge indisponível"}
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        if parsed.path == "/api/tts":
            content_length = int(self.headers.get('Content-Length', 0))
            raw_bytes = self.rfile.read(content_length) if content_length > 0 else b'{}'
            try:
                data = json.loads(raw_bytes.decode('utf-8'))
                text = data.get("text", "")
                audio_path = get_or_generate_tts(text)
                if audio_path and os.path.exists(audio_path):
                    rel = os.path.relpath(audio_path, DIRECTORY).replace("\\", "/")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(json.dumps({"url": f"/{rel}", "status": "ok"}).encode())
                    return
            except Exception as e:
                print(f"[!] Erro ao processar POST /api/tts: {e}")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Falha no TTS"}).encode())
            return

        # Endpoint de Transcrição Whisper Local (Modelo Small em Português)
        # TTS em PCM 16k mono s16le (para a esfera ESP32 / nós de áudio)
        if parsed.path == "/api/hud/broadcast":
            cl = int(self.headers.get('Content-Length', 0))
            raw = self.rfile.read(cl) if cl > 0 else b'{}'
            try:
                data = json.loads(raw.decode('utf-8'))
                broadcast_hud_event(data)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(b'{"status":"ok"}')
            except Exception as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
            return

        if parsed.path == "/api/tts_pcm":
            cl = int(self.headers.get('Content-Length', 0))
            raw = self.rfile.read(cl) if cl > 0 else b'{}'
            try:
                data = json.loads(raw.decode('utf-8'))
            except Exception:
                data = {}
            text = data.get("text", "")
            pcm_file = get_or_generate_tts_pcm(text)
            if pcm_file and os.path.exists(pcm_file):
                with open(pcm_file, "rb") as f:
                    pcm = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("X-Sample-Rate", "16000")
                self.send_header("X-Channels", "1")
                self.send_header("Content-Length", str(len(pcm)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(pcm)
            else:
                self.send_response(503)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "TTS PCM indisponível neste nó"}).encode("utf-8"))
            return

        if parsed.path == "/api/transcribe":
            content_length = int(self.headers.get('Content-Length', 0))
            audio_bytes = self.rfile.read(content_length)
            ctype = self.headers.get("Content-Type", "audio/wav")
            text = ""
            err = None

            # 1) Whisper local (se carregado — ex.: nó Windows)
            if whisper_model is not None:
                temp_audio = os.path.join(DIRECTORY, f"temp_rec_{int(time.time()*1000)}.wav")
                try:
                    with open(temp_audio, "wb") as f:
                        f.write(audio_bytes)
                    segments, info = whisper_model.transcribe(
                        temp_audio, language="pt", beam_size=1, best_of=1,
                        vad_filter=True, vad_parameters=dict(min_silence_duration_ms=300),
                        initial_prompt="Jarvis, comando de voz em português brasileiro para automação e consulta de dados."
                    )
                    text = " ".join([s.text.strip() for s in segments]).strip()
                    if text:
                        try:
                            hc.record_local_whisper()
                        except Exception:
                            pass
                except Exception as e:
                    err = str(e)
                    print("[!] Erro Whisper local:", e)
                finally:
                    if os.path.exists(temp_audio):
                        try: os.remove(temp_audio)
                        except: pass

            # 2) Fallback: container Whisper dedicado (OpenAI-compatible) — ex.: núcleo ZimaOS
            if not text:
                try:
                    text = _transcribe_via_container(audio_bytes, ctype)
                    if text:
                        print(f"[Whisper container] Transcrição: '{text}'")
                except Exception as e:
                    err = (f"{err} | container: {e}" if err else f"container: {e}")

            resp = {"text": text}
            if not text and err:
                resp["error"] = err[:250]
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(resp).encode("utf-8"))
            return

        # ================= ESFERA FÍSICA (ESP32-S3) — CONTROLE PELO NÚCLEO =================
        if parsed.path == "/api/esfera/show_screen":
            content_length = int(self.headers.get('Content-Length', 0))
            raw = self.rfile.read(content_length) if content_length else b"{}"
            try:
                body = json.loads(raw.decode("utf-8"))
            except Exception:
                body = {}
            device_id = body.get("device_id") or _ESFERA_STATE["last_device"]
            screen = body.get("screen", {}) or {}
            ws_payload = {
                "type": "custom",
                "payload": {
                    "event": "jarvis.show_screen",
                    "request_id": str(body.get("request_id") or f"req-{int(time.time()*1000)}"),
                    "screen": {
                        "title": str(screen.get("title", "J.A.R.V.I.S.")),
                        "message": str(screen.get("message", "")),
                        "button1_id": str(screen.get("button1_id", "")),
                        "button1_label": str(screen.get("button1_label", "")),
                        "button2_id": str(screen.get("button2_id", "")),
                        "button2_label": str(screen.get("button2_label", "")),
                        "button3_id": str(screen.get("button3_id", "")),
                        "button3_label": str(screen.get("button3_label", "")),
                    },
                },
            }
            ok, err = _sphere_ws_push(device_id, ws_payload)
            result = {"status": "success", "via": "wss"} if ok else {"status": "error", "message": err}
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode("utf-8"))
            return

        if parsed.path == "/api/esfera/emotion":
            content_length = int(self.headers.get('Content-Length', 0))
            raw = self.rfile.read(content_length) if content_length else b"{}"
            try:
                body = json.loads(raw.decode("utf-8"))
            except Exception:
                body = {}
            device_id = body.get("device_id") or _ESFERA_STATE["last_device"]
            ws_payload = {"type": "emotion", "emotion": str(body.get("emotion", "happy"))}
            ok, err = _sphere_ws_push(device_id, ws_payload)
            result = {"status": "success", "via": "wss"} if ok else {"status": "error", "message": err}
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode("utf-8"))
            return

        # Fala na esfera: texto → TTS → áudio via WSS (exige segredo da ponte)
        if parsed.path == "/api/esfera/say":
            content_length = int(self.headers.get('Content-Length', 0))
            raw = self.rfile.read(content_length) if content_length else b"{}"
            try:
                body = json.loads(raw.decode("utf-8"))
            except Exception:
                body = {}
            if not _bridge_secret_ok(self.headers.get("X-Bridge-Secret", "")):
                self.send_response(403)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": "Segredo da ponte inválido."}).encode("utf-8"))
                return
            text = clean_text_for_speech(str(body.get("text", ""))[:600])
            if not text:
                self.send_response(400)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": "text obrigatório."}).encode("utf-8"))
                return
            device_id = body.get("device_id") or _ESFERA_STATE["last_device"]
            try:
                pcm_path = get_or_generate_tts_pcm(text)
                pcm = open(pcm_path, "rb").read() if pcm_path and os.path.isfile(pcm_path) else b""
            except Exception:
                pcm = b""
            if len(pcm) < 1000:
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": "TTS indisponível (nuvem+fallback falharam)."}).encode("utf-8"))
                return
            try:
                import asyncio
                from sphere_audio_bridge import speak_to_device, get_loop
                loop = get_loop()
                if loop is None or loop.is_closed():
                    raise RuntimeError("Ponte WSS inativa.")
                dur = max(12.0, len(pcm) / 32000.0 + 10.0)
                fut = asyncio.run_coroutine_threadsafe(speak_to_device(device_id, pcm), loop)
                ok = bool(fut.result(timeout=dur))
                err = "" if ok else "Esfera não está conectada ao WSS."
            except Exception as e:
                ok = False
                err = f"Falha no envio WSS: {type(e).__name__}"
            result = {"ok": True, "via": "wss", "chars": len(text)} if ok else {"ok": False, "error": err}
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode("utf-8"))
            return

        # Envio administrativo direto pela ponte WSS (OTA, timers, etc.) — exige segredo da ponte
        if parsed.path == "/api/esfera/send":
            content_length = int(self.headers.get('Content-Length', 0))
            raw = self.rfile.read(content_length) if content_length else b"{}"
            try:
                body = json.loads(raw.decode("utf-8"))
            except Exception:
                body = {}
            if not _bridge_secret_ok(self.headers.get("X-Bridge-Secret", "")):
                self.send_response(403)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": "Segredo da ponte inválido."}).encode("utf-8"))
                return
            device_id = body.get("device_id") or _ESFERA_STATE["last_device"]
            ws_payload = body.get("payload") if isinstance(body.get("payload"), dict) else {}
            ok, err = _sphere_ws_push(device_id, ws_payload)
            result = {"status": "success", "via": "wss"} if ok else {"status": "error", "message": err}
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode("utf-8"))
            return

        if parsed.path == "/api/bridge/execute":
            content_length = int(self.headers.get('Content-Length', 0))
            raw_bytes = self.rfile.read(content_length)
            try:
                raw_str = raw_bytes.decode('utf-8', errors='replace').strip()
                try:
                    data = json.loads(raw_str)
                except Exception:
                    cleaned = re.sub(r'\\"', '"', raw_str)
                    data = json.loads(cleaned)
                action = data.get("action", "")
                params = data.get("params", {})

                # RBAC: verifica a permissão exigida pela ação do bridge
                br_auth = self._get_request_auth()
                br_perm = _required_permission_for_bridge_action(str(action).lower().strip())
                if not self._perm_allowed(br_auth, br_perm):
                    self._send_forbidden(br_auth, br_perm)
                    return

                b_inst = win_bridge
                if b_inst is None:
                    try:
                        from desktop.windows_bridge import bridge as b_inst
                    except Exception:
                        pass
                if b_inst:
                    res = b_inst.execute(action, **params)
                    print(f"[BRIDGE EXECUTE API] {action} -> {res}")
                else:
                    res = {"status": "error", "message": "WindowsBridge indisponível"}
            except Exception as e:
                res = {"status": "error", "message": str(e)}

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        # Endpoint de Controle de Energia do Windows (Desligar, Reiniciar, Cancelar, Suspender)
        if parsed.path == "/api/system/power":
            content_length = int(self.headers.get('Content-Length', 0))
            raw_bytes = self.rfile.read(content_length) if content_length > 0 else b'{}'
            try:
                data = json.loads(raw_bytes.decode('utf-8'))
                act = data.get("action", "shutdown")

                # RBAC: operações de energia exigem power_control
                pw_auth = self._get_request_auth()
                if not self._perm_allowed(pw_auth, "power_control"):
                    self._send_forbidden(pw_auth, "power_control")
                    return

                delay = int(data.get("delay", 30))
                b_inst = win_bridge
                if b_inst is None:
                    try:
                        from desktop.windows_bridge import bridge as b_inst
                    except Exception:
                        pass
                if b_inst:
                    if act in ["shutdown", "desligar"]:
                        res = b_inst.shutdown_pc(delay=delay)
                        broadcast_hud_event({
                            "action": "alert",
                            "title": "DESLIGAMENTO DO SISTEMA",
                            "message": f"Desligamento agendado para daqui a {delay} segundos. Diga 'cancelar desligamento' para abortar.",
                            "level": "aviso"
                        })
                    elif act in ["abort", "cancel", "cancelar"]:
                        res = b_inst.abort_shutdown()
                        broadcast_hud_event({
                            "action": "alert",
                            "title": "DESLIGAMENTO CANCELADO",
                            "message": "Ordem de desligamento abortada com sucesso.",
                            "level": "sucesso"
                        })
                    elif act in ["restart", "reiniciar"]:
                        res = b_inst.restart_pc(delay=delay)
                        broadcast_hud_event({
                            "action": "alert",
                            "title": "REINICIALIZAÇÃO DO SISTEMA",
                            "message": f"Reinicialização agendada para {delay}s.",
                            "level": "aviso"
                        })
                    elif act in ["sleep", "suspender"]:
                        res = b_inst.sleep_pc()
                    else:
                        res = {"status": "error", "message": f"Ação desconhecida: {act}"}
                else:
                    res = {"status": "error", "message": "WindowsBridge indisponível"}
            except Exception as e:
                res = {"status": "error", "message": str(e)}

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        # ==================================================================
        # WAKE-ON-LAN: ligar PCs da própria rede ou de rede remota com IP fixo
        # ==================================================================
        if parsed.path == "/api/wol":
            content_length = int(self.headers.get('Content-Length', 0))
            raw_bytes = self.rfile.read(content_length) if content_length > 0 else b'{}'
            try:
                data = json.loads(raw_bytes.decode('utf-8'))
            except Exception:
                data = {}
            action = str(data.get("action", "wake")).lower().strip()
            auth = self._get_request_auth()

            if action == "wake":
                if not self._perm_allowed(auth, "wake_on_lan"):
                    self._send_forbidden(auth, "wake_on_lan")
                    return
                name = str(data.get("name", "")).strip()
                mac = str(data.get("mac", "")).strip()
                ip = str(data.get("ip", "")).strip()
                port = data.get("port", 9)
                device = None
                if not mac and name:
                    device = find_wol_device(name)
                    if not device:
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json; charset=utf-8")
                        self.send_header("Access-Control-Allow-Origin", "*")
                        self.end_headers()
                        self.wfile.write(json.dumps({
                            "success": False,
                            "error": f"Dispositivo '{name}' não encontrado no registro Wake-on-LAN.",
                            "devices": [d.get("name") for d in _load_wol_devices()]
                        }, ensure_ascii=False).encode("utf-8"))
                        return
                if device:
                    mac = device.get("mac", mac)
                    ip = ip or device.get("ip", "255.255.255.255")
                    port = data.get("port", device.get("port", 9))
                if not mac:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "success": False,
                        "error": "Informe o MAC do dispositivo ou o nome de um dispositivo cadastrado."
                    }, ensure_ascii=False).encode("utf-8"))
                    return
                res = send_wake_on_lan(mac, ip, port)
                level = "sucesso" if res.get("success") else "erro"
                broadcast_hud_event({
                    "action": "alert",
                    "title": "WAKE-ON-LAN",
                    "message": res.get("message") or res.get("error", ""),
                    "level": level
                })

            elif action in ("add", "register", "update"):
                if not (self._perm_allowed(auth, "infra_control") or self._is_master_key_request()):
                    self._send_forbidden(auth, "infra_control")
                    return
                name = str(data.get("name", "")).strip()
                mac = str(data.get("mac", "")).strip()
                if not name or not mac:
                    res = {"success": False, "error": "Informe 'name' e 'mac' para cadastrar o dispositivo."}
                else:
                    try:
                        mac_norm = _normalize_mac(mac)
                    except ValueError as e:
                        res = {"success": False, "error": str(e)}
                    else:
                        devices = _load_wol_devices()
                        entry = {
                            "name": name,
                            "mac": mac_norm,
                            "ip": str(data.get("ip", "")).strip() or "255.255.255.255",
                            "port": int(data.get("port", 9) or 9),
                            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")
                        }
                        devices = [d for d in devices if str(d.get("name", "")).lower() != name.lower()]
                        devices.append(entry)
                        _save_wol_devices(devices)
                        res = {"success": True, "device": entry, "message": f"Dispositivo '{name}' cadastrado para Wake-on-LAN."}

            elif action == "remove":
                if not (self._perm_allowed(auth, "infra_control") or self._is_master_key_request()):
                    self._send_forbidden(auth, "infra_control")
                    return
                name = str(data.get("name", "")).strip()
                devices = _load_wol_devices()
                remaining = [d for d in devices if str(d.get("name", "")).lower() != name.lower()]
                if len(remaining) == len(devices):
                    res = {"success": False, "error": f"Dispositivo '{name}' não encontrado."}
                else:
                    _save_wol_devices(remaining)
                    res = {"success": True, "message": f"Dispositivo '{name}' removido do registro Wake-on-LAN."}

            else:
                res = {"success": False, "error": f"Ação WoL desconhecida: '{action}' (use wake, add ou remove)."}

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(res, ensure_ascii=False).encode("utf-8"))
            return

        # ==================================================================
        # OPERADORES & PERMISSÕES (RBAC) - reservado ao Proprietário/master key
        # ==================================================================
        if parsed.path == "/api/operators":
            auth = self._get_request_auth()
            if not (self._perm_allowed(auth, "full_access") or self._is_master_key_request()):
                self._send_forbidden(auth, "full_access")
                return
            content_length = int(self.headers.get('Content-Length', 0))
            raw_bytes = self.rfile.read(content_length) if content_length > 0 else b'{}'
            try:
                data = json.loads(raw_bytes.decode('utf-8'))
            except Exception:
                data = {}
            name = str(data.get("name", "")).strip()
            if not name:
                res = {"success": False, "error": "Informe o 'name' do operador."}
            else:
                perms_in = data.get("permissions")
                if isinstance(perms_in, str):
                    try:
                        perms_in = json.loads(perms_in)
                    except Exception:
                        perms_in = None
                res = biometrics.set_operator_permissions(name, perms_in or {}, role=data.get("role"))
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(res, ensure_ascii=False).encode("utf-8"))
            return

        # ==================================================================
        # CENTRAL DO NÓ — POST: permissões, autostart e testes manuais
        # ==================================================================
        def _read_json_body():
            cl = int(self.headers.get('Content-Length', 0))
            raw = self.rfile.read(cl) if cl > 0 else b'{}'
            try:
                return json.loads(raw.decode('utf-8'))
            except Exception:
                return {}

        def _json_out(payload, code=200):
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

        if parsed.path == "/api/spotify/control":
            data = _read_json_body()
            action = str(data.get("action", "")).strip()
            value = data.get("value")
            query = data.get("query")
            device = data.get("device")
            res = spotify_control(action, value, query, device)
            _json_out({"ok": bool(res.get("success")), **res})
            return

        if parsed.path == "/api/canvas/push":
            data = _read_json_body()
            payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
            if not payload:
                _json_out({"ok": False, "error": "Campo 'payload' (dict) obrigatório."}, 400)
                return
            title = str(payload.get("title") or data.get("title") or "Painel J.A.R.V.I.S.")
            pid = _canvas_panel_push(payload, title)
            _json_out({"ok": True, "id": pid, "url": f"/canvas_panel?pid={pid}"})
            return

        if parsed.path == "/api/node/settings":
            data = _read_json_body()
            settings_file_path = os.path.join(_perm_base, "config", "island_settings.json")
            st = {"wake_word_enabled": True, "ask_before_show": True, "core_url": "https://jarvis.werikspace.xyz"}
            try:
                if os.path.exists(settings_file_path):
                    with open(settings_file_path, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                    if isinstance(loaded, dict):
                        st = loaded
            except Exception:
                pass
            if isinstance(data.get("settings"), dict):
                st.update(data["settings"])
                with open(settings_file_path, "w", encoding="utf-8") as f:
                    json.dump(st, f, indent=2, ensure_ascii=False)
            _json_out({"ok": True, "settings": st})
            return

        if parsed.path == "/api/node/permission":
            data = _read_json_body()
            category = str(data.get("category", "")).strip()
            enabled = bool(data.get("enabled", True))
            if category not in NODE_PERM_CATEGORIES:
                _json_out({"ok": False, "error": "Categoria de permissão desconhecida."}, 400)
                return
            perms = _node_permissions_load()
            perms[category] = enabled
            _node_permission_save(perms)
            _json_out({"ok": True, "category": category, "enabled": enabled,
                       "message": f"Permissão '{NODE_PERM_CATEGORIES[category]}' {'ATIVADA' if enabled else 'DESATIVADA'}."})
            return

        if parsed.path == "/api/node/autostart":
            data = _read_json_body()
            if "enabled" not in data:
                autostart, cmd = _node_autostart_query()
                _json_out({"ok": True, "enabled": autostart, "command": cmd})
                return
            ok = _node_autostart_set(bool(data.get("enabled")))
            _json_out({"ok": ok, "enabled": bool(data.get("enabled"))})
            return

        if parsed.path == "/api/node/test/screenshot":
            try:
                import io as _io
                import mss as _mss
                from PIL import Image as _Img
                with _mss.mss() as sct:
                    mon = sct.monitors[1]
                    raw = sct.grab(mon)
                    img = _Img.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
                os.makedirs(os.path.join(_perm_base, "logs"), exist_ok=True)
                full_path = os.path.join(_perm_base, "logs", f"node_screenshot_{int(time.time())}.png")
                img.save(full_path)
                thumb = img.copy()
                if thumb.width > 960:
                    ratio = 960 / thumb.width
                    thumb = thumb.resize((960, int(thumb.height * ratio)))
                buf = _io.BytesIO()
                thumb.save(buf, format="JPEG", quality=60)
                b64 = base64.b64encode(buf.getvalue()).decode("ascii")
                _json_out({"ok": True, "path": full_path, "image": "data:image/jpeg;base64," + b64,
                           "w": img.width, "h": img.height})
            except Exception as e:
                _json_out({"ok": False, "error": f"Captura falhou: {e}"}, 500)
            return

        if parsed.path == "/api/node/test/mic":
            try:
                import numpy as _np
                import sounddevice as sd
                mic_idx, mic_name = _node_mic_resolve()
                dur = 1.5
                rec = sd.rec(int(16000 * dur), samplerate=16000, channels=1, dtype="float32", device=mic_idx)
                sd.wait()
                data = _np.asarray(rec).flatten()
                rms = float(_np.sqrt(_np.mean(data ** 2)))
                pct = min(100, int(rms * 400))
                _json_out({"ok": True, "rms": round(rms, 4), "level_pct": pct, "device": mic_name,
                           "message": f"Mic '{mic_name}' capturou OK (nível: {pct}%). Fale perto do microfone."})
            except Exception as e:
                _json_out({"ok": False, "error": f"Microfone falhou: {e}"}, 500)
            return

        if parsed.path == "/api/node/test/mouse":
            try:
                import pyautogui
                old = pyautogui.position()
                cx, cy = pyautogui.size()[0] // 2, pyautogui.size()[1] // 2
                pyautogui.moveTo(cx, cy, duration=0.35)
                at = pyautogui.position()
                time.sleep(0.25)
                pyautogui.moveTo(old.x, old.y, duration=0.35)
                _json_out({"ok": True, "center": [cx, cy], "reached": [at.x, at.y],
                           "returned": [old.x, old.y],
                           "message": f"Cursor moveu ao centro ({cx},{cy}) e voltou ({old.x},{old.y})."})
            except Exception as e:
                _json_out({"ok": False, "error": f"Teste do mouse falhou: {e}"}, 500)
            return

        if parsed.path == "/api/node/test/bridge":
            try:
                cfg = {}
                try:
                    with open(os.path.join(DIRECTORY, "config", "jarvis_desktop_config.json"), "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                except Exception:
                    pass
                node_id = (cfg.get("node") or {}).get("node_id", f"jarvis-pc-{socket.gethostname().lower()}")
                secret = os.environ.get("BRIDGE_SECRET", os.environ.get("OPENCLAW_GATEWAY_TOKEN", "casaos"))
                core_url = os.environ.get("ZIMA_CORE_URL", "https://jarvis.werikspace.xyz")
                t0 = time.time()
                payload = json.dumps({"action": "system.info", "params": {}, "node_id": node_id}).encode("utf-8")
                req = urllib.request.Request(f"{core_url}/api/remote/enqueue", data=payload,
                                             headers={"Content-Type": "application/json", "X-Bridge-Secret": secret})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    enqueue = json.loads(resp.read().decode("utf-8"))
                cid = str(enqueue.get("id", ""))
                if not cid:
                    _json_out({"ok": False, "error": f"Núcleo recusou o enfileiramento: {enqueue}"}, 500)
                    return
                for _ in range(10):
                    time.sleep(1.2)
                    r = urllib.request.Request(f"{core_url}/api/remote/result?id={cid}", headers={"X-Bridge-Secret": secret})
                    with urllib.request.urlopen(r, timeout=10) as resp:
                        entry = json.loads(resp.read().decode("utf-8"))
                    if not entry.get("pending", True):
                        tel = ((entry.get("result") or {}).get("telemetry") or {})
                        _json_out({"ok": bool(entry.get("ok")), "roundtrip_ms": int((time.time() - t0) * 1000),
                                   "gpu": (tel.get("gpu") or {}).get("name"), "cpu_pct": tel.get("cpu_percent"),
                                   "ram_pct": tel.get("ram_percent"),
                                   "message": f"Roundtrip núcleo→nó concluiu em {int((time.time()-t0)*1000)} ms (GPU {(tel.get('gpu') or {}).get('name')})."})
                        return
                _json_out({"ok": False, "error": "Núcleo accepted mas o NÃO retornou resultado dentro de 12s — ponte offline."})
            except Exception as e:
                _json_out({"ok": False, "error": f"Roundtrip falhou: {e}"}, 500)
            return

        # ==================================================================
        # PONTE DE COMANDOS REMOTOS (JARVIS no Zima -> Windows via desktop app)
        # ==================================================================
        if parsed.path == "/api/remote/enqueue":
            content_length = int(self.headers.get('Content-Length', 0))
            raw_bytes = self.rfile.read(content_length) if content_length > 0 else b'{}'
            try:
                data = json.loads(raw_bytes.decode('utf-8'))
            except Exception:
                data = {}
            if not _bridge_secret_ok(self.headers.get("X-Bridge-Secret", "")):
                self.send_response(403)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": "Segredo da ponte inválido (X-Bridge-Secret)."}).encode("utf-8"))
                return
            action = str(data.get("action", "")).strip()
            params = data.get("params") if isinstance(data.get("params"), dict) else {}
            node_id = str(data.get("node_id", "")).strip().lower()
            if not action:
                self.send_response(400)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": "Campo 'action' obrigatório."}).encode("utf-8"))
                return
            with _remote_lock:
                cmd_id = _remote_state["next_id"]
                _remote_state["next_id"] += 1
                _remote_state["queue"].append({"id": cmd_id, "action": action, "params": params, "ts": time.time(), "node_id": node_id})
                if len(_remote_state["queue"]) > 50:
                    _remote_state["queue"] = _remote_state["queue"][-50:]
                _remote_save()
            _infra_note({"id": cmd_id, "action": action, "ts": time.time(), "ok": None})
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "id": cmd_id, "pending": True}).encode("utf-8"))
            return

        if parsed.path == "/api/remote/poll":
            content_length = int(self.headers.get('Content-Length', 0))
            raw_bytes = self.rfile.read(content_length) if content_length > 0 else b'{}'
            try:
                data = json.loads(raw_bytes.decode('utf-8'))
            except Exception:
                data = {}
            if not _bridge_secret_ok(self.headers.get("X-Bridge-Secret", "") or (data.get("secret") if isinstance(data, dict) else "")):
                self.send_response(403)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": "Segredo da ponte inválido."}).encode("utf-8"))
                return
            with _remote_lock:
                _remote_state["last_poll"] = time.time()
                req_node = str(data.get("node_id", "")).strip().lower()
                matched, rest = [], []
                for c in _remote_state["queue"]:
                    tgt = str(c.get("node_id", "")).strip().lower()
                    if (not tgt) or (not req_node) or (tgt == req_node):
                        matched.append(c)
                    else:
                        rest.append(c)
                commands = matched[:10]
                _remote_state["queue"] = rest + matched[10:]
                _remote_save()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "commands": commands}).encode("utf-8"))
            return

        if parsed.path == "/api/remote/result":
            content_length = int(self.headers.get('Content-Length', 0))
            raw_bytes = self.rfile.read(content_length) if content_length > 0 else b'{}'
            try:
                data = json.loads(raw_bytes.decode('utf-8'))
            except Exception:
                data = {}
            if not _bridge_secret_ok(self.headers.get("X-Bridge-Secret", "")):
                self.send_response(403)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": "Segredo da ponte inválido."}).encode("utf-8"))
                return
            cmd_id = str(data.get("id", ""))
            if cmd_id:
                with _remote_lock:
                    _remote_state["results"][cmd_id] = {
                        "ok": bool(data.get("ok", False)),
                        "result": data.get("result"),
                        "ts": time.time()
                    }
                    ids = list(_remote_state["results"].keys())
                    if len(ids) > 100:
                        for old in ids[:len(ids) - 100]:
                            _remote_state["results"].pop(old, None)
                    _remote_save()
                try:
                    for _e in _infra_recent:
                        if str(_e.get("id")) == cmd_id:
                            _e["ok"] = bool(data.get("ok", False))
                            break
                except Exception:
                    pass
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))
            return

        # ==============================================================
        # NODES REGISTRY (registro e edição de nós via ponte autenticada)
        # ==============================================================
        if parsed.path == "/api/nodes/register":
            content_length = int(self.headers.get('Content-Length', 0))
            raw_bytes = self.rfile.read(content_length) if content_length > 0 else b'{}'
            try:
                data = json.loads(raw_bytes.decode('utf-8'))
            except Exception:
                data = {}
            if not _bridge_secret_ok(self.headers.get("X-Bridge-Secret", "")):
                self.send_response(403)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": "Segredo da ponte inválido."}).encode("utf-8"))
                return
            node_id = str(data.get("id", "")).strip()
            if not node_id:
                self.send_response(400)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": "id obrigatório."}).encode("utf-8"))
                return
            registry = _nodes_registry_load()
            entry = registry.get(node_id, {})
            entry.update({
                "id": node_id,
                "name": str(data.get("name", entry.get("name", node_id))),
                "type": str(data.get("type", entry.get("type", "pc"))),
                "owner": str(data.get("owner", entry.get("owner", ""))),
                "last_seen": time.strftime("%Y-%m-%d %H:%M:%S"),
            })
            if isinstance(data.get("capabilities"), dict):
                entry["capabilities"] = data["capabilities"]
            registry[node_id] = entry
            ok = _nodes_registry_save(registry)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": ok}).encode("utf-8"))
            return

        if parsed.path == "/api/nodes/update":
            content_length = int(self.headers.get('Content-Length', 0))
            raw_bytes = self.rfile.read(content_length) if content_length > 0 else b'{}'
            try:
                data = json.loads(raw_bytes.decode('utf-8'))
            except Exception:
                data = {}
            if not _bridge_secret_ok(self.headers.get("X-Bridge-Secret", "")):
                self.send_response(403)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": "Segredo da ponte inválido."}).encode("utf-8"))
                return
            node_id = str(data.get("id", "")).strip()
            registry = _nodes_registry_load()
            if not node_id or node_id not in registry:
                self.send_response(404)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": "nó desconhecido."}).encode("utf-8"))
                return
            entry = registry[node_id]
            if isinstance(data.get("name"), str) and data["name"].strip():
                entry["name"] = data["name"].strip()
            if isinstance(data.get("people"), list):
                entry["people"] = [str(p) for p in data["people"]][:20]
            if isinstance(data.get("permissions"), dict):
                entry["permissions"] = {str(k): bool(v) for k, v in list(data["permissions"].items())[:30]}
            entry["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
            ok = _nodes_registry_save(registry)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": ok}).encode("utf-8"))
            return
        # ==================================================================
        if parsed.path == "/api/push/subscribe":
            content_length = int(self.headers.get('Content-Length', 0))
            raw_bytes = self.rfile.read(content_length) if content_length > 0 else b'{}'
            try:
                data = json.loads(raw_bytes.decode('utf-8'))
            except Exception:
                data = {}
            sub = data.get("subscription") if isinstance(data.get("subscription"), dict) else data
            if not isinstance(sub, dict) or not sub.get("endpoint") or not sub.get("keys"):
                res = {"success": False, "error": "Assinatura push inválida (endpoint/keys ausentes)."}
            else:
                total = _register_push_subscription(sub)
                res = {"success": True, "total_devices": total, "message": "Dispositivo registrado para notificações push do J.A.R.V.I.S."}
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(res, ensure_ascii=False).encode("utf-8"))
            return

        if parsed.path == "/api/push/unsubscribe":
            content_length = int(self.headers.get('Content-Length', 0))
            raw_bytes = self.rfile.read(content_length) if content_length > 0 else b'{}'
            try:
                data = json.loads(raw_bytes.decode('utf-8'))
            except Exception:
                data = {}
            endpoint = str(data.get("endpoint", "")).strip()
            _remove_push_subscription(endpoint)
            res = {"success": True, "message": "Dispositivo removido das notificações push."}
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(res, ensure_ascii=False).encode("utf-8"))
            return

        if parsed.path == "/api/push/test":
            content_length = int(self.headers.get('Content-Length', 0))
            raw_bytes = self.rfile.read(content_length) if content_length > 0 else b'{}'
            try:
                data = json.loads(raw_bytes.decode('utf-8'))
            except Exception:
                data = {}
            endpoint = str(data.get("endpoint", "")).strip()
            if endpoint:
                targets = [s for s in _load_push_subscriptions() if s.get("endpoint") == endpoint]
            else:
                # disparo para todos: exige full_access ou chave mestre
                auth = self._get_request_auth()
                if not (self._perm_allowed(auth, "full_access") or self._is_master_key_request()):
                    self._send_forbidden(auth, "full_access")
                    return
                targets = _load_push_subscriptions()
            if not targets:
                res = {"success": False, "error": "Nenhum dispositivo inscrito para push ainda."}
            else:
                sent = 0
                for t in targets:
                    if send_web_push(t, {"title": "J.A.R.V.I.S.", "body": "Notificações push operacionais, Senhor.", "tag": "push-test"}):
                        sent += 1
                res = {"success": sent > 0, "sent": sent, "total": len(targets)}
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(res, ensure_ascii=False).encode("utf-8"))
            return

        if parsed.path == "/api/push/broadcast":
            auth = self._get_request_auth()
            if not (self._perm_allowed(auth, "full_access") or self._is_master_key_request()):
                self._send_forbidden(auth, "full_access")
                return
            content_length = int(self.headers.get('Content-Length', 0))
            raw_bytes = self.rfile.read(content_length) if content_length > 0 else b'{}'
            try:
                data = json.loads(raw_bytes.decode('utf-8'))
            except Exception:
                data = {}
            title = str(data.get("title", "J.A.R.V.I.S.")).strip()[:80] or "J.A.R.V.I.S."
            body = str(data.get("body", "")).strip()[:300]
            if not body:
                res = {"success": False, "error": "Informe 'body' para a notificação."}
            else:
                sent = broadcast_push(title, body, tag=str(data.get("tag", "jarvis-announce")))
                res = {"success": True, "sent": sent}
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(res, ensure_ascii=False).encode("utf-8"))
            return

        if parsed.path == "/api/chat":
            content_length = int(self.headers.get('Content-Length', 0))
            raw_bytes = self.rfile.read(content_length)
            try:
                body = raw_bytes.decode('utf-8')
            except UnicodeDecodeError:
                body = raw_bytes.decode('latin-1', errors='replace')
            try:
                data = json.loads(body)
                user_msg = data.get("message", "").strip()
                lower_msg = user_msg.lower()

                # ORIGEM: identifica se o comando veio da Esfera física e de QUAL esfera
                src_device = (data.get("device_id") or "").strip()
                src_kind = (data.get("source") or "").strip().lower()
                if src_kind == "esfera" and src_device:
                    _ESFERA_STATE["last_device"] = src_device
                    print(f"[ESFERA ORIGEM] Comando de voz recebido de: {src_device}")

                # RBAC: verifica a permissão exigida pela mensagem antes de executar
                auth = self._get_request_auth()
                required_perm = _required_permission_for_message(lower_msg)
                if not self._perm_allowed(auth, required_perm):
                    deny_user = auth.get("user", "Visitante")
                    deny_msg = (
                        f"Acesso não autorizado, {deny_user}: esta operação exige a permissão "
                        f"'{required_perm}', que sua credencial não possui. Solicite liberação ao Proprietário."
                    )
                    print(f"[RBAC] Acesso negado: user='{deny_user}' perm='{required_perm}' msg='{user_msg[:60]}'")
                    broadcast_hud_event({
                        "action": "alert",
                        "title": "ACESSO RESTRITO // RBAC",
                        "message": deny_msg,
                        "level": "aviso"
                    })
                    resp_deny = {
                        "reply": deny_msg,
                        "audio_url": None,
                        "target_widget": "custom",
                        "custom_card": {
                            "action": "custom_card",
                            "title": "ACESSO RESTRITO",
                            "subtitle": "CONTROLE DE PERMISSÕES J.A.R.V.I.S.",
                            "content": deny_msg,
                            "card_type": "padrao",
                            "duration": 0
                        },
                        "forbidden": True,
                        "required_permission": required_perm,
                        "user": deny_user
                    }
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(json.dumps(resp_deny, ensure_ascii=False).encode("utf-8"))
                    return

                # JEV & Laya: Triagem Ultrarrápida de Sistema 1 (~33ms)
                jev_decision = jev_engine.triage(user_msg)
                print(f"[JEV Sistema 1] Triagem: Alvo={jev_decision.target_agent.upper()} | Confiança={int(jev_decision.confidence*100)}% | Latência={jev_decision.latency_ms}ms")
                broadcast_hud_event({
                    "action": "jev_triage",
                    "target_agent": jev_decision.target_agent,
                    "confidence": jev_decision.confidence,
                    "latency_ms": jev_decision.latency_ms,
                    "category": jev_decision.category,
                    "is_urgent": jev_decision.is_urgent,
                    "entities": jev_decision.entities
                })
                
                raw_reply = None
                model_failed = False
                widget = "weather"
                visual_spec = None
                custom_card = None
                yt_payload = None
                hw_payload = None
                news_payload = None
                digest_payload = None
                zima_payload = None
                canvas_payload = None

                # 0. BRIEFING MATINAL EXECUTIVO (MORNING DIGEST - OPENJARVIS PORT)
                if any(w in lower_msg for w in ["briefing matinal", "relatório matinal", "relatorio matinal", "briefing do dia", "relatório do dia", "relatorio do dia", "resumo do dia", "bom dia jarvis", "bom dia"]):
                    digest = generate_morning_digest()
                    raw_reply = digest["spoken_script"]
                    widget = "morning_digest"
                    digest_payload = digest
                    broadcast_hud_event({
                        "action": "morning_digest",
                        "title": "BRIEFING MATINAL EXECUTIVO",
                        "digest": digest,
                        "tactical_content": digest["tactical_markdown"]
                    })

                # 0.5 WAKE-ON-LAN: LIGAR PCs REMOTAMENTE VIA PACOTE MÁGICO (mesma rede ou rede remota)
                elif re.search(r'\b(?:wake\s*on\s*lan|wol|ligar|ligue|liga|acorda|acorde|acordar|despertar)\b', lower_msg) and any(w in lower_msg for w in [
                    "pc", "computador", "máquina", "maquina", "servidor", "notebook", "note",
                    "dispositivo", "estação", "estacao", "wake", "wol"
                ]):
                    devices = _load_wol_devices()
                    target = None
                    for d in devices:
                        if str(d.get("name", "")).lower() in lower_msg:
                            target = d
                            break
                    if target is None and len(devices) == 1:
                        target = devices[0]

                    if target is None:
                        if devices:
                            names = ", ".join(str(d.get("name", "?")) for d in devices)
                            raw_reply = f"Não identifiquei qual dispositivo ligar, Senhor Werik. Dispositivos cadastrados para Wake-on-LAN: {names}."
                        else:
                            raw_reply = "Nenhum dispositivo Wake-on-LAN cadastrado ainda, Senhor Werik. Cadastre via API /api/wol (nome e MAC) para que eu possa ligar máquinas remotamente."
                        widget = "custom"
                    else:
                        wol_res = send_wake_on_lan(
                            target.get("mac", ""),
                            str(data.get("ip", "")).strip() or target.get("ip", "255.255.255.255"),
                            int(target.get("port", 9) or 9)
                        )
                        if wol_res.get("success"):
                            raw_reply = f"Protocolo Wake-on-LAN executado: pacote mágico enviado para ligar '{target.get('name')}'. Aguarde o boot da máquina, Senhor Werik."
                        else:
                            raw_reply = f"Falha no Wake-on-LAN para '{target.get('name')}': {wol_res.get('error', 'erro desconhecido')}"
                        widget = "custom"
                        broadcast_hud_event({
                            "action": "alert",
                            "title": "WAKE-ON-LAN",
                            "message": wol_res.get("message") or wol_res.get("error", ""),
                            "level": "sucesso" if wol_res.get("success") else "erro"
                        })

                # 0.8 PREVISÃO DO TEMPO DA SEMANA (SISTEMA OPERACIONAL VISUAL)
                elif any(w in lower_msg for w in [
                    "tempo", "clima", "previsão", "previsao", "chuva", "chover", "temperatura",
                    "calor", "frio", "graus", "meteorologia", "sol", "vai chover"
                ]) and not any(w in lower_msg for w in ["finance", "dólar", "dolar", "servidor", "notícia", "noticia", "hardware", "cpu", "gpu"]):
                    visual_spec = build_weather_ui_spec()
                    rainiest = visual_spec.get("highlight_quote", "")
                    raw_reply = f"Apresentando a previsão da semana para Catanduva no seu HUD tático. {rainiest}"
                    widget = "weather"
                    broadcast_hud_event({
                        "action": "visual_spec",
                        "spec": visual_spec
                    })

                # 1. YOUTUBE CYBER PLAYER (ZERO CONTAS)
                elif re.search(r'(?:toca|tocar|coloque|coloca|tocar música|toca música|ouvir|reproduz|reproduzir|pesquisa no youtube|pesquise no youtube|youtube)\s*(?:a música|o som|o clipe|de|do|da|no youtube)?\s*(.+)', lower_msg) or ("youtube" in lower_msg and len(lower_msg) > 7):
                    yt_match = re.search(r'(?:toca|tocar|coloque|coloca|tocar música|toca música|ouvir|reproduz|reproduzir|pesquisa no youtube|pesquise no youtube|youtube)\s*(?:a música|o som|o clipe|de|do|da|no youtube)?\s*(.+)', lower_msg)
                    q = yt_match.group(1) if yt_match else re.sub(r'youtube|pesquisa|coloca|toca|tocar', '', lower_msg).strip()
                    yt = hc.search_youtube_video(q)

                    if yt:
                        raw_reply = f"Iniciando reprodução de {yt['title']} no terminal holográfico, Senhor Werik."
                        widget = "youtube"
                        yt_payload = yt
                        broadcast_hud_event({
                            "action": "play_youtube",
                            "video_id": yt["video_id"],
                            "title": yt["title"],
                            "embed_url": yt["embed_url"]
                        })

                # 2. CONTROLE DE VOLUME DO WINDOWS (PYCAW)
                elif any(w in lower_msg for w in ["volume", "mutar", "silenciar", "desmutar", "mudo"]):
                    vol_num_match = re.search(r'(\d+)\s*%', lower_msg) or re.search(r'volume\s*(?:em|para|de)?\s*(\d+)', lower_msg)
                    if vol_num_match:
                        target_pct = int(vol_num_match.group(1))
                        res_vol = hc.set_windows_volume(target_pct)
                        raw_reply = f"Volume principal do sistema ajustado para {res_vol}%, Senhor Werik."
                    elif any(w in lower_msg for w in ["aumenta", "sobe", "mais alto"]):
                        res_vol = hc.change_windows_volume(+15)
                        raw_reply = f"Volume principal elevado para {res_vol}%, Senhor Werik."
                    elif any(w in lower_msg for w in ["abaixa", "diminui", "mais baixo"]):
                        res_vol = hc.change_windows_volume(-15)
                        raw_reply = f"Volume principal reduzido para {res_vol}%, Senhor Werik."
                    elif any(w in lower_msg for w in ["mutar", "mudo", "silenciar"]):
                        hc.mute_windows_volume(True)
                        raw_reply = "Áudio do sistema silenciado, Senhor Werik."
                    elif "desmutar" in lower_msg:
                        hc.mute_windows_volume(False)
                        raw_reply = "Áudio do sistema reativado, Senhor Werik."
                    else:
                        cur_vol = hc.get_windows_volume()
                        raw_reply = f"O volume atual do Windows está em {cur_vol}%, Senhor Werik."
                    widget = "custom"
                    broadcast_hud_event({
                        "action": "alert",
                        "title": "ÁUDIO DO WINDOWS",
                        "message": raw_reply,
                        "level": "sucesso"
                    })

                # 3. LANÇADOR DE APLICATIVOS WINDOWS
                elif re.search(r'(?:abre|abrir|inicia|iniciar|executa|executar|roda|rodar|lan[çc]a|lan[çc]ar)\s+(?:o|a)?\s*(vs\s*code|vscode|spotify|chrome|navegador|browser|calculadora|calc|notepad|bloco de notas|terminal|powershell|cmd|explorer|pastas|arquivos)', lower_msg):
                    app_match = re.search(r'(?:abre|abrir|inicia|iniciar|executa|executar|roda|rodar|lan[çc]a|lan[çc]ar)\s+(?:o|a)?\s*(.+)', lower_msg)
                    app_name = app_match.group(1).strip() if app_match else "app"
                    ok = hc.open_windows_app(app_name)
                    raw_reply = f"Iniciando {app_name} no ambiente Windows, Senhor Werik." if ok else f"Disparada ordem para iniciar {app_name}."
                    widget = "custom"
                    broadcast_hud_event({
                        "action": "alert",
                        "title": "WINDOWS APP LAUNCHER",
                        "message": raw_reply,
                        "level": "sucesso"
                    })

                # 4. CONTROLE DE MÍDIA GLOBAL (SPOTIFY / YOUTUBE / PLAYERS)
                elif win_bridge and any(w in lower_msg for w in ["pausar música", "pausa a música", "pausar musica", "pausa a musica", "pausar vídeo", "pausa o vídeo", "play/pause", "play pause", "pausar", "pausa"]):
                    win_bridge.media_play_pause()
                    raw_reply = "Comando de reprodução e pausa executado, Senhor Werik."
                    widget = "custom"
                    broadcast_hud_event({"action": "alert", "title": "CONTROLE DE MÍDIA", "message": raw_reply, "level": "sucesso"})

                elif win_bridge and any(w in lower_msg for w in ["próxima música", "proxima musica", "passa a música", "passa a musica", "pula a música", "pula a musica", "próxima faixa", "proxima faixa", "avançar música"]):
                    win_bridge.media_next()
                    raw_reply = "Avançando para a próxima faixa de áudio, Senhor Werik."
                    widget = "custom"
                    broadcast_hud_event({"action": "alert", "title": "MÍDIA // PRÓXIMA", "message": raw_reply, "level": "sucesso"})

                elif win_bridge and any(w in lower_msg for w in ["música anterior", "musica anterior", "volta a música", "volta a musica", "faixa anterior", "voltar música"]):
                    win_bridge.media_previous()
                    raw_reply = "Retornando para a faixa anterior, Senhor Werik."
                    widget = "custom"
                    broadcast_hud_event({"action": "alert", "title": "MÍDIA // ANTERIOR", "message": raw_reply, "level": "sucesso"})

                # 5. GERENCIAMENTO DE JANELAS E ÁREA DE TRABALHO
                elif win_bridge and any(w in lower_msg for w in ["minimizar tudo", "minimiza tudo", "mostrar área de trabalho", "mostra a área de trabalho", "limpar tela", "mostrar desktop"]):
                    win_bridge.minimize_all_windows()
                    raw_reply = "Todas as janelas minimizadas. Área de trabalho visível, Senhor Werik."
                    widget = "custom"
                    broadcast_hud_event({"action": "alert", "title": "ÁREA DE TRABALHO", "message": raw_reply, "level": "sucesso"})

                elif win_bridge and any(w in lower_msg for w in ["bloquear tela", "bloqueia a tela", "bloquear computador", "bloqueia o computador", "bloquear pc", "bloqueia o pc", "travar tela"]):
                    raw_reply = "Bloqueando a estação de trabalho imediatamente, Senhor Werik."
                    broadcast_hud_event({"action": "alert", "title": "SEGURANÇA", "message": raw_reply, "level": "aviso"})
                    threading.Thread(target=lambda: (time.sleep(0.5), win_bridge.lock_screen()), daemon=True).start()

                # CONTROLE DE ENERGIA DO WINDOWS (DESLIGAR, REINICIAR, CANCELAR, SUSPENDER)
                elif win_bridge and any(w in lower_msg for w in [
                    "desligar pc", "desligar o pc", "desligue o pc", "desligar computador",
                    "desligue o computador", "desligar a máquina", "desliga o pc", "desliga pc",
                    "encerrar o windows", "desligamento do sistema", "desligar máquina"
                ]):
                    is_immediate = any(w in lower_msg for w in ["agora", "já", "imediato", "imediatamente", "rápido"])
                    delay = 0 if is_immediate else 30
                    win_bridge.shutdown_pc(delay=delay)
                    if delay == 0:
                        raw_reply = "Desligando o computador imediatamente, Senhor Werik. Até logo."
                    else:
                        raw_reply = f"Iniciando protocolo de desligamento do Windows em {delay} segundos, Senhor Werik. Diga 'cancelar desligamento' se desejar abortar."
                    widget = "custom"
                    broadcast_hud_event({
                        "action": "alert",
                        "title": "DESLIGAMENTO DO SISTEMA",
                        "message": raw_reply,
                        "level": "aviso"
                    })
                    broadcast_hud_event({
                        "action": "canvas_projection",
                        "canvas": build_hardware_charts_canvas("sidebar")
                    })

                elif win_bridge and any(w in lower_msg for w in [
                    "cancelar desligamento", "cancela o desligamento", "cancela desligamento",
                    "abortar desligamento", "aborta o desligamento", "não desligar", "nao desliga",
                    "cancela o desligar", "cancelar desligar"
                ]):
                    win_bridge.abort_shutdown()
                    raw_reply = "Protocolo de desligamento cancelado com sucesso, Senhor Werik. O computador continuará ligado normalmente."
                    widget = "custom"
                    broadcast_hud_event({
                        "action": "alert",
                        "title": "DESLIGAMENTO CANCELADO",
                        "message": raw_reply,
                        "level": "sucesso"
                    })

                elif win_bridge and any(w in lower_msg for w in [
                    "reiniciar pc", "reiniciar o pc", "reinicie o pc", "reiniciar computador",
                    "reinicie o computador", "reinicia o pc", "reinicia pc"
                ]):
                    is_immediate = any(w in lower_msg for w in ["agora", "já", "imediato", "imediatamente"])
                    delay = 0 if is_immediate else 30
                    win_bridge.restart_pc(delay=delay)
                    raw_reply = f"Reinicialização agendada para daqui a {delay} segundos, Senhor Werik." if delay > 0 else "Reiniciando o sistema operacional imediatamente, Senhor Werik."
                    widget = "custom"
                    broadcast_hud_event({
                        "action": "alert",
                        "title": "REINICIALIZAÇÃO DO WINDOWS",
                        "message": raw_reply,
                        "level": "aviso"
                    })

                elif win_bridge and any(w in lower_msg for w in [
                    "suspender pc", "suspender o pc", "suspenda o pc", "suspender computador",
                    "modo suspensão", "modo soneca", "hibernar pc", "hibernar computador"
                ]):
                    raw_reply = "Colocando o sistema operacional em modo de suspensão, Senhor Werik."
                    widget = "custom"
                    broadcast_hud_event({
                        "action": "alert",
                        "title": "SUSPENSÃO DO WINDOWS",
                        "message": raw_reply,
                        "level": "info"
                    })
                    threading.Thread(target=lambda: (time.sleep(1.2), win_bridge.sleep_pc()), daemon=True).start()

                elif any(w in lower_msg for w in [
                    "gráfico", "grafico", "gráficos", "graficos", "telemetria de hardware",
                    "gráfico de gpu", "grafico de gpu", "gráfico do hardware", "grafico de cpu",
                    "canvas com gráfico", "canvas de gráfico"
                ]):
                    updated_canvas = build_hardware_charts_canvas("sidebar")
                    broadcast_hud_event({
                        "action": "canvas_projection",
                        "canvas": updated_canvas
                    })
                    raw_reply = "Gráficos de telemetria em tempo real da GPU GTX 1660 Ti e CPU projetados no seu Canvas, Senhor Werik."
                    widget = "custom"

                elif win_bridge and any(w in lower_msg for w in ["alternar janela", "alterna janela", "trocar janela", "troca de janela", "alt tab"]):
                    win_bridge.switch_window()
                    raw_reply = "Janela alternada com sucesso, Senhor Werik."
                    widget = "custom"

                elif win_bridge and any(w in lower_msg for w in ["abrir canvas", "abra o canvas", "abre o canvas", "janela canvas", "mostrar canvas", "mostre o canvas", "abrir janela canvas"]):
                    c_mode = "charts" if any(x in lower_msg for x in ["gráfico", "grafico", "hardware", "cpu", "gpu"]) else "reactor"
                    if any(x in lower_msg for x in ["visão", "visao", "mao", "mão"]):
                        c_mode = "vision"
                    elif any(x in lower_msg for x in ["radar"]):
                        c_mode = "radar"
                    elif "matrix" in lower_msg:
                        c_mode = "matrix"
                    win_bridge.open_canvas_window(c_mode)
                    broadcast_hud_event({
                        "action": "canvas_projection",
                        "canvas": build_hardware_charts_canvas("sidebar")
                    })
                    raw_reply = "Abrindo a janela Canvas holográfica de gráficos diretamente no seu monitor principal, Senhor Werik."
                    widget = "custom"
                    broadcast_hud_event({"action": "alert", "title": "CANVAS WINDOW", "message": raw_reply, "level": "sucesso"})

                elif any(w in lower_msg for w in ["ativar gestos", "ativa os gestos", "ligar gestos", "ativar visão", "ativar camera", "ligar camera"]):
                    vision_engine.enable_camera()
                    raw_reply = "Controle por gestos e visão computacional ativados com sucesso, Senhor Werik."
                    widget = "custom"
                    broadcast_hud_event({"action": "alert", "title": "VISÃO ATIVADA", "message": raw_reply, "level": "sucesso"})

                elif any(w in lower_msg for w in ["desativar gestos", "desativa os gestos", "desligar gestos", "desativar visão", "desligar camera", "parar gestos", "gestos desligar", "desative gestos"]):
                    vision_engine.disable_camera()
                    raw_reply = "Controle por gestos desativado e colocado em modo de espera, Senhor Werik."
                    widget = "custom"
                    broadcast_hud_event({"action": "alert", "title": "STANDBY", "message": raw_reply, "level": "aviso"})

                elif win_bridge and any(w in lower_msg for w in ["tirar print", "tira um print", "capturar tela", "captura a tela", "print da tela"]):
                    p = win_bridge.capture_screen()
                    raw_reply = f"Captura de tela realizada e salva no banco de dados, Senhor Werik."
                    widget = "custom"
                    broadcast_hud_event({"action": "alert", "title": "CAPTURA DE TELA", "message": raw_reply, "level": "sucesso"})

                # 6. CONTROLE DE MOUSE E ROLAGEM
                elif win_bridge and any(w in lower_msg for w in ["rolar para baixo", "rola para baixo", "descer a página", "desce a página", "scroll para baixo"]):
                    win_bridge.mouse_scroll(-350)
                    raw_reply = "Página rolada para baixo, Senhor Werik."
                    widget = "custom"

                elif win_bridge and any(w in lower_msg for w in ["rolar para cima", "rola para cima", "subir a página", "sobe a página", "scroll para cima"]):
                    win_bridge.mouse_scroll(350)
                    raw_reply = "Página rolada para cima, Senhor Werik."
                    widget = "custom"

                elif win_bridge and any(w in lower_msg for w in ["clique duplo", "dois cliques", "duplo clique"]):
                    win_bridge.mouse_click('left', clicks=2)
                    raw_reply = "Duplo clique executado na posição do mouse."
                    widget = "custom"

                elif win_bridge and any(w in lower_msg for w in ["clique direito", "botão direito", "clicar com o botão direito"]):
                    win_bridge.mouse_click('right')
                    raw_reply = "Clique com botão direito executado."
                    widget = "custom"

                elif win_bridge and any(w in lower_msg for w in ["clicar", "clica aqui", "clique esquerdo", "clica"]):
                    win_bridge.mouse_click('left')
                    raw_reply = "Clique do mouse executado."
                    widget = "custom"

                # 7. CONTROLE DE TECLADO
                elif win_bridge and re.search(r'(?:digite|digita|escreva|escrever)\s+(.+)', lower_msg):
                    m = re.search(r'(?:digite|digita|escreva|escrever)\s+(.+)', lower_msg)
                    text_to_type = m.group(1).strip()
                    win_bridge.type_text(text_to_type)
                    raw_reply = f"Texto digitado na janela ativa, Senhor Werik."
                    widget = "custom"

                elif win_bridge and any(w in lower_msg for w in ["pressionar enter", "aperta enter", "pressione enter", "dar enter", "dá enter"]):
                    win_bridge.press_key("enter")
                    raw_reply = "Tecla Enter acionada."
                    widget = "custom"

                elif win_bridge and any(w in lower_msg for w in ["pressionar esc", "aperta esc", "pressione esc"]):
                    win_bridge.press_key("escape")
                    raw_reply = "Tecla Escape acionada."
                    widget = "custom"

                # CONSULTAS, PROJEÇÕES E COMANDOS: CHAMA O NÚCLEO OPENCLAW COM CONTEXTO SISTEMA 1
                if raw_reply is None:
                    pre_call_time = time.time()
                    raw_reply = call_openclaw_jarvis(
                        user_msg,
                        intent_decision=jev_decision,
                        include_finance=self._perm_allowed(auth, "finance_view"),
                        auth_user=auth.get("user") if auth.get("source") == "session" else None,
                        auth_role=auth.get("role") if auth.get("source") == "session" else None,
                        source_device=src_device if src_kind == "esfera" else None
                    )
                    model_failed = raw_reply == OPENCLAW_MODEL_FAILURE_TOKEN
                    if model_failed:
                        raw_reply = "Modelo falhou."

                    # Extrai especificação de UI explícita (```json:visual ... ```) retornada pelo OpenClaw
                    if raw_reply and isinstance(raw_reply, str):
                        vis_match = re.search(r'```(?:json:visual|json)?\s*(\{[\s\S]*?"type"\s*:\s*"[\s\S]*?\})\s*```', raw_reply)
                        if vis_match:
                            try:
                                extracted_spec = json.loads(vis_match.group(1))
                                if extracted_spec and isinstance(extracted_spec, dict) and extracted_spec.get("type"):
                                    visual_spec = extracted_spec
                                    raw_reply = re.sub(r'```(?:json:visual|json)?\s*\{[\s\S]*?"type"\s*:\s*"[\s\S]*?\}\s*```', '', raw_reply).strip()
                                    if not raw_reply:
                                        raw_reply = f"Projetando {visual_spec.get('title', 'painel visual')} no seu HUD tático."
                            except Exception as ex_v:
                                print("[!] Aviso: Falha ao extrair json:visual da resposta:", ex_v)

                    # Garantia Visual: Se a resposta for sobre clima e não houver visual_spec, gera o spec meteorológico de 7 dias
                    if visual_spec is None and raw_reply and isinstance(raw_reply, str):
                        lower_combined = (user_msg + " " + raw_reply).lower()
                        if any(w in lower_combined for w in ["clima", "tempo", "previsão", "previsao", "chuva", "temperatura", "°c"]):
                            visual_spec = build_weather_ui_spec()

                    # Se um visual_spec explícito foi construído, emite o evento visual OS!
                    # Caso contrário, se nenhuma projeção MCP visual foi disparada pelo OpenClaw, projeta custom_card
                    if visual_spec:
                        widget = "visual"
                        broadcast_hud_event({
                            "action": "visual_spec",
                            "spec": visual_spec
                        })
                    elif last_hud_event_time < pre_call_time:
                        widget = "custom"
                        clean_reply_for_card = raw_reply.strip()
                        card_title = user_msg.strip().capitalize()
                        if len(card_title) > 38:
                            card_title = card_title[:35] + "..."
                        custom_card = {
                            "action": "custom_card",
                            "title": card_title.upper(),
                            "subtitle": "PAINEL DINÂMICO J.A.R.V.I.S.",
                            "content": clean_reply_for_card,
                            "card_type": "padrao",
                            "duration": 0
                        }
                        broadcast_hud_event(custom_card)
                    else:
                        widget = "canvas"

                # JEV Guard: Auditoria de Saída (Fidelidade Factual e Validação de Contrato)
                guard_result = jev_engine.guard(raw_reply, intent=jev_decision)
                if not guard_result.passed:
                    print(f"[JEV Guard] Alerta de auditoria: Violações encontradas: {guard_result.violations}")

                spoken_reply = clean_text_for_speech(guard_result.sanitized_text)
                audio_filename = f"response_{int(time.time())}.mp3"
                audio_path = os.path.join(DIRECTORY, audio_filename)
                
                for f in os.listdir(DIRECTORY):
                    if f.startswith("response_") and f.endswith(".mp3"):
                        try: os.remove(os.path.join(DIRECTORY, f))
                        except: pass

                asyncio.run(generate_speech(spoken_reply, audio_path))
                
                print(f"[HUD DISPATCH] User: '{user_msg}' | Target: '{widget}' | Agent: '{jev_decision.target_agent.upper()}' | Guard Score: {guard_result.audit_score}")
                    
                resp_payload = {
                    "reply": spoken_reply,
                    "model_failed": model_failed,
                    "audio_url": f"/{audio_filename}?t={int(time.time())}",
                    "target_widget": widget,
                    "visual": visual_spec,
                    "custom_card": custom_card,
                    "youtube": yt_payload,
                    "hardware": hw_payload,
                    "news": news_payload,
                    "digest": digest_payload,
                    "zima": zima_payload,
                    "canvas": canvas_payload,
                    "jev_system_one": jev_decision.to_dict(),
                    "jev_guard": guard_result.to_dict()
                }


            except Exception as e:
                resp_payload = {
                    "reply": f"Erro interno de processamento: {e}",
                    "audio_url": None,
                    "target_widget": "system"
                }

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(resp_payload).encode("utf-8"))
            return
            
        self.send_response(404)
        self.end_headers()

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.startswith("/api/memory"):
            data = None
            last_err = None
            for base_url in [os.environ.get("MEMORY_PRIMARY_URL", "${ZIMA_ROUTER_URL:-http://127.0.0.1:8095}"), "http://127.0.0.1:8090"]:
                try:
                    mem_url = f"{base_url}{self.path}"
                    req = urllib.request.Request(mem_url, method="DELETE")
                    with urllib.request.urlopen(req, timeout=3) as resp:
                        data = resp.read()
                        break
                except Exception as em:
                    last_err = em
            if data is not None:
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)
                return
            else:
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"error": f"Erro proxy memória DELETE: {last_err}"}).encode('utf-8'))
                return
        self.send_response(404)
        self.end_headers()

def zima_live_stream_worker():
    print("[*] Worker de telemetria ZimaOS & Visão Computacional ativo.")
    step = 0
    while True:
        try:
            with sse_lock:
                active_subs = len(sse_subscribers)
            if active_subs > 0:
                metrics = get_zima_metrics(force=True)
                broadcast_hud_event({
                    "action": "zima_telemetry",
                    "zima": metrics
                })
                # Telemetria periódica do motor de visão
                try:
                    broadcast_hud_event({
                        "action": "vision_telemetry",
                        "vision": vision_engine.get_status()
                    })
                except Exception:
                    pass

                step += 1
                if step % 2 == 0:
                    hw = hc.get_hardware_telemetry()
                    broadcast_hud_event({
                        "action": "hardware_telemetry",
                        "metrics": hw
                    })
        except Exception:
            pass
        time.sleep(2.0)

class EnrollmentRequestHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Enroll-Key")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path in ["", "/", "/enroll", "/enroll.html"]:
            enroll_path = os.path.join(DIRECTORY, "web", "enroll.html")
            if os.path.exists(enroll_path):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_cors_headers()
                self.end_headers()
                with open(enroll_path, "r", encoding="utf-8") as f:
                    self.wfile.write(f.read().encode("utf-8"))
            else:
                self.send_response(404)
                self.end_headers()
            return

        if parsed.path == "/api/enroll/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({"enabled": biometrics.is_portal_enabled()}).encode("utf-8"))
            return

        if parsed.path == "/api/enroll/profiles":
            if not biometrics.is_portal_enabled():
                self.send_response(403)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({"error": "PORTAL_DISABLED"}).encode("utf-8"))
                return

            key = self.headers.get("X-Enroll-Key", "")
            if not biometrics.verify_enrollment_password(key):
                self.send_response(401)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({"error": "UNAUTHORIZED_INVALID_ENROLL_KEY"}).encode("utf-8"))
                return

            profs = biometrics.get_registered_profiles()
            summary = [
                {"id": p.get("id"), "name": p.get("name"), "role": p.get("role", "Operador"), "registered_at": p.get("registered_at")}
                for p in profs
            ]
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({"profiles": summary}).encode("utf-8"))
            return

        # Static files (face-api models, icons)
        if parsed.path.startswith("/models/") or parsed.path in ["/icon-512.png", "/icon-192.png"]:
            rel = parsed.path.lstrip("/")
            fp = os.path.join(DIRECTORY, rel)
            if os.path.exists(fp) and os.path.isfile(fp):
                self.send_response(200)
                ct = "application/octet-stream"
                if fp.endswith(".js"): ct = "application/javascript"
                elif fp.endswith(".json"): ct = "application/json"
                elif fp.endswith(".png"): ct = "image/png"
                self.send_header("Content-Type", ct)
                self.send_header("Cache-Control", "public, max-age=86400")
                self.send_cors_headers()
                self.end_headers()
                with open(fp, "rb") as f:
                    self.wfile.write(f.read())
                return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        content_length = int(self.headers.get('Content-Length', 0))
        raw_bytes = self.rfile.read(content_length)

        data = {}
        try:
            data = json.loads(raw_bytes.decode('utf-8'))
        except Exception:
            pass

        if parsed.path == "/api/enroll/auth":
            if not biometrics.is_portal_enabled():
                self.send_response(403)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({"authenticated": False, "reason": "PORTAL_DISABLED"}).encode("utf-8"))
                return

            pwd = str(data.get("password", "")).strip()
            is_valid = biometrics.verify_enrollment_password(pwd)
            self.send_response(200 if is_valid else 401)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({"authenticated": is_valid}).encode("utf-8"))
            return

        if parsed.path == "/api/enroll/register":
            if not biometrics.is_portal_enabled():
                self.send_response(403)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "error": "PORTAL_DISABLED"}).encode("utf-8"))
                return

            key = self.headers.get("X-Enroll-Key", "")
            if not biometrics.verify_enrollment_password(key):
                self.send_response(401)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({"success": False, "error": "UNAUTHORIZED"}).encode("utf-8"))
                return

            name = data.get("name", "Operador")
            role = data.get("role", "Operador Autorizado")
            descriptor = data.get("descriptor")
            res = biometrics.register_face_profile(name, role, descriptor)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))
            return

        if parsed.path == "/api/enroll/delete":
            if not biometrics.is_portal_enabled():
                self.send_response(403)
                self.send_cors_headers()
                self.end_headers()
                return

            key = self.headers.get("X-Enroll-Key", "")
            if not biometrics.verify_enrollment_password(key):
                self.send_response(401)
                self.send_cors_headers()
                self.end_headers()
                return

            prof_id = data.get("id")
            ok = biometrics.delete_face_profile(prof_id)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({"success": ok}).encode("utf-8"))
            return

        if parsed.path == "/api/enroll/toggle":
            key = self.headers.get("X-Enroll-Key", "")
            if not biometrics.verify_enrollment_password(key):
                self.send_response(401)
                self.send_cors_headers()
                self.end_headers()
                return

            enabled = bool(data.get("enabled", True))
            biometrics.set_portal_enabled(enabled)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "enabled": enabled}).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True

def run_enrollment_server():
    try:
        e_port = biometrics.ENROLLMENT_PORT
        with ThreadedTCPServer(("", e_port), EnrollmentRequestHandler) as enroll_httpd:
            print(f"[+] Portal de Cadastro Facial ativo em http://localhost:{e_port} (Chave 12D: ***)")
            enroll_httpd.serve_forever()
    except Exception as e:
        print(f"[!] Erro ao iniciar Portal de Cadastro Facial: {e}")

def run_xiaozhi_websocket_server():
    """Ponte WSS da esfera: áudio protegido, transcrição em memória e resposta falada."""
    try:
        import asyncio
        import io
        import wave
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from sphere_audio_bridge import serve_sphere_audio
        from sphere_voice import (
            classify_fast_command,
            create_audio_turn_gate,
            parse_alarm_time,
            parse_timer_seconds,
            strip_wake_word,
        )

        sessions = {}

        def _pcm_wav(pcm):
            buffer = io.BytesIO()
            with wave.open(buffer, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(16000)
                wav_file.writeframes(pcm)
            return buffer.getvalue()

        def _transcribe_pcm(pcm):
            # Mantém a fala em RAM. Não grava áudio da esfera em arquivo.
            # 1) Nuvem via 9router (Groq whisper-large-v3-turbo, ~0.5s) — o Core chama o provedor.
            try:
                _t0 = time.time()
                _txt = _transcribe_via_router(_pcm_wav(pcm), "audio/wav", "pt")
                if _txt:
                    print(f"[ESFERA STT] nuvem ({os.environ.get('SPHERE_STT_MODEL', 'groq/whisper-large-v3-turbo')}) em {time.time()-_t0:.2f}s")
                    return _txt
            except Exception as exc:
                print(f"[ESFERA STT] nuvem indisponível ({type(exc).__name__}); usando local.")
            if whisper_model is not None:
                samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
                segments, _ = whisper_model.transcribe(
                    samples,
                    language="pt",
                    beam_size=1,
                    best_of=1,
                    vad_filter=False,
                    condition_on_previous_text=False,
                    initial_prompt="Comando de voz em português brasileiro para o J.A.R.V.I.S.",
                )
                return " ".join(segment.text.strip() for segment in segments).strip()
            return _transcribe_via_container(_pcm_wav(pcm), "audio/wav", "pt")

        def _fast_command(command):
            kind = classify_fast_command(command)
            if kind == "time":
                now = datetime.now(ZoneInfo("America/Sao_Paulo"))
                if now.minute:
                    return f"Agora são {now.hour:02d} horas e {now.minute:02d} minutos.", None
                return f"Agora são {now.hour} horas.", None
            if kind == "weather":
                weather = get_catanduva_weather()
                return (
                    f"Em Catanduva, agora são {round(weather.get('temperature', 0))} graus, "
                    f"com {str(weather.get('condition', 'tempo estável')).lower()}. "
                    f"Umidade em {weather.get('humidity', '--')} por cento.",
                    None,
                )
            if kind == "timer":
                seconds = parse_timer_seconds(command)
                if not seconds:
                    return "Por quanto tempo devo iniciar o timer?", None
                minutes, remaining = divmod(seconds, 60)
                duration = f"{minutes} minuto(s)" if minutes else f"{remaining} segundo(s)"
                if minutes and remaining:
                    duration += f" e {remaining} segundo(s)"
                event = {"type": "custom", "payload": {"event": "jarvis.timer", "seconds": seconds, "label": "TIMER"}}
                return f"Timer iniciado para {duration}.", event
            if kind == "alarm":
                alarm = parse_alarm_time(command)
                if alarm is None:
                    return "Para que horas devo programar o alarme?", None
                hour, minute = alarm
                event = {"type": "custom", "payload": {"event": "jarvis.alarm", "hour": hour, "minute": minute, "label": "ALARME"}}
                return f"Alarme programado para {hour:02d} e {minute:02d}.", event
            return None

        def _stream_worker(command, device_id, output):
            base = os.environ.get("SPHERE_OPENCLAW_STREAM_URL", "").strip().rstrip("/")
            token = os.environ.get("SPHERE_OPENCLAW_STREAM_TOKEN", "").strip()
            if not base or not token:
                output.put(("error", "stream não configurado"))
                return
            endpoint = base if base.endswith("/chat/completions") else (
                base + "/chat/completions" if base.endswith("/v1") else base + "/v1/chat/completions"
            )
            payload = {
                "model": os.environ.get("SPHERE_OPENCLAW_MODEL", "openclaw/default"),
                "user": f"conv:jarvis-sphere:{device_id}",
                "stream": True,
                "messages": [{"role": "user", "content": f"[JARVIS | ORIGEM: ESFERA]\n{command}"}],
            }
            request = urllib.request.Request(
                endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "text/event-stream"},
            )
            try:
                with urllib.request.urlopen(request, timeout=120) as response:
                    for raw_line in response:
                        line = raw_line.decode("utf-8", errors="replace").strip()
                        if not line.startswith("data:"):
                            continue
                        item = line[5:].strip()
                        if item == "[DONE]":
                            break
                        event = json.loads(item)
                        if event.get("error"):
                            raise RuntimeError("stream OpenClaw inválido")
                        choices = event.get("choices") or []
                        if choices:
                            content = (choices[0].get("delta") or {}).get("content", "")
                            if isinstance(content, list):
                                content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
                            if content:
                                output.put(("delta", str(content)))
                output.put(("done", None))
            except Exception as exc:
                output.put(("error", type(exc).__name__))

        async def _status(websocket, state):
            await websocket.send(json.dumps({"type": "jarvis.status", "state": state}, ensure_ascii=False))

        async def _speak(websocket, text, announce=True):
            sent = 0
            total = 0
            try:
                clean = clean_text_for_speech(text)
                if not clean:
                    return False
                pcm_path = await asyncio.to_thread(get_or_generate_tts_pcm, clean)
                if not pcm_path or not os.path.isfile(pcm_path):
                    return False
                with open(pcm_path, "rb") as pcm_file:
                    pcm = pcm_file.read()
                if len(pcm) < 1000:
                    return False
                total = len(pcm)
                if announce:
                    await websocket.send(json.dumps({"type": "tts", "state": "start"}))
                # PACING ~TEMPO REAL: 640B = 20ms de áudio por ~19ms de espera.
                # Enviar mais rápido que o playback (era 16ms) enche o buffer TCP/TLS
                # da esfera (~98KB) e o socket morre no meio do TTS (close 1006).
                for offset in range(0, len(pcm), 640):  # 20 ms, 16 kHz mono s16le
                    frame = pcm[offset:offset + 640]
                    if len(frame) % 2:
                        frame = frame[:-1]
                    if frame:
                        await websocket.send(frame)
                        sent += len(frame)
                        await asyncio.sleep(0.019)
                return True
            except Exception as exc:
                print(f"[ESFERA] TTS interrompido em {sent}/{total} bytes ({type(exc).__name__}).")
                return False

        async def _stream_reply(websocket, command, device_id):
            output = queue.Queue()
            threading.Thread(
                target=_stream_worker,
                args=(command, device_id, output),
                daemon=True,
                name="sphere-openclaw-stream",
            ).start()
            pending = ""
            full_text = []
            speaking = False
            while True:
                kind, value = await asyncio.to_thread(output.get)
                if kind == "error":
                    if speaking:
                        await websocket.send(json.dumps({"type": "tts", "state": "stop"}))
                    return OPENCLAW_MODEL_FAILURE_TOKEN
                if kind == "done":
                    break
                pending += value
                full_text.append(value)
                while True:
                    match = re.search(r"[.!?][\"'’”)]*\s+", pending)
                    if not match:
                        break
                    sentence = pending[:match.end()].strip()
                    pending = pending[match.end():]
                    if sentence and await _speak(websocket, sentence, announce=not speaking):
                        speaking = True
            if pending.strip() and await _speak(websocket, pending.strip(), announce=not speaking):
                speaking = True
            if speaking:
                await websocket.send(json.dumps({"type": "tts", "state": "stop"}))
            return " ".join(full_text).strip()

        async def _handle_utterance(websocket, gate, audio, device_id):
            _t_vad = time.time()
            await _status(websocket, "transcribing")
            try:
                transcript = await asyncio.to_thread(_transcribe_pcm, audio)
            except Exception as exc:
                print(f"[ESFERA] STT indisponível ({type(exc).__name__}).")
                if await _speak(websocket, "Não consegui entender o áudio. Tente novamente."):
                    await websocket.send(json.dumps({"type": "tts", "state": "stop"}))
                await _status(websocket, "idle")
                return
            _t_stt = time.time()
            if not transcript:
                await _status(websocket, "idle")
                return
            command, wake_only = strip_wake_word(transcript)
            print(f"[ESFERA STT] texto: {transcript!r} ({len(transcript)} chars); comando: {command!r}")
            if wake_only:
                gate.extend_conversation()
                await _status(websocket, "listening")
                return
            if not command:
                await _status(websocket, "listening")
                return
            if len(command.strip()) < 3:
                # Fragmento/ruído (ex.: eco de 1 char): ignora sem gastar agente.
                await _status(websocket, "listening")
                return

            await _status(websocket, "sending")
            fast = await asyncio.to_thread(_fast_command, command)
            if fast is not None:
                reply, event = fast
                if event:
                    await websocket.send(json.dumps(event, ensure_ascii=False))
                if await _speak(websocket, reply):
                    await websocket.send(json.dumps({"type": "tts", "state": "stop"}))
                gate.extend_conversation()
                await _status(websocket, "success")
                return

            await _status(websocket, "thinking")
            # ACK IMEDIATO: resposta curta enquanto o agente pensa (sem eventos tts
            # start/stop para não piscar o rosto — o reply real anuncia o próprio).
            try:
                await _speak(websocket, "Senhor.", announce=False)
            except Exception:
                pass
            _t_ack = time.time()
            stream_url = os.environ.get("SPHERE_OPENCLAW_STREAM_URL", "").strip()
            stream_token = os.environ.get("SPHERE_OPENCLAW_STREAM_TOKEN", "").strip()
            if stream_url and stream_token:
                reply = await _stream_reply(websocket, command, device_id)
            else:
                reply = await asyncio.to_thread(
                    call_openclaw_jarvis,
                    command,
                    auth_user=None,
                    auth_role=None,
                    source_device=device_id,
                    source_authenticated=True,
                )
            _t_agent = time.time()
            if not reply or reply == OPENCLAW_MODEL_FAILURE_TOKEN:
                await _status(websocket, "error")
                if await _speak(websocket, "O modelo falhou. Voltando à tela inicial."):
                    await websocket.send(json.dumps({"type": "tts", "state": "stop"}))
                await _status(websocket, "idle")
                return
            if not (stream_url and stream_token):
                if await _speak(websocket, reply):
                    await websocket.send(json.dumps({"type": "tts", "state": "stop"}))
            gate.extend_conversation()
            await _status(websocket, "success")
            print(
                f"[ESFERA TEMPOS] vad→stt={_t_stt-_t_vad:.2f}s | stt→ack={_t_ack-_t_stt:.2f}s | "
                f"agente={_t_agent-_t_ack:.2f}s | até resposta={_t_agent-_t_vad:.2f}s (device={device_id})"
            )

        _audio_diag = {"n": 0, "last": 0.0}

        async def _on_audio(device_id, pcm, websocket):
            _audio_diag["n"] += 1
            if time.time() - _audio_diag["last"] >= 5.0:
                print(f"[ESFERA DIAG] áudio chegando: {_audio_diag['n']} frames nos últimos 5s (device={device_id})")
                _audio_diag["n"] = 0
                _audio_diag["last"] = time.time()
            # Gate por DEVICE (não por socket): uma queda de conexão (1006) não perde
            # o contexto de fala — o gate sobrevive à reconexão da esfera.
            key = device_id or id(websocket)
            gate = sessions.get(key)
            if gate is None:
                gate = await asyncio.to_thread(create_audio_turn_gate, DIRECTORY)
                sessions[key] = gate
            for event in await asyncio.to_thread(gate.feed, pcm):
                if event.kind == "wake":
                    await websocket.send(json.dumps({"type": "wakeup", "score": round(event.score, 3)}))
                    await _status(websocket, "listening")
                elif event.kind == "utterance":
                    await _handle_utterance(websocket, gate, event.audio, device_id)
                elif event.kind == "idle":
                    await _status(websocket, "idle")

        def _on_disconnect(_device_id, websocket):
            # Gate por device: mantém o gate na reconexão (não descarta por socket).
            pass

        async def _async_start():
            await serve_sphere_audio(_on_audio, _on_disconnect)

        asyncio.run(_async_start())
    except Exception as e:
        print(f"[!] Erro no Servidor Xiaozhi WebSocket: {e}")

if __name__ == "__main__":
    # Inicia motor de visão computacional local
    try:
        vision_engine.start()
        print("[+] Motor de Visão Computacional J.A.R.V.I.S. pronto.")
    except Exception as e:
        print(f"[!] Erro ao inicializar Visão Computacional: {e}")

    t_worker = threading.Thread(target=zima_live_stream_worker, daemon=True)
    t_worker.start()

    t_enroll = threading.Thread(target=run_enrollment_server, daemon=True)
    t_enroll.start()

    t_xiaozhi = threading.Thread(target=run_xiaozhi_websocket_server, daemon=True)
    t_xiaozhi.start()

    # Pré-aquece o TTS do ack imediato da esfera ("Senhor.") fora do caminho crítico
    def _warm_ack_tts():
        try:
            get_or_generate_tts_pcm("Senhor.")
            print("[+] TTS de ack ('Senhor.') pré-aquecido.")
        except Exception:
            pass
    threading.Thread(target=_warm_ack_tts, daemon=True, name="tts-ack-warm").start()

    with ThreadedTCPServer(("", PORT), JarvisRequestHandler) as httpd:
        print(f"[*] J.A.R.V.I.S. Core Server ativo em http://localhost:{PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[*] Servidor encerrado.")
            try:
                vision_engine.stop()
            except Exception:
                pass
