"""
Jarvis Desktop - Command Bus & Windows Execution Layer
Camada que executa ações locais no Windows solicitadas remotamente pelo OpenClaw:
- Controle de Janelas (get_active_window, list_windows, focus, minimize, close)
- Aplicativos (open, close, restart, list)
- Teclado & Mouse (press_key, hotkey, type_text, move, click, scroll)
- Área de Transferência (get, set)
- Sistema & Captura de Tela (screenshot, multi-monitor, volume, mute)
- Validação e Classificação de Segurança (LOW, MEDIUM, HIGH)
"""

import os
import sys
import json
import time
import subprocess
import threading
from typing import Dict, Any, List, Optional
import pyautogui
import psutil
import win32gui
import win32process
import win32con
import pyperclip

import hardware_control as hc

# Configurações de segurança padrão do PyAutoGUI
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05

# Impede o flash do console preto em chamadas shell (processo é GUI/windowless)
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

# Permissões do nó (Central de Controle): arquivo vivo compartilhado com o server local
if getattr(sys, "frozen", False):
    # Pack com 2 exes: JarvisDesktop\..\JarvisServer\ -> raiz do pack
    _perm_base = os.path.normpath(os.path.join(os.path.dirname(sys.executable), ".."))
else:
    _perm_base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE_PERM_FILE = os.path.join(_perm_base, "config", "node_permissions.json")

PERM_CATEGORIES = {
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
    "power": "Desligar/Reiniciar/Suspender",
    "web_automation": "Automação Web (Puppeteer / Playwright)"
}

PERM_ACTION_MAP = {
    "screen.snapshot": "screen_capture",
    "screen.list_monitors": "screen_capture",
    "keyboard.press_key": "keyboard_mouse",
    "keyboard.press_hotkey": "keyboard_mouse",
    "keyboard.type_text": "keyboard_mouse",
    "mouse.get_position": "keyboard_mouse",
    "mouse.move": "keyboard_mouse",
    "mouse.click": "keyboard_mouse",
    "mouse.double_click": "keyboard_mouse",
    "mouse.right_click": "keyboard_mouse",
    "mouse.scroll": "keyboard_mouse",
    "clipboard.get": "clipboard",
    "clipboard.set": "clipboard",
    "application.open": "apps",
    "windows.open_application": "apps",
    "application.close": "apps",
    "windows.close_application": "apps",
    "windows.focus_window": "windows_mgmt",
    "windows.minimize_window": "windows_mgmt",
    "windows.maximize_window": "windows_mgmt",
    "windows.close_window": "windows_mgmt",
    "media.play_pause": "media",
    "media.next": "media",
    "media.prev": "media",
    "audio.volume_up": "media",
    "audio.volume_down": "media",
    "audio.set_volume": "media",
    "audio.mute": "media",
    "system.info": "telemetry",
    "windows.get_active_window": "telemetry",
    "windows.list_windows": "telemetry",
    "application.list": "telemetry",
    "system.run": "system_commands",
    "browser.puppeteer_navigate": "web_automation",
    "browser.puppeteer_screenshot": "web_automation",
    "browser.puppeteer_interact": "web_automation"
}

def load_node_permissions(default_if_missing=True) -> dict:
    try:
        if os.path.exists(NODE_PERM_FILE):
            with open(NODE_PERM_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    if not default_if_missing:
        return {}
    return {k: True for k in PERM_CATEGORIES}

class SecurityLevel:
    LOW = "low"        # Volume, mídia, consulta status, abrir apps padrão
    MEDIUM = "medium"  # Teclado, mouse, digitação, clipboard
    HIGH = "high"      # Comandos cmd/powershell, apagar arquivos, matar processos de sistema

class CommandBus:
    def __init__(self, config=None, event_bus=None):
        self.config = config
        self.event_bus = event_bus
        self.pending_confirmations: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def execute(self, command_name: str, args: Dict[str, Any] = None, origin: str = "openclaw", confirmed: bool = False) -> Dict[str, Any]:
        if args is None:
            args = {}
        cmd = command_name.lower().strip()

        # 0. Política de bloqueio absoluto do nó (blocked_commands na configuração)
        blocked = []
        if self.config:
            try:
                blocked = [str(b).lower() for b in (self.config.get("security", "blocked_commands", default=[]) or [])]
            except Exception:
                blocked = []
        if blocked:
            args_str = json.dumps(args).lower() if args else ""
            if any(b and (b in cmd or b in args_str) for b in blocked):
                if self.event_bus:
                    self.event_bus.emit("command.blocked", {
                        "command": cmd,
                        "args": args,
                        "origin": origin
                    })
                return {
                    "success": False,
                    "status": "blocked_by_policy",
                    "command": cmd,
                    "message": f"Comando '{cmd}' bloqueado pela política de segurança do nó (blocked_commands)."
                }

        # 1. GATE DE PERMISSÕES DO NÓ (Central de Controle)
        category = PERM_ACTION_MAP.get(cmd, "")
        if not category and cmd == "system.run":
            args_str_low = json.dumps(args).lower() if args else ""
            if any(w in args_str_low for w in ["shutdown ", "/s", "/r", "rundll32", "logoff"]):
                category = "power"
        if not category and cmd.startswith("system."):
            category = "system_commands"
        perms = load_node_permissions()
        if category and perms.get(category, True) is False:
            if self.event_bus:
                self.event_bus.emit("command.denied", {
                    "command": cmd,
                    "category": category,
                    "origin": origin
                })
            return {
                "success": False,
                "status": "permission_denied",
                "permission": category,
                "command": cmd,
                "message": f"Comando '{cmd}' bloqueado: a permissão '{PERM_CATEGORIES.get(category, category)}' está DESATIVADA nesta máquina (Central de Controle do Nó)."
            }

        # 1.1 Classificação de Segurança
        risk = self._classify_risk(cmd, args)
        if risk == SecurityLevel.HIGH and not confirmed:
            # Nó com acesso total configurado: executa alto risco sem confirmação
            auto_confirm = bool(self.config and self.config.get("security", "auto_confirm_high_risk", default=False))
            if auto_confirm:
                print(f"[CommandBus] Alto risco '{cmd}' executado direto (auto_confirm_high_risk=True neste nó).")
            else:
                req_id = f"confirm_{int(time.time()*1000)}"
                with self._lock:
                    self.pending_confirmations[req_id] = {
                        "command": cmd,
                        "args": args,
                        "created_at": time.time()
                    }
                if self.event_bus:
                    self.event_bus.emit("security.confirmation_needed", {
                        "confirmation_id": req_id,
                        "command": cmd,
                        "args": args,
                        "message": f"O comando '{cmd}' requer confirmação explícita de segurança."
                    })
                return {
                    "success": False,
                    "status": "requires_confirmation",
                    "confirmation_id": req_id,
                    "message": f"Comando de alto risco '{cmd}' bloqueado. Confirmação do usuário necessária."
                }

        # 2. Roteamento de Comandos
        try:
            handler = self._get_handler(cmd)
            if not handler:
                return {
                    "success": False,
                    "status": "unknown_command",
                    "command": cmd,
                    "message": f"Comando desconhecido: '{cmd}'"
                }

            result = handler(args)
            if self.event_bus:
                self.event_bus.emit("command.executed", {
                    "command": cmd,
                    "args": args,
                    "success": result.get("success", True),
                    "origin": origin
                })
            return result

        except Exception as e:
            err_msg = str(e)
            print(f"[CommandBus] Erro ao executar '{cmd}': {err_msg}")
            if self.event_bus:
                self.event_bus.emit("command.failed", {
                    "command": cmd,
                    "args": args,
                    "error": err_msg
                })
            return {
                "success": False,
                "status": "error",
                "command": cmd,
                "error": err_msg
            }

    def _classify_risk(self, cmd: str, args: dict) -> str:
        # Alto Risco
        if any(h in cmd for h in ["system.run", "exec", "powershell", "cmd", "delete", "format", "kill_system"]):
            return SecurityLevel.HIGH
        # Médio Risco
        if any(m in cmd for m in ["keyboard.", "mouse.", "clipboard.set", "window.close", "application.close"]):
            return SecurityLevel.MEDIUM
        # Baixo Risco
        return SecurityLevel.LOW

    def _get_handler(self, cmd: str):
        handlers = {
            # Janelas & Aplicações
            "windows.get_active_window": self.cmd_get_active_window,
            "windows.list_windows": self.cmd_list_windows,
            "windows.focus_window": self.cmd_focus_window,
            "windows.minimize_window": self.cmd_minimize_window,
            "windows.maximize_window": self.cmd_maximize_window,
            "windows.close_window": self.cmd_close_window,
            "application.open": self.cmd_open_app,
            "windows.open_application": self.cmd_open_app,
            "application.close": self.cmd_close_app,
            "windows.close_application": self.cmd_close_app,
            "application.list": self.cmd_list_apps,

            # Teclado & Mouse
            "keyboard.press_key": self.cmd_press_key,
            "keyboard.press_hotkey": self.cmd_press_hotkey,
            "keyboard.type_text": self.cmd_type_text,
            "mouse.get_position": self.cmd_mouse_get_pos,
            "mouse.move": self.cmd_mouse_move,
            "mouse.click": self.cmd_mouse_click,
            "mouse.double_click": self.cmd_mouse_double_click,
            "mouse.right_click": self.cmd_mouse_right_click,
            "mouse.scroll": self.cmd_mouse_scroll,

            # Clipboard
            "clipboard.get": self.cmd_clipboard_get,
            "clipboard.set": self.cmd_clipboard_set,

            # Áudio & Mídia
            "audio.volume_up": lambda a: {"success": True, "volume": hc.change_windows_volume(+10)},
            "audio.volume_down": lambda a: {"success": True, "volume": hc.change_windows_volume(-10)},
            "audio.set_volume": lambda a: {"success": True, "volume": hc.set_windows_volume(a.get("percent", 50))},
            "audio.mute": lambda a: {"success": True, "muted": hc.mute_windows_volume(a.get("mute", True))},
            "media.play_pause": self.cmd_media_playpause,
            "media.next": self.cmd_media_next,
            "media.prev": self.cmd_media_prev,

            # Captura de Tela
            "screen.snapshot": self.cmd_screen_snapshot,
            "screen.list_monitors": self.cmd_screen_list_monitors,

            # Sistema & Telemetria
            "system.info": self.cmd_system_info,
            "system.notify": self.cmd_system_notify,
            "system.run": self.cmd_system_run,

            # Automação Web (Puppeteer / Playwright)
            "browser.puppeteer_navigate": self.cmd_puppeteer_navigate,
            "browser.puppeteer_screenshot": self.cmd_puppeteer_screenshot,
            "browser.puppeteer_interact": self.cmd_puppeteer_interact,
        }
        return handlers.get(cmd)

    # -------------------------------------------------------------
    # IMPLEMENTAÇÃO DAS AÇÕES NATIVAS DO WINDOWS
    # -------------------------------------------------------------

    def cmd_get_active_window(self, args: dict) -> dict:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return {"success": True, "window": None}
        title = win32gui.GetWindowText(hwnd)
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        proc_name = ""
        try:
            proc_name = psutil.Process(pid).name()
        except Exception:
            pass
        return {
            "success": True,
            "window": {
                "hwnd": hwnd,
                "title": title,
                "process_id": pid,
                "application": proc_name
            }
        }

    def cmd_list_windows(self, args: dict) -> dict:
        windows = []
        def enum_cb(hwnd, extra):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title and len(title.strip()) > 1:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    p_name = ""
                    try:
                        p_name = psutil.Process(pid).name()
                    except Exception:
                        pass
                    windows.append({
                        "hwnd": hwnd,
                        "title": title,
                        "application": p_name,
                        "process_id": pid
                    })
        win32gui.EnumWindows(enum_cb, None)
        return {"success": True, "windows": windows[:30]}

    def cmd_focus_window(self, args: dict) -> dict:
        hwnd = args.get("hwnd")
        title_sub = args.get("title", "").lower()
        if not hwnd and title_sub:
            def enum_cb(h, extra):
                if win32gui.IsWindowVisible(h):
                    t = win32gui.GetWindowText(h)
                    if title_sub in t.lower():
                        extra.append(h)
            found = []
            win32gui.EnumWindows(enum_cb, found)
            if found:
                hwnd = found[0]

        if hwnd:
            try:
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(hwnd)
                return {"success": True, "hwnd": hwnd}
            except Exception as e:
                return {"success": False, "error": str(e)}
        return {"success": False, "message": "Janela não encontrada."}

    def cmd_minimize_window(self, args: dict) -> dict:
        hwnd = args.get("hwnd") or win32gui.GetForegroundWindow()
        if hwnd:
            win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
            return {"success": True, "hwnd": hwnd}
        return {"success": False, "message": "Janela inválida."}

    def cmd_maximize_window(self, args: dict) -> dict:
        hwnd = args.get("hwnd") or win32gui.GetForegroundWindow()
        if hwnd:
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
            return {"success": True, "hwnd": hwnd}
        return {"success": False, "message": "Janela inválida."}

    def cmd_close_window(self, args: dict) -> dict:
        hwnd = args.get("hwnd") or win32gui.GetForegroundWindow()
        if hwnd:
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            return {"success": True, "hwnd": hwnd}
        return {"success": False, "message": "Janela inválida."}

    def cmd_open_app(self, args: dict) -> dict:
        app_name = args.get("application") or args.get("app") or args.get("name", "")
        if not app_name:
            return {"success": False, "message": "Nome do aplicativo ausente."}
        ok = hc.open_windows_app(app_name)
        return {"success": ok, "application": app_name}

    def cmd_close_app(self, args: dict) -> dict:
        app_name = args.get("application", "").lower()
        closed = []
        for p in psutil.process_iter(['name', 'pid']):
            try:
                if app_name in p.info['name'].lower():
                    p.terminate()
                    closed.append(p.info['name'])
            except Exception:
                pass
        return {"success": len(closed) > 0, "closed": closed}

    def cmd_list_apps(self, args: dict) -> dict:
        apps = []
        for p in psutil.process_iter(['name', 'pid', 'cpu_percent', 'memory_percent']):
            try:
                if p.info['cpu_percent'] is not None and p.info['cpu_percent'] > 0.05:
                    apps.append(p.info)
            except Exception:
                pass
        return {"success": True, "running_apps": apps[:20]}

    def cmd_press_key(self, args: dict) -> dict:
        key = args.get("key", "")
        if key:
            pyautogui.press(key)
            return {"success": True, "key": key}
        return {"success": False, "message": "Tecla ausente."}

    def cmd_press_hotkey(self, args: dict) -> dict:
        keys = args.get("keys", [])
        if isinstance(keys, str):
            keys = [k.strip() for k in keys.split("+")]
        if keys:
            pyautogui.hotkey(*keys)
            return {"success": True, "keys": keys}
        return {"success": False, "message": "Teclas ausentes."}

    def cmd_type_text(self, args: dict) -> dict:
        text = args.get("text", "")
        interval = args.get("interval", 0.02)
        if text:
            pyautogui.write(text, interval=interval)
            return {"success": True, "length": len(text)}
        return {"success": False, "message": "Texto ausente."}

    def cmd_mouse_get_pos(self, args: dict) -> dict:
        pos = pyautogui.position()
        return {"success": True, "x": pos.x, "y": pos.y}

    def cmd_mouse_move(self, args: dict) -> dict:
        x = args.get("x", 0)
        y = args.get("y", 0)
        duration = args.get("duration", 0.1)
        pyautogui.moveTo(x, y, duration=duration)
        return {"success": True, "x": x, "y": y}

    def cmd_mouse_click(self, args: dict) -> dict:
        x = args.get("x")
        y = args.get("y")
        button = args.get("button", "left")
        if x is not None and y is not None:
            pyautogui.click(x=x, y=y, button=button)
        else:
            pyautogui.click(button=button)
        return {"success": True, "button": button}

    def cmd_mouse_double_click(self, args: dict) -> dict:
        pyautogui.doubleClick()
        return {"success": True}

    def cmd_mouse_right_click(self, args: dict) -> dict:
        pyautogui.rightClick()
        return {"success": True}

    def cmd_mouse_scroll(self, args: dict) -> dict:
        clicks = args.get("clicks", 0)
        pyautogui.scroll(clicks)
        return {"success": True, "clicks": clicks}

    def cmd_clipboard_get(self, args: dict) -> dict:
        text = pyperclip.paste()
        return {"success": True, "text": text}

    def cmd_clipboard_set(self, args: dict) -> dict:
        text = args.get("text", "")
        pyperclip.copy(text)
        return {"success": True}

    def cmd_media_playpause(self, args: dict) -> dict:
        pyautogui.press('playpause')
        return {"success": True}

    def cmd_media_next(self, args: dict) -> dict:
        pyautogui.press('nexttrack')
        return {"success": True}

    def cmd_media_prev(self, args: dict) -> dict:
        pyautogui.press('prevtrack')
        return {"success": True}

    def cmd_screen_snapshot(self, args: dict) -> dict:
        """Captura a tela inteira ou de monitor específico via mss ultra-rápido."""
        import base64
        import mss
        from io import BytesIO
        from PIL import Image

        monitor_index = args.get("monitor", 1) # Monitor 1 padrão
        with mss.MSS() as sct:
            if monitor_index >= len(sct.monitors):
                monitor_index = 0 # Toda a tela
            mon = sct.monitors[monitor_index]
            sct_img = sct.grab(mon)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

            buffered = BytesIO()
            img.save(buffered, format="JPEG", quality=80)
            b64_str = base64.b64encode(buffered.getvalue()).decode('utf-8')
            return {
                "success": True,
                "monitor": monitor_index,
                "width": img.width,
                "height": img.height,
                "format": "jpeg",
                "base64": b64_str
            }

    def cmd_screen_list_monitors(self, args: dict) -> dict:
        import mss
        with mss.MSS() as sct:
            return {"success": True, "monitors": sct.monitors}

    def cmd_system_info(self, args: dict) -> dict:
        telemetry = hc.get_hardware_telemetry()
        return {"success": True, "telemetry": telemetry}

    def cmd_system_notify(self, args: dict) -> dict:
        title = args.get("title", "Jarvis")
        body = args.get("body") or args.get("message", "")
        print(f"[Jarvis Notification] {title}: {body}")
        if self.event_bus:
            self.event_bus.emit("notification.received", {"title": title, "body": body})
        return {"success": True, "notified": True}

    def cmd_system_run(self, args: dict) -> dict:
        """Execução de comando do sistema (Requer confirmação em alto risco)."""
        cmd_str = args.get("command", "")
        if not cmd_str:
            return {"success": False, "message": "Comando vazio."}
        
        proc = subprocess.run(cmd_str, shell=True, capture_output=True, text=True, timeout=15, creationflags=CREATE_NO_WINDOW)
        return {
            "success": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr
        }

    # -------------------------------------------------------------
    # AUTOMAÇÃO WEB (PUPPETEER / PLAYWRIGHT)
    # -------------------------------------------------------------
    def cmd_puppeteer_navigate(self, args: dict) -> dict:
        try:
            from puppeteer_bridge import puppeteer_engine
            url = args.get("url", "")
            headless = args.get("headless", True)
            res = puppeteer_engine.navigate(url, headless=headless)
            res["success"] = res.get("status") == "ok"
            return res
        except Exception as e:
            return {"success": False, "error": str(e)}

    def cmd_puppeteer_screenshot(self, args: dict) -> dict:
        try:
            from puppeteer_bridge import puppeteer_engine
            url = args.get("url", "")
            res = puppeteer_engine.full_page_screenshot(url)
            res["success"] = res.get("status") == "ok"
            return res
        except Exception as e:
            return {"success": False, "error": str(e)}

    def cmd_puppeteer_interact(self, args: dict) -> dict:
        try:
            from puppeteer_bridge import puppeteer_engine
            url = args.get("url", "")
            actions = args.get("actions", [])
            headless = args.get("headless", True)
            res = puppeteer_engine.interact(url, actions=actions, headless=headless)
            res["success"] = res.get("status") == "ok"
            return res
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # CONFIRMAÇÕES PENDENTES DE ALTO RISCO (Interface para o usuário/HUD)
    # ------------------------------------------------------------------
    def get_pending_confirmations(self) -> List[Dict[str, Any]]:
        """Lista as confirmações de alto risco aguardando aprovação do usuário."""
        with self._lock:
            return [
                {
                    "confirmation_id": rid,
                    "command": req.get("command"),
                    "args": req.get("args"),
                    "created_at": req.get("created_at")
                }
                for rid, req in self.pending_confirmations.items()
            ]

    def confirm_request(self, confirmation_id: str) -> Dict[str, Any]:
        """Aprova e executa uma confirmação pendente de alto risco."""
        with self._lock:
            req = self.pending_confirmations.pop(confirmation_id, None)
        if not req:
            return {
                "success": False,
                "status": "unknown_confirmation",
                "message": f"Confirmação '{confirmation_id}' inexistente ou já resolvida."
            }
        return self.execute(req["command"], req["args"], origin="user_confirmation", confirmed=True)

    def reject_request(self, confirmation_id: str) -> Dict[str, Any]:
        """Rejeita uma confirmação pendente de alto risco."""
        with self._lock:
            req = self.pending_confirmations.pop(confirmation_id, None)
        if not req:
            return {
                "success": False,
                "status": "unknown_confirmation",
                "message": f"Confirmação '{confirmation_id}' inexistente ou já resolvida."
            }
        if self.event_bus:
            self.event_bus.emit("command.rejected", {
                "command": req.get("command"),
                "args": req.get("args"),
                "origin": "user_rejection"
            })
        return {"success": True, "status": "rejected", "message": f"Comando '{req.get('command')}' rejeitado pelo usuário."}
