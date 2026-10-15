"""
J.A.R.V.I.S. Native 3D Brain Viewer Window (PyWebView)
Carrega o Cérebro Agêntico 3D diretamente do ZimaOS em uma janela NATIVA dedicada do Windows,
sem necessidade de abrir navegador de internet externo.
"""

import sys
import os
import ctypes

# Ativa DPI Awareness para janelas nitidas no Windows
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

ZIMA_BRAIN_URL = os.environ.get("ZIMA_BRAIN_URL", "${ZIMA_ROUTER_URL:-http://127.0.0.1:8095}/")

def main():
    try:
        import webview
        print(f"[NativeBrain] Abrindo janela nativa do Cérebro 3D: {ZIMA_BRAIN_URL}")
        webview.create_window(
            title="J.A.R.V.I.S. - Cérebro Agêntico 3D & Central de Memória (ZimaOS Core)",
            url=ZIMA_BRAIN_URL,
            width=1400,
            height=900,
            resizable=True,
            min_size=(1024, 700),
            confirm_close=False
        )
        webview.start(debug=False)
    except Exception as e:
        print(f"[NativeBrain Error] Falha ao iniciar pywebview: {e}")

if __name__ == "__main__":
    main()
