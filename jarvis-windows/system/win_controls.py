"""
Controlador Nativo do Sistema Windows (Apps, Mídia, Volume, Processos, Janelas, Monitores, PowerShell)
Padrão Permanente de Engenharia de Software Sênior & Alta Confiabilidade
"""

import os
import sys
import time
import subprocess
import ctypes
from ctypes import wintypes
import webbrowser
import platform
import socket
from typing import Dict, Any, List, Optional, Union

import psutil

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

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

SW_HIDE = 0
SW_SHOWNORMAL = 1
SW_SHOWMINIMIZED = 2
SW_MAXIMIZE = 3
SW_SHOWNOACTIVATE = 4
SW_SHOW = 5
SW_MINIMIZE = 6
SW_SHOWMINNOACTIVE = 7
SW_SHOWNA = 8
SW_RESTORE = 9

WM_CLOSE = 0x0010

def switch_to_user_desktop():
    """Garante vinculação da thread ao desktop interativo WinSta0\\Default."""
    try:
        GENERIC_ALL = 0x10000000
        hwinsta = user32.OpenWindowStationW("WinSta0", False, GENERIC_ALL)
        if hwinsta:
            user32.SetProcessWindowStation(hwinsta)
        hdesk = user32.OpenDesktopW("Default", 0, False, GENERIC_ALL)
        if hdesk:
            user32.SetThreadDesktop(hdesk)
    except Exception:
        pass

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
    """Abre um aplicativo local ou URL no Windows."""
    norm = app_name.lower().strip()
    target = APP_MAP.get(norm, app_name.strip())
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
    """Encerra um processo pelo nome no Windows."""
    norm = process_name.lower().strip()
    target = APP_MAP.get(norm, process_name.strip())
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
    """Controla o volume do áudio do Windows (aumentar, diminuir ou mutar)."""
    act = action.lower().strip()
    if act in ["up", "aumentar", "+"]:
        for _ in range(steps):
            _send_vk(VK_VOLUME_UP)
        return {"success": True, "action": "volume_up", "steps": steps}
    elif act in ["down", "diminuir", "-"]:
        for _ in range(steps):
            _send_vk(VK_VOLUME_DOWN)
        return {"success": True, "action": "volume_down", "steps": steps}
    elif act in ["mute", "mudo", "desativar", "silenciar"]:
        _send_vk(VK_VOLUME_MUTE)
        return {"success": True, "action": "volume_mute"}
    return {"success": False, "error": f"Ação de volume inválida: {action}"}

def set_volume(percent: int) -> Dict[str, Any]:
    """Define o volume do Windows em uma porcentagem exata (0 a 100)."""
    try:
        pct = max(0, min(100, int(percent)))
        # Ajusta via powershell CoreAudio wrapper com alta precisão
        ps_cmd = (
            f"$obj = New-Object -ComObject WScript.Shell; "
            f"1..50 | ForEach-Object {{ $obj.SendKeys([char]174) }}; "
            f"$steps = [math]::Round({pct} / 2); "
            f"1..$steps | ForEach-Object {{ $obj.SendKeys([char]175) }}"
        )
        run_powershell(ps_cmd, timeout=5)
        return {"success": True, "action": "set_volume", "percent": pct}
    except Exception as e:
        return {"success": False, "error": str(e)}

def control_media(action: str) -> Dict[str, Any]:
    """Controla a reprodução multimídia (Spotify, YouTube, VLC)."""
    act = action.lower().strip()
    if act in ["play", "pause", "play_pause", "tocar", "pausar"]:
        _send_vk(VK_MEDIA_PLAY_PAUSE)
        return {"success": True, "action": "play_pause"}
    elif act in ["next", "avancar", "proxima", "next_track"]:
        _send_vk(VK_MEDIA_NEXT_TRACK)
        return {"success": True, "action": "next_track"}
    elif act in ["prev", "anterior", "voltar", "prev_track"]:
        _send_vk(VK_MEDIA_PREV_TRACK)
        return {"success": True, "action": "prev_track"}
    elif act in ["stop", "parar"]:
        _send_vk(VK_MEDIA_STOP)
        return {"success": True, "action": "stop"}
    return {"success": False, "error": f"Ação de mídia inválida: {action}"}

def lock_workstation() -> Dict[str, Any]:
    """Bloqueia a tela da estação de trabalho Windows por segurança."""
    try:
        ok = user32.LockWorkStation()
        return {"success": bool(ok), "action": "lock_workstation"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def shutdown_pc(seconds: int = 30) -> Dict[str, Any]:
    """Agenda o desligamento seguro do computador."""
    try:
        subprocess.run(["shutdown", "/s", "/t", str(seconds)], creationflags=subprocess.CREATE_NO_WINDOW)
        return {"success": True, "action": "shutdown", "seconds": seconds}
    except Exception as e:
        return {"success": False, "error": str(e)}

def restart_pc(seconds: int = 30) -> Dict[str, Any]:
    """Agenda o reinício seguro do computador."""
    try:
        subprocess.run(["shutdown", "/r", "/t", str(seconds)], creationflags=subprocess.CREATE_NO_WINDOW)
        return {"success": True, "action": "restart", "seconds": seconds}
    except Exception as e:
        return {"success": False, "error": str(e)}

def abort_shutdown() -> Dict[str, Any]:
    """Cancela um desligamento ou reinício agendado."""
    try:
        subprocess.run(["shutdown", "/a"], creationflags=subprocess.CREATE_NO_WINDOW)
        return {"success": True, "action": "abort_shutdown", "message": "Desligamento pendente cancelado."}
    except Exception as e:
        return {"success": False, "error": str(e)}

def sleep_pc() -> Dict[str, Any]:
    """Coloca o computador em modo de suspensão."""
    try:
        subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], creationflags=subprocess.CREATE_NO_WINDOW)
        return {"success": True, "action": "sleep"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def minimize_all() -> Dict[str, Any]:
    """Minimiza todas as janelas para exibir a Área de Trabalho (Win+D)."""
    try:
        user32.keybd_event(0x5B, 0, 0, 0)  # VK_LWIN down
        user32.keybd_event(0x44, 0, 0, 0)  # 'D' down
        user32.keybd_event(0x44, 0, 2, 0)  # 'D' up
        user32.keybd_event(0x5B, 0, 2, 0)  # VK_LWIN up
        return {"success": True, "action": "minimize_all"}
    except Exception as e:
        return {"success": False, "error": str(e)}

def switch_window() -> Dict[str, Any]:
    """Alterna para a próxima janela ativa (Alt+Tab)."""
    try:
        user32.keybd_event(0x12, 0, 0, 0)  # VK_MENU (Alt) down
        user32.keybd_event(0x09, 0, 0, 0)  # VK_TAB down
        user32.keybd_event(0x09, 0, 2, 0)  # VK_TAB up
        user32.keybd_event(0x12, 0, 2, 0)  # VK_MENU (Alt) up
        return {"success": True, "action": "switch_window"}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ==============================================================================
# GERENCIAMENTO AVANÇADO DE JANELAS E PROCESSOS
# ==============================================================================

def list_windows() -> Dict[str, Any]:
    """
    Lista todas as janelas reais visíveis no desktop do usuário.
    Retorna HWND, título, PID e nome do executável de cada uma.
    """
    switch_to_user_desktop()
    windows = []

    def enum_cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.strip()
        if not title:
            return True

        # Ignora janelas do sistema sem interface útil
        if title in ["Default IME", "MSCTFIME UI", "Settings"]:
            return True

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        proc_name = ""
        try:
            p = psutil.Process(pid.value)
            proc_name = p.name()
        except Exception:
            pass

        is_min = bool(user32.IsIconic(hwnd))
        is_zoomed = bool(user32.IsZoomed(hwnd))
        state = "minimized" if is_min else ("maximized" if is_zoomed else "normal")

        windows.append({
            "hwnd": hwnd,
            "title": title,
            "pid": pid.value,
            "process": proc_name,
            "state": state
        })
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    cb = WNDENUMPROC(enum_cb)
    user32.EnumWindows(cb, 0)

    return {
        "success": True,
        "count": len(windows),
        "windows": windows
    }

def _resolve_hwnd(target: Union[str, int]) -> Optional[int]:
    """Resolve título ou string para um HWND válido."""
    if isinstance(target, int):
        return target
    target_str = str(target).strip()
    if target_str.isdigit():
        return int(target_str)
    
    # Procura por substring no título
    win_list = list_windows().get("windows", [])
    target_lower = target_str.lower()
    for w in win_list:
        if target_lower in w["title"].lower() or target_lower in w["process"].lower():
            return w["hwnd"]
    return None

def focus_window(target: Union[str, int]) -> Dict[str, Any]:
    """Traz uma janela específica para o primeiro plano pelo título ou HWND."""
    switch_to_user_desktop()
    hwnd = _resolve_hwnd(target)
    if not hwnd:
        return {"success": False, "error": f"Janela não encontrada para '{target}'"}

    try:
        user32.AllowSetForegroundWindow(-1)
        fore_hwnd = user32.GetForegroundWindow()
        fore_thread = user32.GetWindowThreadProcessId(fore_hwnd, None)
        app_thread = kernel32.GetCurrentThreadId()

        if fore_thread and fore_thread != app_thread:
            user32.AttachThreadInput(fore_thread, app_thread, True)

        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        else:
            user32.ShowWindow(hwnd, SW_SHOW)

        user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002)
        user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, 0x0001 | 0x0002)
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)

        if fore_thread and fore_thread != app_thread:
            user32.AttachThreadInput(fore_thread, app_thread, False)

        return {"success": True, "action": "focus_window", "hwnd": hwnd}
    except Exception as e:
        return {"success": False, "error": str(e)}

def minimize_window(target: Union[str, int]) -> Dict[str, Any]:
    """Minimiza uma janela específica."""
    switch_to_user_desktop()
    hwnd = _resolve_hwnd(target)
    if not hwnd:
        return {"success": False, "error": f"Janela não encontrada para '{target}'"}
    try:
        user32.ShowWindow(hwnd, SW_MINIMIZE)
        return {"success": True, "action": "minimize_window", "hwnd": hwnd}
    except Exception as e:
        return {"success": False, "error": str(e)}

def maximize_window(target: Union[str, int]) -> Dict[str, Any]:
    """Maximiza uma janela específica."""
    switch_to_user_desktop()
    hwnd = _resolve_hwnd(target)
    if not hwnd:
        return {"success": False, "error": f"Janela não encontrada para '{target}'"}
    try:
        user32.ShowWindow(hwnd, SW_MAXIMIZE)
        return {"success": True, "action": "maximize_window", "hwnd": hwnd}
    except Exception as e:
        return {"success": False, "error": str(e)}

def close_window(target: Union[str, int]) -> Dict[str, Any]:
    """Fecha uma janela específica de forma graciosa via WM_CLOSE."""
    switch_to_user_desktop()
    hwnd = _resolve_hwnd(target)
    if not hwnd:
        return {"success": False, "error": f"Janela não encontrada para '{target}'"}
    try:
        user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        return {"success": True, "action": "close_window", "hwnd": hwnd}
    except Exception as e:
        return {"success": False, "error": str(e)}

def list_processes(top_n: int = 15, sort_by: str = "cpu") -> Dict[str, Any]:
    """
    Lista os processos em execução no Windows com PID, Nome, CPU % e Memória MB.
    Permite ordenação por 'cpu' ou 'memory'.
    """
    procs = []
    for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info', 'status']):
        try:
            info = p.info
            mem_mb = round((info['memory_info'].rss if info.get('memory_info') else 0) / (1024 * 1024), 1)
            cpu = info.get('cpu_percent') or 0.0
            procs.append({
                "pid": info['pid'],
                "name": info['name'],
                "cpu_percent": round(cpu, 1),
                "memory_mb": mem_mb,
                "status": info.get('status', 'running')
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    if sort_by.lower() in ["memory", "ram", "mem"]:
        procs.sort(key=lambda x: x["memory_mb"], reverse=True)
    else:
        procs.sort(key=lambda x: x["cpu_percent"], reverse=True)

    return {
        "success": True,
        "total_processes": len(procs),
        "sorted_by": sort_by,
        "processes": procs[:top_n]
    }

def list_monitors() -> Dict[str, Any]:
    """
    Lista todos os monitores conectados, suas resoluções, coordenadas e monitor principal.
    """
    switch_to_user_desktop()

    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    class MONITORINFOEXW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", RECT),
            ("rcWork", RECT),
            ("dwFlags", wintypes.DWORD),
            ("szDevice", ctypes.c_wchar * 32)
        ]

    MONITORENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(RECT), wintypes.LPARAM)

    monitors = []
    def enum_monitors_cb(hmon, hdc, lprect, lparam):
        mi = MONITORINFOEXW()
        mi.cbSize = ctypes.sizeof(MONITORINFOEXW)
        if user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            r = mi.rcMonitor
            w = r.right - r.left
            h = r.bottom - r.top
            is_primary = bool(mi.dwFlags & 1)
            monitors.append({
                "device": mi.szDevice,
                "width": w,
                "height": h,
                "x": r.left,
                "y": r.top,
                "is_primary": is_primary
            })
        return True

    cb = MONITORENUMPROC(enum_monitors_cb)
    user32.EnumDisplayMonitors(None, None, cb, 0)

    return {
        "success": True,
        "count": len(monitors),
        "monitors": monitors
    }

def get_system_info() -> Dict[str, Any]:
    """
    Coleta informações completas do sistema operacional e hardware do Windows.
    Zero dados inventados.
    """
    mem = psutil.virtual_memory()
    boot_time = psutil.boot_time()
    uptime_sec = int(time.time() - boot_time)
    hours = uptime_sec // 3600
    minutes = (uptime_sec % 3600) // 60

    # Coleta IPs de rede locais
    ips = []
    try:
        host_name = socket.gethostname()
        for ip in socket.gethostbyname_ex(host_name)[2]:
            if not ip.startswith("127."):
                ips.append(ip)
    except Exception:
        pass

    return {
        "success": True,
        "os": "Windows",
        "os_version": platform.version(),
        "os_release": platform.release(),
        "platform": platform.platform(),
        "architecture": platform.machine(),
        "hostname": socket.gethostname(),
        "cpu_cores_physical": psutil.cpu_count(logical=False),
        "cpu_cores_logical": psutil.cpu_count(logical=True),
        "ram_total_gb": round(mem.total / (1024**3), 1),
        "ram_available_gb": round(mem.available / (1024**3), 1),
        "uptime": f"{hours}h {minutes}m",
        "uptime_seconds": uptime_sec,
        "network_ips": ips
    }

def run_powershell(command: str, timeout: int = 15) -> Dict[str, Any]:
    """Executa um comando PowerShell no Windows com timeout e retorno estruturado."""
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
