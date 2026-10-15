"""Portão PIN do JARVIS Desktop: teclado numérico, 8 dígitos, hash+salt local.

Ao iniciar o app (e portanto a cada boot do Windows), abre esta tela;
só libera o node após o PIN correto. Sem segredo no código — hash e salt
ficam em config/pin_auth.json (não versionado).

CORREÇÃO DO CRASH ANTERIOR ("QWidget: Must construct a QApplication
before a QWidget"): o QApplication criado dentro de uma função era
coletado pelo garbage collector quando a função retornava. A referência
agora é guardada na global _QT_APP.
"""

import hashlib
import json
import os
import secrets
import time

PIN_LENGTH = 8
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 60

_QT_APP = None  # referência GLOBAL obrigatória — sem ela o Qt morre


def _pin_path():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "config", "pin_auth.json")


def _load_state():
    try:
        with open(_pin_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _save_state(state):
    try:
        os.makedirs(os.path.dirname(_pin_path()), exist_ok=True)
        with open(_pin_path(), "w", encoding="utf-8") as f:
            json.dump(state, f)
        return True
    except Exception:
        return False


def is_configured():
    st = _load_state()
    return bool(st.get("salt")) and bool(st.get("hash"))


def hash_pin(pin, salt):
    return hashlib.sha256((salt + ":" + pin).encode("utf-8")).hexdigest()


def set_pin(pin):
    """Define o PIN (8 dígitos). Retorna (ok, mensagem)."""
    pin = str(pin or "").strip()
    if not (pin.isdigit() and len(pin) == PIN_LENGTH):
        return False, f"PIN deve ter {PIN_LENGTH} dígitos numéricos."
    salt = secrets.token_hex(16)
    if not _save_state({"salt": salt, "hash": hash_pin(pin, salt), "fails": 0, "locked_until": 0}):
        return False, "Falha ao salvar. Verifique a pasta config/."
    return True, "PIN definido."


def verify_pin(pin):
    """Confere o PIN com trava anti-força-bruta. Retorna (ok, mensagem)."""
    st = _load_state()
    now = time.time()
    if not st.get("salt") or not st.get("hash"):
        return False, "PIN não configurado."
    if float(st.get("locked_until", 0)) > now:
        wait = int(float(st["locked_until"]) - now)
        return False, f"Bloqueado. Tente em {wait}s."
    ok = hash_pin(str(pin or "").strip(), st["salt"]) == st["hash"]
    if ok:
        st["fails"] = 0
        st["locked_until"] = 0
        _save_state(st)
        return True, "Desbloqueado."
    fails = int(st.get("fails", 0)) + 1
    st["fails"] = fails
    if fails >= MAX_ATTEMPTS:
        st["locked_until"] = now + LOCKOUT_SECONDS
        _save_state(st)
        return False, f"5 erros. Bloqueado por {LOCKOUT_SECONDS}s."
    _save_state(st)
    return False, f"PIN incorreto ({MAX_ATTEMPTS - fails} tentativas restantes)."


QSS = """
QDialog { background: #0d0e13; }
QLabel#PinTitle { color: #00f0ff; font-size: 20px; font-weight: 800; }
QLabel#PinDots { color: #f4f4f7; font-size: 34px; letter-spacing: 8px; }
QLabel#PinMsg { color: #9c9eaa; font-size: 12px; }
QPushButton#PinKey {
    background: #1c1d24; color: #f4f4f7; border: 1px solid #393a43;
    border-radius: 12px; font-size: 22px; font-weight: 700; min-width: 72px; min-height: 56px;
}
QPushButton#PinKey:hover { border-color: #00f0ff; }
QPushButton#PinGo {
    background: rgba(0,240,255,.12); color: #00f0ff; border: 1px solid #00f0ff;
    border-radius: 12px; font-size: 15px; font-weight: 800; min-height: 48px;
}
"""


def _ensure_qapp():
    """Cria/segura o QApplication. A referência GLOBAL é obrigatória:
    sem ela o Python coleta o objeto e o próximo widget morre com
    'QWidget: Must construct a QApplication before a QWidget'."""
    global _QT_APP
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    _QT_APP = app
    return app


def run_pin_gate():
    """Abre a tela do PIN (cria no primeiro uso). Retorna True se desbloqueado."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QDialog, QVBoxLayout, QGridLayout, QLabel, QPushButton

    _ensure_qapp()
    creating = not is_configured()
    first_entry = {"value": None}

    dlg = QDialog()
    dlg.setWindowTitle("J.A.R.V.I.S. — Desbloquear")
    dlg.setFixedSize(320, 480 if creating else 440)
    dlg.setStyleSheet(QSS)
    dlg.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

    layout = QVBoxLayout(dlg)
    title = QLabel("Criar PIN de 8 dígitos" if creating else "Digite o PIN")
    title.setObjectName("PinTitle")
    layout.addWidget(title)

    dots = QLabel("")
    dots.setObjectName("PinDots")
    dots.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(dots)

    msg = QLabel("Somente números." if creating else "8 dígitos para desbloquear.")
    msg.setObjectName("PinMsg")
    msg.setWordWrap(True)
    layout.addWidget(msg)

    state = {"buf": ""}

    def refresh():
        dots.setText("●" * len(state["buf"]))

    def submit():
        entered = state["buf"]
        if len(entered) != PIN_LENGTH:
            msg.setText(f"Digite os {PIN_LENGTH} dígitos.")
            return
        if creating:
            if first_entry["value"] is None:
                first_entry["value"] = entered
                state["buf"] = ""
                refresh()
                msg.setText("Repita para confirmar.")
                return
            if entered != first_entry["value"]:
                first_entry["value"] = None
                state["buf"] = ""
                refresh()
                msg.setText("Não conferiu. Comece de novo.")
                return
            ok, text = set_pin(entered)
            msg.setText(text)
            if ok:
                dlg.accept()
            else:
                first_entry["value"] = None
                state["buf"] = ""
                refresh()
        else:
            ok, text = verify_pin(entered)
            msg.setText(text)
            state["buf"] = ""
            refresh()
            if ok:
                dlg.accept()

    def press(d):
        if len(state["buf"]) < PIN_LENGTH:
            state["buf"] += d
            refresh()
            if len(state["buf"]) == PIN_LENGTH:
                submit()

    grid = QGridLayout()
    positions = [("1", 0, 0), ("2", 0, 1), ("3", 0, 2),
                 ("4", 1, 0), ("5", 1, 1), ("6", 1, 2),
                 ("7", 2, 0), ("8", 2, 1), ("9", 2, 2)]
    for digit, r, c in positions:
        b = QPushButton(digit)
        b.setObjectName("PinKey")
        b.clicked.connect(lambda _=False, d=digit: press(d))
        grid.addWidget(b, r, c)
    b0 = QPushButton("0")
    b0.setObjectName("PinKey")
    b0.clicked.connect(lambda: press("0"))
    grid.addWidget(b0, 3, 1)
    bclr = QPushButton("⌫")
    bclr.setObjectName("PinKey")
    bclr.clicked.connect(lambda: (state.update(buf=state["buf"][:-1]), refresh()))
    grid.addWidget(bclr, 3, 2)
    layout.addLayout(grid)

    go = QPushButton("DESBLOQUEAR")
    go.setObjectName("PinGo")
    go.clicked.connect(submit)
    layout.addWidget(go)

    dlg.setLayout(layout)
    # Janela criada: força visibilidade NATIVA. O VBS lança o app com
    # wShowWindow=SW_HIDE no STARTUPINFO e o Qt herda o "escondido" —
    # o diálogo ficava preso invisível. SW_RESTORE (9) vence o SW_HIDE.
    dlg.show()
    try:
        import ctypes
        hwnd = int(dlg.winId())
        ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    except Exception:
        pass
    dlg.raise_()
    dlg.activateWindow()
    return dlg.exec() == QDialog.DialogCode.Accepted
