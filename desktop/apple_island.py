"""
JARVIS Dynamic Island - Apple Glass Edition (PyQt6)
- Estilo Apple 1:1: Formato Estádio (cantos 100% arredondados)
- Efeito Dark Frosted Glass translúcido com reflexo
- Aura holográfica ciano luminosa (#00f0ff) idêntica ao painel web do JARVIS
- Avatar / Arc Reactor animado na esquerda + Status verde
- Ponto focal central (estilo câmera Apple)
- Visualizador de ondas de áudio (equalizador animado colorido) na direita
- Always-On-Top na Área de Trabalho Principal Real (WinSta0\\Default - DISPLAY1)
- Clique para expandir / recolher e arrastar livremente
"""

import sys
import os
import math
import time
import json
import ctypes
import ctypes.wintypes
import urllib.request
import threading
import webbrowser
import subprocess

# Garante acesso aos módulos do projeto (desktop/, desktop/canvas_window.py)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

ISLAND_SETTINGS_FILE = os.path.join(PROJECT_ROOT, "config", "island_settings.json")
CORE_BASE_URL = os.environ.get("JARVIS_CORE_URL", "https://jarvis.werikspace.xyz")

def island_settings() -> dict:
    try:
        if os.path.exists(ISLAND_SETTINGS_FILE):
            with open(ISLAND_SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {"wake_word_enabled": True, "ask_before_show": True, "core_url": "https://jarvis.werikspace.xyz"}

def small_button_style():
    return """
        QPushButton {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(56,189,248,0.16), stop:1 rgba(0,240,255,0.16));
            color: #7dd3fc; font-family: 'Segoe UI'; font-size: 10px; font-weight: 800;
            border-radius: 10px; padding: 3px 12px; border: 1px solid rgba(0, 240, 255, 0.4);
        }
        QPushButton:hover { background: rgba(0, 240, 255, 0.3); color: #ffffff; }
    """

def glow_button_style():
    return """
        QPushButton {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00e5ff, stop:1 #0284c7);
            color: #020d20; font-family: 'Segoe UI'; font-size: 10px; font-weight: 800;
            border-radius: 10px; padding: 3px 14px; border: none;
        }
        QPushButton:hover { background: #38bdf8; color: #000000; }
    """

# Garante acoplamento na Área de Trabalho Principal do Usuário
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
        print("[ISLAND] Desktop attach warning:", e)

attach_to_default_desktop()

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

from PyQt6.QtCore import Qt, QTimer, QPoint, QRect, pyqtSignal, QObject, QEvent
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QRadialGradient, QLinearGradient, QPainterPath
from PyQt6.QtWidgets import (
    QApplication, QWidget, QFrame, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QGraphicsDropShadowEffect
)

try:
    from desktop.audio_listener import NativeAudioListener
except Exception:
    NativeAudioListener = None

class EventBridge(QObject):
    event_received = pyqtSignal(dict)
    speech_state_changed = pyqtSignal(str)
    transcript_arrived = pyqtSignal(str, str, object, dict)
    rms_level_changed = pyqtSignal(float)
    partial_transcript_changed = pyqtSignal(str)
    core_live_changed = pyqtSignal(bool)
    canvas_offer = pyqtSignal(dict, str)

class CircularVortexWidget(QWidget):
    """Ondas circulares orgânicas idênticas ao Organic Fluid Plasma Vortex do painel web do JARVIS."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(38, 38)
        self.time_val = 0.0
        # Camadas com ondas e velocidades idênticas ao canvas web
        self.layers = [
            {"baseRadius": 14.2, "waves": 6, "amp": 1.9, "speed": 0.035, "color": QColor(0, 240, 255, 235), "width": 1.7},
            {"baseRadius": 11.2, "waves": 8, "amp": 1.5, "speed": -0.045, "color": QColor(56, 189, 248, 215), "width": 1.4},
            {"baseRadius": 8.4,  "waves": 5, "amp": 1.2, "speed": 0.055, "color": QColor(125, 211, 252, 230), "width": 1.2},
            {"baseRadius": 5.6,  "waves": 4, "amp": 0.9, "speed": -0.065, "color": QColor(0, 140, 255, 180), "width": 1.0},
        ]

    def update_anim(self):
        self.time_val += 1.0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2

        # Glow radial suave no núcleo
        grad = QRadialGradient(cx, cy, 18)
        grad.setColorAt(0, QColor(0, 240, 255, 80))
        grad.setColorAt(0.5, QColor(0, 140, 255, 30))
        grad.setColorAt(1, QColor(0, 240, 255, 0))
        painter.setBrush(QBrush(grad))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(int(cx - 18), int(cy - 18), 36, 36)

        # Desenha cada anel de onda orgânica com fórmula trigonométrica do painel web
        points = 64
        for layer in self.layers:
            pen = QPen(layer["color"], layer["width"])
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            path = QPainterPath()
            first = True
            for i in range(points + 1):
                theta = (i / points) * (2 * math.pi)
                offset = (math.sin(theta * layer["waves"] + self.time_val * layer["speed"] * 8) * layer["amp"]
                        + math.cos(theta * 3 - self.time_val * layer["speed"] * 4) * (layer["amp"] * 0.45))
                r = layer["baseRadius"] + offset
                x = cx + math.cos(theta) * r
                y = cy + math.sin(theta) * r

                if first:
                    path.moveTo(x, y)
                    first = False
                else:
                    path.lineTo(x, y)

            path.closeSubpath()
            painter.drawPath(path)

class AudioWaveformWidget(QWidget):
    """Equalizador de ondas sonoras Apple na ponta direita - Estático em repouso, reage apenas à voz."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(56, 26)
        # Alturas de repouso idênticas à imagem enviada pelo usuário
        self.idle_bars = [14.0, 16.0, 10.0, 4.0, 4.0, 10.0, 16.0, 18.0]
        self.bars = list(self.idle_bars)
        self.tick = 0
        self.live_rms = 0.0
        self.is_active = False

    def set_live_rms(self, rms: float):
        self.live_rms = rms

    def set_active_state(self, active: bool):
        self.is_active = active

    def update_anim(self):
        # Se NÃO estiver falando e o som ambiente for baixo: FICA 100% PARADO
        if not self.is_active and self.live_rms < 0.020:
            changed = False
            for i in range(len(self.bars)):
                diff = self.idle_bars[i] - self.bars[i]
                if abs(diff) > 0.2:
                    self.bars[i] += diff * 0.3
                    changed = True
                else:
                    self.bars[i] = self.idle_bars[i]
            if changed:
                self.update()
            return

        # SÓ MEXE SE ESTIVER OUVIDO/FALANDO
        self.tick += 1
        rms_norm = min(1.0, max(0.0, (self.live_rms - 0.015) * 14.0))
        for i in range(len(self.bars)):
            mod = math.sin(self.tick * 0.45 + i * 0.85)
            boost = rms_norm * 12.0 * (0.65 + 0.35 * mod)
            target = max(3.5, min(24.0, self.idle_bars[i] + boost))
            self.bars[i] += (target - self.bars[i]) * 0.4
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bar_w = 3.2
        spacing = 3.2
        total_w = len(self.bars) * (bar_w + spacing)
        start_x = (self.width() - total_w) / 2
        cy = self.height() / 2

        # Paleta exata do print: verde, verde, amarelo, laranja, ciano, azul, verde, verde
        palette = [
            QColor(16, 185, 129), # Verde
            QColor(52, 211, 153), # Verde claro
            QColor(251, 191, 36), # Amarelo ouro
            QColor(245, 158, 11), # Laranja
            QColor(0, 240, 255),  # Ciano JARVIS
            QColor(56, 189, 248), # Azul celeste
            QColor(52, 211, 153), # Verde claro
            QColor(16, 185, 129)  # Verde
        ]

        for i, h in enumerate(self.bars):
            x = start_x + i * (bar_w + spacing)
            y = cy - (h / 2)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(palette[i % len(palette)])
            painter.drawRoundedRect(int(x), int(y), int(bar_w), int(h), 1.6, 1.6)

class AppleDynamicIsland(QWidget):
    def __init__(self):
        super().__init__()
        self.bridge = EventBridge()
        self.bridge.event_received.connect(self.on_hud_event)
        self.bridge.speech_state_changed.connect(self._on_speech_state_changed)
        self.bridge.transcript_arrived.connect(self._on_transcript_arrived)
        self.bridge.rms_level_changed.connect(self._on_rms_level_changed)
        self.bridge.partial_transcript_changed.connect(self._on_partial_transcript)
        self.bridge.core_live_changed.connect(self._on_core_live)
        self.bridge.canvas_offer.connect(self._on_canvas_offer)

        self.is_expanded = False
        self.drag_position = None
        self.drag_moved = False
        self.is_voice_active = False
        self.pending_panels = []      # [(titulo, payload)] — "Mais tarde"
        self.current_offer = None     # payload em aprovação
        self.core_live = False

        self.auto_collapse_timer = QTimer(self)
        self.auto_collapse_timer.setSingleShot(True)
        self.auto_collapse_timer.timeout.connect(self.collapse)

        # Timer para sumir e só reaparecer quando chamado
        self.auto_hide_timer = QTimer(self)
        self.auto_hide_timer.setSingleShot(True)
        self.auto_hide_timer.timeout.connect(self.hide_island)

        # Fechar a ilha e voltar ao segundo plano quando NÃO houver novo chamado
        # após a resposta (força fechar mesmo se ainda estiver expandida).
        self.idle_hide_timer = QTimer(self)
        self.idle_hide_timer.setSingleShot(True)
        self.idle_hide_timer.timeout.connect(self._idle_hide)

        self.setWindowTitle("JARVIS Apple Dynamic Island")

        # Configurações de Janela Frameless + Translucent + Always On Top
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # Dimensões da pílula (Apple Stadium Pill)
        self.compact_w = 350
        self.compact_h = 54
        self.expanded_w = 550
        self.expanded_h = 138

        # Margem externa para conter o Drop Shadow (Aura holográfica) sem cortes
        self.shadow_margin = 30

        # Resolução do monitor principal (DISPLAY1 - 2560x1440)
        screen = QApplication.primaryScreen()
        screen_geo = screen.geometry() if screen else QRect(0, 0, 2560, 1440)
        self.screen_w = screen_geo.width()
        self.screen_h = screen_geo.height()

        self.cur_y = 35 # Distância do topo da tela (evita corte da aura holográfica)

        self.setup_ui()
        self.apply_compact_geometry()
        self.setup_timers()
        self.start_sse_listener()

        # Inicia a escuta contínua de microfone independente do navegador
        self.audio_listener = None
        self.start_native_audio()

    def show_island(self):
        """Faz a Dynamic Island aparecer suavemente no topo."""
        self.show()
        self.keep_topmost_win32()

    def hide_island(self):
        """Oculta a Dynamic Island até o Jarvis ser chamado novamente."""
        if not self.is_voice_active and not self.is_expanded:
            self.hide()

    def _idle_hide(self):
        """Fecha a ilha e volta ao segundo plano quando ninguém chama o Jarvis de novo."""
        if self.current_offer:
            return  # gate de painel aberto: não fechar (o usuário ainda vai decidir)
        self.is_voice_active = False
        try:
            self.collapse()
        except Exception:
            pass
        try:
            self.hide()
        except Exception:
            pass

    def _reset_idle(self, ms: int = 10000):
        """(Re)inicia o contador de inatividade: se não houver novo chamado, a ilha fecha."""
        try:
            self.idle_hide_timer.start(ms)
        except Exception:
            pass

    def start_native_audio(self):
        """Inicia escuta contínua do microfone físico em background (wake word + partials)."""
        if NativeAudioListener:
            try:
                self.audio_listener = NativeAudioListener(
                    on_speech_start=lambda: self.bridge.speech_state_changed.emit("speaking"),
                    on_speech_end=lambda: self.bridge.speech_state_changed.emit("processing"),
                    on_rms_level=lambda rms: self.bridge.rms_level_changed.emit(rms),
                    on_transcript_ready=lambda t, r, a, m: self.bridge.transcript_arrived.emit(t, r, a, m or {}),
                    on_partial_transcript=lambda txt: self.bridge.partial_transcript_changed.emit(txt)
                )
                self.audio_listener.start()
            except Exception as e:
                print("[ISLAND] Erro ao iniciar listener de microfone:", e)

    def _on_speech_state_changed(self, state: str):
        if state == "speaking":
            self.is_voice_active = True
            self.auto_hide_timer.stop()
            self.idle_hide_timer.stop()
            self.show_island()
            # Expandir para dar palco à transcrição ao vivo
            if not self.is_expanded and not self.current_offer:
                self.expand()
            self.waveform.set_active_state(True)
            self.lbl_status.setText("● OUVINDO")
            self.lbl_status.setStyleSheet("color: #38bdf8; font-family: 'Segoe UI', Consolas; font-size: 11px; font-weight: 800; margin-left: 2px;")
        elif state == "processing":
            self.waveform.set_active_state(False)
            self.lbl_status.setText("● PROCESSANDO")
            self.lbl_status.setStyleSheet("color: #fbbf24; font-family: 'Segoe UI', Consolas; font-size: 11px; font-weight: 800; margin-left: 2px;")
        else:
            self.is_voice_active = False
            self.waveform.set_active_state(False)
            self.lbl_status.setText("● ONLINE")
            self.lbl_status.setStyleSheet("color: #10b981; font-family: 'Segoe UI', Consolas; font-size: 11px; font-weight: 700; margin-left: 2px;")

    def _on_transcript_arrived(self, user_text: str, jarvis_reply: str, audio_url=None, meta=None):
        meta = meta or {}
        self.is_voice_active = False
        self.lbl_partial.setText("")
        self.lbl_partial.setVisible(False)
        self.show_island()
        self._on_speech_state_changed("online")
        title = f'VOCÊ: "{user_text}"'
        if len(title) > 42:
            title = title[:39] + '..."'
        self.show_notification(title, jarvis_reply, duration_ms=12000)
        # Após a resposta, se ninguém chamar o Jarvis de novo, a ilha fecha e
        # volta para o segundo plano.
        self._reset_idle(15000)
        # Painel/canvas pedido: passa pelo GATE "perguntar antes de exibir"
        payload = meta.get("canvas") if isinstance(meta, dict) else None
        if payload:
            self.bridge.canvas_offer.emit(payload if isinstance(payload, dict) else {"payload": payload}, str((payload or {}).get("title") or "Painel do J.A.R.V.I.S."))

    def _on_partial_transcript(self, text: str):
        """Exibe a transcrição crescendo enquanto o usuário fala (igual legenda do painel web)."""
        if text:
            self.show_island()
            self.idle_hide_timer.stop()
            self.lbl_partial.setText(text)
            self.lbl_partial.setVisible(True)
        else:
            self.lbl_partial.setText("")
            self.lbl_partial.setVisible(False)

    def _on_core_live(self, live: bool):
        self.core_live = live
        # Ponto central da pílula indica a saúde do link com o núcleo
        color = "#10b981" if live else "#fbbf24"
        mode = "NÚCLEO AO VIVO" if live else "MODO LOCAL"
        self.camera_notch.setText("●")
        self.camera_notch.setStyleSheet(f"color: {color}; font-size: 8px;")
        self.camera_notch.setToolTip(f"Link com o núcleo: {mode}")

    # ==================== GATE DE EXIBIÇÃO (CANVAS/PAINÉIS) ====================
    def _on_canvas_offer(self, payload: dict, title: str):
        """Pergunta antes de jogar uma tela na cara do usuário."""
        st = island_settings()
        if not st.get("ask_before_show", True):
            self._open_canvas(payload)
            return
        self.show_island()
        self.show_island_top()
        self.idle_hide_timer.stop()
        self.current_offer = {"payload": payload, "title": title}
        self.lbl_badge.setText("// J.A.R.V.I.S. QUER EXIBIR")
        self.lbl_message.setText(f"{title} — abrir agora? (não interromperá o que você faz se deixar)")
        self.btn_canvas_yes.setVisible(True)
        self.btn_canvas_later.setVisible(True)
        if not self.is_expanded:
            self.expand()
        else:
            self.apply_expanded_geometry()
        self.keep_topmost_win32()
        # some dali em 15s (vai para pendentes)
        QTimer.singleShot(15000, self._offer_expiring)

    def _offer_expiring(self):
        if self.current_offer:
            self._on_canvas_later()

    def _on_canvas_yes(self):
        offer = self.current_offer
        self.current_offer = None
        self.btn_canvas_yes.setVisible(False)
        self.btn_canvas_later.setVisible(False)
        if offer:
            self._open_canvas(offer["payload"])
        self._reset_idle(8000)

    def _on_canvas_later(self):
        offer = self.current_offer
        self.current_offer = None
        self.btn_canvas_yes.setVisible(False)
        self.btn_canvas_later.setVisible(False)
        if offer:
            self.pending_panels.append((offer["title"], offer["payload"]))
            self._update_pending_badge()
            self.show_notification("PAINEL ADIADO", f"“{offer['title']}” ficou na fila de pendentes.", 3500)
        self.collapse()
        self._reset_idle(7000)

    def _update_pending_badge(self):
        n = len(self.pending_panels)
        if n > 0:
            self.btn_pending.setText(f"⟲ {n} painel(is) pendente(s) — abrir")
            self.btn_pending.setVisible(True)
        else:
            self.btn_pending.setVisible(False)

    def _on_pending_next(self):
        if not self.pending_panels:
            return
        title, payload = self.pending_panels.pop(0)
        self._update_pending_badge()
        self._open_canvas(payload)

    def _open_canvas(self, payload: dict):
        """Abre o painel holográfico em JANELA NATIVA PyQt (interface própria do nó)."""
        try:
            title = str(payload.get("title") or "Painel J.A.R.V.I.S.")
            data = json.dumps({"payload": payload, "title": title}).encode("utf-8")
            req = urllib.request.Request(
                f"{CORE_BASE_URL}/api/canvas/push",
                data=data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=6) as resp:
                pid = json.loads(resp.read().decode("utf-8")).get("id", "")
            if not pid:
                self.show_notification("CANVAS FALHOU", "Servidor local não aceitou o painel.", 4000)
                return
            launched = False
            try:
                if getattr(sys, "frozen", False):
                    args = [sys.executable, "--canvas", pid]
                    subprocess.Popen(args, cwd=os.path.dirname(sys.executable) or ".")
                    launched = True
                else:
                    canvas_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "native_canvas.py")
                    pyw = (sys.executable or "python.exe").replace("python.exe", "pythonw.exe")
                    target = pyw if os.path.exists(pyw) else (sys.executable or "python.exe")
                    subprocess.Popen([target, canvas_script, pid], shell=False)
                    launched = True
            except Exception as e_launch:
                print("[ISLAND] Canvas nativo falhou, usando navegador:", e_launch)
            if not launched:
                webbrowser.open(f"{CORE_BASE_URL}/canvas_panel?pid={pid}")
            self.lbl_message.setText(f"Painel “{title}” aberto na área de trabalho.")
        except Exception as e:
            self.show_notification("CANVAS ERRO", str(e)[:160], 5000)

    def show_island_top(self):
        self.raise_()
        self.activateWindow()
        self.keep_topmost_win32()

    def _on_rms_level_changed(self, rms: float):
        self.waveform.set_live_rms(rms)

    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(self.shadow_margin, self.shadow_margin, self.shadow_margin, self.shadow_margin)

        # 1. Container Pílula Estilo Apple Glass
        self.pill = QFrame(self)
        self.pill.setObjectName("pillContainer")
        self.update_pill_style(expanded=False)

        # 2. Aura Holográfica idêntica ao painel web do JARVIS (#00f0ff glow blur)
        self.aura = QGraphicsDropShadowEffect(self.pill)
        self.aura.setBlurRadius(38)
        self.aura.setColor(QColor(0, 240, 255, 175))
        self.aura.setOffset(0, 0)
        self.pill.setGraphicsEffect(self.aura)

        # Layout interno da pílula
        self.pill_layout = QVBoxLayout(self.pill)
        self.pill_layout.setContentsMargins(10, 6, 12, 6)
        self.pill_layout.setSpacing(0)

        # Linha Compacta (Estilo Apple Dynamic Island do print)
        self.compact_row = QWidget(self.pill)
        row_layout = QHBoxLayout(self.compact_row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        # A. Ondas Circulares Orgânicas (igual ao painel web) à esquerda
        self.vortex = CircularVortexWidget(self.compact_row)
        row_layout.addWidget(self.vortex)

        # B. Título e Status verde online
        self.lbl_title = QLabel("J.A.R.V.I.S.")
        self.lbl_title.setStyleSheet("color: #00f0ff; font-family: 'Segoe UI'; font-size: 13px; font-weight: 800; letter-spacing: 0.5px;")
        row_layout.addWidget(self.lbl_title)

        self.lbl_status = QLabel("● ONLINE")
        self.lbl_status.setStyleSheet("color: #10b981; font-family: 'Segoe UI', Consolas; font-size: 11px; font-weight: 700; margin-left: 2px;")
        row_layout.addWidget(self.lbl_status)

        row_layout.addStretch()

        # C. Sensor central / Camera notch estilo Apple
        self.camera_notch = QLabel("●")
        self.camera_notch.setStyleSheet("color: rgba(56, 189, 248, 0.45); font-size: 8px;")
        row_layout.addWidget(self.camera_notch)

        row_layout.addStretch()

        # D. Equalizador de áudio animado à direita
        self.waveform = AudioWaveformWidget(self.compact_row)
        row_layout.addWidget(self.waveform)

        self.pill_layout.addWidget(self.compact_row)

        # Painel Expandido (notificações e HUD)
        self.expand_panel = QWidget(self.pill)
        self.expand_panel.setVisible(False)
        expand_layout = QVBoxLayout(self.expand_panel)
        expand_layout.setContentsMargins(4, 6, 4, 2)
        expand_layout.setSpacing(4)

        self.lbl_badge = QLabel("// INTELIGÊNCIA EM TEMPO REAL")
        self.lbl_badge.setStyleSheet("color: #38bdf8; font-family: 'Segoe UI'; font-size: 10px; font-weight: 800; letter-spacing: 1px;")
        expand_layout.addWidget(self.lbl_badge)

        # Transcrição AO VIVO (aparece enquanto o usuário fala)
        self.lbl_partial = QLabel("")
        self.lbl_partial.setStyleSheet("color: #7dd3fc; font-family: 'Segoe UI'; font-size: 11px; font-style: italic;")
        self.lbl_partial.setWordWrap(True)
        self.lbl_partial.setVisible(False)
        expand_layout.addWidget(self.lbl_partial)

        self.lbl_message = QLabel("Sistemas J.A.R.V.I.S. sincronizados e ativos.")
        self.lbl_message.setStyleSheet("color: #f8fafc; font-family: 'Segoe UI'; font-size: 12px; line-height: 1.3;")
        self.lbl_message.setWordWrap(True)
        expand_layout.addWidget(self.lbl_message)

        # Botões do GATE de exibição de canvas/painéis (perguntar antes)
        gate_row = QHBoxLayout()
        gate_row.addStretch()

        self.btn_canvas_later = QPushButton("Mais tarde")
        self.btn_canvas_later.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_canvas_later.setStyleSheet(small_button_style())
        self.btn_canvas_later.clicked.connect(self._on_canvas_later)
        self.btn_canvas_later.setVisible(False)
        gate_row.addWidget(self.btn_canvas_later)

        self.btn_canvas_yes = QPushButton("Ver agora")
        self.btn_canvas_yes.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_canvas_yes.setStyleSheet(glow_button_style())
        self.btn_canvas_yes.clicked.connect(self._on_canvas_yes)
        self.btn_canvas_yes.setVisible(False)
        gate_row.addWidget(self.btn_canvas_yes)

        expand_layout.addLayout(gate_row)

        # Fila de painéis pendentes ("Mais tarde")
        self.btn_pending = QPushButton("")
        self.btn_pending.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pending.setStyleSheet(small_button_style())
        self.btn_pending.clicked.connect(self._on_pending_next)
        self.btn_pending.setVisible(False)
        expand_layout.addWidget(self.btn_pending)

        # Botão de Acesso ao HUD Completo
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.btn_hud = QPushButton("Abrir HUD Completo ↗")
        self.btn_hud.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_hud.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00e5ff, stop:1 #0284c7);
                color: #020d20;
                font-family: 'Segoe UI';
                font-size: 11px;
                font-weight: 800;
                border-radius: 11px;
                padding: 4px 14px;
                border: none;
            }
            QPushButton:hover {
                background: #38bdf8;
                color: #000000;
            }
        """)
        self.btn_hud.clicked.connect(self.open_hud)
        btn_row.addWidget(self.btn_hud)

        expand_layout.addLayout(btn_row)
        self.pill_layout.addWidget(self.expand_panel)

        self.main_layout.addWidget(self.pill)

        # Instala filtro de eventos para permitir clique e arrasto em qualquer parte
        for w in [self.pill, self.compact_row, self.lbl_title, self.lbl_status, self.camera_notch, self.vortex, self.waveform]:
            w.installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                self.drag_moved = False
                return True
        elif event.type() == QEvent.Type.MouseMove:
            if event.buttons() == Qt.MouseButton.LeftButton and self.drag_position:
                new_pos = event.globalPosition().toPoint() - self.drag_position
                if (new_pos - self.pos()).manhattanLength() > 4:
                    self.drag_moved = True
                self.move(new_pos)
                return True
        elif event.type() == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.LeftButton:
                if not self.drag_moved:
                    self.toggle_expand()
                self.drag_position = None
                return True
        return super().eventFilter(watched, event)

    def update_pill_style(self, expanded=False):
        radius = 27 if not expanded else 20
        self.pill.setStyleSheet(f"""
            QFrame#pillContainer {{
                background-color: rgba(6, 11, 20, 0.94);
                border: 1.2px solid rgba(0, 240, 255, 0.50);
                border-radius: {radius}px;
            }}
        """)

    def apply_compact_geometry(self):
        self.is_expanded = False
        self.expand_panel.setVisible(False)
        self.update_pill_style(expanded=False)

        self.pill.setFixedSize(self.compact_w, self.compact_h)
        tot_w = self.compact_w + self.shadow_margin * 2
        tot_h = self.compact_h + self.shadow_margin * 2
        self.setFixedSize(tot_w, tot_h)

        target_x = int((self.screen_w - self.compact_w) / 2)
        self.move(target_x - self.shadow_margin, self.cur_y - self.shadow_margin)

    def apply_expanded_geometry(self):
        self.is_expanded = True
        self.expand_panel.setVisible(True)
        self.update_pill_style(expanded=True)

        self.pill.setFixedSize(self.expanded_w, self.expanded_h)
        tot_w = self.expanded_w + self.shadow_margin * 2
        tot_h = self.expanded_h + self.shadow_margin * 2
        self.setFixedSize(tot_w, tot_h)

        target_x = int((self.screen_w - self.expanded_w) / 2)
        self.move(target_x - self.shadow_margin, self.cur_y - self.shadow_margin)

    def toggle_expand(self):
        if self.is_expanded:
            self.collapse()
        else:
            self.expand()

    def expand(self, auto_collapse_ms=0):
        if self.is_expanded:
            if auto_collapse_ms > 0:
                self.auto_collapse_timer.start(auto_collapse_ms)
            return

        self.apply_expanded_geometry()
        self.keep_topmost_win32()

        if auto_collapse_ms > 0:
            self.auto_collapse_timer.start(auto_collapse_ms)

    def collapse(self):
        if not self.is_expanded:
            return

        self.auto_collapse_timer.stop()
        self.apply_compact_geometry()
        self.keep_topmost_win32()

    def setup_timers(self):
        # 1. Animação de ticks (Ondas Circulares Vortex + Ondas Sonoras)
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._on_tick_anim)
        self.anim_timer.start(45)

        # 2. Always-on-top persistente no Windows
        self.topmost_timer = QTimer(self)
        self.topmost_timer.timeout.connect(self.keep_topmost_win32)
        self.topmost_timer.start(2500)

    def _on_tick_anim(self):
        self.vortex.update_anim()
        self.waveform.update_anim()

    def _update_clock(self):
        now_str = time.strftime("%H:%M")
        self.lbl_timer.setText(now_str)

    def keep_topmost_win32(self):
        """Força Always-On-Top real via Win32 API (SEM reexibir se estiver escondida)."""
        try:
            if not self.isVisible():
                return  # não reexibir a ilha escondida (evita o 'não some')
            hwnd = int(self.winId())
            if hwnd:
                # 0x0013 = NOSIZE | NOMOVE | NOACTIVATE (sem SWP_SHOWWINDOW, que forçava reaparecer)
                ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0013)
        except Exception:
            pass

    def open_hud(self):
        webbrowser.open(CORE_BASE_URL)

    def show_notification(self, title, message, duration_ms=5000):
        self.show_island()
        self.lbl_badge.setText(f"// {title.upper()}")
        self.lbl_message.setText(message)
        self.expand(auto_collapse_ms=duration_ms)
        self.auto_hide_timer.start(duration_ms + 1500)

    def on_hud_event(self, data):
        src = str(data.get("source", "")).lower()
        dev = str(data.get("device_id", "")).lower()

        # SUPPRESSION: Se a voz/comando veio da Esfera (ESP32-S3),
        # NÃO acionar, NÃO abrir e NÃO expandir a janela Dynamic Island no Windows PC!
        if src == "esfera" or "esfera" in dev or "sphere" in dev or data.get("from_sphere"):
            if data.get("action") == "play_tts_pcm":
                text = data.get("text", "")
                try:
                    from desktop.sound_dispatcher import play_tts_async
                    play_tts_async(text)
                except Exception:
                    pass
            return  # MANTÉM DYNAMIC ISLAND 100% OCULTA NO WINDOWS PC

        action = data.get("action", "")
        ev_type = data.get("type", "")

        if action == "play_tts_pcm":
            text = data.get("text", "")
            try:
                from desktop.sound_dispatcher import play_tts_async
                play_tts_async(text)
            except Exception:
                pass
            return

        # Canvas/painéis vindos do núcleo: SEMPRE passam pelo gate "perguntar antes"
        canvas_payload = data.get("canvas")
        if canvas_payload or action in ("canvas_show", "project_canvas"):
            title = str((canvas_payload or {}).get("title") or data.get("title") or "Painel do J.A.R.V.I.S.")
            payload = canvas_payload if isinstance(canvas_payload, dict) else {"title": title, "content": data.get("content", data.get("message", ""))}
            self.bridge.canvas_offer.emit(payload, title)
            return

        if action == "island_show":
            # Chamada do operador (bandeja/console): ilha sobe e fica pronta para ouvir
            self.show_island()
            self.expand()
            self._on_speech_state_changed("online")
            self.show_notification("J.A.R.V.I.S. PRONTO", "Como posso ajudar, Senhor Werik? Fale — estou ouvindo.", 5000)
            self._reset_idle(12000)
            return

        if action == "vision_event" or ev_type == "vision.gesture":
            ev = data.get("event", {})
            gest = ev.get("gesture") or data.get("gesture", "Gesto")
            self.show_notification("GESTO RECONHECIDO", f"Comando visual: {gest}", 4500)
        elif action == "alert":
            title = data.get("title", "NOTIFICAÇÃO")
            msg = data.get("message", "")
            self.show_notification(title, msg, 5500)
        elif action == "custom_card":
            title = data.get("title", "PAINEL J.A.R.V.I.S.")
            msg = data.get("content", "")
            self.show_notification(title, msg, 6000)
        elif action == "speech" or ev_type == "voice.command":
            text = data.get("text", "")
            self.show_notification("VOZ PROCESSADA", text, 4500)

    def start_sse_listener(self):
        """CONEXÃO REAL com o núcleo: assina o MESMO stream de eventos do painel web."""
        def loop():
            settings = island_settings()
            core_url = os.environ.get("JARVIS_CORE_URL", settings.get("core_url", "https://jarvis.werikspace.xyz"))
            url = f"{core_url}/api/hud/events"
            while True:
                ok = True
                try:
                    req = urllib.request.Request(url)
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        for line in resp:
                            decoded = line.decode("utf-8").strip()
                            if decoded.startswith("data:"):
                                payload = decoded[5:].strip()
                                if not self.core_live:
                                    self.bridge.core_live_changed.emit(True)
                                try:
                                    data = json.loads(payload)
                                    self.bridge.event_received.emit(data)
                                except Exception:
                                    pass
                except Exception:
                    ok = False
                if not ok:
                    self.bridge.core_live_changed.emit(False)
                    time.sleep(2)

        threading.Thread(target=loop, daemon=True, name="PyQtIslandSSE").start()

def main():
    # Guard de instância única (Windows Mutex): nunca permitir duas ilhas
    if sys.platform == "win32":
        try:
            kernel32 = ctypes.windll.kernel32
            mutex = kernel32.CreateMutexW(None, False, "JARVIS_DynamicIsland_Singleton")
            if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
                print("[ISLAND] Outra instância da Dynamic Island já está ativa — encerrando esta.")
                return
        except Exception:
            pass
    app = QApplication(sys.argv)
    island = AppleDynamicIsland()
    # Inicia escondida: só aparece quando você falar ("Jarvis") ou fizer um gesto
    island.hide()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
