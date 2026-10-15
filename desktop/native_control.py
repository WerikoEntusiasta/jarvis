"""
J.A.R.V.I.S. Native Control Center — Central de Controle NATIVA (PyQt6)
Interface PROPRIA do nó Windows (sem página web): status do núcleo, permissões,
testes de mic/screenshot/mouse, autostart, comportamento da ilha e log da ponte.
Uso: pythonw native_control.py  (ou JarvisDesktop.exe --control em modo empacotado)
"""
import sys
import os
import json
import ctypes
import urllib.request

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QScrollArea, QPlainTextEdit,
    QGridLayout, QCheckBox
)

SERVER = os.environ.get("JARVIS_CORE_URL", os.environ.get("JARVIS_LOCAL_URL", "https://jarvis.werikspace.xyz"))

QSS = """
QWidget#Root { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #020617, stop:0.45 #051126, stop:1 #020617); }
QLabel { color: #f1f5f9; font-family: 'Segoe UI', 'Plus Jakarta Sans', sans-serif; }
QLabel#H1 { color: #00f0ff; font-size: 20px; font-weight: 800; letter-spacing: 4px; }
QLabel#Sub { color: #94a3b8; font-size: 11px; letter-spacing: 2px; }

QFrame#Card {
    background: rgba(6, 18, 42, 0.85);
    border: 1px solid rgba(0, 240, 255, 0.25);
    border-radius: 16px;
}
QLabel#CardTitle { color: #00f0ff; font-size: 11px; font-weight: 800; letter-spacing: 2.5px; }
QLabel#Val { color: #f8fafc; font-size: 12px; font-weight: 700; font-family: 'Segoe UI'; }
QLabel#Muted { color: #94a3b8; font-size: 11px; font-family: 'Segoe UI'; }

QLabel#StatusBadgeOk {
    background: rgba(16, 185, 129, 0.16);
    color: #34d399;
    border: 1px solid rgba(16, 185, 129, 0.4);
    border-radius: 10px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 700;
}
QLabel#StatusBadgeErr {
    background: rgba(244, 63, 94, 0.16);
    color: #fb7185;
    border: 1px solid rgba(244, 63, 94, 0.4);
    border-radius: 10px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 700;
}

QPushButton {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 rgba(0,240,255,0.18), stop:1 rgba(56,189,248,0.22));
    color: #f8fafc;
    border: 1px solid rgba(0, 240, 255, 0.45);
    border-radius: 12px;
    padding: 8px 16px;
    font-size: 11.5px;
    font-weight: 700;
    font-family: 'Segoe UI';
}
QPushButton:hover {
    background: rgba(0, 240, 255, 0.32);
    border-color: rgba(0, 240, 255, 0.8);
    box-shadow: 0 0 15px rgba(0, 240, 255, 0.3);
}
QPushButton:pressed {
    background: rgba(0, 240, 255, 0.45);
}

QPlainTextEdit {
    background: rgba(2, 6, 23, 0.85);
    color: #38bdf8;
    border: 1px solid rgba(0, 240, 255, 0.2);
    border-radius: 12px;
    font-family: 'Consolas', 'JetBrains Mono', monospace;
    font-size: 11px;
    padding: 10px;
}

QCheckBox { color: #e2e8f0; font-size: 12px; font-family: 'Segoe UI'; spacing: 10px; }
QCheckBox::indicator {
    width: 38px;
    height: 20px;
    border-radius: 10px;
    border: 1px solid rgba(148, 163, 184, 0.3);
    background: rgba(15, 23, 42, 0.6);
}
QCheckBox::indicator:checked {
    background: rgba(16, 185, 129, 0.45);
    border: 1px solid rgba(52, 211, 153, 0.8);
}
"""


def api(path, payload=None):
    headers = {"Content-Type": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(SERVER + path, data=data, headers=headers,
                                 method="POST" if payload is not None else "GET")
    with urllib.request.urlopen(req, timeout=14) as resp:
        return json.loads(resp.read().decode("utf-8"))


def card_frame(title):
    f = QFrame(); f.setObjectName("Card")
    lay = QVBoxLayout(f); lay.setContentsMargins(16, 14, 16, 14); lay.setSpacing(8)
    t = QLabel("⚡ " + title.upper()); t.setObjectName("CardTitle")
    line = QFrame(); line.setFixedHeight(1)
    line.setStyleSheet("background: rgba(0,240,255,0.35); border: none;")
    lay.addWidget(t); lay.addWidget(line)
    return f, lay


class Dot(QLabel):
    def __init__(self):
        super().__init__("●"); self.setAlignment(Qt.AlignmentFlag.AlignCenter); self.set_ok(False)
    def set_ok(self, ok):
        self.setStyleSheet(f"color: {'#10b981' if ok else '#f43f5e'}; font-size: 13px; font-family: 'Segoe UI';")


class StatusThread(QThread):
    ready = pyqtSignal(dict)
    def run(self):
        try:
            self.ready.emit(api("/api/node/status"))
        except Exception:
            self.ready.emit({"ok": False})


class ActionResult(QThread):
    done = pyqtSignal(dict)
    def __init__(self, path, parent=None):
        super().__init__(parent); self.path = path
    def run(self):
        try:
            self.done.emit(api(self.path, {}))
        except Exception as e:
            self.done.emit({"ok": False, "error": str(e)})


PERMS = [
    ("voice_whisper", "Voz / Whisper"), ("camera_vision", "Câmera e Gestos"),
    ("screen_capture", "Captura de tela"), ("keyboard_mouse", "Teclado e Mouse"),
    ("clipboard", "Clipboard"), ("apps", "Abrir/Fechar apps"),
    ("windows_mgmt", "Janelas"), ("media", "Mídia e Volume"),
    ("telemetry", "Telemetria"), ("system_commands", "PowerShell/CMD livre"),
    ("power", "Desligar/Reiniciar/Suspender"),
]
PERM_LABELS = dict(PERMS)


class ControlWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("J.A.R.V.I.S. — Central de Controle do Nó")
        self.resize(1100, 830)
        self._settings_loaded = False
        root = QWidget(); root.setObjectName("Root"); self.setCentralWidget(root)
        outer = QVBoxLayout(root); outer.setContentsMargins(24, 18, 24, 18); outer.setSpacing(12)

        self.h1 = QLabel("J.A.R.V.I.S. · NODE CONTROL"); self.h1.setObjectName("H1")
        self.sub = QLabel("conectando…"); self.sub.setObjectName("Sub")
        outer.addWidget(self.h1); outer.addWidget(self.sub)

        scroller = QScrollArea(); scroller.setWidgetResizable(True)
        scroller.setStyleSheet("QScrollArea{border:none;background:transparent}")
        body = QWidget(); body.setStyleSheet("background: transparent")
        grid = QGridLayout(body); grid.setSpacing(12); grid.setContentsMargins(0, 0, 0, 0)
        scroller.setWidget(body); outer.addWidget(scroller, 1)

        # === Núcleo
        f, lay = card_frame("Núcleo (ZimaOS)")
        row = QHBoxLayout(); self.coreDot = Dot(); row.addWidget(self.coreDot)
        row.addWidget(QLabel("Ponte de comandos")); self.vBridge = QLabel("—"); self.vBridge.setObjectName("Val")
        row.addStretch(); row.addWidget(self.vBridge); lay.addLayout(row)
        row2 = QHBoxLayout(); row2.addWidget(QLabel("Último poll"))
        self.vPoll = QLabel("—"); self.vPoll.setObjectName("Val"); row2.addStretch(); row2.addWidget(self.vPoll)
        lay.addLayout(row2)
        self.btnRound = QPushButton("⇄ TESTAR ROUNDTRIP NÚCLEO→NÓ")
        self.btnRound.clicked.connect(self._roundtrip); lay.addWidget(self.btnRound)
        grid.addWidget(f, 0, 0)

        # === Voz
        f, lay = card_frame("Voz / Whisper")
        row = QHBoxLayout(); row.addWidget(QLabel("Motor"))
        self.vWhisper = QLabel("—"); self.vWhisper.setObjectName("Val"); row.addStretch(); row.addWidget(self.vWhisper)
        lay.addLayout(row)
        rowM = QHBoxLayout(); rowM.addWidget(QLabel("Microfone"))
        self.vMic = QLabel("—"); self.vMic.setObjectName("Val"); rowM.addStretch(); rowM.addWidget(self.vMic)
        lay.addLayout(rowM)
        self.btnMic = QPushButton("🎙 TESTAR MICROFONE (1.5s)")
        self.btnMic.clicked.connect(self._mic); lay.addWidget(self.btnMic)
        self.btnCallJarvis = QPushButton("◉ CHAMAR JARVIS (acordar ilha)")
        self.btnCallJarvis.clicked.connect(self._call_jarvis); lay.addWidget(self.btnCallJarvis)
        lay.addWidget(self._muted("A ilha escuta continuamente; fale 'Jarvis' e veja a transcrição ao vivo."))
        grid.addWidget(f, 0, 1)

        # === Comportamento
        f, lay = card_frame("Comportamento da Ilha")
        self.chkWake = QCheckBox("Wake word “Jarvis” (só fala com ativação)")
        self.chkAsk = QCheckBox("Perguntar antes de exibir painéis")
        self.chkWake.toggled.connect(self._save_settings)
        self.chkAsk.toggled.connect(self._save_settings)
        lay.addWidget(self.chkWake); lay.addWidget(self.chkAsk)
        lay.addWidget(self._muted("Wake OFF: toda fala é enviada. Ask OFF: painéis abrem na hora."))
        grid.addWidget(f, 0, 2)

        # === Captura
        f, lay = card_frame("Captura de Tela")
        self.btnShot = QPushButton("📸 CAPTURAR AGORA")
        self.btnShot.clicked.connect(self._shot); lay.addWidget(self.btnShot)
        self.shotBox = QLabel("—"); self.shotBox.setStyleSheet("border:1px solid rgba(0,240,255,0.3); border-radius:10px;")
        self.shotBox.setFixedHeight(150); self.shotBox.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.shotBox)
        grid.addWidget(f, 1, 0)

        # === Mouse
        f, lay = card_frame("Teclado & Mouse")
        row = QHBoxLayout(); row.addWidget(QLabel("Cursor"))
        self.vMouse = QLabel("—"); self.vMouse.setObjectName("Val"); row.addStretch(); row.addWidget(self.vMouse)
        lay.addLayout(row)
        self.btnMouse = QPushButton("🖱 CURSOR AO CENTRO E VOLTAR")
        self.btnMouse.clicked.connect(self._mouse); lay.addWidget(self.btnMouse)
        grid.addWidget(f, 1, 1)

        # === Autostart + info do nó
        f, lay = card_frame("Inicialização & Nó")
        self.chkAuto = QCheckBox("Iniciar com o Windows")
        self.chkAuto.toggled.connect(self._autostart_toggle)
        lay.addWidget(self.chkAuto)
        self.lblNode = QLabel("node: —"); self.lblNode.setObjectName("Muted"); lay.addWidget(self.lblNode)
        self.lblPlatform = QLabel("—"); self.lblPlatform.setObjectName("Muted"); lay.addWidget(self.lblPlatform)
        grid.addWidget(f, 1, 2)

        # === Permissões
        f, lay = card_frame("Permissões do nó — o J.A.R.V.I.S. respeita na hora")
        gridp = QGridLayout(); gridp.setHorizontalSpacing(24); gridp.setVerticalSpacing(6)
        self.perm_checks = {}
        for i, (cat, label) in enumerate(PERMS):
            chk = QCheckBox(label); chk.setChecked(True)
            chk.toggled.connect(lambda on, c=cat: self._set_perm(c, on))
            gridp.addWidget(chk, i // 4, i % 4)
            self.perm_checks[cat] = chk
        lay.addLayout(gridp)
        grid.addWidget(f, 2, 0, 1, 3)

        # === Log
        f, lay = card_frame("Log da Ponte — comandos recebidos/executados")
        self.log = QPlainTextEdit(); self.log.setReadOnly(True)
        self.log.setFixedHeight(180); lay.addWidget(self.log)
        grid.addWidget(f, 3, 0, 1, 3)

        self._t = QTimer(self); self._t.timeout.connect(self.refresh); self._t.start(4000)
        self.refresh()

    def _muted(self, txt):
        q = QLabel(txt); q.setObjectName("Muted"); q.setWordWrap(True); return q

    def refresh(self):
        self.thread = StatusThread(); self.thread.ready.connect(self._apply_status); self.thread.start()

    def _apply_status(self, st):
        if not st.get("ok"):
            self.coreDot.set_ok(False); self.vBridge.setText("OFFLINE"); self.vBridge.setStyleSheet("color:#f43f5e;")
            return
        b = st.get("bridge", {})
        live = bool(b.get("connected"))
        self.coreDot.set_ok(live)
        self.vBridge.setText("CONECTADO" if live else "OFFLINE")
        self.vBridge.setStyleSheet("color:#10b981;" if live else "color:#f43f5e;")
        self.vPoll.setText((str(b.get("seconds_since_poll")) + "s") if b.get("seconds_since_poll") is not None else "nunca")
        w = st.get("whisper", {})
        self.vWhisper.setText("Whisper LOCAL na GPU" if w.get("runtime_local") else f"Fallback → {w.get('fallback')}")
        m = st.get("mic", {})
        if m:
            self.vMic.setText(str(m.get("selected", "—")))
        self.sub.setText(f"{st.get('node_id')} · {st.get('hostname')} — centrada na máquina local · núcleo no ZimaOS")
        self.lblNode.setText(f"node: {st.get('node_id')} · porta {st.get('port')}")
        self.lblPlatform.setText(str(st.get('platform', ''))[:60])
        self.chkAuto.blockSignals(True); self.chkAuto.setChecked(bool(st.get("autostart"))); self.chkAuto.blockSignals(False)
        if not self._settings_loaded:
            self._settings_loaded = True
            self._load_settings()
            self._apply_perms(st.get("permissions", {}))
        self._load_log()

    def _apply_perms(self, perms):
        for cat, on in perms.items():
            chk = self.perm_checks.get(cat)
            if chk is not None:
                chk.blockSignals(True); chk.setChecked(bool(on)); chk.blockSignals(False)

    def _load_settings(self):
        try:
            s = api("/api/node/settings").get("settings", {})
            self.chkWake.blockSignals(True); self.chkWake.setChecked(bool(s.get("wake_word_enabled", True))); self.chkWake.blockSignals(False)
            self.chkAsk.blockSignals(True); self.chkAsk.setChecked(bool(s.get("ask_before_show", True))); self.chkAsk.blockSignals(False)
        except Exception:
            pass

    def _save_settings(self, *_):
        payload = {"settings": {
            "wake_word_enabled": self.chkWake.isChecked(),
            "ask_before_show": self.chkAsk.isChecked()
        }}
        try:
            api("/api/node/settings", payload)
        except Exception:
            pass

    def _set_perm(self, cat, on):
        try:
            api("/api/node/permission", {"category": cat, "enabled": on})
        except Exception:
            pass

    def _roundtrip(self):
        self.btnRound.setText("⇄ medindo ciclo…"); self.btnRound.setEnabled(False)
        def fin(res):
            ok = res.get("ok")
            txt = res.get("message") or res.get("error") or "sem resposta"
            self.btnRound.setEnabled(True); self.btnRound.setText("⇄ TESTAR ROUNDTRIP NÚCLEO→NÓ")
            self.statusBar().showMessage(("ROUNDTRIP OK — " if ok else "ROUNDTRIP FALHOU — ") + str(txt)[:120], 8000)
        self._job = ActionResult("/api/node/test/bridge"); self._job.done.connect(fin); self._job.start()

    def _mic(self):
        self.btnMic.setEnabled(True); self.btnMic.setText("🎙 escutando…")
        def fin(res):
            self.btnMic.setEnabled(True); self.btnMic.setText("🎙 TESTAR MICROFONE (1.5s)")
            txt = res.get("message") or res.get("error") or "sem resposta"
            self.statusBar().showMessage(str(txt)[:140], 6000)
        self._job2 = ActionResult("/api/node/test/mic"); self._job2.done.connect(fin); self._job2.start()
        self.btnMic.setEnabled(False)

    def _shot(self):
        self.btnShot.setEnabled(False); self.btnShot.setText("📸 capturando…")
        def fin(res):
            self.btnShot.setEnabled(True); self.btnShot.setText("📸 CAPTURAR AGORA")
            if res.get("ok"):
                import base64
                pm = QPixmap()
                pm.loadFromData(base64.b64decode((res.get("image") or "").split(",", 1)[-1]), "JPEG")
                self.shotBox.setPixmap(pm.scaled(self.shotBox.width(), 150, Qt.AspectRatioMode.KeepAspectRatioByExpanding))
                self.statusBar().showMessage(f"Captura salva: {res.get('path')}", 6000)
            else:
                self.statusBar().showMessage(str(res.get("error", "falha"))[:140], 6000)
        self._job3 = ActionResult("/api/node/test/screenshot"); self._job3.done.connect(fin); self._job3.start()
        self.btnShot.setEnabled(False)

    def _mouse(self):
        self.btnMouse.setEnabled(False)
        def fin(res):
            self.btnMouse.setEnabled(True)
            txt = res.get("message") or res.get("error") or "sem resposta"
            self.statusBar().showMessage(str(txt)[:140], 6000)
        self._job4 = ActionResult("/api/node/test/mouse"); self._job4.done.connect(fin); self._job4.start()

    def _call_jarvis(self):
        """Acorda a Dynamic Island via SSE local (sem navegador)."""
        try:
            payload = json.dumps({"action": "island_show", "title": "J.A.R.V.I.S.", "message": "Ilha chamada da Central de Controle."}).encode("utf-8")
            req = urllib.request.Request(SERVER + "/api/hud/control", data=payload, headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=5)
            self.statusBar().showMessage("Ilha acordada — fale com o Jarvis, Senhor Werik.", 5000)
        except Exception as e:
            self.statusBar().showMessage(f"Falha ao acordar ilha: {e}", 6000)

    def _load_log(self):
        try:
            r = urllib.request.Request(SERVER + "/api/node/log")
            with urllib.request.urlopen(r, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            self.log.setPlainText((data.get("log") or "").strip()[-2500:])
        except Exception:
            pass

    def _autostart_toggle(self, on):
        try:
            api("/api/node/autostart", {"enabled": bool(on)})
            self.statusBar().showMessage("Autostart registrado" if on else "Autostart removido", 5000)
        except Exception:
            pass


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS)
    w = ControlWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
