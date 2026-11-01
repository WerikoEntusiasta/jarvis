"""
Estilos e Temas Visuais Fiel ao WebUI J.A.R.V.I.S. (Stark High-Tech HUD)
Cores, Glassmorphism, Fontes e Gradientes idênticos ao painel web.
"""

HUD_STYLESHEET = """
/* Fundo Principal Translúcido e Janela */
QWidget#CentralWidget {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(2, 6, 23, 0.96), stop:1 rgba(1, 4, 18, 0.98));
    border: 1px solid rgba(0, 240, 255, 0.45);
    border-radius: 16px;
}

/* Barra Superior / Header Pills */
QFrame#TopBarFrame {
    background-color: rgba(3, 15, 45, 0.90);
    border-bottom: 1px solid rgba(0, 240, 255, 0.30);
    border-top-left-radius: 16px;
    border-top-right-radius: 16px;
}

QLabel#BrandLogo {
    color: #00f0ff;
    font-size: 16px;
    font-weight: 800;
    letter-spacing: 3px;
    font-family: 'Space Grotesk', 'Segoe UI', sans-serif;
}

QLabel#BrandSub {
    color: #38bdf8;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1px;
}

/* Pílula de Status Geral */
QLabel#PillBadge {
    background-color: rgba(3, 28, 76, 0.90);
    border: 1px solid rgba(0, 240, 255, 0.50);
    border-radius: 12px;
    color: #38bdf8;
    font-size: 10px;
    font-weight: 700;
    padding: 3px 10px;
}

QLabel#OnlineDot {
    color: #34d399;
    font-size: 14px;
    font-weight: bold;
}

/* Cards de Vidro Táticos da Esquerda (Glassmorphism Stark) */
QFrame.StarkCard {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(3, 14, 38, 0.85), stop:1 rgba(1, 7, 24, 0.95));
    border: 1px solid rgba(0, 240, 255, 0.28);
    border-radius: 12px;
}

QFrame.StarkCard:hover {
    border: 1px solid rgba(0, 240, 255, 0.70);
}

QLabel.CardCategory {
    color: #38bdf8;
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 1.5px;
    text-transform: uppercase;
}

QLabel.CardTitle {
    color: #ffffff;
    font-size: 12px;
    font-weight: 700;
}

QLabel.CardStatText {
    color: #94a3b8;
    font-size: 11px;
    font-family: 'Consolas', 'JetBrains Mono', monospace;
}

QLabel.CardStatVal {
    color: #00f0ff;
    font-size: 11px;
    font-weight: 700;
    font-family: 'Consolas', 'JetBrains Mono', monospace;
}

/* Barras de Progresso Táticas */
QProgressBar {
    background-color: rgba(15, 23, 42, 0.9);
    border: 1px solid rgba(0, 240, 255, 0.2);
    border-radius: 3px;
    height: 6px;
    text-align: center;
}

QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0099ff, stop:1 #00f0ff);
    border-radius: 2px;
}

/* Área de Conversa e Terminal de IA */
QScrollArea {
    background: transparent;
    border: none;
}

QScrollBar:vertical {
    border: none;
    background: rgba(2, 6, 23, 0.4);
    width: 6px;
    border-radius: 3px;
}

QScrollBar::handle:vertical {
    background: rgba(0, 240, 255, 0.35);
    border-radius: 3px;
}

QScrollBar::handle:vertical:hover {
    background: #00f0ff;
}

/* Barra de Comando Inferior */
QFrame#CommandBarFrame {
    background-color: rgba(3, 14, 40, 0.85);
    border-top: 1px solid rgba(0, 240, 255, 0.25);
    border-bottom-left-radius: 16px;
    border-bottom-right-radius: 16px;
}

QLineEdit#CommandInput {
    background-color: rgba(1, 6, 22, 0.95);
    border: 1px solid rgba(0, 240, 255, 0.35);
    border-radius: 10px;
    color: #f8fafc;
    font-size: 13px;
    padding: 10px 14px;
    font-family: 'Segoe UI', sans-serif;
}

QLineEdit#CommandInput:focus {
    border: 1px solid #00f0ff;
    background-color: rgba(2, 8, 30, 1.0);
}

QPushButton#SendButton {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284c7, stop:1 #00f0ff);
    color: #020617;
    font-weight: 800;
    font-size: 11px;
    letter-spacing: 1px;
    border: none;
    border-radius: 10px;
    padding: 10px 18px;
}

QPushButton#SendButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0369a1, stop:1 #38bdf8);
}

QPushButton#MicButton {
    background-color: rgba(3, 20, 56, 0.85);
    border: 1px solid rgba(0, 240, 255, 0.4);
    border-radius: 10px;
    color: #00f0ff;
    font-size: 15px;
    padding: 9px 14px;
}

QPushButton#MicButton:hover {
    background-color: rgba(0, 240, 255, 0.2);
    border-color: #00f0ff;
}

QPushButton#NavPill {
    background-color: rgba(3, 20, 56, 0.7);
    border: 1px solid rgba(0, 240, 255, 0.35);
    border-radius: 12px;
    color: #38bdf8;
    font-size: 10px;
    font-weight: 700;
    padding: 3px 10px;
}

QPushButton#NavPill:hover {
    color: #ffffff;
    border-color: #00f0ff;
    background-color: rgba(0, 240, 255, 0.25);
}

QPushButton#HeaderCloseBtn {
    background: transparent;
    border: none;
    color: #94a3b8;
    font-size: 14px;
    font-weight: bold;
    padding: 4px;
}

QPushButton#HeaderCloseBtn:hover {
    color: #ff4d4d;
}
"""
