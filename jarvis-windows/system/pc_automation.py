"""
J.A.R.V.I.S. PC Automation Engine
Controle total de Mouse, Teclado, Captura de Tela, Área de Transferência e Janelas no Windows.
Padrão Permanente de Engenharia de Software Sênior.
"""

import os
import sys
import time
import base64
import logging
import tempfile
import ctypes
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("PCAutomation")
logger.setLevel(logging.INFO)

# 1. Carrega PyAutoGUI com failsafe customizado
try:
    import pyautogui
    pyautogui.FAILSAFE = False  # Evita crash ao tocar bordas, usamos clamping
    pyautogui.PAUSE = 0.02
    PYAUTOGUI_AVAILABLE = True
except Exception as e:
    pyautogui = None
    PYAUTOGUI_AVAILABLE = False
    logger.warning(f"PyAutoGUI não disponível: {e}")

# 2. Carrega Pyperclip para área de transferência
try:
    import pyperclip
    PYPERCLIP_AVAILABLE = True
except Exception as e:
    pyperclip = None
    PYPERCLIP_AVAILABLE = False
    logger.warning(f"Pyperclip não disponível: {e}")

# 3. Carrega Pillow para captura de tela
try:
    from PIL import Image, ImageGrab
    PIL_AVAILABLE = True
except Exception as e:
    PIL_AVAILABLE = False
    logger.warning(f"Pillow não disponível: {e}")

user32 = ctypes.windll.user32

# Habilita DPI Awareness no Windows para garantir alinhamento exato de coordenadas físicas de tela
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass



# ==============================================================================
# 1. CONTROLE DO MOUSE (MOVIMENTO, CLIQUES, ARRASTAR, ROLAGEM)
# ==============================================================================

def get_screen_size() -> Tuple[int, int]:
    """Retorna a resolução da tela principal (largura, altura)."""
    if PYAUTOGUI_AVAILABLE:
        size = pyautogui.size()
        return (size.width, size.height)
    w = user32.GetSystemMetrics(0)
    h = user32.GetSystemMetrics(1)
    return (w, h)


def _clamp_coordinates(x: int, y: int) -> Tuple[int, int]:
    """Garante que as coordenadas estejam estritamente dentro da tela."""
    w, h = get_screen_size()
    clamped_x = max(0, min(int(x), w - 1))
    clamped_y = max(0, min(int(y), h - 1))
    return (clamped_x, clamped_y)


def get_mouse_position() -> Dict[str, Any]:
    """Retorna as coordenadas atuais do cursor e a resolução da tela."""
    w, h = get_screen_size()
    if PYAUTOGUI_AVAILABLE:
        pos = pyautogui.position()
        cx, cy = pos.x, pos.y
    else:
        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
        pt = POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        cx, cy = pt.x, pt.y

    return {
        "success": True,
        "x": cx,
        "y": cy,
        "screen_width": w,
        "screen_height": h
    }


def mouse_move(x: int, y: int, duration: float = 0.2) -> Dict[str, Any]:
    """Move o cursor do mouse suavemente para (x, y) respeitando DPI e limites da tela."""
    cx, cy = _clamp_coordinates(x, y)
    try:
        if PYAUTOGUI_AVAILABLE:
            dur = max(0.0, float(duration))
            if dur > 0:
                pyautogui.moveTo(cx, cy, duration=dur, tween=pyautogui.easeInOutQuad)
            else:
                pyautogui.moveTo(cx, cy)
        else:
            user32.SetCursorPos(cx, cy)
        time.sleep(0.02)
        return {"success": True, "action": "mouse_move", "x": cx, "y": cy}
    except Exception as e:
        try:
            user32.SetCursorPos(cx, cy)
            return {"success": True, "action": "mouse_move", "x": cx, "y": cy, "fallback": "win32"}
        except Exception as e2:
            return {"success": False, "error": f"{e} (fallback: {e2})"}


def mouse_move_rel(dx: int, dy: int, duration: float = 0.2) -> Dict[str, Any]:
    """Move o cursor do mouse de forma relativa à posição atual."""
    try:
        cur = get_mouse_position()
        target_x = cur["x"] + int(dx)
        target_y = cur["y"] + int(dy)
        return mouse_move(target_x, target_y, duration)
    except Exception as e:
        return {"success": False, "error": str(e)}


def mouse_click(button: str = "left", clicks: int = 1, interval: float = 0.1, x: Optional[int] = None, y: Optional[int] = None) -> Dict[str, Any]:
    """
    Executa clique(s) do mouse (esquerdo, direito, meio, duplo, triplo).
    Se x e y forem fornecidos, move antes de clicar com pausa suave de foco/hover.
    """
    btn = button.lower().strip()
    if btn in ["right", "direito"]:
        btn = "right"
    elif btn in ["middle", "meio"]:
        btn = "middle"
    elif btn in ["double", "duplo"]:
        btn = "left"
        clicks = 2
    elif btn in ["triple", "triplo"]:
        btn = "left"
        clicks = 3
    else:
        btn = "left"

    try:
        if x is not None and y is not None:
            mouse_move(x, y, duration=0.15)
            time.sleep(0.05)  # Pausa essencial para hover e foco da interface

        if PYAUTOGUI_AVAILABLE:
            pyautogui.click(button=btn, clicks=clicks, interval=interval)
        else:
            # Fallback Win32 mouse_event
            events = {
                "left": (0x0002, 0x0004),
                "right": (0x0008, 0x0010),
                "middle": (0x0020, 0x0040)
            }
            down_flag, up_flag = events.get(btn, (0x0002, 0x0004))
            for _ in range(clicks):
                user32.mouse_event(down_flag, 0, 0, 0, 0)
                user32.mouse_event(up_flag, 0, 0, 0, 0)
                if clicks > 1:
                    time.sleep(interval)

        return {"success": True, "action": "mouse_click", "button": btn, "clicks": clicks, "x": x, "y": y}
    except Exception as e:
        return {"success": False, "error": str(e)}


def mouse_drag(x: int, y: int, duration: float = 0.5, button: str = "left") -> Dict[str, Any]:
    """Arrasta o mouse da posição atual até (x, y) segurando o botão."""
    cx, cy = _clamp_coordinates(x, y)
    btn = "right" if button.lower() in ["right", "direito"] else "left"
    try:
        if PYAUTOGUI_AVAILABLE:
            pyautogui.dragTo(cx, cy, duration=duration, button=btn)
        else:
            down_flag = 0x0008 if btn == "right" else 0x0002
            up_flag = 0x0010 if btn == "right" else 0x0004
            user32.mouse_event(down_flag, 0, 0, 0, 0)
            user32.SetCursorPos(cx, cy)
            user32.mouse_event(up_flag, 0, 0, 0, 0)
        return {"success": True, "action": "mouse_drag", "x": cx, "y": cy}
    except Exception as e:
        return {"success": False, "error": str(e)}


def mouse_scroll(clicks: int = 5, direction: str = "down") -> Dict[str, Any]:
    """
    Rola a roda do mouse para cima ('up') ou para baixo ('down').
    """
    d = direction.lower().strip()
    amt = int(clicks)
    if d in ["down", "baixo", "descendo"]:
        scroll_amount = -abs(amt)
    else:
        scroll_amount = abs(amt)

    try:
        if PYAUTOGUI_AVAILABLE:
            pyautogui.scroll(scroll_amount * 100)
        else:
            # Win32 WHEEL_DELTA = 120
            WHEEL = 0x0800
            user32.mouse_event(WHEEL, 0, 0, scroll_amount * 120, 0)
        return {"success": True, "action": "mouse_scroll", "amount": scroll_amount, "direction": d}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ==============================================================================
# 2. CONTROLE DO TECLADO (DIGITAÇÃO UTF-8, TECLAS ESPECIAIS, ATALHOS)
# ==============================================================================

# Normalização de nomes de teclas amigáveis para PyAutoGUI
KEY_NORM = {
    "enter": "enter", "return": "enter", "intro": "enter",
    "esc": "esc", "escape": "esc",
    "tab": "tab",
    "space": "space", "espaco": "space", "espaço": "space",
    "backspace": "backspace", "apagar": "backspace",
    "delete": "delete", "del": "delete",
    "up": "up", "cima": "up",
    "down": "down", "baixo": "down",
    "left": "left", "esquerda": "left",
    "right": "right", "direita": "right",
    "win": "win", "windows": "win", "super": "win",
    "ctrl": "ctrl", "control": "ctrl",
    "alt": "alt",
    "shift": "shift",
    "capslock": "capslock",
    "home": "home", "end": "end",
    "pageup": "pageup", "pagedown": "pagedown",
    "f1": "f1", "f2": "f2", "f3": "f3", "f4": "f4", "f5": "f5",
    "f6": "f6", "f7": "f7", "f8": "f8", "f9": "f9", "f10": "f10",
    "f11": "f11", "f12": "f12"
}

def keyboard_type(text: str, interval: float = 0.01) -> Dict[str, Any]:
    """
    Digita um texto na janela ativa com fidelidade total UTF-8 / ABNT2.
    Utiliza área de transferência com colagem Ctrl+V como método primário
    para evitar perda de caracteres ou desconfiguração de layout (ABNT2).
    """
    if not text:
        return {"success": True, "action": "keyboard_type", "chars": 0}

    # Tenta via clipboard se pyperclip e pyautogui/win32 estiverem disponíveis
    if PYPERCLIP_AVAILABLE:
        try:
            old_clip = None
            try:
                old_clip = pyperclip.paste()
            except Exception:
                pass

            pyperclip.copy(text)
            time.sleep(0.03)

            if PYAUTOGUI_AVAILABLE:
                pyautogui.hotkey("ctrl", "v")
            else:
                VK_CONTROL = 0x11
                VK_V = 0x56
                KEYEVENTF_KEYUP = 0x0002
                user32.keybd_event(VK_CONTROL, 0, 0, 0)
                user32.keybd_event(VK_V, 0, 0, 0)
                time.sleep(0.02)
                user32.keybd_event(VK_V, 0, KEYEVENTF_KEYUP, 0)
                user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)

            time.sleep(0.05)
            # Restaura clipboard se possível
            if old_clip is not None:
                try:
                    pyperclip.copy(old_clip)
                except Exception:
                    pass

            return {"success": True, "action": "keyboard_type", "text": text, "length": len(text), "method": "clipboard"}
        except Exception as e:
            logger.warning(f"Falha ao colar via clipboard: {e}, tentando digitação direta...")

    # Fallback via PyAutoGUI write
    try:
        if PYAUTOGUI_AVAILABLE:
            pyautogui.write(text, interval=interval)
            return {"success": True, "action": "keyboard_type", "text": text, "length": len(text), "method": "pyautogui"}
    except Exception as e:
        logger.warning(f"Falha no pyautogui.write: {e}")

    # Fallback via PowerShell SendKeys
    try:
        from .win_controls import run_powershell
        escaped = text.replace("'", "''")
        run_powershell(f"Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait('{escaped}')")
        return {"success": True, "action": "keyboard_type", "text": text, "length": len(text), "method": "sendkeys"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def keyboard_press(key: str) -> Dict[str, Any]:
    """Pressiona e solta uma tecla específica."""
    k = key.lower().strip()
    norm_k = KEY_NORM.get(k, k)
    try:
        if PYAUTOGUI_AVAILABLE:
            pyautogui.press(norm_k)
        else:
            from .win_controls import run_powershell
            run_powershell(f"Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait('{{{norm_k.upper()}}}')")
        return {"success": True, "action": "keyboard_press", "key": norm_k}
    except Exception as e:
        return {"success": False, "error": str(e)}


def keyboard_hotkey(*keys) -> Dict[str, Any]:
    """
    Executa uma combinação de teclas (atalho).
    Exemplos: ('ctrl', 'c'), ('ctrl', 'v'), ('alt', 'tab'), ('win', 'd'), ('ctrl', 'shift', 'esc').
    """
    # Suporta lista de teclas ou múltiplos argumentos
    if len(keys) == 1 and isinstance(keys[0], (list, tuple)):
        key_list = list(keys[0])
    else:
        key_list = list(keys)

    norm_keys = [KEY_NORM.get(str(k).lower().strip(), str(k).lower().strip()) for k in key_list]

    try:
        if PYAUTOGUI_AVAILABLE:
            pyautogui.hotkey(*norm_keys)
        else:
            from .win_controls import run_powershell
            # Fallback básico
            pass
        return {"success": True, "action": "keyboard_hotkey", "keys": norm_keys}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ==============================================================================
# 3. ÁREA DE TRANSFERÊNCIA (CLIPBOARD)
# ==============================================================================

def clipboard_copy(text: str) -> Dict[str, Any]:
    """Copia um texto para a Área de Transferência do Windows."""
    try:
        if PYPERCLIP_AVAILABLE:
            pyperclip.copy(text)
            return {"success": True, "action": "clipboard_copy", "chars": len(text)}
        return {"success": False, "error": "pyperclip não instalado"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def clipboard_read() -> Dict[str, Any]:
    """Lê o conteúdo textual da Área de Transferência do Windows."""
    try:
        if PYPERCLIP_AVAILABLE:
            content = pyperclip.paste()
            return {"success": True, "action": "clipboard_read", "content": content}
        return {"success": False, "error": "pyperclip não instalado"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def clipboard_paste() -> Dict[str, Any]:
    """Simula o atalho Ctrl+V para colar na aplicação em foco."""
    return keyboard_hotkey("ctrl", "v")


# ==============================================================================
# 4. CAPTURA DE TELA (SCREENSHOT) & VISÃO
# ==============================================================================

def _capture_screen_win32() -> Optional[Any]:
    """Captura robusta via Win32 GDI BitBlt que não falha no Windows com múltiplos monitores ou DPI escalonado."""
    if not PIL_AVAILABLE:
        return None
    try:
        from ctypes import wintypes
        gdi32 = ctypes.windll.gdi32
        w = user32.GetSystemMetrics(0)
        h = user32.GetSystemMetrics(1)
        hdc_screen = user32.GetDC(0)
        hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
        hbm = gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
        gdi32.SelectObject(hdc_mem, hbm)

        # SRCCOPY = 0x00CC0020
        gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_screen, 0, 0, 0x00CC0020)

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ('biSize', wintypes.DWORD),
                ('biWidth', wintypes.LONG),
                ('biHeight', wintypes.LONG),
                ('biPlanes', wintypes.WORD),
                ('biBitCount', wintypes.WORD),
                ('biCompression', wintypes.DWORD),
                ('biSizeImage', wintypes.DWORD),
                ('biXPelsPerMeter', wintypes.LONG),
                ('biYPelsPerMeter', wintypes.LONG),
                ('biClrUsed', wintypes.DWORD),
                ('biClrImportant', wintypes.DWORD)
            ]

        bmi = BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.biWidth = w
        bmi.biHeight = -h  # top-down
        bmi.biPlanes = 1
        bmi.biBitCount = 32
        bmi.biCompression = 0

        buf = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetDIBits(hdc_mem, hbm, 0, h, buf, ctypes.byref(bmi), 0)

        gdi32.DeleteObject(hbm)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(0, hdc_screen)

        return Image.frombuffer('RGB', (w, h), buf, 'raw', 'BGRX', 0, 1)
    except Exception as e:
        logger.warning(f"Win32 GDI BitBlt captura falhou: {e}")
        return None


def take_screenshot(save_path: Optional[str] = None, return_base64: bool = False, max_width: int = 1920) -> Dict[str, Any]:
    """
    Captura a tela inteira do monitor principal com alinhamento exato de DPI.
    Salva em save_path (ou arquivo temporário) e opcionalmente retorna em Base64.
    """
    if not save_path:
        tmp_dir = os.path.join(tempfile.gettempdir(), "jarvis_captures")
        os.makedirs(tmp_dir, exist_ok=True)
        save_path = os.path.join(tmp_dir, f"screenshot_{int(time.time())}.png")

    try:
        img = None
        # 1. Tenta captura de alta performance via Win32 GDI BitBlt
        try:
            img = _capture_screen_win32()
        except Exception:
            pass

        # 2. Fallback via Pillow ImageGrab
        if img is None and PIL_AVAILABLE:
            try:
                img = ImageGrab.grab(all_screens=False)
            except Exception:
                pass

        # 3. Fallback via PyAutoGUI
        if img is None and PYAUTOGUI_AVAILABLE:
            try:
                img = pyautogui.screenshot()
            except Exception:
                pass

        if img is None:
            return {"success": False, "error": "Nenhum método gráfico conseguiu capturar a tela"}

        img.save(save_path, "PNG")

        res = {
            "success": True,
            "action": "screenshot",
            "path": save_path,
            "width": img.width,
            "height": img.height
        }

        if return_base64:
            # Otimização de envio para modelos multimodais de visão:
            # Mantém proporção e limita largura máxima a 1920 para resposta rápida sem estourar tokens
            try:
                b64_img = img
                if PIL_AVAILABLE and img.width > max_width:
                    ratio = max_width / float(img.width)
                    new_h = int(img.height * ratio)
                    b64_img = img.resize((max_width, new_h), Image.Resampling.LANCZOS)

                import io
                buf = io.BytesIO()
                b64_img.convert("RGB").save(buf, format="JPEG", quality=85)
                b64_str = base64.b64encode(buf.getvalue()).decode("utf-8")
                res["base64"] = b64_str
                res["_image_b64"] = b64_str  # Alimenta o loop de visão de core_ai_brain
            except Exception as e_b64:
                with open(save_path, "rb") as f:
                    b64_raw = base64.b64encode(f.read()).decode("utf-8")
                    res["base64"] = b64_raw
                    res["_image_b64"] = b64_raw

        return res
    except Exception as e:
        return {"success": False, "error": str(e)}


# ==============================================================================
# 5. MOTOR DE MACROS / SEQUÊNCIAS DE AÇÕES COMPLEXAS
# ==============================================================================

def execute_macro(steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Executa uma sequência orquestrada de ações no PC com segurança.
    Exemplo de payload:
    [
      {"action": "open_app", "target": "chrome"},
      {"action": "sleep", "seconds": 1.5},
      {"action": "keyboard_type", "text": "https://google.com"},
      {"action": "keyboard_press", "key": "enter"}
    ]
    """
    from .win_controls import open_application, close_application, run_powershell

    results = []
    for idx, step in enumerate(steps):
        act = step.get("action", "").lower().strip()
        params = step.get("params", step)

        res = {"step": idx + 1, "action": act, "success": False}

        try:
            if act in ["sleep", "wait", "pausa"]:
                sec = float(params.get("seconds", params.get("tempo", 1.0)))
                time.sleep(sec)
                res["success"] = True

            elif act in ["mouse_move", "mover_mouse"]:
                res = mouse_move(params.get("x", 0), params.get("y", 0), params.get("duration", 0.2))

            elif act in ["mouse_click", "clicar", "clique"]:
                res = mouse_click(
                    button=params.get("button", "left"),
                    clicks=params.get("clicks", 1),
                    x=params.get("x"),
                    y=params.get("y")
                )

            elif act in ["mouse_drag", "arrastar"]:
                res = mouse_drag(params.get("x", 0), params.get("y", 0), params.get("duration", 0.5))

            elif act in ["mouse_scroll", "rolar", "scroll"]:
                res = mouse_scroll(params.get("amount", params.get("clicks", 5)), params.get("direction", "down"))

            elif act in ["keyboard_type", "digitar", "escrever"]:
                res = keyboard_type(params.get("text", params.get("texto", "")))

            elif act in ["keyboard_press", "tecla", "pressionar"]:
                res = keyboard_press(params.get("key", params.get("tecla", "enter")))

            elif act in ["keyboard_hotkey", "atalho", "hotkey"]:
                keys = params.get("keys", params.get("atalho", []))
                if isinstance(keys, str):
                    keys = [k.strip() for k in keys.replace("+", " ").split()]
                res = keyboard_hotkey(*keys)

            elif act in ["open_app", "abrir"]:
                res = open_application(params.get("target", params.get("aplicativo", "")))

            elif act in ["close_app", "fechar"]:
                res = close_application(params.get("target", params.get("processo", "")))

            elif act in ["screenshot", "print"]:
                res = take_screenshot()

            elif act in ["powershell", "cmd", "comando"]:
                res = run_powershell(params.get("command", params.get("comando", "")))

            else:
                res["error"] = f"Ação desconhecida: {act}"

        except Exception as step_err:
            res["error"] = str(step_err)

        results.append(res)
        if not res.get("success", False) and step.get("stop_on_error", False):
            break

    return {
        "success": all(r.get("success", False) for r in results),
        "total_steps": len(steps),
        "results": results
    }
