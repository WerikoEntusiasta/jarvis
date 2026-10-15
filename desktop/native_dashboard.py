"""
J.A.R.V.I.S. Console Nativo — chat de comando SEM navegador
Interface interna do app Windows: status do nó + console de conversa com o Jarvis
(chamada direta ao núcleo via /api/chat, com transcrição na Dynamic Island).
Uso: pythonw native_dashboard.py (ou JarvisDesktop.exe --dashboard)
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

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QPlainTextEdit, QLineEdit, QScrollArea
)

SERVER = os.environ.get("JARVIS_CORE_URL", os.environ.get("JARVIS_LOCAL_URL", "https://jarvis.werikspace.xyz"))

QSS = """
QWidget#Root { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #01091d, stop:0.55 #030e22, stop:1 #010b16); }
QLabel { color: #e2f3ff; font-family: 'Segoe UI'; }
QLabel#H1 { color: #00f0ff; font-size: 18px; font-weight: 800; letter-spacing: 3px; }
QLabel#Sub { color: #7fb1cc; font-size: 11px; letter-spacing: 2px; }
QLabel#Chip { color: #cfe8ff; font-size: 12px; font-family: 'Segoe UI'; }
QFrame#Card { background: rgba(4,12,28,0.92); border: 1px solid rgba(0,240,255,0.26); border-radius: 14px; }
QPlainTextEdit { background: rgba(0,0,0,0.42); color: #cfe8ff; border: 1px solid rgba(0,240,255,0.18);
    border-radius: 10px; font-family: 'Segoe UI'; font-size: 12.5px; padding: 10px; }
QLineEdit {
    background: rgba(4,12,28,0.95); color: #e2f3ff; border: 1px solid rgba(0,240,255,0.4);
    border-radius: 12px; padding: 10px 14px; font-size: 13px; font-family: 'Segoe UI';
}
QLineEdit:focus { border-color: #00f0ff; }
QPushButton {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #00e5ff, stop:1 #0284c7);
    color: #020d20; border: none; border-radius: 12px; padding: 9px 18px;
    font-size: 12px; font-weight: 800; font-family: 'Segoe UI';
}
QPushButton:hover { background: #38bdf8; }
QPushButton:disabled { background: rgba(0,240,255,0.2); color: #7fb1cc; }
QPushButton#Ghost {
    background: rgba(0,240,255,0.14); color: #7dd3fc; border: 1px solid rgba(0,240,255,0.4);
}
QPushButton#Ghost:hover { background: rgba(0,240,255,0.3); color: #ffffff; }
"""


def api(path, payload=None, timeout=45):
    headers = {"Content-Type": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(SERVER + path, data=data, headers=headers,
                                 method="POST" if payload is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


class ChatWorker(QThread):
    done = pyqtSignal(dict)
    def __init__(self, message, parent=None):
        super().__init__(parent); self.message = message
    def run(self):
        try:
            self.done.emit(api("/api/chat", {"message": self.message}))
        except Exception as e:
            self.done.emit({"reply": f"✗ Falha na comunicação com o núcleo: {e}", "error": True})


class StatusWorker(QThread):
    done = pyqtSignal(dict)
    def run(self):
        try:
            self.done.emit(api("/api/node/status", timeout=8))
        except Exception:
            self.done.emit({"ok": False})


class ConsoleWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("J.A.R.V.I.S. — Console")
        self.resize(920, 760)
        root = QWidget(); root.setObjectName("Root"); self.setCentralWidget(root)
        outer = QVBoxLayout(root); outer.setContentsMargins(22, 16, 22, 16); outer.setSpacing(10)

        h1 = QLabel("J.A.R.V.I.S. · CONSOLE NATIVO"); h1.setObjectName("H1")
        self.sub = QLabel("núcleo no ZimaOS · island ouvindo · wake word ativa"); self.sub.setObjectName("Sub")
        outer.addWidget(h1); outer.addWidget(self.sub)

        # Chipes de status
        chips = QHBoxLayout(); chips.setSpacing(14)
        self.chipCore = QLabel("● núcleo …"); self.chipCore.setObjectName("Chip")
        self.chipWhisper = QLabel("whisper …"); self.chipWhisper.setObjectName("Chip")
        self.chipMic = QLabel("mic …"); self.chipMic.setObjectName("Chip")
        chips.addWidget(self.chipCore); chips.addWidget(self.chipWhisper); chips.addWidget(self.chipMic); chips.addStretch()
        outer.addLayout(chips)

        # Ações
        acts = QHBoxLayout(); acts.setSpacing(10)
        self.btnCall = QPushButton("◉ CHAMAR JARVIS (isla)")
        self.btnCall.setObjectName("Ghost")
        self.btnCall.clicked.connect(self.call_jarvis)
        acts.addWidget(self.btnCall)
        self.btnCentral = QPushButton("⚙ CENTRAL DO NÓ")
        self.btnCentral.setObjectName("Ghost")
        self.btnCentral.clicked.connect(self.open_central)
        acts.addWidget(self.btnCentral)
        acts.addStretch()
        outer.addLayout(acts)

        # Console de chat
        self.chat = QPlainTextEdit(); self.chat.setReadOnly(True)
        self.chat.setPlaceholderText("Digite um comando para o Jarvis e pressione Enter…\nEx.: \"abrir spotify\", \"telemetria do meu pc\", \"próxima música\"")
        outer.addWidget(self.chat, 1)

        # Input
        row = QHBoxLayout(); row.setSpacing(10)
        self.input = QLineEdit()
        self.input.setPlaceholderText("Falar com o J.A.R.V.I.S. …")
        self.input.returnPressed.connect(self.send)
        row.addWidget(self.input, 1)
        self.btnSend = QPushButton("➤ ENVIAR")
        self.btnSend.clicked.connect(self.send)
        row.addWidget(self.btnSend)
        outer.addLayout(row)

        self._t = QTimer(self); self._t.timeout.connect(self.refresh_status); self._t.start(5000)
        self.refresh_status()
        self._append("sys", "Console nativo do J.A.R.V.I.S. pronto, Senhor Werik.")
        self._append("sys", "A ilha escuta continuamente — diga \"Jarvis\" e fale. Este console aceita comandos escritos.")

    def _append(self, who, text):
        prefix = "VOCÊ" if who == "user" else ("JARVIS" if who == "jarvis" else "·")
        self.chat.appendPlainText(f"[{prefix}] {text}")
        sb = self.chat.verticalScrollBar()
        sb.setValue(sb.maximum())

    def refresh_status(self):
        w = StatusWorker(); w.done.connect(self._apply); w.start()

    def _apply(self, st):
        if not st.get("ok"):
            self.chipCore.setText("● núcleo OFFLINE"); self.chipCore.setStyleSheet("color:#f43f5e;")
            return
        b = st.get("bridge", {})
        live = bool(b.get("connected"))
        self.chipCore.setText(("● núcleo CONNECTED" if live else "● núcleo OFFLINE"))
        self.chipCore.setStyleSheet(f"color:{'#10b981' if live else '#f43f5e'};")
        w = st.get("whisper", {})
        self.chipWhisper.setText(("whisper LOCAL" if w.get("runtime_local") else f"whisper → {w.get('fallback')}"))
        m = st.get("mic", {})
        self.chipMic.setText(f"mic: {m.get('selected', '—')}")
        self.sub.setText(f"{st.get('node_id')} · island ouvindo · wake word ativa")

    def send(self):
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self._append("user", text)
        self.btnSend.setEnabled(False); self.btnSend.setText("⏳")
        self._worker = ChatWorker(text); self._worker.done.connect(self._reply); self._worker.start()

    def _reply(self, data):
        self.btnSend.setEnabled(True); self.btnSend.setText("➤ ENVIAR")
        reply = data.get("reply") or "(sem resposta)"
        self._append("jarvis", reply)
        audio = data.get("audio_url")
        if audio:
            self._append("sys", f"resposta falada em áudio: {audio}")

    def call_jarvis(self):
        try:
            api("/api/hud/control", {"action": "island_show", "title": "J.A.R.V.I.S.", "message": "Console nativo chamado pelo operador."})
            self._append("sys", "isla acordada — fale com o Jarvis, Senhor Werik.")
        except Exception as e:
            self._append("sys", f"falha ao acordar a ilha: {e}")

    def open_central(self):
        import subprocess
        try:
            if getattr(sys, "frozen", False):
                subprocess.Popen([sys.executable, "--control"], cwd=os.path.dirname(sys.executable) or ".")
            else:
                script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "native_control.py")
                pyw = (sys.executable or "python.exe").replace("python.exe", "pythonw.exe")
                target = pyw if os.path.exists(pyw) else (sys.executable or "python.exe")
                subprocess.Popen([target, script], shell=False)
        except Exception:
            import webbrowser
            webbrowser.open(SERVER + "/node")


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS)
    w = ConsoleWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
