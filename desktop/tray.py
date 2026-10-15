"""
Jarvis Desktop - Windows System Tray & Autostart
Cria o ícone na bandeja do sistema (System Tray) com menu tático:
- Status da conexão com o JARVIS Core
- Ligar / Desligar Visão Computacional
- Abrir HUD / Painel Web
- Reconectar ponte do Core
- Habilitar / Desabilitar Inicialização com o Windows (Registro HKCU Run)
- Sair
"""

import os
import sys
import webbrowser
import threading
import winreg
from PIL import Image, ImageDraw
import pystray

REG_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "JarvisDesktop"
CORE_BASE_URL = os.environ.get("JARVIS_CORE_URL", "https://jarvis.werikspace.xyz")

class SystemTrayApp:
    def __init__(self, core):
        self.core = core
        self.icon = None
        self._thread = None

    def _create_icon_image(self, connected: bool = False):
        # Gera ícone dinâmico 64x64 com o anel holográfico J.A.R.V.I.S.
        image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
        dc = ImageDraw.Draw(image)
        # Fundo do reator
        dc.ellipse((4, 4, 60, 60), fill=(2, 11, 24, 255), outline=(0, 210, 255, 255), width=3)
        # Núcleo de status
        core_color = (0, 240, 255, 255) if connected else (255, 180, 0, 255)
        dc.ellipse((20, 20, 44, 44), fill=core_color)
        return image

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True, name="SystemTrayThread")
        self._thread.start()

    def _run(self):
        bridge_status = lambda: (self.core.remote_bridge.status if getattr(self.core, "remote_bridge", None) else "DISCONNECTED")
        menu = pystray.Menu(
            pystray.MenuItem("J.A.R.V.I.S. ● Online", None, enabled=False),
            pystray.MenuItem(lambda text: f"JARVIS no Zima: {bridge_status()}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Console J.A.R.V.I.S. (Chat)", self.action_open_hud, default=True),
            pystray.MenuItem("🧠 Cérebro & Memória 3D", self.action_open_memory),
            pystray.MenuItem("Central de Controle do Nó", self.action_node_center),
            pystray.MenuItem("Chamar Jarvis (acordar ilha)", self.action_call_jarvis),
            pystray.MenuItem(lambda text: "Desativar Visão" if self.core.vision_enabled else "Ativar Visão (Webcam)", self.action_toggle_vision),
            pystray.MenuItem("Reconectar Ponte JARVIS", self.action_reconnect_bridge),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Iniciar com o Windows", self.action_toggle_autostart, checked=lambda item: self.is_autostart_enabled()),
            pystray.MenuItem("Sair do Jarvis Desktop", self.action_quit)
        )

        self.icon = pystray.Icon(
            "JarvisDesktop",
            self._create_icon_image(connected=(bridge_status() == "CONNECTED")),
            "Jarvis Desktop - Node Windows",
            menu
        )

        # Atualiza o ícone conforme a conexão Windows → JARVIS Core.
        if self.core.event_bus:
            self.core.event_bus.subscribe("bridge.status", self._on_status_change)

        self.icon.run()

    def _on_status_change(self, event):
        if self.icon:
            st = event.get("data", {}).get("status")
            is_conn = (st == "CONNECTED")
            self.icon.icon = self._create_icon_image(connected=is_conn)
            self.icon.title = f"Jarvis Desktop ● {st}"

    def action_open_hud(self, icon, item):
        if hasattr(self.core, 'open_hud_window'):
            self.core.open_hud_window()

    def action_open_memory(self, icon, item):
        if hasattr(self.core, 'open_memory_window'):
            self.core.open_memory_window()

    def action_node_center(self, icon, item):
        if hasattr(self.core, 'open_node_center'):
            self.core.open_node_center()

    def action_call_jarvis(self, icon, item):
        """Acorda a Dynamic Island via SSE do servidor local (sem navegador)."""
        try:
            import json
            import urllib.request
            payload = json.dumps({"action": "island_show", "title": "J.A.R.V.I.S.", "message": "Console nativo chamado pelo operador."}).encode("utf-8")
            req = urllib.request.Request(CORE_BASE_URL + "/api/hud/control", data=payload, headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=5)
        except Exception as e:
            print(f"[SystemTray] Falha ao acordar ilha: {e}")

    def action_toggle_vision(self, icon, item):
        self.core.toggle_vision()

    def action_reconnect_bridge(self, icon, item):
        bridge = getattr(self.core, "remote_bridge", None)
        if bridge:
            bridge.stop()
            threading.Timer(0.5, bridge.run).start()

    def action_toggle_autostart(self, icon, item):
        currently_enabled = self.is_autostart_enabled()
        self.set_autostart(not currently_enabled)

    def action_quit(self, icon, item):
        self.core.stop()
        if self.icon:
            self.icon.stop()

    def is_autostart_enabled(self) -> bool:
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_READ)
            winreg.QueryValueEx(key, APP_NAME)
            winreg.CloseKey(key)
            return True
        except FileNotFoundError:
            return False
        except Exception:
            return False

    def set_autostart(self, enable: bool):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_SET_VALUE)
            if enable:
                vbs_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "jarvis_autostart.vbs")
                cmd = f'wscript.exe "{vbs_path}"'
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
                print(f"[SystemTray] Inicialização automática com o Windows ativada: {cmd}")
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                    print("[SystemTray] Inicialização automática com o Windows desativada.")
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except Exception as e:
            print(f"[SystemTray] Erro ao alterar registro do Windows Run: {e}")
