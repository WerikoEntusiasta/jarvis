"""
Testes das funcionalidades de manipulação de cards do HUD (spatial):
mover, redimensionar, zoom/expand, minimizar, agrupar/separar,
z-index, destacar, salvar/restaurar layout.

Regressões cobertas:
- dispatch completo do spatial_workspace_action (todas as actions)
- z_index calculado sobre o registry (front/back/up/down)
- save/load roundtrip com arquivo real (JARVIS_HOME em temp)
- componente restaurado no MESMO formato que o frontend espera
"""

import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

import mimo_tools


def setUpModule():
    # Nada de relay para o HUD real: estes testes criam/varrem cards e o
    # broadcast cross-process injetaria tudo no palco do app rodando.
    os.environ["JARVIS_NO_RELAY"] = "1"


def tearDownModule():
    os.environ.pop("JARVIS_NO_RELAY", None)


class TestSchemaEspacial(unittest.TestCase):
    def test_enum_contem_todas_as_actions(self):
        alvo = [t for t in mimo_tools.TOOLS
                if t["function"]["name"] == "spatial_workspace_action"]
        self.assertEqual(len(alvo), 1)
        acoes = alvo[0]["function"]["parameters"]["properties"]["action"]["enum"]
        esperadas = [
            # criacao/composicao
            "compose", "create", "add_component", "update_component",
            # 1-4: mover/redimensionar/zoom/minimizar
            "move_component", "resize_component", "expand_component",
            "minimize_component", "focus_component",
            # 5-6: agrupar/separar
            "group_component", "separate_component",
            # 7: z-index   8: destacar   (connect/remove/clear extras)
            "z_index_component", "highlight_component",
            "connect_component", "remove_component", "clear",
            # 10: layouts
            "save_layout", "load_layout",
        ]
        for a in esperadas:
            self.assertIn(a, acoes, f"action '{a}' fora do enum")

    def test_params_z_mode_e_layout_name(self):
        alvo = [t for t in mimo_tools.TOOLS
                if t["function"]["name"] == "spatial_workspace_action"][0]
        props = alvo["function"]["parameters"]["properties"]
        self.assertIn("z_mode", props)
        self.assertEqual(sorted(props["z_mode"]["enum"]),
                         ["back", "down", "front", "up"])
        self.assertIn("layout_name", props)


class TestDispatchEspacial(unittest.TestCase):
    """Cada action despacha para a funcao certa do engine."""

    def _dispatch(self, args):
        return mimo_tools.execute_tool("spatial_workspace_action", args)

    def test_move_despacha_para_apply_operation(self):
        with patch("dynamic_presentation_engine.apply_spatial_operation",
                   return_value={"ok": True, "via": "apply"}) as m:
            r = self._dispatch({"action": "move_component",
                                "component_id": "c1",
                                "position": {"x": 50, "y": 20}})
        self.assertTrue(r.get("ok"))
        m.assert_called_once()
        args = m.call_args[0]
        self.assertEqual(args[0], "c1")
        self.assertEqual(args[1], "move")
        self.assertEqual(args[2].get("x"), 50)

    def test_resize_despacha(self):
        with patch("dynamic_presentation_engine.apply_spatial_operation",
                   return_value={"ok": True}) as m:
            self._dispatch({"action": "resize_component", "component_id": "c1",
                            "position": {"width": 60, "height": 50}})
        self.assertEqual(m.call_args[0][1], "resize")
        self.assertEqual(m.call_args[0][2].get("width"), 60)

    def test_expand_minimize_group_separate(self):
        for acao, operacao in (("expand_component", "expand"),
                               ("minimize_component", "minimize"),
                               ("group_component", "group"),
                               ("separate_component", "separate")):
            with patch("dynamic_presentation_engine.apply_spatial_operation",
                       return_value={"ok": True}) as m:
                self._dispatch({"action": acao, "component_id": "c1",
                                "group_id": "g1"})
            self.assertEqual(m.call_args[0][1], operacao,
                             f"{acao} nao virou operacao '{operacao}'")

    def test_z_index_vai_como_operation_z_index_e_modo(self):
        with patch("dynamic_presentation_engine.apply_spatial_operation",
                   return_value={"ok": True}) as m:
            self._dispatch({"action": "z_index_component", "component_id": "c1",
                            "z_mode": "front"})
        self.assertEqual(m.call_args[0][1], "z_index")
        self.assertEqual(m.call_args[0][2].get("mode"), "front")

    def test_save_layout_despacha(self):
        with patch("dynamic_presentation_engine.save_spatial_layout",
                   return_value={"ok": True, "layout": "meu"}) as m:
            r = self._dispatch({"action": "save_layout",
                                "layout_name": "Meu Layout!"})
        self.assertTrue(r.get("ok"))
        m.assert_called_once_with("Meu Layout!")

    def test_load_layout_despacha(self):
        with patch("dynamic_presentation_engine.load_spatial_layout",
                   return_value={"ok": True}) as m:
            self._dispatch({"action": "load_layout", "layout_name": "meu"})
        m.assert_called_once_with("meu")


class TestZIndexOperacao(unittest.TestCase):
    """z_index: front/back calculados sobre todos os cards; up/down relativos."""

    def setUp(self):
        import dynamic_presentation_engine as pe
        self.pe = pe
        pe.clear_spatial_workspace()
        pe.create_spatial_workspace(title="T")
        pe.add_spatial_component("a", "annotation", {"x": 5, "y": 5}, {})
        pe.add_spatial_component("b", "annotation", {"x": 50, "y": 5}, {})

    def tearDown(self):
        self.pe.clear_spatial_workspace()

    def _z(self, cid):
        ws = self.pe.get_spatial_workspace()
        return int(ws["components"][cid]["position"].get("zIndex") or 0)

    def test_front_sobe_para_cima(self):
        r = self.pe.apply_spatial_operation("a", "z_index", {"mode": "front"})
        self.assertTrue(r.get("ok"), r)
        self.assertGreater(self._z("a"), self._z("b"))

    def test_back_desce(self):
        self.pe.apply_spatial_operation("a", "z_index", {"mode": "front"})
        r = self.pe.apply_spatial_operation("a", "z_index", {"mode": "back"})
        self.assertTrue(r.get("ok"), r)
        self.assertLessEqual(self._z("a"), self._z("b"))

    def test_up_down_unitario(self):
        antes = self._z("a")
        self.pe.apply_spatial_operation("a", "z_index", {"mode": "up"})
        self.assertEqual(self._z("a"), min(antes + 1, 99))
        self.pe.apply_spatial_operation("a", "z_index", {"mode": "down"})
        self.assertEqual(self._z("a"), antes)

    def test_modo_invalido_erro(self):
        r = self.pe.apply_spatial_operation("a", "z_index", {"mode": "sideways"})
        self.assertFalse(r.get("ok"))
        self.assertIn("front", r.get("error", ""))

    def test_broadcast_de_update_com_zindex(self):
        with patch.object(self.pe, "_broadcast_to_hud",
                          return_value=True) as m:
            self.pe.apply_spatial_operation("a", "z_index", {"mode": "front"})
        eventos = [c[0][0] for c in m.call_args_list]
        self.assertIn("spatial_component_updated", eventos)
        payload = m.call_args[0][1]
        self.assertIn("zIndex", payload["updates"]["position"])

    def test_z_index_nao_teleporta_position(self):
        # o payload de updates pode vir parcial (só zIndex); o frontend
        # precisa nao aplicar geometria nesse caso - aqui garantimos que o
        # registry mantem a position completa (x/y preservados)
        ws_before = dict(self.pe.get_spatial_workspace()["components"]["a"]["position"])
        self.pe.apply_spatial_operation("a", "z_index", {"mode": "up"})
        ws_after = self.pe.get_spatial_workspace()["components"]["a"]["position"]
        self.assertEqual(ws_before["x"], ws_after["x"])
        self.assertEqual(ws_before["y"], ws_after["y"])


class TestSaveLoadLayout(unittest.TestCase):
    """Roundtrip real de layout em arquivo (JARVIS_HOME em diretorio temp)."""

    def setUp(self):
        import dynamic_presentation_engine as pe
        self.pe = pe
        self.tmp = tempfile.mkdtemp(prefix="jarvis_layouts_")
        self._old_home = os.environ.get("JARVIS_HOME")
        os.environ["JARVIS_HOME"] = self.tmp
        # recria o caminho apontando para o novo home
        pe.LAYOUTS_DIR = pe.Path(self.tmp) / "spatial_layouts"
        pe.clear_spatial_workspace()

    def tearDown(self):
        self.pe.clear_spatial_workspace()
        if self._old_home is None:
            os.environ.pop("JARVIS_HOME", None)
        else:
            os.environ["JARVIS_HOME"] = self._old_home
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_save_sem_cards_erro(self):
        r = self.pe.save_spatial_layout("vazio")
        self.assertFalse(r.get("ok"))
        self.assertIn("palco", r.get("error", ""))

    def test_roundtrip_save_load(self):
        # monta 2 cards com geometria conhecida
        self.pe.create_spatial_workspace(title="Meu Palco")
        self.pe.add_spatial_component(
            "card_a", "annotation", {"x": 12, "y": 30, "width": 40,
                                     "height": 35, "zIndex": 7},
            {"title": "Card A", "content": "conteudo a"})
        self.pe.add_spatial_component(
            "card_b", "narrative", {"x": 60, "y": 10, "width": 30,
                                    "height": 50},
            {"title": "Card B"})

        # salva
        r = self.pe.save_spatial_layout("Meu Palco Top")
        self.assertTrue(r.get("ok"), r)
        self.assertEqual(r["total_components"], 2)
        self.assertTrue(os.path.isfile(r["path"]))
        # slug normalizado
        self.assertTrue(r["layout"].replace("_", "").isalnum())

        # limpa e confirma que sumiu
        self.pe.clear_spatial_workspace()
        self.assertIsNone(self.pe.get_spatial_workspace())

        # restaura e confirma geometria + props + formato do broadcast
        with patch.object(self.pe, "_broadcast_to_hud", return_value=True) as m:
            r2 = self.pe.load_spatial_layout("Meu Palco Top")
        self.assertTrue(r2.get("ok"), r2)
        self.assertEqual(r2["total_components"], 2)

        ws = self.pe.get_spatial_workspace()
        self.assertIn("card_a", ws["components"])
        comp = ws["components"]["card_a"]
        self.assertEqual(comp["props"]["title"], "Card A")
        self.assertEqual(comp["position"]["x"], 12)
        self.assertEqual(comp["position"]["zIndex"], 7)

        # formato do broadcast e o que o frontend espera
        adicionados = [c[0][1] for c in m.call_args_list
                       if c[0][0] == "spatial_component_added"]
        self.assertEqual(len(adicionados), 2)
        for payload in adicionados:
            for campo in ("id", "type", "position", "props"):
                self.assertIn(campo, payload,
                              f"broadcast sem '{campo}' (frontend quebraria)")
        # palco marcado como visivel para a pergunta de limpeza
        self.assertTrue(self.pe.get_presentation_status()["cards_visible"])

    def test_load_inexistente_lista_disponiveis(self):
        self.pe.create_spatial_workspace(title="T")
        self.pe.add_spatial_component("c1", "annotation", {}, {})
        self.pe.save_spatial_layout("existe")
        r = self.pe.load_spatial_layout("nao_existe")
        self.assertFalse(r.get("ok"))
        self.assertIn("existe", r.get("available", []))

    def test_list_layouts(self):
        self.pe.create_spatial_workspace(title="T")
        self.pe.add_spatial_component("c1", "annotation", {}, {})
        self.pe.save_spatial_layout("um")
        self.pe.save_spatial_layout("dois")
        self.assertEqual(sorted(self.pe.list_spatial_layouts()),
                         ["dois", "um"])

    def test_normaliza_position_preserva_zindex(self):
        pos = self.pe._normalize_spatial_position(
            "annotation", {"x": 10, "y": 10, "zIndex": 42}, 0)
        self.assertEqual(pos["zIndex"], 42)


class TestOperacoesViaTool(unittest.TestCase):
    """End-to-end: execute_tool -> engine (broadcast real nao-op fora do app)."""

    def test_expand_e_minimize_via_tool(self):
        import dynamic_presentation_engine as pe
        pe.clear_spatial_workspace()
        pe.create_spatial_workspace(title="T")
        try:
            pe.add_spatial_component("card_x", "annotation",
                                     {"x": 5, "y": 5}, {"title": "X"})
            r1 = mimo_tools.execute_tool(
                "spatial_workspace_action",
                {"action": "expand_component", "component_id": "card_x"})
            self.assertTrue(r1.get("ok"), r1)
            comp = pe.get_spatial_workspace()["components"]["card_x"]
            self.assertEqual(comp.get("state"), "expanded")
            self.assertEqual(int(comp["position"]["zIndex"]), 20)

            r2 = mimo_tools.execute_tool(
                "spatial_workspace_action",
                {"action": "minimize_component", "component_id": "card_x"})
            self.assertTrue(r2.get("ok"), r2)
            self.assertEqual(
                pe.get_spatial_workspace()["components"]["card_x"].get("state"),
                "minimized")

            r3 = mimo_tools.execute_tool(
                "spatial_workspace_action",
                {"action": "highlight_component", "component_id": "card_x",
                 "duration": 2})
            self.assertTrue(r3.get("ok"), r3)
        finally:
            pe.clear_spatial_workspace()

    def test_acao_desconhecida_erro(self):
        r = mimo_tools.execute_tool("spatial_workspace_action",
                                    {"action": "teleport"})
        self.assertFalse(r.get("ok"))


if __name__ == "__main__":
    unittest.main()
