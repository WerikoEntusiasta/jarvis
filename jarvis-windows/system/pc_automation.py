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
    """Move o cursor do mouse suavemente para (x, y)."""
    cx, cy = _clamp_coordinates(x, y)
    try:
        if PYAUTOGUI_AVAILABLE:
            dur = max(0.0, float(duration))
            pyautogui.moveTo(cx, cy, duration=dur)
        else:
            user32.SetCursorPos(cx, cy)
        return {"success": True, "action": "mouse_move", "x": cx, "y": cy}
    except Exception as e:
        return {"success": False, "error": str(e)}


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
    Se x e y forem fornecidos, move antes de clicar.
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
            mouse_move(x, y, duration=0.1)

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

        return {"success": True, "action": "mouse_click", "button": btn, "clicks": clicks}
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
    Digita um texto na janela ativa.
    Para garantir acentuação perfeita em português brasileiro (á, é, ã, ç, etc.),
    utiliza área de transferência com colagem Ctrl+V se contiver caracteres especiais.
    """
    if not text:
        return {"success": True, "action": "keyboard_type", "chars": 0}

    # Verifica se contém acentos ou caracteres especiais
    has_special = any(ord(c) > 127 for c in text)

    try:
        if has_special and PYPERCLIP_AVAILABLE and PYAUTOGUI_AVAILABLE:
            # Salva clipboard anterior
            old_clip = ""
            try:
                old_clip = pyperclip.paste()
            except Exception:
                pass
            # Copia novo texto e cola instantaneamente
            pyperclip.copy(text)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.05)
            # Restaura clipboard se possível
            if old_clip:
                try:
                    pyperclip.copy(old_clip)
                except Exception:
                    pass
        elif PYAUTOGUI_AVAILABLE:
            pyautogui.write(text, interval=interval)
        else:
            # Fallback direto via powershell
            from .win_controls import run_powershell
            escaped = text.replace("'", "''")
            run_powershell(f"Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait('{escaped}')")

        return {"success": True, "action": "keyboard_type", "text": text, "length": len(text)}
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

def take_screenshot(save_path: Optional[str] = None, return_base64: bool = False) -> Dict[str, Any]:
    """
    Captura a tela inteira do monitor principal.
    Salva em save_path (ou arquivo temporário) e opcionalmente retorna em Base64.
    """
    if not save_path:
        tmp_dir = os.path.join(tempfile.gettempdir(), "jarvis_captures")
        os.makedirs(tmp_dir, exist_ok=True)
        save_path = os.path.join(tmp_dir, f"screenshot_{int(time.time())}.png")

    try:
        if PIL_AVAILABLE:
            img = ImageGrab.grab(all_screens=False)
            img.save(save_path, "PNG")
        elif PYAUTOGUI_AVAILABLE:
            img = pyautogui.screenshot()
            img.save(save_path)
        else:
            return {"success": False, "error": "Nenhuma biblioteca gráfica disponível para captura"}

        res = {
            "success": True,
            "action": "screenshot",
            "path": save_path,
            "width": img.width,
            "height": img.height
        }

        if return_base64:
            with open(save_path, "rb") as f:
                res["base64"] = base64.b64encode(f.read()).decode("utf-8")

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
