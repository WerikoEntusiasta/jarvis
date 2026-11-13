"""
Testes do SISTEMA DINAMICO DE AGENTES (agent_dynamic.py) — pedido do Senhor
Werik (2026-11-13):

1. Config dinamica: config.json (global e por agente) lido AO VIVO a cada
   chamada — mudar API de IA pesada, modelo, voz ou instrucoes vale na
   proxima conversa, sem restart.
2. Auto-edicao com aprovacao: o agente PROPÕE edicao nos proprios arquivos
   (SOUL.md/USER.md/IDENTITY.md/MEMORY.md/config.json) e NUNCA aplica sem
   aprovacao explicita; aprovacao gera backup + auditoria; recusa descarta.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "jarvis-windows")):
    if p not in sys.path:
        sys.path.insert(0, p)

import agent_dynamic as ad


class _TempAgents(unittest.TestCase):
    """Isolamento total: AGENTS_DIR aponta para diretório temporário."""

    def setUp(self):
        self._old_dir = os.environ.get("JARVIS_AGENTS_DIR")
        self._tmp = tempfile.mkdtemp(prefix="agent_dyn_test_")
        os.environ["JARVIS_AGENTS_DIR"] = self._tmp
        # agente 'jarvis' com SOUL.md e USER.md reais (estado inicial)
        self.agent_dir = Path(self._tmp) / "jarvis"
        self.agent_dir.mkdir()
        (self.agent_dir / "SOUL.md").write_text(
            "# SOUL\nTrate o operador por 'Senhor'.\nRespostas curtas.\n",
            encoding="utf-8")
        (self.agent_dir / "USER.md").write_text(
            "# USER\nWerik: prefere respostas diretas.\n", encoding="utf-8")

    def tearDown(self):
        if self._old_dir is None:
            os.environ.pop("JARVIS_AGENTS_DIR", None)
        else:
            os.environ["JARVIS_AGENTS_DIR"] = self._old_dir
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)


class TestConfigDinamica(_TempAgents):
    def test_config_lida_ao_vivo_sem_restart(self):
        """Mudou config.json no disco => próxima chamada já vê (dinâmico)."""
        self.assertEqual(ad.effective_config("jarvis"), {})
        (Path(self._tmp) / "config.json").write_text(
            json.dumps({"model": "mimo-v2.6-pro"}), encoding="utf-8")
        self.assertEqual(ad.effective_config("jarvis").get("model"), "mimo-v2.6-pro")
        # config por agente vence o global
        (self.agent_dir / "config.json").write_text(
            json.dumps({"model": "gpt-pesado-x"}), encoding="utf-8")
        self.assertEqual(ad.effective_config("jarvis").get("model"), "gpt-pesado-x")

    def test_merge_api_global_com_por_agente(self):
        (Path(self._tmp) / "config.json").write_text(json.dumps({
            "api": {"base": "https://global.example/v1", "key": "sk-g", "model": "m1"},
        }), encoding="utf-8")
        (self.agent_dir / "config.json").write_text(json.dumps({
            "api": {"base": "https://agente.example/v1"},
        }), encoding="utf-8")
        cfg = ad.effective_config("jarvis")
        # base vence do agente, key herdada do global
        self.assertEqual(cfg["api"]["base"], "https://agente.example/v1")
        self.assertEqual(cfg["api"]["key"], "sk-g")

    def test_override_model(self):
        """Nova API/modelo no config substitui o roteador (tarefas pesadas)."""
        cfg = {"model": "auto"}
        self.assertEqual(ad.override_model(cfg, "flash-x", "pro-y", "pro"), "pro-y")
        self.assertEqual(ad.override_model(cfg, "flash-x", "pro-y", "flash"), "flash-x")
        self.assertEqual(ad.override_model({"model": "pro"}, "f", "p", "flash"), "p")
        self.assertEqual(ad.override_model({"api": {"model": "nova-ia"}}, "f", "p", "pro"),
                         "nova-ia")

    def test_config_summary_injeta_instrucoes_e_autoedicao(self):
        (Path(self._tmp) / "config.json").write_text(json.dumps({
            "instructions": ["Trate-me por 'chefe'."],
            "voice": {"engine": "qwen"},
        }), encoding="utf-8")
        s = ad.config_summary("jarvis")
        self.assertIn("Trate-me por 'chefe'.", s)
        self.assertIn("qwen", s)
        self.assertIn("agent_self_edit", s)   # agente sabe como se autoeditar


class TestAutoEdicaoAprovacao(_TempAgents):
    def test_propose_exige_aprovacao_e_id_deterministico(self):
        r = ad.propose_self_edit("jarvis", "SOUL.md",
                                 "# SOUL\nTrate o operador por 'chefe'.\n",
                                 "pediu para mudar o tratamento")
        self.assertTrue(r.get("approval_required"))
        self.assertTrue(r["approval_id"].startswith("aed_"))
        # deterministico: mesma proposta => mesmo id
        r2 = ad.propose_self_edit("jarvis", "SOUL.md",
                                  "# SOUL\nTrate o operador por 'chefe'.\n",
                                  "outro motivo")
        self.assertEqual(r["approval_id"], r2["approval_id"])
        pend = ad.pending_edit("jarvis")
        self.assertIsNotNone(pend)
        self.assertEqual(pend["approval_id"], r["approval_id"])

    def test_arquivo_sofre_mudanca_somente_apos_aprovacao(self):
        """O CORAÇÃO DO PEDIDO: sem aprovação, NADA muda em disco."""
        novo = "# SOUL\nTrate o operador por 'chefe'.\nMais informal.\n"
        r = ad.propose_self_edit("jarvis", "SOUL.md", novo, "teste")
        aid = r["approval_id"]
        # arquivo atual INTACTO enquanto pendente
        self.assertIn("Senhor", (self.agent_dir / "SOUL.md").read_text(encoding="utf-8"))
        # approve com id errado NÃO aplica
        wrong = ad.approve_self_edit("aed_" + "0" * 16)
        self.assertFalse(wrong.get("ok"))
        self.assertIn("Senhor", (self.agent_dir / "SOUL.md").read_text(encoding="utf-8"))
        # approve correto aplica
        ok = ad.approve_self_edit(aid)
        self.assertTrue(ok.get("ok"))
        self.assertIn("chefe", (self.agent_dir / "SOUL.md").read_text(encoding="utf-8"))
        # pendente resolvida
        self.assertIsNone(ad.pending_edit("jarvis"))
        # backup criado
        backups = list((self.agent_dir / "backups").glob("SOUL.md.*.bak"))
        self.assertEqual(len(backups), 1)
        self.assertIn("Senhor", backups[0].read_text(encoding="utf-8"))
        # auditoria registrou propose e approve
        audit = (Path(self._tmp) / "_audit" / "self_edit.jsonl").read_text(encoding="utf-8")
        self.assertIn('"action": "propose"', audit)
        self.assertIn('"action": "approve"', audit)

    def test_reject_descarta_sem_alterar_arquivo(self):
        novo = "# SOUL\nVersao recusada.\n"
        r = ad.propose_self_edit("jarvis", "SOUL.md", novo, "teste")
        res = ad.reject_self_edit(r["approval_id"], "nao gostei")
        self.assertTrue(res.get("ok"))
        self.assertIn("Senhor", (self.agent_dir / "SOUL.md").read_text(encoding="utf-8"))
        self.assertIsNone(ad.pending_edit("jarvis"))

    def test_whitelist_e_agente_desconhecido(self):
        self.assertFalse(ad.propose_self_edit("jarvis", "AGENTS.md", "x").get("ok"))
        self.assertFalse(ad.propose_self_edit("fantasma", "SOUL.md", "x").get("ok"))
        self.assertFalse(ad.propose_self_edit("jarvis", "SOUL.md", "   ").get("ok"))

    def test_config_json_validado_na_proposta(self):
        r = ad.propose_self_edit("jarvis", "config.json", "{isso nao e json", "x")
        self.assertFalse(r.get("ok"))
        self.assertIn("invalido", r.get("error", ""))
        r2 = ad.propose_self_edit("jarvis", "config.json",
                                  json.dumps({"instructions": ["ok"]}), "x")
        self.assertTrue(r2.get("ok"))

    def test_handle_tool_propose_approve_e2e(self):
        """A IA usa a tool: propose -> approval_required -> approve aplica."""
        novo = "# USER\nWerik prefere ser chamado de 'chefe'.\n"
        r = ad.handle_tool({"action": "propose", "agent_id": "jarvis",
                            "file": "USER.md", "content": novo,
                            "reason": "pedido do senhor"})
        self.assertTrue(r.get("approval_required"))
        ok = ad.handle_tool({"action": "approve", "approval_id": r["approval_id"]})
        self.assertTrue(ok.get("ok"))
        self.assertIn("chefe", (self.agent_dir / "USER.md").read_text(encoding="utf-8"))

    def test_status_mascara_chave_de_api(self):
        (Path(self._tmp) / "config.json").write_text(json.dumps({
            "api": {"base": "https://x/v1", "key": "sk-1234567890abcdwxyz"},
        }), encoding="utf-8")
        st = ad.handle_tool({"action": "status", "agent_id": "jarvis"})
        k = st["config"]["api"]["key"]
        self.assertNotIn("sk-1234567890abcdwxyz", k)
        self.assertIn("...", k)


if __name__ == "__main__":
    unittest.main()
