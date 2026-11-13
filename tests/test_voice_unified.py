"""
Testes da UNIFICAÇÃO DE VOZ (2026-11-13): wake word e hotkey devem ativar o
ÚNICO sistema de voz (QwenLiveVoice via sinal Qt) e NUNCA iniciar o pipeline
local STT->LLM->TTS, que respondia em voz masculina junto com a do Qwen
("tem 2 jarvis"). Regressão: o acionamento usava QTimer.singleShot(0) de uma
thread sem event loop, que nunca dispara.
"""
import os
import sys
import unittest
from unittest.mock import MagicMock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "jarvis-windows")):
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS",
                      "--no-sandbox --ignore-gpu-blocklist")

import voice.voice_engine as ve


def _engine_sem_init() -> "ve.JarvisVoiceEngine":
    """Instancia sem __init__ (que carrega wake model e aquece TTS de rede)."""
    eng = ve.JarvisVoiceEngine.__new__(ve.JarvisVoiceEngine)
    eng.state = "WAKEWORD"
    eng.followup_mode = False
    eng.speaker = MagicMock()
    eng.on_wake_word = MagicMock()
    eng.on_speech_recognized = MagicMock()
    eng.on_speech_reply = MagicMock()
    eng._begin_recording = MagicMock()
    eng._play_wake_chime = MagicMock()
    return eng


class TestWakeWordUnificado(unittest.TestCase):
    def test_wake_word_ativa_qwen_e_nao_pipeline_local(self):
        """NÚCLEO: gatilho nao grava/STT/LLM/TTS - so aciona o HUD (Qwen)."""
        eng = _engine_sem_init()
        eng.trigger_manual_listen()
        eng._begin_recording.assert_not_called()    # pipeline local desligado
        eng.on_wake_word.assert_called_once()        # -> HUD -> QwenLiveVoice
        eng._play_wake_chime.assert_called_once()    # feedback sonoro curto
        self.assertEqual(eng.state, "WAKEWORD")      # segue detectando wake word

    def test_gatilho_repetido_nao_gera_estado_de_gravacao(self):
        """Repetido N vezes: nunca entra em RECORDING (sem segunda voz)."""
        eng = _engine_sem_init()
        for _ in range(5):
            eng.trigger_manual_listen()
        eng._begin_recording.assert_not_called()
        self.assertEqual(eng.state, "WAKEWORD")
        self.assertEqual(eng.on_wake_word.call_count, 5)

    def test_barge_in_local_mudo_sem_tts_pendente(self):
        """speaker.stop() e chamado (interrompe TTS local legado se houver)."""
        eng = _engine_sem_init()
        eng.trigger_manual_listen()
        eng.speaker.stop.assert_called_once()


class TestSinalQtWake(unittest.TestCase):
    def test_classe_expoe_sinal_wake_requested(self):
        """JarvisHUDWindow.deve expor o sinal (auto->queued, seguro cross-thread)."""
        from ui.hud_window import JarvisHUDWindow
        self.assertTrue(
            hasattr(JarvisHUDWindow, "wake_requested"),
            "sinal wake_requested ausente: acionamento cross-thread quebraria",
        )

    def test_handler_aciona_qwen_live_voice(self):
        """O JS injetado deve ativar QwenLiveVoice.start() (idempotente)."""
        from ui.hud_window import JarvisHUDWindow
        src_source = None
        # Garante que o metodo de slot existe e referencia o QwenLiveVoice
        import inspect
        src_source = inspect.getsource(JarvisHUDWindow._handle_wake_requested)
        self.assertIn("QwenLiveVoice.start()", src_source)
        # E que NAO usa o padrao morto (thread sem event loop)
        self.assertNotIn("QTimer.singleShot", src_source)


class TestMecanismoCrossThread(unittest.TestCase):
    def test_qt_single_shot_nao_dispara_fora_da_main_thread(self):
        """Documenta a causa raiz: singleShot de thread sem event loop morre.
        Se este teste falhar (disparar), o Qt mudou e o sinal ainda e valido.
        """
        import threading
        import time as _time
        from PyQt6.QtCore import QCoreApplication, QTimer

        app = QCoreApplication.instance()
        criado = False
        if app is None:
            app = QCoreApplication(["test"])
            criado = True
        resultado = {"fired": False}

        def worker():
            QTimer.singleShot(0, lambda: resultado.__setitem__("fired", True))

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        t.join(timeout=1.0)

        # Processa eventos por pouco tempo na main thread
        fim = _time.time() + 0.4
        while _time.time() < fim:
            app.processEvents()
            _time.sleep(0.01)

        self.assertFalse(
            resultado["fired"],
            "QTimer.singleShot cross-thread disparou (comportamento inesperado "
            "- revisar se ainda precisamos do sinal Qt)",
        )
        if criado:
            pass  # QCoreApplication nao pode ser destruido no meio dos testes


if __name__ == "__main__":
    unittest.main()
