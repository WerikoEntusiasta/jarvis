"""
Testes automatizados da Janela Nativa e do Sistema de Apresentação de Notícias do J.A.R.V.I.S.
"""
import os
import sys
import unittest

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox --ignore-gpu-blocklist")

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from PyQt6.QtWidgets import QApplication
from desktop.events import EventBus
from desktop.commands import CommandBus
from desktop.jarvis_window import JarvisMainWindow, DEMO_TECH_NEWS, ArcReactorWidget, NewsCardWidget

class TestJarvisWindowAndPresentation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance()
        if not cls.app:
            cls.app = QApplication(["--platform", "offscreen"])

    def setUp(self):
        self.event_bus = EventBus()
        self.command_bus = CommandBus(event_bus=self.event_bus)
        self.window = JarvisMainWindow(event_bus=self.event_bus)

    def tearDown(self):
        if self.window.playback_worker and self.window.playback_worker.isRunning():
            self.window.playback_worker.stop()
            self.window.playback_worker.wait(500)
        self.window.close()

    def test_window_initialization(self):
        """Verifica se a janela inicializa no estado Core Standby com Arc Reactor."""
        self.assertIsNotNone(self.window.arc_reactor)
        self.assertEqual(self.window.stacked_area.currentWidget(), self.window.page_core)
        self.assertEqual(self.window.arc_reactor.assistant_state, "idle")

    def test_news_presentation_start_and_cards(self):
        """Verifica a inicialização da apresentação de notícias e geração dos cards."""
        self.window.start_news_briefing(DEMO_TECH_NEWS)
        self.assertEqual(self.window.stacked_area.currentWidget(), self.window.page_presentation)
        self.assertEqual(len(self.window.card_widgets), len(DEMO_TECH_NEWS))
        self.assertTrue(self.window.card_widgets[0].is_active)
        self.assertFalse(self.window.card_widgets[1].is_active)
        self.assertEqual(self.window.active_news_idx, 0)

    def test_navigation_and_focus(self):
        """Verifica navegação entre notícias e transferência de foco."""
        self.window.start_news_briefing(DEMO_TECH_NEWS)
        self.window.next_news()
        self.assertEqual(self.window.active_news_idx, 1)
        self.assertFalse(self.window.card_widgets[0].is_active)
        self.assertTrue(self.window.card_widgets[1].is_active)

        self.window.prev_news()
        self.assertEqual(self.window.active_news_idx, 0)
        self.assertTrue(self.window.card_widgets[0].is_active)

    def test_pause_and_stop_narration(self):
        """Verifica pausa e cancelamento da narração."""
        self.window.start_news_briefing(DEMO_TECH_NEWS)
        self.window.toggle_pause()
        self.assertTrue(self.window.is_paused)
        self.window.stop_narration()
        self.assertEqual(self.window.mini_arc.assistant_state, "idle")

    def test_close_presentation(self):
        """Verifica retorno ao núcleo ao fechar a apresentação."""
        self.window.start_news_briefing(DEMO_TECH_NEWS)
        self.window.close_presentation()
        self.assertEqual(self.window.stacked_area.currentWidget(), self.window.page_core)
        self.assertEqual(self.window.arc_reactor.assistant_state, "idle")

    def test_event_bus_presentation_command(self):
        """Verifica o disparo de apresentação via CommandBus/EventBus."""
        res = self.command_bus.execute("presentation.show", {"kind": "news", "items": DEMO_TECH_NEWS})
        self.assertTrue(res.get("success"))
        self.assertEqual(self.window.stacked_area.currentWidget(), self.window.page_presentation)

    def test_widescreen_hero_stage_sync(self):
        """Verifica se o Hero Stage reflete os dados do item ativo e a barra de progresso."""
        self.window.start_news_briefing(DEMO_TECH_NEWS)
        first_item = DEMO_TECH_NEWS[0]
        self.assertEqual(self.window.hero_stage.lbl_title.text(), first_item["title"])
        self.assertEqual(self.window.hero_stage.lbl_summary.text(), first_item["summary"])
        
        # Testar sincronização de progresso
        self.window._on_playback_progress(first_item["id"], 0.75)
        self.assertEqual(self.window.hero_stage.progress_bar.value(), 75)
        self.assertEqual(self.window.card_widgets[0].progress_bar.value(), 75)

    def test_queue_visibility_toggle(self):
        """Verifica a alternância de exibição da coluna contextual de fila."""
        self.window.start_news_briefing(DEMO_TECH_NEWS)
        self.assertFalse(self.window.queue_container.isHidden())
        self.window.toggle_queue_visibility()
        self.assertTrue(self.window.queue_container.isHidden())
        self.window.toggle_queue_visibility()
        self.assertFalse(self.window.queue_container.isHidden())

    def test_immersive_mode_and_command_bus(self):
        """Verifica a alternância do modo imersivo via método e via CommandBus."""
        self.assertFalse(self.window.isFullScreen())
        self.window.toggle_immersive_mode()
        self.assertTrue(self.window.isFullScreen())
        self.assertEqual(self.window.btn_immersive.text(), "🗗 JANELA")

        # Alternar de volta via CommandBus
        res = self.command_bus.execute("presentation.immersive_toggle", {})
        self.assertTrue(res.get("success"))
        self.assertFalse(self.window.isFullScreen())
        self.assertEqual(self.window.btn_immersive.text(), "⛶ IMERSIVO")

    def test_keyboard_shortcuts(self):
        """Verifica atalhos de teclado (F11 para tela cheia, Espaço para pausa, Setas para navegação)."""
        from PyQt6.QtGui import QKeyEvent
        from PyQt6.QtCore import QEvent, Qt

        self.window.start_news_briefing(DEMO_TECH_NEWS)
        
        # Espaço: pausa
        event_space = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier)
        self.window.keyPressEvent(event_space)
        self.assertTrue(self.window.is_paused)

        # Seta direita: próxima notícia
        event_right = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier)
        self.window.keyPressEvent(event_right)
        self.assertEqual(self.window.active_news_idx, 1)

        # Seta esquerda: notícia anterior
        event_left = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Left, Qt.KeyboardModifier.NoModifier)
        self.window.keyPressEvent(event_left)
        self.assertEqual(self.window.active_news_idx, 0)

        # F11: modo imersivo
        event_f11 = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_F11, Qt.KeyboardModifier.NoModifier)
        self.window.keyPressEvent(event_f11)
        self.assertTrue(self.window.isFullScreen())

        # Escape: sair do modo imersivo
        event_esc = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
        self.window.keyPressEvent(event_esc)
        self.assertFalse(self.window.isFullScreen())


if __name__ == "__main__":
    unittest.main()
