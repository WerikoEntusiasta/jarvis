"""
Ponto de Entrada Principal — J.A.R.V.I.S. Windows v2 (Independente)
"""

import sys
import os
import traceback
import time

if hasattr(sys, "_MEIPASS"):
    BASE_DIR = os.path.abspath(sys._MEIPASS)
    proc_exe = os.path.join(BASE_DIR, "PyQt6", "Qt6", "bin", "QtWebEngineProcess.exe")
    if os.path.exists(proc_exe):
        os.environ["QTWEBENGINEPROCESS_PATH"] = proc_exe
    res_dir = os.path.join(BASE_DIR, "PyQt6", "Qt6", "resources")
    if os.path.exists(res_dir):
        os.environ["QTWEBENGINE_RESOURCES_PATH"] = res_dir
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

for p in [BASE_DIR, "C:/JARVIS", "C:/JARVIS/jarvis-windows"]:
    if p not in sys.path:
        sys.path.insert(0, p)

LOG_FILE = "C:/JARVIS/jarvis_windows.log"

def _log(msg):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass

def _uncaught_handler(t, v, tb):
    _log(f"CRASH: {t} {v} {''.join(traceback.format_tb(tb))}")
sys.excepthook = _uncaught_handler
import socket
import threading
import ctypes
import atexit

# IMPORTANTE: QtWebEngineWidgets DEVE ser importado antes de QApplication
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QAction, QColor, QPixmap, QPainter, QGuiApplication
from PyQt6.QtCore import Qt

from config.settings import MUTEX_NAME, IPC_PORT, LOCAL_PORT
from core.local_server import start_local_server
from core.network_client import JarvisNetworkClient
from voice.voice_engine import JarvisVoiceEngine
from ui.hud_window import JarvisHUDWindow

_MUTEX_HANDLE = None

def _try_contact_existing_instance() -> bool:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.0)
        s.connect(("127.0.0.1", IPC_PORT))
        s.sendall(b"SHOW\n")
        s.close()
        return True
    except Exception:
        return False

def ensure_single_instance() -> bool:
    global _MUTEX_HANDLE
    kernel32 = ctypes.windll.kernel32
    _MUTEX_HANDLE = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    last_error = kernel32.GetLastError()
    if last_error == 183:  # ERROR_ALREADY_EXISTS
        print("[SingleInstance] Outra instância detectada. Tentando contato via IPC...")
        contacted = _try_contact_existing_instance()
        if not contacted:
            for _ in range(5):
                time.sleep(0.4)
                contacted = _try_contact_existing_instance()
                if contacted:
                    break
        if contacted:
            print("[SingleInstance] Instância ativa contatada com sucesso. Encerrando duplicata.")
            return False

        current_pid = os.getpid()
        try:
            import psutil
            for p in psutil.process_iter(['pid', 'name']):
                try:
                    pname = (p.info.get('name') or '').upper()
                    if p.info.get('pid') != current_pid and 'JARVIS' in pname:
                        print(f"[SingleInstance] Processo {pname} (PID {p.info['pid']}) já está ativo no Windows. Abortando duplicata.")
                        return False
                except Exception:
                    pass
        except Exception:
            pass

        print("[SingleInstance] Instância anterior inativa ou sem IPC. Assumindo lock órfão e iniciando...")
        return True
    return True

def release_mutex():
    global _MUTEX_HANDLE
    if _MUTEX_HANDLE:
        ctypes.windll.kernel32.CloseHandle(_MUTEX_HANDLE)
        _MUTEX_HANDLE = None

atexit.register(release_mutex)

def create_hud_icon() -> QIcon:
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#00d4ff"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(4, 4, 24, 24)
    painter.setBrush(QColor("#0a0f18"))
    painter.drawEllipse(10, 10, 12, 12)
    painter.setBrush(QColor("#00ffaa"))
    painter.drawEllipse(13, 13, 6, 6)
    painter.end()
    return QIcon(pixmap)

def force_window_to_front(hwnd: int):
    try:
        user32 = ctypes.windll.user32
        user32.AllowSetForegroundWindow(-1)
        user32.ShowWindow(hwnd, 9)
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
    except Exception as e:
        _log(f"force_window_to_front erro: {e}")

def start_ipc_server(hud_window: JarvisHUDWindow):
    def _loop():
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind(("127.0.0.1", IPC_PORT))
            server.listen(5)
            while True:
                conn, _ = server.accept()
                data = conn.recv(1024)
                if b"SHOW" in data:
                    from PyQt6.QtCore import QTimer
                    def _show_act():
                        primary = QGuiApplication.primaryScreen()
                        if primary:
                            hud_window.setScreen(primary)
                        if hud_window.isMinimized():
                            hud_window.showNormal()
                        else:
                            hud_window.show()
                        hud_window.raise_()
                        hud_window.activateWindow()
                        try:
                            force_window_to_front(int(hud_window.winId()))
                        except Exception:
                            pass
                    QTimer.singleShot(0, _show_act)
                elif b"RELOAD" in data:
                    from PyQt6.QtCore import QTimer, QUrl
                    import time
                    def _force_reload():
                        hud_window.web_view.setUrl(QUrl(f"http://127.0.0.1:{LOCAL_PORT}/?_t={int(time.time()*1000)}"))
                    QTimer.singleShot(0, _force_reload)
                conn.close()
        except Exception:
            pass

    t = threading.Thread(target=_loop, daemon=True, name="JarvisIpcServer")
    t.start()

def switch_to_user_desktop():
    try:
        user32 = ctypes.windll.user32
        GENERIC_ALL = 0x10000000
        hwinsta = user32.OpenWindowStationW("WinSta0", False, GENERIC_ALL)
        if hwinsta:
            user32.SetProcessWindowStation(hwinsta)
            _log("ProcessWindowStation vinculado a 'WinSta0'.")
        hdesk = user32.OpenDesktopW("Default", 0, False, GENERIC_ALL)
        if hdesk:
            user32.SetThreadDesktop(hdesk)
            _log("Thread desktop comutado para 'Default' (Monitor Físico).")
        else:
            _log("OpenDesktop 'Default' falhou.")
    except Exception as e:
        _log(f"Erro ao comutar desktop: {e}")

def main():
    _log("main() iniciada")
    switch_to_user_desktop()
    if not ensure_single_instance():
        _log("ensure_single_instance() retornou False -> saindo")
        sys.exit(0)

    _log("Criando QApplication...")
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
        "--autoplay-policy=no-user-gesture-required "
        "--use-fake-ui-for-media-stream "
        "--ignore-certificate-errors "
        "--allow-running-insecure-content "
        "--disable-web-security "
        "--disable-features=SpeechRecognition "
        "--enable-gpu-rasterization"
    )
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    _log("Iniciando Servidor Local 100% Independente...")
    start_local_server(LOCAL_PORT)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    icon = create_hud_icon()
    app.setWindowIcon(icon)

    _log("Criando componentes de voz...")
    try:
        voice = JarvisVoiceEngine()
        _log("JarvisVoiceEngine criado com sucesso.")
    except Exception as e:
        _log(f"Erro ao criar JarvisVoiceEngine: {e}")
        voice = None

    _log("Criando componentes de rede...")
    try:
        network = JarvisNetworkClient()
        _log("JarvisNetworkClient criado com sucesso.")
    except Exception as e:
        _log(f"Erro ao criar JarvisNetworkClient: {e}")
        network = None

    _log("Criando JarvisHUDWindow...")
    try:
        hud = JarvisHUDWindow(network_client=network, voice_engine=voice)
        _log("JarvisHUDWindow criada com sucesso.")
    except Exception as e:
        _log(f"Erro fatal ao criar JarvisHUDWindow: {e}")
        raise

    # Conecta eventos de rede e voz à UI
    def _on_network_cmd(cmd):
        act = cmd.get('action', '')
        params = cmd.get('params', {})
        print(f"[JarvisDesktop] Executando comando local: {act}")
        # Injeta alerta visual no HUD na thread principal
        try:
            from PyQt6.QtCore import QTimer
            safe_text = str(act).replace("'", "\\'")
            QTimer.singleShot(0, lambda: hud.web_view.page().runJavaScript(f"if (window.showJarvisToast) window.showJarvisToast('Comando: {safe_text}');"))
        except Exception:
            pass
    if network:
        network.on_command = _on_network_cmd

    # Hotkey global: abre/mostra o HUD ou ativa microfone se já visível
    def _on_hotkey():
        from PyQt6.QtCore import QTimer
        def _act():
            if not hud.isVisible() or hud.isMinimized():
                hud.show()
                hud.raise_()
                hud.activateWindow()
            else:
                hud.trigger_mic()
        QTimer.singleShot(0, _act)
    if voice:
        voice.on_hotkey = _on_hotkey

    def _on_wake():
        from PyQt6.QtCore import QTimer
        def _act():
            if not hud.isVisible() or hud.isMinimized():
                hud.showMaximized()
            hud.raise_()
            hud.activateWindow()
            try:
                ctypes.windll.user32.SetForegroundWindow(int(hud.winId()))
            except Exception:
                pass
            hud.web_view.page().runJavaScript("if (window.showJarvisToast) window.showJarvisToast('🎙 J.A.R.V.I.S. Ouvindo...');")
        QTimer.singleShot(0, _act)
    if voice:
        voice.on_wake_word = _on_wake

    def _on_speech(txt):
        from PyQt6.QtCore import QTimer
        safe = txt.replace("'", "\\'").replace('"', '\\"').replace('\n', ' ')
        js = (
            f"if (window.showJarvisToast) window.showJarvisToast('Senhor: {safe}'); "
            f"const inp = document.getElementById('user-input'); if (inp) inp.value = '{safe}'; "
            f"const sub = document.getElementById('live-subtitle'); if (sub) sub.innerText = '{safe[:95]}';"
        )
        QTimer.singleShot(0, lambda: hud.web_view.page().runJavaScript(js))
    if voice:
        voice.on_speech_recognized = _on_speech

    def _on_reply(rep):
        from PyQt6.QtCore import QTimer
        safe = rep.replace("'", "\\'").replace('"', '\\"').replace('\n', ' ')
        sub_safe = safe[:95]
        js = (
            f"if (window.showJarvisToast) window.showJarvisToast('J.A.R.V.I.S.: {safe}'); "
            f"const el = document.getElementById('live-subtitle'); if (el) el.innerText = '{sub_safe}'; "
            f"if (window.openRightSidebarWithContent) window.openRightSidebarWithContent('Comando de Voz', '{safe}');"
        )
        QTimer.singleShot(0, lambda: hud.web_view.page().runJavaScript(js))
    if voice:
        voice.on_speech_reply = _on_reply

    # Inicia threads de segundo plano
    if network:
        network.start()
    if voice:
        voice.start()
    start_ipc_server(hud)

    # 3. System Tray Icon
    tray = QSystemTrayIcon(icon, app)
    tray.setToolTip("J.A.R.V.I.S. Windows v2 (Conectado)")
    tray_menu = QMenu()

    action_show = QAction("Abrir HUD (Ctrl+Espaço)", tray_menu)
    action_show.triggered.connect(lambda: (hud.show(), hud.raise_(), hud.activateWindow()))
    tray_menu.addAction(action_show)

    action_telem = QAction("Ver Telemetria", tray_menu)
    action_telem.triggered.connect(lambda: (hud.show(), hud.raise_(), hud.activateWindow()))
    tray_menu.addAction(action_telem)

    tray_menu.addSeparator()
    def shutdown_all():
        _log("Encerrando J.A.R.V.I.S. Windows e liberando recursos...")
        try:
            if voice:
                voice.stop()
        except Exception:
            pass
        try:
            if network:
                network.stop()
        except Exception:
            pass
        try:
            from vision import get_vision_engine
            get_vision_engine().stop()
        except Exception:
            pass
        try:
            release_mutex()
        except Exception:
            pass
        _log("Recursos liberados com sucesso.")

    app.aboutToQuit.connect(shutdown_all)

    action_quit = QAction("Encerrar J.A.R.V.I.S.", tray_menu)
    action_quit.triggered.connect(app.quit)
    tray_menu.addAction(action_quit)

    tray.setContextMenu(tray_menu)
    tray.activated.connect(lambda reason: hud.show() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
    tray.show()

    primary = QGuiApplication.primaryScreen()
    if primary:
        hud.setScreen(primary)
    hud.showMaximized()
    hud.raise_()
    hud.activateWindow()
    try:
        hwnd = int(hud.winId())
        force_window_to_front(hwnd)
        _log(f"Janela HUD (HWND {hwnd}) posicionada no monitor principal com force_window_to_front.")
    except Exception as e:
        _log(f"Erro ao registrar HWND: {e}")
    _log("hud.show() chamado com sucesso. Iniciando app.exec()...")
    print("[JarvisDesktop] J.A.R.V.I.S. Windows v2 iniciado com sucesso.")
    ret = app.exec()
    _log(f"app.exec() finalizou com código {ret}")
    sys.exit(ret)

if __name__ == "__main__":
    main()
