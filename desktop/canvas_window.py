"""
J.A.R.V.I.S. Desktop Canvas Window - Stark High-Tech HUD & Visualizer
Janela desktop nativa independente no Windows para gráficos, telemetria e visão.
"""

import os
import sys
import time
import subprocess

CANVAS_HTML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "canvas_ui.html")

def launch_canvas_window(mode: str = "charts"):
    """Inicia a janela Canvas holográfica de gráficos diretamente na tela principal do Windows via arquivo interno."""
    file_uri = f"file:///{CANVAS_HTML_PATH.replace(os.sep, '/')}"
    target_url = file_uri

    # Caminhos comuns dos navegadores Chromium no Windows
    chrome_candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")
    ]
    edge_candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
    ]

    browser_exe = None
    for p in chrome_candidates + edge_candidates:
        if os.path.exists(p):
            browser_exe = p
            break

    launched = False
    if browser_exe:
        try:
            # Lança como janela Desktop nativa sem abas nem barra de URL (--app)
            args = [
                browser_exe,
                f"--app={target_url}",
                "--window-size=1200,780",
                "--new-window"
            ]
            subprocess.Popen(args)
            launched = True
            print(f"[CanvasWindow] Canvas Desktop lançado com sucesso via {browser_exe} no monitor principal.")
        except Exception as eb:
            print(f"[CanvasWindow] Erro ao abrir com browser_exe: {eb}")

    if not launched:
        try:
            # Fallback nativo do shell do Windows
            os.startfile(target_url)
            launched = True
            print("[CanvasWindow] Canvas Desktop aberto via os.startfile no monitor principal.")
        except Exception as e_start:
            print(f"[CanvasWindow] Erro startfile: {e_start}")
            try:
                os.startfile(CANVAS_HTML_PATH)
                launched = True
            except Exception:
                pass

    # Trazer janela para o primeiro plano na área de trabalho principal
    try:
        time.sleep(0.6)
        import win32gui
        import win32con

        def enum_cb(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd).lower()
                if "canvas" in title or "j.a.r.v.i.s." in title:
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                    win32gui.SetForegroundWindow(hwnd)

        win32gui.EnumWindows(enum_cb, None)
    except Exception:
        pass

def launch_url_in_app_window(url: str, title: str = "J.A.R.V.I.S. Canvas"):
    """Abre uma URL qualquer numa janela nativa 'app' (sem abas/barra) via Chrome/Edge."""
    browser_exe = None
    for p in [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
    ]:
        if os.path.exists(p):
            browser_exe = p
            break

    args = [f"--app={url}", "--window-size=1240,820", "--new-window"]
    claimed_title = None
    if browser_exe:
        try:
            subprocess.Popen([browser_exe] + args)
            claimed_title = title.lower()
            print(f"[CanvasWindow] Painel aberto via {os.path.basename(browser_exe)}: {url}")
        except Exception as eb:
            print("[CanvasWindow] Erro ao abrir app-window:", eb)
    if not claimed_title:
        try:
            os.startfile(url)
        except Exception as e:
            print("[CanvasWindow] startfile falhou:", e)

    # Foco na área de trabalho principal após abrir
    try:
        time.sleep(0.8)
        import win32gui
        import win32con

        def enum_cb(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                t = win32gui.GetWindowText(hwnd)
                if claimed_title and (claimed_title in t.lower() or "j.a.r.v.i.s." in t.lower()):
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                    win32gui.SetForegroundWindow(hwnd)

        win32gui.EnumWindows(enum_cb, None)
    except Exception:
        pass

if __name__ == "__main__":
    m = sys.argv[1] if len(sys.argv) > 1 else "charts"
    launch_canvas_window(m)
