"""
Testes OFFLINE do controle da TV LG (tv_lg_control.py) — arquitetura 2026-11-13:

- WoL nativo (magic packet, envios) — sem rede real.
- Pontes Node (ssap_bridge / nova_luna / ssap_pair_bridge) MOCKADAS: valida
  o contrato de entrada/saida, o fluxo de cada acao e os fallbacks
  (mute = setVolume 0 + restaurar; desligar = sleep timer).
- TV inalcancavel (IP localhost/porta fechada) sem tocar na TV real.
"""
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "jarvis-windows")):
    if p not in sys.path:
        sys.path.insert(0, p)

import tv_lg_control as tv


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
        """destinos x portas => envios (redundancia do guia)."""
        sent = tv._send_wol("78:dd:12:38:4f:8e", "",
                            ["255.255.255.255", "127.0.0.1"], [9, 7])
        self.assertGreaterEqual(sent, 1)


class TestPontesIndisponiveis(unittest.TestCase):
    """node/C:/LGTV ausente => falhas amigaveis (nunca excecao crua)."""

    def setUp(self):
        self._old_dir = os.environ.get("TV_LG_NODE_DIR")
        os.environ["TV_LG_NODE_DIR"] = r"C:\nao_existe_nada\123"

    def tearDown(self):
        if self._old_dir is None:
            os.environ.pop("TV_LG_NODE_DIR", None)
        else:
            os.environ["TV_LG_NODE_DIR"] = self._old_dir

    def test_node_script_none(self):
        self.assertIsNone(tv._node_script("ssap_bridge.js"))

    def test_luna_sem_ponte(self):
        r = tv._luna("com.webos.audio/getVolume", "{}")
        self.assertFalse(r.get("ok"))
        self.assertIn("indisponivel", r["error"])

    def test_ssap_sem_ponte(self):
        r = tv._launch_ssap("com.lgtv.purpleflix")
        self.assertFalse(r.get("ok"))
        self.assertIn("indisponivel", r["error"])

    def test_volume_up_sem_ponte(self):
        r = tv.volume_up()
        self.assertFalse(r.get("ok"))


class TestFluxosComPonteMockada(unittest.TestCase):
    def setUp(self):
        self._old = {k: os.environ.get(k) for k in
                     ("TV_LG_IP", "TV_LG_SSAAP_PORT", "TV_LG_KEY_FILE",
                      "TV_LG_BIND_IP", "TV_LG_MAC", "TV_LG_BROADCAST")}
        os.environ["TV_LG_IP"] = "127.0.0.1"
        os.environ["TV_LG_SSAAP_PORT"] = "1"
        os.environ["TV_LG_MAC"] = "78:dd:12:38:4f:8e"
        os.environ["TV_LG_BROADCAST"] = "127.0.0.255"
        os.environ["TV_LG_BIND_IP"] = ""
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

    # ---- status ---------------------------------------------------------- #

    def test_tv_desligada_status(self):
        s = tv.status()
        self.assertFalse(s["tv_on"])
        self.assertFalse(s["paired"])
        self.assertTrue(s["ok"])
        self.assertTrue(s["power_blocked"])
        self.assertEqual(s["off_method"], "firmware_blocked")

    def test_status_tv_ligada_sem_chave(self):
        with patch.object(tv, "is_on", return_value=True):
            s = tv.status()
            self.assertTrue(s["tv_on"])
            self.assertFalse(s["paired"])
            self.assertFalse(s["can_power_off"])
            self.assertTrue(s["power_blocked"])
            self.assertEqual(s["off_method"], "firmware_blocked")

    # ---- desligar (firmware bloqueia) ------------------------------------- #

    def test_turn_off_tv_desligada(self):
        r = tv.turn_off()
        self.assertFalse(r.get("ok"))
        self.assertIn("ligue", r.get("error", ""))

    def test_turn_off_ssap_aceito(self):
        """Se um firmware futuro liberar turnOff, a acao funciona."""
        with patch.object(tv, "is_on", return_value=True), \
             patch.object(tv, "_ssap_bridge") as br:
            br.return_value = {"ok": True, "last": {}}
            r = tv.turn_off()
            self.assertTrue(r["ok"])
            self.assertEqual(br.call_args[0][0][0]["uri"], "ssap://system/turnOff")

    def test_turn_off_firmware_bloqueia_honesto(self):
        """Firmware nega => ok=False, firmware_blocked=True, alternativas."""
        with patch.object(tv, "is_on", return_value=True), \
             patch.object(tv, "_ssap_bridge") as br:
            br.return_value = {"ok": False, "error": "401 insufficient permissions"}
            r = tv.turn_off()
            self.assertFalse(r["ok"])
            self.assertTrue(r["firmware_blocked"])
            self.assertIn("alternatives", r)
            self.assertTrue(any("controle" in a for a in r["alternatives"]))

    def test_power_info_consolida_diagnostico(self):
        r = tv.power_blocked_info()
        self.assertTrue(r["blocked"])
        self.assertTrue(len(r["tested"]) >= 5)
        self.assertIn("ligar via WoL", r["working"])

    # ---- launch ----------------------------------------------------------- #

    def test_launch_sem_chave(self):
        with patch.object(tv, "is_on", return_value=True):
            r = tv.handle_tool({"action": "launch"})
            self.assertFalse(r.get("ok"))
            self.assertIn("pareamento", r["error"])

    def test_launch_formato_uri(self):
        """Com chave: payload {id} (formato que funciona; ?target= era 404)."""
        with open(os.environ["TV_LG_KEY_FILE"], "w", encoding="utf-8") as f:
            json.dump({"clientKey": "k"}, f)
        with patch.object(tv, "_ssap_bridge") as br:
            br.return_value = {"ok": True, "last": {"returnValue": True}}
            r = tv.launch_app("com.lgtv.purpleflix")
            self.assertTrue(r["ok"])
            reqs = br.call_args[0][0]
            self.assertEqual(reqs[0]["uri"], "ssap://system.launcher/open")
            self.assertEqual(reqs[0]["payload"], {"id": "com.lgtv.purpleflix"})

    # ---- volume / mute ----------------------------------------------------- #

    def test_set_volume_clamp_e_payload(self):
        with patch.object(tv, "_luna") as luna:
            luna.return_value = {"ok": True, "data": {}}
            r = tv.set_volume(250)
            self.assertTrue(r["ok"])
            self.assertEqual(r["volume"], 100)
            self.assertEqual(json.loads(luna.call_args[0][1]), {"volume": 100})
            r2 = tv.set_volume(-5)
            self.assertEqual(json.loads(luna.call_args_list[1][0][1]), {"volume": 0})
            self.assertEqual(r2["volume"], 0)

    def test_mute_guarda_e_zera_unmute_restaura(self):
        tmp_mute = Path(os.environ.get("TEMP", "/tmp")) / "test_tv_mute.json"
        with patch.object(tv, "_MUTE_FILE", str(tmp_mute)):
            with patch.object(tv, "_luna") as luna:
                def luna_fake(method, payload):
                    if method.endswith("getVolume"):
                        return {"ok": True, "data": {"volume": 22, "muted": False}}
                    return {"ok": True, "data": {}}
                luna.side_effect = luna_fake
                r = tv.set_mute(True)
                self.assertTrue(r["ok"])
                self.assertTrue(r["muted"])
                payload = json.loads(luna.call_args_list[-1][0][1])
                self.assertEqual(payload, {"volume": 0})
                salvo = json.loads(tmp_mute.read_text())
                self.assertEqual(salvo["volume"], 22)

                r2 = tv.set_mute(False)
                self.assertFalse(r2["muted"])
                payload2 = json.loads(luna.call_args_list[-1][0][1])
                self.assertEqual(payload2, {"volume": 22})

    # ---- pareamento --------------------------------------------------------- #

    def test_handle_tool_acoes_e_erro(self):
        self.assertFalse(tv.handle_tool({"action": "rebobinar"}).get("ok"))
        self.assertTrue(tv.handle_tool({"action": "status"}).get("ok"))
        self.assertTrue(tv.handle_tool({"action": "pair_status"}).get("ok"))

    def test_start_pairing_dispara_background(self):
        with patch.object(tv, "is_on", return_value=True), \
             patch.object(tv, "_pair_loop") as loop:
            r = tv.start_pairing()
            self.assertTrue(r.get("pairing_started"))
            self.assertIn("OK/PERMITIR", r["message"])
            ps = tv.pair_status()
            self.assertTrue(ps["running"])
            tv._PAIR_STATE["running"] = False


if __name__ == "__main__":
    unittest.main()
