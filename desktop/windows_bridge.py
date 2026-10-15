"""
J.A.R.V.I.S. Windows Bridge - Native System Automation Controller
Ponte completa entre o J.A.R.V.I.S. e o Windows:
- Teclado: digitação, atalhos (Win+D, Alt+Tab, Win+L, etc.)
- Mouse: movimentação, cliques, scroll
- Mídia & Áudio: Play/Pause global, Próxima/Anterior, Volume mestre (pycaw), Mudo
- Janelas: listar, focar (Chrome, VS Code, WhatsApp, etc.), restaurar, minimizar
- Clipboard: ler e colar conteúdo
- Captura de Tela: screenshot rápida para visão computacional
"""

import os
import sys
import time
import ctypes
import ctypes.wintypes
import subprocess
from typing import Dict, Any, Optional, List

# Evita o flash do console preto a cada comando shell (o app é windowless)
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

try:
    import pyautogui
    pyautogui.FAILSAFE = False
except Exception:
    pyautogui = None

try:
    import pyperclip
except Exception:
    pyperclip = None

try:
    from PIL import ImageGrab
except Exception:
    ImageGrab = None

def attach_to_default_desktop():
    try:
        user32 = ctypes.windll.user32
        h_winsta = user32.OpenWindowStationW("WinSta0", False, 0xF037F)
        if h_winsta:
            user32.SetProcessWindowStation(h_winsta)
        h_desk = user32.OpenDesktopW("Default", 0, False, 0x1FF)
        if h_desk:
            user32.SetThreadDesktop(h_desk)
    except Exception as e:
        pass

attach_to_default_desktop()

# Códigos de teclas virtuais do Windows (Win32 API)
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002

def _send_win32_key(vk_code: int):
    """Dispara um evento de tecla virtual no nível mais baixo do Windows com scan code mapeado."""
    user32 = ctypes.windll.user32
    scan = user32.MapVirtualKeyW(vk_code, 0)
    user32.keybd_event(vk_code, scan, 0, 0)
    time.sleep(0.04)
    user32.keybd_event(vk_code, scan, KEYEVENTF_KEYUP, 0)

class WindowsBridge:
    def __init__(self):
        self.user32 = ctypes.windll.user32

    # ==========================================
    # 1. CONTROLE DE MÍDIA GLOBAL (SPOTIFY / YOUTUBE / NAVEGADOR)
    # ==========================================
    def media_play_pause(self) -> Dict[str, Any]:
        """Alterna Play / Pause em qualquer reprodutor aberto no Windows."""
        _send_win32_key(VK_MEDIA_PLAY_PAUSE)
        if pyautogui:
            try:
                pyautogui.FAILSAFE = False
                pyautogui.press('playpause')
            except Exception:
                pass
        return {"status": "ok", "action": "media_play_pause", "message": "Comando Play/Pause de mídia enviado."}

    def media_next(self) -> Dict[str, Any]:
        """Avança para a próxima música ou vídeo."""
        _send_win32_key(VK_MEDIA_NEXT_TRACK)
        if pyautogui:
            try:
                pyautogui.FAILSAFE = False
                pyautogui.press('nexttrack')
            except Exception:
                pass
        return {"status": "ok", "action": "media_next", "message": "Avançado para a próxima faixa."}

    def media_previous(self) -> Dict[str, Any]:
        """Retorna para a música ou vídeo anterior."""
        _send_win32_key(VK_MEDIA_PREV_TRACK)
        if pyautogui:
            try:
                pyautogui.FAILSAFE = False
                pyautogui.press('prevtrack')
            except Exception:
                pass
        return {"status": "ok", "action": "media_previous", "message": "Retornado para a faixa anterior."}

    def media_mute(self) -> Dict[str, Any]:
        """Alterna (toggle) o mudo do áudio do Windows usando hardware_control."""
        try:
            import hardware_control as hc
            novo_mudo = not hc.is_windows_muted()
            hc.mute_windows_volume(novo_mudo)
            msg = "Áudio silenciado." if novo_mudo else "Áudio restaurado."
            return {"status": "ok", "action": "media_mute", "muted": novo_mudo, "message": msg}
        except Exception:
            _send_win32_key(VK_VOLUME_MUTE)
            return {"status": "ok", "action": "media_mute", "message": "Comando de alternância de mudo enviado via tecla virtual."}

    def volume_up(self, steps: int = 3) -> Dict[str, Any]:
        """Aumenta o volume do sistema via pycaw / hardware_control."""
        try:
            import hardware_control as hc
            new_v = hc.change_windows_volume(+10)
            return {"status": "ok", "action": "volume_up", "volume": new_v}
        except Exception:
            for _ in range(steps):
                _send_win32_key(VK_VOLUME_UP)
                time.sleep(0.02)
            return {"status": "ok", "action": "volume_up", "steps": steps}

    def volume_down(self, steps: int = 3) -> Dict[str, Any]:
        """Diminui o volume do sistema via pycaw / hardware_control."""
        try:
            import hardware_control as hc
            new_v = hc.change_windows_volume(-10)
            return {"status": "ok", "action": "volume_down", "volume": new_v}
        except Exception:
            for _ in range(steps):
                _send_win32_key(VK_VOLUME_DOWN)
                time.sleep(0.02)
            return {"status": "ok", "action": "volume_down", "steps": steps}

    def set_volume_percent(self, pct: int) -> Dict[str, Any]:
        """Ajusta o volume para um percentual exato (0-100) via pycaw se disponível."""
        try:
            import hardware_control as hc
            res = hc.set_windows_volume(pct)
            return {"status": "ok", "action": "set_volume", "volume": res}
        except Exception:
            return {"status": "error", "message": "Falha ao definir volume exato via hardware_control"}

    # ==========================================
    # BRILHO DE TELA (ADAPTADO DO MARK-LV)
    # ==========================================
    def get_brightness(self) -> Optional[int]:
        """Obtém o nível atual de brilho da tela (0-100)."""
        try:
            flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightness).CurrentBrightness"],
                capture_output=True, text=True, timeout=3, creationflags=flags
            )
            val = int(r.stdout.strip())
            return max(0, min(100, val))
        except Exception:
            return None

    def set_brightness(self, value: int) -> Dict[str, Any]:
        """Ajusta o brilho da tela para um percentual exato (0-100)."""
        val = max(0, min(100, int(value)))
        try:
            flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"(Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1, {val})"],
                capture_output=True, timeout=4, creationflags=flags
            )
            return {"status": "ok", "action": "set_brightness", "brightness": val}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def brightness_up(self, step: int = 15) -> Dict[str, Any]:
        """Aumenta o brilho da tela."""
        cur = self.get_brightness() or 50
        return self.set_brightness(min(100, cur + step))

    def brightness_down(self, step: int = 15) -> Dict[str, Any]:
        """Diminui o brilho da tela."""
        cur = self.get_brightness() or 50
        return self.set_brightness(max(0, cur - step))

    # ==========================================
    # 2. AUTOMAÇÃO DE TECLADO & ATALHOS DO WINDOWS
    # ==========================================
    def type_text(self, text: str) -> Dict[str, Any]:
        """Digita texto na janela ativa com suporte a acentuação e pontuação."""
        if not text:
            return {"status": "ignored"}
        if pyperclip and pyautogui:
            # Preserva o clipboard anterior e usa Ctrl+V para velocidade e acentos perfeitos
            old_clip = pyperclip.paste()
            pyperclip.copy(text)
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(0.05)
            pyperclip.copy(old_clip)
        elif pyautogui:
            pyautogui.write(text, interval=0.01)
        return {"status": "ok", "action": "type_text", "text": text}

    def press_key(self, key_name: str) -> Dict[str, Any]:
        """Pressiona uma tecla individual (enter, esc, backspace, tab, space, etc.)."""
        if pyautogui:
            pyautogui.press(key_name)
            return {"status": "ok", "action": "press_key", "key": key_name}
        return {"status": "error", "message": "pyautogui não disponível"}

    def hotkey(self, *keys: str) -> Dict[str, Any]:
        """Dispara um atalho de teclado composto (ex: 'ctrl', 'c' ou 'win', 'd')."""
        if pyautogui:
            pyautogui.hotkey(*keys)
            return {"status": "ok", "action": "hotkey", "keys": list(keys)}
        return {"status": "error", "message": "pyautogui não disponível"}

    def minimize_all_windows(self) -> Dict[str, Any]:
        """Minimiza todas as janelas e exibe a Área de Trabalho nativamente."""
        try:
            import win32com.client
            shell = win32com.client.Dispatch("Shell.Application")
            shell.ToggleDesktop()
            return {"status": "ok", "action": "minimize_all", "message": "Área de Trabalho alternada via Shell COM."}
        except Exception:
            self.user32.keybd_event(0x5B, 0, 0, 0) # Win
            self.user32.keybd_event(0x44, 0, 0, 0) # D
            time.sleep(0.04)
            self.user32.keybd_event(0x44, 0, 2, 0)
            self.user32.keybd_event(0x5B, 0, 2, 0)
            return {"status": "ok", "action": "minimize_all", "message": "Área de Trabalho exibida."}

    def switch_window(self) -> Dict[str, Any]:
        """Alterna para a próxima janela ativa visível (Alt+Tab / Alt+Esc nativo)."""
        try:
            wins = self.list_open_windows()
            if len(wins) > 1:
                target_hwnd = wins[1]["hwnd"]
                self.user32.ShowWindow(target_hwnd, 9) # SW_RESTORE
                self.user32.SetForegroundWindow(target_hwnd)
                self.user32.BringWindowToTop(target_hwnd)
                return {"status": "ok", "action": "switch_window", "title": wins[1]["title"]}
        except Exception:
            pass
        self.user32.keybd_event(0x12, 0, 0, 0) # Alt
        self.user32.keybd_event(0x1B, 0, 0, 0) # Esc
        time.sleep(0.04)
        self.user32.keybd_event(0x1B, 0, 2, 0)
        self.user32.keybd_event(0x12, 0, 2, 0)
        return {"status": "ok", "action": "switch_window", "message": "Janela alternada."}

    def lock_screen(self) -> Dict[str, Any]:
        """Bloqueia a sessão do Windows (Win + L)."""
        self.user32.LockWorkStation()
        return {"status": "ok", "action": "lock_screen", "message": "Estação de trabalho bloqueada por segurança."}

    # ==========================================
    # 3. CONTROLE DE MOUSE
    # ==========================================
    def mouse_move(self, x: int, y: int) -> Dict[str, Any]:
        """Move o cursor para coordenadas absolutas."""
        if pyautogui:
            pyautogui.moveTo(x, y)
            return {"status": "ok", "action": "mouse_move", "x": x, "y": y}
        return {"status": "error", "message": "pyautogui ausente"}

    def mouse_click(self, button: str = "left", clicks: int = 1) -> Dict[str, Any]:
        """Clica na posição atual do cursor."""
        if pyautogui:
            pyautogui.click(button=button, clicks=clicks)
            return {"status": "ok", "action": "mouse_click", "button": button, "clicks": clicks}
        return {"status": "error", "message": "pyautogui ausente"}

    def mouse_scroll(self, amount: int = -300) -> Dict[str, Any]:
        """Rola a página para cima (positivo) ou para baixo (negativo)."""
        if pyautogui:
            pyautogui.scroll(amount)
            return {"status": "ok", "action": "mouse_scroll", "amount": amount}
        return {"status": "error", "message": "pyautogui ausente"}

    # ==========================================
    # 4. GERENCIAMENTO DE JANELAS & APLICATIVOS
    # ==========================================
    def list_open_windows(self) -> List[Dict[str, Any]]:
        """Lista janelas ativas visíveis com seus títulos e identificadores."""
        windows = []
        def enum_cb(hwnd, extra):
            if self.user32.IsWindowVisible(hwnd):
                length = self.user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    self.user32.GetWindowTextW(hwnd, buff, length + 1)
                    title = buff.value.strip()
                    if title and title not in ["Default IME", "MSCTFIME UI", "Program Manager"]:
                        windows.append({"hwnd": hwnd, "title": title})
            return True

        CMPFUNC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
        self.user32.EnumWindows(CMPFUNC(enum_cb), 0)
        return windows

    def focus_window(self, keyword: str) -> Dict[str, Any]:
        """Traz para primeiro plano a janela cujo título coincida com a palavra-chave."""
        kw = keyword.lower()
        windows = self.list_open_windows()
        for w in windows:
            if kw in w["title"].lower():
                hwnd = w["hwnd"]
                self.user32.ShowWindow(hwnd, 9) # SW_RESTORE
                self.user32.SetForegroundWindow(hwnd)
                return {"status": "ok", "action": "focus_window", "title": w["title"], "hwnd": hwnd}
        return {"status": "not_found", "keyword": keyword}

    def launch_app(self, app_name: str) -> Dict[str, Any]:
        """Inicia um programa no Windows com base no catálogo estendido do Mark-LV."""
        raw = app_name.lower().strip()
        app_map = {
            "chrome": "start chrome",
            "google chrome": "start chrome",
            "navegador": "start chrome",
            "firefox": "start firefox",
            "edge": "start msedge",
            "msedge": "start msedge",
            "brave": "start brave",
            "opera": "start opera",
            "spotify": "start spotify:",
            "musica": "start spotify:",
            "whatsapp": "start whatsapp:",
            "telegram": "start telegram",
            "discord": "start discord:",
            "slack": "start slack:",
            "zoom": "start zoom",
            "teams": "start msteams:",
            "vs code": "code",
            "vscode": "code",
            "code": "code",
            "terminal": "wt",
            "cmd": "start cmd",
            "powershell": "start powershell",
            "bloco de notas": "notepad",
            "notepad": "notepad",
            "calculadora": "calc",
            "configuracoes": "start ms-settings:",
            "settings": "start ms-settings:",
            "painel": "start ms-settings:",
            "gerenciador de tarefas": "start taskmgr",
            "task manager": "start taskmgr",
            "taskmgr": "start taskmgr",
            "explorer": "start explorer",
            "arquivos": "start explorer",
            "word": "start winword",
            "excel": "start excel",
            "powerpoint": "start powerpnt",
            "paint": "start mspaint",
            "steam": "start steam:",
            "epic": "start com.epicgames.launcher:",
            "notion": "start notion:",
            "obsidian": "start obsidian:"
        }
        cmd = app_map.get(raw, f"start {raw}")
        try:
            subprocess.Popen(cmd, shell=True, creationflags=CREATE_NO_WINDOW)
            return {"status": "ok", "action": "launch_app", "app": app_name, "cmd": cmd}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # ==========================================
    # 5. CLIPBOARD (ÁREA DE TRANSFERÊNCIA)
    # ==========================================
    def get_clipboard_text(self) -> str:
        """Obtém o texto atual na Área de Transferência."""
        if pyperclip:
            return pyperclip.paste()
        return ""

    def set_clipboard_text(self, text: str) -> Dict[str, Any]:
        """Define o texto da Área de Transferência."""
        if pyperclip:
            pyperclip.copy(text)
            return {"status": "ok", "action": "set_clipboard"}
        return {"status": "error", "message": "pyperclip ausente"}

    # ==========================================
    # 6. CAPTURA DE TELA (SCREENSHOT)
    # ==========================================
    def capture_screen(self, save_path: Optional[str] = None) -> Optional[str]:
        """Captura a tela principal e salva em disco."""
        if not save_path:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            save_path = os.path.join(project_root, "logs", f"screenshot_{int(time.time())}.png")
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        try:
            if ImageGrab:
                img = ImageGrab.grab()
                img.save(save_path)
                return save_path
            elif pyautogui:
                img = pyautogui.screenshot()
                img.save(save_path)
                return save_path
        except Exception as e:
            print("[BRIDGE] Erro na captura de tela:", e)
        return None

    # ==========================================
    # 7. EXECUTOR UNIFICADO DE AÇÕES
    # ==========================================
    def execute(self, action: str, **params) -> Dict[str, Any]:
        """Despacha uma ação requisitada pelo JARVIS."""
        act = action.lower().strip()
        if act in ["play_pause", "media_play_pause", "pausar", "tocar"]:
            return self.media_play_pause()
        elif act in ["next_track", "proxima", "avancar", "swipe_right"]:
            return self.media_next()
        elif act in ["prev_track", "anterior", "voltar", "swipe_left"]:
            return self.media_previous()
        elif act in ["mute", "silenciar", "volume_mute"]:
            return self.media_mute()
        elif act in ["volume_up", "aumentar_volume", "point_up"]:
            return self.volume_up(params.get("steps", 3))
        elif act in ["volume_down", "diminuir_volume", "point_down"]:
            return self.volume_down(params.get("steps", 3))
        elif act in ["set_volume"]:
            return self.set_volume_percent(params.get("pct", 50))
        elif act in ["brightness_up", "aumentar_brilho"]:
            return self.brightness_up(params.get("step", 15))
        elif act in ["brightness_down", "diminuir_brilho"]:
            return self.brightness_down(params.get("step", 15))
        elif act in ["set_brightness"]:
            return self.set_brightness(params.get("brightness", 50))
        elif act in ["minimize_all", "desktop", "area_de_trabalho", "fist"]:
            return self.minimize_all_windows()
        elif act in ["switch_window", "alt_tab", "three_fingers"]:
            return self.switch_window()
        elif act in ["lock", "bloquear", "lock_screen"]:
            return self.lock_screen()
        elif act in ["confirm", "enter", "thumbs_up"]:
            return self.press_key("enter")
        elif act in ["cancel", "esc", "thumbs_down"]:
            return self.press_key("esc")
        elif act in ["zoom_in"]:
            return self.hotkey("ctrl", "+")
        elif act in ["zoom_out"]:
            return self.hotkey("ctrl", "-")
        elif act in ["type", "digitar"]:
            return self.type_text(params.get("text", ""))
        elif act in ["press"]:
            return self.press_key(params.get("key", "enter"))
        elif act in ["hotkey", "atalho"]:
            keys = params.get("keys", [])
            return self.hotkey(*keys)
        elif act in ["scroll_down", "swipe_down"]:
            return self.mouse_scroll(-350)
        elif act in ["scroll_up", "swipe_up"]:
            return self.mouse_scroll(350)
        elif act in ["focus", "focar"]:
            return self.focus_window(params.get("keyword", ""))
        elif act in ["launch", "abrir"]:
            return self.launch_app(params.get("app", ""))
        elif act in ["open_canvas", "canvas", "janela_canvas", "mostrar_canvas"]:
            return self.open_canvas_window(params.get("mode", "reactor"))
        elif act in ["shutdown", "shutdown_pc", "desligar", "desligar_pc"]:
            delay = int(params.get("delay", 30))
            force = bool(params.get("force", False))
            msg = str(params.get("message", "Desligamento solicitado via J.A.R.V.I.S. HUD"))
            return self.shutdown_pc(delay=delay, force=force, message=msg)
        elif act in ["restart", "restart_pc", "reiniciar", "reiniciar_pc"]:
            delay = int(params.get("delay", 30))
            force = bool(params.get("force", False))
            return self.restart_pc(delay=delay, force=force)
        elif act in ["abort_shutdown", "cancel_shutdown", "cancelar_desligamento", "abortar_desligamento"]:
            return self.abort_shutdown()
        elif act in ["sleep", "sleep_pc", "suspender", "suspender_pc"]:
            return self.sleep_pc()
        elif act in ["screenshot", "print"]:
            path = self.capture_screen()
            return {"status": "ok", "action": "screenshot", "path": path}
        elif act in ["puppeteer_navigate", "puppeteer_browse", "web_navigate"]:
            try:
                from puppeteer_bridge import puppeteer_engine
                url = params.get("url", "")
                headless = params.get("headless", True)
                return puppeteer_engine.navigate(url, headless=headless)
            except Exception as e:
                return {"status": "error", "action": "puppeteer_navigate", "message": str(e)}
        elif act in ["puppeteer_screenshot", "puppeteer_full_screenshot", "web_screenshot"]:
            try:
                from puppeteer_bridge import puppeteer_engine
                url = params.get("url", "")
                return puppeteer_engine.full_page_screenshot(url)
            except Exception as e:
                return {"status": "error", "action": "puppeteer_screenshot", "message": str(e)}
        elif act in ["puppeteer_interact", "web_interact"]:
            try:
                from puppeteer_bridge import puppeteer_engine
                url = params.get("url", "")
                actions = params.get("actions", [])
                headless = params.get("headless", True)
                return puppeteer_engine.interact(url, actions=actions, headless=headless)
            except Exception as e:
                return {"status": "error", "action": "puppeteer_interact", "message": str(e)}
        else:
            return {"status": "unknown_action", "action": action}

    def shutdown_pc(self, delay: int = 30, force: bool = False, message: str = "Desligamento agendado pelo JARVIS HUD") -> Dict[str, Any]:
        """Inicia o desligamento do computador Windows com timer e mensagem."""
        try:
            cmd = ["shutdown", "/s", "/t", str(max(0, delay)), "/c", message]
            if force:
                cmd.append("/f")
            subprocess.run(cmd, check=True, shell=True, creationflags=CREATE_NO_WINDOW)
            return {
                "status": "ok",
                "action": "shutdown",
                "delay": delay,
                "message": f"Desligamento agendado para daqui a {delay} segundos." if delay > 0 else "Desligando agora."
            }
        except Exception as e:
            return {"status": "error", "action": "shutdown", "message": str(e)}

    def restart_pc(self, delay: int = 30, force: bool = False) -> Dict[str, Any]:
        """Reinicia o computador Windows com timer."""
        try:
            cmd = ["shutdown", "/r", "/t", str(max(0, delay)), "/c", "Reinicializacao solicitada pelo JARVIS HUD"]
            if force:
                cmd.append("/f")
            subprocess.run(cmd, check=True, shell=True, creationflags=CREATE_NO_WINDOW)
            return {
                "status": "ok",
                "action": "restart",
                "delay": delay,
                "message": f"Reinicialização agendada para daqui a {delay} segundos." if delay > 0 else "Reiniciando agora."
            }
        except Exception as e:
            return {"status": "error", "action": "restart", "message": str(e)}

    def abort_shutdown(self) -> Dict[str, Any]:
        """Cancela qualquer ordem pendente de desligamento ou reinício do Windows."""
        try:
            subprocess.run(["shutdown", "/a"], check=True, shell=True, creationflags=CREATE_NO_WINDOW)
            return {"status": "ok", "action": "abort_shutdown", "message": "Desligamento pendente cancelado com sucesso."}
        except Exception as e:
            # Se não havia desligamento agendado, shutdown /a retorna erro 1116
            return {"status": "ok", "action": "abort_shutdown", "message": "Nenhum desligamento estava ativo ou foi cancelado."}

    def sleep_pc(self) -> Dict[str, Any]:
        """Coloca o computador em modo de suspensão / sleep."""
        try:
            subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], shell=True, creationflags=CREATE_NO_WINDOW)
            return {"status": "ok", "action": "sleep", "message": "Modo de suspensão ativado."}
        except Exception as e:
            return {"status": "error", "action": "sleep", "message": str(e)}

    def open_canvas_window(self, mode: str = "reactor") -> Dict[str, Any]:
        """Abre uma janela Canvas holográfica nativa diretamente no Windows."""
        canvas_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "canvas_window.py")
        py_exe = sys.executable or "python.exe"
        try:
            subprocess.Popen([py_exe, canvas_script, mode], shell=False)
            return {"status": "ok", "action": "open_canvas", "mode": mode}
        except Exception as e:
            return {"status": "error", "message": str(e)}

bridge = WindowsBridge()

if __name__ == "__main__":
    print("[WindowsBridge] Teste de conectividade...")
    wins = bridge.list_open_windows()
    print(f"[WindowsBridge] Janelas encontradas: {len(wins)}")
    for w in wins[:5]:
        print(f"  - {w['title']}")
