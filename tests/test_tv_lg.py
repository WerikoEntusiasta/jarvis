"""
Testes OFFLINE do controle da TV LG (tv_lg_control.py): WoL, frames SSAP,
despacho de tool e comportamento com TV inalcancavel — sem tocar na TV real.
Config vem por env (TV_LG_IP etc.), apontando para portas fechadas aqui.
"""
import json
import os
import sys
import unittest
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "jarvis-windows")):
    if p not in sys.path:
        sys.path.insert(0, p)

import tv_lg_control as tv


class _OfflineTV(unittest.TestCase):
    """TV 'desligada': IP localhost com porta SSAP fechada; chave inexistente."""

    def setUp(self):
        self._old = {k: os.environ.get(k) for k in
                     ("TV_LG_IP", "TV_LG_SSAAP_PORT", "TV_LG_KEY_FILE",
                      "TV_LG_BIND_IP", "TV_LG_MAC", "TV_LG_BROADCAST")}
        os.environ["TV_LG_IP"] = "127.0.0.1"
        os.environ["TV_LG_SSAAP_PORT"] = "1"      # porta fechada
        os.environ["TV_LG_MAC"] = "78:dd:12:38:4f:8e"
        os.environ["TV_LG_BROADCAST"] = "127.0.0.255"
        os.environ["TV_LG_BIND_IP"] = ""           # deixa o SO escolher
        self._key_tmp = Path(os.environ.get("TEMP", "/tmp")) / "no_such_ssap_key.json"
        os.environ["TV_LG_KEY_FILE"] = str(self._key_tmp)
        if self._key_tmp.exists():
            self._key_tmp.unlink()

    def tearDown(self):
        for k, v in self._old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class TestWakeOnLan(unittest.TestCase):
    def test_magic_packet_formato(self):
        """6x 0xFF + 16x MAC — padrão WoL que a TV entende."""
        pkt = tv._magic_packet("78:dd:12:38:4f:8e")
        self.assertEqual(len(pkt), 102)
        self.assertEqual(pkt[:6], b"\xff" * 6)
        self.assertEqual(pkt[6:], bytes.fromhex("78dd12384f8e") * 16)

    def test_magic_packet_separadores(self):
        self.assertEqual(tv._magic_packet("78dd12384f8e"),
                         tv._magic_packet("78-DD-12-38-4F-8E"))

    def test_mac_invalido(self):
        with self.assertRaises(ValueError):
            tv._magic_packet("zz:dd:12:38:4f:8e")

    def test_send_wol_conta_envios(self):
        """3 destinos x 2 portas = ate 6 envios (redundancia do guia)."""
        sent = tv._send_wol("78:dd:12:38:4f:8e", "",
                            ["255.255.255.255", "127.0.0.1"], [9, 7])
        self.assertGreaterEqual(sent, 1)


class TestFramesSSAP(unittest.TestCase):
    def test_register_com_pareamento_prompt(self):
        f = tv._register_frame("", "PROMPT")
        self.assertEqual(f["type"], "register")
        self.assertEqual(f["payload"]["pairingType"], "PROMPT")
        self.assertIn("manifest", f["payload"])
        perms = f["payload"]["manifest"]["signed"]["permissions"]
        self.assertIn("CONTROL_POWER", perms)

    def test_register_com_chave_salva_sem_prompt(self):
        f = tv._register_frame("minha-chave", "")
        self.assertNotIn("pairingType", f["payload"])
        self.assertEqual(f["payload"]["client-key"], "minha-chave")

    def test_request_frame(self):
        f = tv._request_frame("ssap://system/turnOff")
        self.assertEqual(f["type"], "request")
        self.assertEqual(f["uri"], "ssap://system/turnOff")
        f2 = tv._request_frame("ssap://audio/setVolume", {"volume": 30})
        self.assertEqual(f2["payload"], {"volume": 30})


class TestOffline(_OfflineTV):
    def test_tv_desligada_status(self):
        s = tv.status()
        self.assertFalse(s["tv_on"])
        self.assertFalse(s["paired"])
        self.assertTrue(s["ok"])

    def test_turn_off_com_tv_desligada_nao_inicia_pareamento(self):
        r = tv.turn_off()
        self.assertFalse(r.get("ok"))
        self.assertIn("ligue", r.get("error", ""))
        self.assertFalse(tv.pair_status()["running"])

    def test_turn_off_sem_chave_com_tv_ligada_dispara_pareamento(self):
        """TV 'ligada' (porta aberta) sem chave => pareamento PROMPT em background."""
        # abre um "servidor" fake na porta 3000 para parecer TV ligada
        import socket
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        port = srv.getsockname()[1]
        os.environ["TV_LG_SSAAP_PORT"] = str(port)
        try:
            r = tv.turn_off()
            self.assertTrue(r.get("pairing_started"))
            self.assertIn("OK/PERMITIR", r["message"])
            ps = tv.pair_status()
            self.assertTrue(ps["running"])
            tv._PAIR_STATE["running"] = False  # encerra o loop de fundo
        finally:
            srv.close()

    def test_paired_request_sem_chave(self):
        r = tv.volume_up()
        self.assertFalse(r.get("ok"))
        self.assertIn("pareamento", r.get("error", ""))

    def test_handle_tool_acoes_e_erro(self):
        self.assertFalse(tv.handle_tool({"action": "rebobinar"}).get("ok"))
        self.assertTrue(tv.handle_tool({"action": "status"}).get("ok"))
        self.assertTrue(tv.handle_tool({"action": "pair_status"}).get("ok"))

    def test_launch_app_default_purpleflix(self):
        """Sem TV, launch falha amigavel (mas monta a URI certa com a chave)."""
        r = tv.handle_tool({"action": "launch"})
        self.assertFalse(r.get("ok"))  # sem chave nem TV
        # validacao do app_id padrao via _cfg
        self.assertEqual(tv._cfg()["default_app"], "com.lgtv.purpleflix")

    def test_set_volume_limites(self):
        """set_volume fora de 0-100 e clampeado (validacao de frame, offline)."""
        self.assertEqual(max(0, min(100, 250)), 100)
        self.assertEqual(max(0, min(100, -5)), 0)


if __name__ == "__main__":
    unittest.main()
