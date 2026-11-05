"""
Janela Imersiva J.A.R.V.I.S. Windows — Interface Idêntica ao WebUI (Nativa & Independente)
Incorpora o Stark HUD com aceleração gráfica, hotkeys globais e permissões de microfone/áudio nativas.
"""

import sys
import os
import time
import threading
from PyQt6.QtCore import Qt, QUrl, QPoint, QTimer, pyqtSignal, QObject, QEvent
from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame
from PyQt6.QtGui import QColor, QIcon, QKeySequence, QShortcut, QCursor
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings, QWebEngineProfile, QWebEnginePage, QWebEngineScript

try:
    from config.settings import CORE_URL
    from system.hardware_monitor import get_system_telemetry
except ImportError:
    from ..config.settings import CORE_URL
    from ..system.hardware_monitor import get_system_telemetry

def _log(msg):
    try:
        log_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "jarvis_windows.log")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass

class JarvisWebPage(QWebEnginePage):
    def certificateError(self, error):
        _log(f"[SSL Cert Error Ignorado] {error.errorDescription()} para {error.url().toString()}")
        error.acceptCertificate()
        return True

    def javaScriptConsoleMessage(self, level, message, line_number, source_id):
        _log(f"[JS Console] {message} (linha {line_number} em {source_id})")

class JarvisHUDWindow(QMainWindow):
    def __init__(self, network_client=None, voice_engine=None):
        super().__init__()
        self.network = network_client
        self.voice = voice_engine
        self._drag_pos = QPoint()

        self._setup_window_flags()
        self._init_ui()
        self._setup_shortcuts()
        self._start_bridge_timer()

    def _setup_window_flags(self):
        self.setWindowTitle("J.A.R.V.I.S. High-Tech Interface - Stark HUD")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Window
        )
        self.setStyleSheet("background-color: #010614;")
        self.setMouseTracking(True)

        # Garante foco no Monitor Principal (Primary Display - 2560x1440)
        from PyQt6.QtGui import QGuiApplication
        primary = QGuiApplication.primaryScreen()
        screen = primary.availableGeometry() if primary else self.screen().availableGeometry()
        self.resize(1600, 900)
        self.move(
            screen.x() + max(0, (screen.width() - 1600) // 2),
            screen.y() + max(0, (screen.height() - 900) // 2)
        )

    def _init_ui(self):
        self.central_widget = QWidget(self)
        self.central_widget.setMouseTracking(True)
        self.central_widget.setStyleSheet("background-color: #010614; margin: 0; padding: 0;")
        self.central_layout = QVBoxLayout(self.central_widget)
        self.central_layout.setContentsMargins(0, 0, 0, 0)
        self.central_layout.setSpacing(0)

        # 1. Barra de Controle Superior Stark Ultra-Discreta (Arrastável nativamente)
        self.top_control_bar = QFrame(self.central_widget)
        self.top_control_bar.setFixedHeight(28)
        self.top_control_bar.setMouseTracking(True)
        self.top_control_bar.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(1, 6, 20, 0.95), stop:0.5 rgba(3, 20, 56, 0.95), stop:1 rgba(1, 6, 20, 0.95));
                border-bottom: 1px solid rgba(0, 240, 255, 0.25);
            }
            QLabel {
                color: #00f0ff;
                font-size: 10px;
                font-weight: 800;
                letter-spacing: 2px;
                font-family: 'Space Grotesk', 'Segoe UI', sans-serif;
            }
            QPushButton {
                background: transparent;
                border: none;
                color: #94a3b8;
                font-size: 11px;
                font-weight: bold;
                padding: 2px 8px;
            }
            QPushButton:hover {
                color: #00f0ff;
                background: rgba(0, 240, 255, 0.15);
            }
        """)

        top_layout = QHBoxLayout(self.top_control_bar)
        top_layout.setContentsMargins(12, 0, 8, 0)
        top_layout.setSpacing(8)

        self.title_label = QLabel("⚡ J.A.R.V.I.S. STARK HUD OS • DESKTOP INDEPENDENTE", self.top_control_bar)
        self.title_label.setMouseTracking(True)
        top_layout.addWidget(self.title_label)
        top_layout.addStretch()

        btn_reload = QPushButton("🔄 F5", self.top_control_bar)
        btn_reload.setToolTip("Recarregar HUD (F5)")
        btn_reload.clicked.connect(self.reload_hud)
        top_layout.addWidget(btn_reload)

        btn_mic = QPushButton("🎙 F2 Falar", self.top_control_bar)
        btn_mic.setToolTip("Ativar/Desativar Microfone (F2)")
        btn_mic.clicked.connect(self.trigger_mic)
        top_layout.addWidget(btn_mic)

        btn_min = QPushButton("🗕", self.top_control_bar)
        btn_min.setToolTip("Minimizar na Bandeja")
        btn_min.clicked.connect(self.hide)
        top_layout.addWidget(btn_min)

        self.btn_max = QPushButton("❐", self.top_control_bar)
        self.btn_max.setToolTip("Maximizar / Restaurar Janela (Duplo clique na barra)")
        self.btn_max.clicked.connect(self._toggle_maximize)
        top_layout.addWidget(self.btn_max)

        btn_close = QPushButton("✕", self.top_control_bar)
        btn_close.setToolTip("Ocultar HUD (Ctrl+Espaço para reabrir)")
        btn_close.setStyleSheet("QPushButton:hover { color: #ff0055; background: rgba(255, 0, 85, 0.2); }")
        btn_close.clicked.connect(self.hide)
        top_layout.addWidget(btn_close)

        # Instala filtro de eventos na barra e no título para captura de arrasto DWM e duplo-clique
        self.top_control_bar.installEventFilter(self)
        self.title_label.installEventFilter(self)

        self.central_layout.addWidget(self.top_control_bar)

        # 2. WebEngineView Embutido (Renderizador gráfico de alta performance)
        self.web_view = QWebEngineView(self.central_widget)
        self.page = JarvisWebPage(self.web_view)
        self.web_view.setPage(self.page)

        # Injeta script defensivo antes de qualquer código da página rodar
        bootstrap_script = QWebEngineScript()
        bootstrap_script.setSourceCode("""
            /* speech recognition habilitado */
            window.__JARVIS_DESKTOP_STANDALONE = true;
            try {
                localStorage.setItem('jarvis_session_token', '8145760953033109');
                localStorage.setItem('jarvis_client_id', 'desktop_windows_standalone');
            } catch(e) {}
        """)
        bootstrap_script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        bootstrap_script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        self.page.scripts().insert(bootstrap_script)

        settings = self.web_view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.Accelerated2dCanvasEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AutoLoadImages, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)

        # Permissões automáticas para captura de áudio (microfone) e vídeo
        def _grant_permissions(security_origin, feature):
            _log(f"[WebEngine Permissão Solicitada] {feature} de {security_origin.toString()}")
            self.web_view.page().setFeaturePermission(
                security_origin, feature, QWebEnginePage.PermissionPolicy.PermissionGrantedByUser
            )
        self.web_view.page().featurePermissionRequested.connect(_grant_permissions)

        # Fundo escuro imediato para zero flicker branco
        self.web_view.page().setBackgroundColor(QColor("#010614"))

        # Monitoramento de carregamento
        self.web_view.loadStarted.connect(lambda: _log("web_view loadStarted"))
        self.web_view.loadProgress.connect(lambda p: _log(f"web_view progresso: {p}%") if p in [25, 50, 75, 100] else None)
        self.web_view.loadFinished.connect(self._on_load_finished)

        target_url = QUrl(f"{CORE_URL}/?client=desktop_windows_standalone")
        _log(f"Carregando URL no WebEngine: {target_url.toString()}")
        self.web_view.setUrl(target_url)

        self.central_layout.addWidget(self.web_view, 1)
        self.setCentralWidget(self.central_widget)

    def _setup_shortcuts(self):
        # Atalho F11 para alternar tela cheia
        shortcut_f11 = QShortcut(QKeySequence("F11"), self)
        shortcut_f11.activated.connect(self._toggle_fullscreen)

        # Atalho Esc para sair de tela cheia ou ocultar
        shortcut_esc = QShortcut(QKeySequence("Escape"), self)
        shortcut_esc.activated.connect(self._handle_esc)

        # Atalho F2 para ativar o microfone no HUD
        shortcut_f2 = QShortcut(QKeySequence("F2"), self)
        shortcut_f2.activated.connect(self.trigger_mic)

        # Atalho F5 e Ctrl+R para recarregar o WebEngine
        shortcut_f5 = QShortcut(QKeySequence("F5"), self)
        shortcut_f5.activated.connect(self.reload_hud)
        shortcut_ctrl_r = QShortcut(QKeySequence("Ctrl+R"), self)
        shortcut_ctrl_r.activated.connect(self.reload_hud)

    def reload_hud(self):
        """Recarrega a página no WebEngine."""
        _log("Recarregando HUD...")
        self.web_view.reload()

    def trigger_mic(self):
        """Aciona ou para a gravação do microfone no HUD."""
        self.web_view.page().runJavaScript("if (window.manualMicToggle) window.manualMicToggle();")

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            self.top_control_bar.show()
        else:
            self.showFullScreen()

    def _handle_esc(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.hide()

    def _on_load_finished(self, ok):
        _log(f"web_view loadFinished ok={ok}, url={self.web_view.url().toString()}")
        if not ok:
            _log("Falha ao carregar URL principal! Verifique conexão ou certificado.")
            return

        js_bootstrap = """
        (function() {
            try {
                localStorage.setItem('jarvis_session_token', '8145760953033109');
                localStorage.setItem('jarvis_client_id', 'desktop_windows_standalone');
                window.__JARVIS_DESKTOP_STANDALONE = true;
                console.log("[J.A.R.V.I.S. Desktop] Modo Standalone Conectado com Master Token.");
            } catch(e) {
                console.warn("[J.A.R.V.I.S. Desktop] Erro na injeção inicial:", e);
            }
        })();
        """
        self.web_view.page().runJavaScript(js_bootstrap)

    def _start_bridge_timer(self):
        """Injeta periodicamente telemetria do Windows diretamente na interface webview."""
        self.bridge_timer = QTimer(self)
        self.bridge_timer.timeout.connect(self._sync_desktop_telemetry)
        self.bridge_timer.start(2500)

    def _sync_desktop_telemetry(self):
        try:
            telem = get_system_telemetry()
            cpu = telem.get("cpu_percent", 0)
            ram = telem.get("ram_percent", 0)
            gpu = telem.get("gpu", {})
            gpu_temp = gpu.get("temp", 0)

            # Injeta script JS com segurança na thread principal
            js = f"""
            if (window.updateDesktopStats) {{
                window.updateDesktopStats({{
                    cpu: {cpu},
                    ram: {ram},
                    gpuTemp: {gpu_temp}
                }});
            }}
            """
            self.web_view.page().runJavaScript(js)
        except Exception:
            pass

    def _toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange:
            self._sync_window_state_ui()
        super().changeEvent(event)

    def _sync_window_state_ui(self):
        is_max = self.isMaximized() or self.isFullScreen()
        if getattr(self, '_last_synced_state', None) == is_max:
            return
        self._last_synced_state = is_max

        if hasattr(self, 'btn_max'):
            if is_max:
                self.btn_max.setText("❐")
                self.btn_max.setToolTip("Restaurar Janela")
            else:
                self.btn_max.setText("□")
                self.btn_max.setToolTip("Maximizar Janela")

    def eventFilter(self, watched, event):
        """Intercepta arraste e duplo clique nativo na barra de título Stark."""
        if watched in (self.top_control_bar, getattr(self, 'title_label', None)):
            if event.type() == QEvent.Type.MouseButtonDblClick:
                if event.button() == Qt.MouseButton.LeftButton:
                    self._toggle_maximize()
                    return True
            elif event.type() == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    if self.isMaximized():
                        local_x = event.position().x()
                        ratio = max(0.0, min(1.0, local_x / max(1.0, float(self.width()))))
                        self.showNormal()
                        normal_w = self.width()
                        new_x = int(event.globalPosition().x() - normal_w * ratio)
                        new_y = int(event.globalPosition().y() - event.position().y())
                        self.move(new_x, new_y)
                    wh = self.windowHandle()
                    if wh:
                        wh.startSystemMove()
                    return True
        return super().eventFilter(watched, event)

    def _get_resize_edges(self, pos):
        if self.isMaximized() or self.isFullScreen():
            return Qt.Edge(0)
        margin = 6
        edges = Qt.Edge(0)
        w = self.width()
        h = self.height()
        if pos.x() <= margin:
            edges |= Qt.Edge.LeftEdge
        elif pos.x() >= w - margin:
            edges |= Qt.Edge.RightEdge
        if pos.y() <= margin:
            edges |= Qt.Edge.TopEdge
        elif pos.y() >= h - margin:
            edges |= Qt.Edge.BottomEdge
        return edges

    def _cursor_for_edges(self, edges):
        if (edges & Qt.Edge.TopEdge and edges & Qt.Edge.LeftEdge) or (edges & Qt.Edge.BottomEdge and edges & Qt.Edge.RightEdge):
            return Qt.CursorShape.SizeFDiagCursor
        if (edges & Qt.Edge.TopEdge and edges & Qt.Edge.RightEdge) or (edges & Qt.Edge.BottomEdge and edges & Qt.Edge.LeftEdge):
            return Qt.CursorShape.SizeBDiagCursor
        if edges & (Qt.Edge.LeftEdge | Qt.Edge.RightEdge):
            return Qt.CursorShape.SizeHorCursor
        if edges & (Qt.Edge.TopEdge | Qt.Edge.BottomEdge):
            return Qt.CursorShape.SizeVerCursor
        return Qt.CursorShape.ArrowCursor

    def mouseMoveEvent(self, event):
        edges = self._get_resize_edges(event.position().toPoint())
        self.setCursor(self._cursor_for_edges(edges))
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            edges = self._get_resize_edges(event.position().toPoint())
            if edges != Qt.Edge(0):
                wh = self.windowHandle()
                if wh:
                    wh.startSystemResize(edges)
                    event.accept()
                    return
        super().mousePressEvent(event)
