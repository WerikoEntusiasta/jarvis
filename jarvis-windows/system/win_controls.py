"""
Controlador Nativo do Sistema Windows (Apps, Mídia, Volume, Processos, PowerShell)
"""

import os
import subprocess
import ctypes
import webbrowser
from typing import Dict, Any

user32 = ctypes.windll.user32

# Códigos de teclas virtuais Win32
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002

def _send_vk(vk_code: int):
    user32.keybd_event(vk_code, 0, KEYEVENTF_EXTENDEDKEY, 0)
    user32.keybd_event(vk_code, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)

APP_MAP = {
    "google": "https://www.google.com",
    "youtube": "https://www.youtube.com",
    "gmail": "https://mail.google.com",
    "whatsapp": "https://web.whatsapp.com",
    "chrome": "chrome",
    "google chrome": "chrome",
    "navegador": "chrome",
    "spotify": "spotify",
    "musica": "spotify",
    "vscode": "code",
    "code": "code",
    "terminal": "wt",
    "cmd": "cmd",
    "powershell": "powershell",
    "calculadora": "calc",
    "calc": "calc",
    "bloco de notas": "notepad",
    "notepad": "notepad",
    "explorador": "explorer",
    "arquivos": "explorer",
    "discord": "discord",
    "steam": "steam"
}

def google_search(query: str, open_browser: bool = True) -> Dict[str, Any]:
    """Abre o Google Search no navegador com o termo pesquisado e retorna status."""
    import urllib.parse
    encoded = urllib.parse.quote_plus(query.strip())
    url = f"https://www.google.com/search?q={encoded}"
    try:
        if open_browser:
            webbrowser.open(url)
        return {
            "success": True,
            "action": "google_search",
            "query": query,
            "url": url,
            "info": f"Pesquisa por '{query}' aberta no Google com sucesso."
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

def open_application(app_name: str) -> Dict[str, Any]:
    norm = app_name.lower().strip()
    target = APP_MAP.get(norm, norm)
    try:
        if target.startswith("http://") or target.startswith("https://"):
            webbrowser.open(target)
            return {"success": True, "action": "open_url", "target": target}
        
        proc = subprocess.Popen(
            f"start \"\" \"{target}\"",
            shell=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        return {"success": True, "action": "open_app", "target": target}
    except Exception as e:
        return {"success": False, "error": str(e)}

def close_application(process_name: str) -> Dict[str, Any]:
    norm = process_name.lower().strip()
    target = APP_MAP.get(norm, norm)
    targets = [target]
    if not target.endswith(".exe"):
        targets.append(target + ".exe")
    if norm in ["calc", "calculadora"]:
        targets.extend(["calc.exe", "CalculatorApp.exe", "Calculator.exe"])

    last_out = ""
    for t in targets:
        try:
            res = subprocess.run(
                ["taskkill", "/F", "/IM", t],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            if res.returncode == 0:
                return {"success": True, "output": res.stdout.strip(), "killed": t}
            last_out = res.stderr.strip()
        except Exception as e:
            last_out = str(e)
    return {"success": False, "error": last_out}

def control_volume(action: str, steps: int = 2) -> Dict[str, Any]:
    act = action.lower().strip()
    if act in ["up", "aumentar", "+"]:
        for _ in range(steps):
            _send_vk(VK_VOLUME_UP)
        return {"success": True, "action": "volume_up", "steps": steps}
    elif act in ["down", "diminuir", "-"]:
        for _ in range(steps):
            _send_vk(VK_VOLUME_DOWN)
        return {"success": True, "action": "volume_down", "steps": steps}
    elif act in ["mute", "mudo", "desativar"]:
        _send_vk(VK_VOLUME_MUTE)
        return {"success": True, "action": "volume_mute"}
    return {"success": False, "error": f"Ação de volume inválida: {action}"}

def control_media(action: str) -> Dict[str, Any]:
    act = action.lower().strip()
    if act in ["play", "pause", "play_pause", "tocar", "pausar"]:
        _send_vk(VK_MEDIA_PLAY_PAUSE)
        return {"success": True, "action": "play_pause"}
    elif act in ["next", "avancar", "proxima"]:
        _send_vk(VK_MEDIA_NEXT_TRACK)
        return {"success": True, "action": "next_track"}
    elif act in ["prev", "anterior", "voltar"]:
        _send_vk(VK_MEDIA_PREV_TRACK)
        return {"success": True, "action": "prev_track"}
    elif act in ["stop", "parar"]:
        _send_vk(VK_MEDIA_STOP)
        return {"success": True, "action": "stop"}
    return {"success": False, "error": f"Ação de mídia inválida: {action}"}

def lock_workstation() -> Dict[str, Any]:
    try:
        ok = user32.LockWorkStation()
        return {"success": bool(ok), "action": "lock_workstation"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def shutdown_pc(seconds: int = 5) -> Dict[str, Any]:
    try:
        subprocess.run(["shutdown", "/s", "/t", str(seconds)], creationflags=subprocess.CREATE_NO_WINDOW)
        return {"success": True, "action": "shutdown", "seconds": seconds}
    except Exception as e:
        return {"success": False, "error": str(e)}

def restart_pc(seconds: int = 5) -> Dict[str, Any]:
    try:
        subprocess.run(["shutdown", "/r", "/t", str(seconds)], creationflags=subprocess.CREATE_NO_WINDOW)
        return {"success": True, "action": "restart", "seconds": seconds}
    except Exception as e:
        return {"success": False, "error": str(e)}

def sleep_pc() -> Dict[str, Any]:
    try:
        subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], creationflags=subprocess.CREATE_NO_WINDOW)
        return {"success": True, "action": "sleep"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def minimize_all() -> Dict[str, Any]:
    try:
        # Win+D toggle
        user32.keybd_event(0x5B, 0, 0, 0) # VK_LWIN down
        user32.keybd_event(0x44, 0, 0, 0) # 'D' down
        user32.keybd_event(0x44, 0, 2, 0) # 'D' up
        user32.keybd_event(0x5B, 0, 2, 0) # VK_LWIN up
        return {"success": True, "action": "minimize_all"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def run_powershell(command: str, timeout: int = 15) -> Dict[str, Any]:
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        return {
            "success": res.returncode == 0,
            "return_code": res.returncode,
            "stdout": res.stdout.strip(),
            "stderr": res.stderr.strip()
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Comando expirou após {timeout}s"}
    except Exception as e:
        return {"success": False, "error": str(e)}
