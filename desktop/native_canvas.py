"""
J.A.R.V.I.S. Native Canvas — janela NATIVA do painel holográfico (PyQt6)
Renderiza blocos do payload (/api/canvas/payload?pid=) sem navegador:
métricas, listas chave-valor, texto, terminal, gráfico de barras e tabelas.
Uso: pythonw native_canvas.py <pid>  (ou JarvisDesktop.exe --canvas <pid>)
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

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame, QScrollArea, QGridLayout, QPlainTextEdit
)

SERVER = os.environ.get("JARVIS_CORE_URL", os.environ.get("JARVIS_LOCAL_URL", "https://jarvis.werikspace.xyz"))

QSS = """
QWidget#Root { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #01091d, stop:0.55 #030e22, stop:1 #010b16); }
QLabel { color: #e2f3ff; font-family: 'Segoe UI'; }
QLabel#H1 { color: #00f0ff; font-size: 17px; font-weight: 800; letter-spacing: 3px; }
QLabel#Sub { color: #7fb1cc; font-size: 10px; letter-spacing: 2px; }
QFrame#Card { background: rgba(4,12,28,0.92); border: 1px solid rgba(0,240,255,0.26); border-radius: 14px; }
QFrame#Line { background: rgba(0,240,255,0.5); border: none; max-height: 1px; }
QLabel#CardTitle { color: #38bdf8; font-size: 11px; font-weight: 800; letter-spacing: 2px; }
QLabel#Big { color: #00f0ff; font-size: 28px; font-weight: 800; }
QLabel#Unit { color: #7fb1cc; font-size: 12px; }
QLabel#Text { color: #d8ecff; font-size: 12.5px; }
QLabel#KVKey { color: #cfe8ff; font-size: 12px; }
QLabel#KVVal { color: #00f0ff; font-size: 12px; font-weight: 700; }
QPlainTextEdit { background: rgba(0,0,0,0.45); color: #9fdceb; border: 1px solid rgba(0,240,255,0.18);
    border-radius: 10px; font-family: 'Consolas', monospace; font-size: 11px; padding: 8px; }
QPushButton {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 rgba(0,240,255,0.16), stop:1 rgba(56,189,248,0.16));
    color: #e2f3ff; border: 1px solid rgba(0,240,255,0.4); border-radius: 10px;
    padding: 6px 13px; font-size: 11.5px; font-weight: 700; font-family: 'Segoe UI';
}
QPushButton:hover { background: rgba(0,240,255,0.3); }
QLabel#Bar { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #00f0ff, stop:1 rgba(56,189,248,0.25));
    border-radius: 3px; }
"""


def card(title=None):
    f = QFrame(); f.setObjectName("Card")
    lay = QVBoxLayout(f); lay.setContentsMargins(14, 12, 14, 12); lay.setSpacing(6)
    if title:
        t = QLabel("◈ " + str(title).upper()); t.setObjectName("CardTitle"); lay.addWidget(t)
        line = QFrame(); line.setObjectName("Line"); line.setFixedHeight(1); lay.addWidget(line)
    return f, lay


def kv_row(k, v):
    row = QHBoxLayout()
    a = QLabel(str(k)); a.setObjectName("KVKey")
    b = QLabel(str(v)); b.setObjectName("KVVal")
    row.addWidget(a); row.addStretch(); row.addWidget(b)
    return row


def build_block(p):
    f, lay = card(p.get("title") or p.get("label"))
    ptype = str(p.get("type") or "").lower()

    if ptype == "metric" or ("value" in p and p.get("big")):
        mrow = QHBoxLayout()
        big = QLabel(str(p.get("value", "—"))); big.setObjectName("Big")
        unit = QLabel(str(p.get("unit") or "")); unit.setObjectName("Unit")
        mrow.addWidget(big); mrow.addWidget(unit); mrow.addStretch()
        lay.addLayout(mrow)
        if p.get("sub"):
            s = QLabel(str(p["sub"])); s.setObjectName("Unit"); lay.addWidget(s)

    elif ptype in ("terminal", "code") or p.get("stdout"):
        t = QPlainTextEdit(); t.setReadOnly(True)
        t.setPlainText(str(p.get("content") or p.get("text") or p.get("stdout") or ""))
        t.setFixedHeight(min(240, 60 + t.toPlainText().count("\n") * 16))
        lay.addWidget(t)

    elif isinstance(p.get("items") or p.get("data"), (list, dict)) and ptype != "chart":
        src = p.get("items") or p.get("data") or {}
        items = src if isinstance(src, list) else [{"label": k, "value": v} for k, v in src.items()]
        for it in items[:40]:
            if isinstance(it, dict):
                lay.addLayout(kv_row(it.get("label") or it.get("name") or it.get("key") or "",
                                     it.get("value") if it.get("value") is not None else it.get("val", "")))
            else:
                lay.addLayout(kv_row(str(it), ""))

    elif isinstance(p.get("rows"), list) and p.get("columns"):
        cols = p["columns"]
        for row in p["rows"][:40]:
            r = QHBoxLayout()
            for c in cols:
                r.addWidget(QLabel(str(row.get(c, "—")))); r.addStretch()
            lay.addLayout(r)

    elif ptype == "chart" or isinstance(p.get("values"), list):
        data = [float(v) for v in (p.get("data") or p.get("values") or []) if str(v).replace(".", "").replace("-", "").isdigit()]
        bars = QHBoxLayout(); bars.setSpacing(4)
        for v in data[:26]:
            bar = QLabel(); bar.setObjectName("Bar")
            bar.setFixedHeight(6 + int(max(0, min(100, v)) * 0.85))
            bar.setFixedWidth(18)
            bars.addWidget(bar)
        bars.addStretch()
        if data:
            lay.addLayout(bars)
        else:
            lay.addWidget(QLabel("sem dados de série"))

    else:
        t = QLabel(str(p.get("content") or p.get("text") or p.get("message") or "—"))
        t.setObjectName("Text"); t.setWordWrap(True); lay.addWidget(t)

    return f


def fetch_payload(pid):
    req = urllib.request.Request(f"{SERVER}/api/canvas/payload?pid=" + str(pid))
    with urllib.request.urlopen(req, timeout=12) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("payload") or {}


try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtCore import QUrl
    HAS_WEBENGINE = True
except Exception:
    HAS_WEBENGINE = False


class CanvasWindow(QMainWindow):
    def __init__(self, pid: str):
        super().__init__()
        self.setWindowTitle("J.A.R.V.I.S. Canvas Holográfico")
        self.resize(1160, 760)

        # Se o QWebEngineView estiver disponível, renderiza o HTML + CSS do OpenClaw com 100% de fidelidade
        if HAS_WEBENGINE and pid:
            try:
                self.web = QWebEngineView()
                self.web.load(QUrl(f"{SERVER}/canvas_panel?pid={pid}"))
                self.setCentralWidget(self.web)
                return
            except Exception as ew:
                print(f"[CanvasWindow] Erro ao carregar WebEngineView: {ew}")

        try:
            payload = fetch_payload(pid)
        except Exception:
            payload = {}
        root = QWidget(); root.setObjectName("Root"); self.setCentralWidget(root)
        outer = QVBoxLayout(root); outer.setContentsMargins(24, 18, 24, 18); outer.setSpacing(14)

        title = str(payload.get("title") or "PAINEL J.A.R.V.I.S.").upper()
        h1 = QLabel(title); h1.setObjectName("H1")
        sub = QLabel(((payload.get("category") or "CANVAS") + " · " + (payload.get("subtitle") or "canvas holográfico")).upper())
        sub.setObjectName("Sub")
        arc = QLabel("◉"); arc.setStyleSheet("color:#00f0ff; font-size: 30px;")
        hrow = QHBoxLayout(); hrow.addWidget(arc); hrow.addLayout(_col(h1, sub)); hrow.addStretch()
        outer.addLayout(hrow)

        scroller = QScrollArea(); scroller.setWidgetResizable(True)
        scroller.setStyleSheet("QScrollArea{border:none;background:transparent}")
        body = QWidget(); body.setStyleSheet("background: transparent")
        grid = QGridLayout(body); grid.setSpacing(12); grid.setContentsMargins(0, 0, 0, 0)
        blocks = payload.get("blocks") or payload.get("sections") or []
        if isinstance(blocks, list) and blocks:
            for i, b in enumerate(blocks):
                if isinstance(b, dict):
                    wide = bool(b.get("wide"))
                    grid.addWidget(build_block(b), grid.rowCount(), 0, 1, 2 if wide else 1)
        else:
            for k, v in payload.items():
                if k in ("title", "layout", "category", "subtitle", "blocks", "sections"):
                    continue
                if isinstance(v, (str, int, float)):
                    f, lay = card(k)
                    t = QLabel(str(v)); t.setObjectName("Text"); t.setWordWrap(True); lay.addWidget(t)
                    grid.addWidget(f, grid.rowCount(), 0, 1, 2)
        if grid.count() == 0:
            empty = QLabel("painel vazio ou expirado"); empty.setObjectName("Sub")
            grid.addWidget(empty, 0, 0)
        scroller.setWidget(body); outer.addWidget(scroller, 1)


def _col(h, s):
    lay = QVBoxLayout(); lay.addWidget(h); lay.addWidget(s); return lay


def main():
    pid = sys.argv[1] if len(sys.argv) > 1 else ""
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS)
    w = CanvasWindow(pid)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
