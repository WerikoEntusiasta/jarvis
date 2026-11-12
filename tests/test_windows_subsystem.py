"""
Suite de Testes Automatizados de Recuperação e Estabilização do J.A.R.V.I.S. Windows
Validação funcional de:
- win_controls (Janelas, Processos, Monitores, Sistema)
- pc_automation (Mouse, Teclado, Captura de Tela)
- hardware_monitor (Telemetria Real CPU/RAM/GPU)
- windows_mcp (Despacho de Ferramentas Nativas)
- vision (Standby Seguro e Mapeamento de Ações)
- laya_screen_subagent (Arquitetura e Layout Dinâmico)
"""

import sys
import os
import unittest
from pathlib import Path

# Garante caminhos no sys.path
ROOT = Path(__file__).resolve().parent.parent
for p in [str(ROOT), str(ROOT / "jarvis-windows")]:
    if p not in sys.path:
        sys.path.insert(0, p)

class TestWindowsSubsystem(unittest.TestCase):

    def test_01_win_controls_system_info(self):
        from system import win_controls
        info = win_controls.get_system_info()
        self.assertTrue(info.get("success"), "get_system_info falhou")
        self.assertEqual(info.get("os"), "Windows")
        self.assertGreater(info.get("cpu_cores_logical", 0), 0)
        self.assertGreater(info.get("ram_total_gb", 0), 0)
        print(f"\n[OK] Info do Sistema: Host={info.get('hostname')}, OS={info.get('os_release')}, Uptime={info.get('uptime')}")

    def test_02_win_controls_monitors(self):
        from system import win_controls
        res = win_controls.list_monitors()
        self.assertTrue(res.get("success"), "list_monitors falhou")
        self.assertGreater(res.get("count", 0), 0, "Nenhum monitor detectado")
        primary_found = any(m.get("is_primary") for m in res.get("monitors", []))
        self.assertTrue(primary_found, "Monitor principal não encontrado")
        print(f"[OK] Monitores detectados: {res.get('count')} (Principal: {[m['width'] for m in res['monitors'] if m['is_primary']]})")

    def test_03_win_controls_windows_and_processes(self):
        from system import win_controls
        wins = win_controls.list_windows()
        self.assertTrue(wins.get("success"), "list_windows falhou")
        print(f"[OK] Janelas visíveis encontradas: {wins.get('count')}")

        procs = win_controls.list_processes(top_n=5, sort_by="cpu")
        self.assertTrue(procs.get("success"), "list_processes falhou")
        self.assertGreater(len(procs.get("processes", [])), 0)
        print(f"[OK] Top 5 Processos CPU: {[p['name'] for p in procs['processes']]}")

    def test_04_hardware_telemetry(self):
        from system import hardware_monitor
        telem = hardware_monitor.get_system_telemetry()
        self.assertIn("cpu_percent", telem)
        self.assertIn("ram_percent", telem)
        self.assertIn("gpu", telem)
        print(f"[OK] Telemetria Real: CPU={telem['cpu_percent']}%, RAM={telem['ram_percent']}%, GPU Temp={telem['gpu'].get('temp')}C")

    def test_05_pc_automation_mouse_and_screenshot(self):
        from system import pc_automation
        pos = pc_automation.get_mouse_position()
        self.assertTrue(pos.get("success"), "get_mouse_position falhou")
        self.assertGreater(pos.get("screen_width", 0), 0)

        shot = pc_automation.take_screenshot(return_base64=False)
        self.assertTrue(shot.get("success"), "take_screenshot falhou")
        self.assertTrue(os.path.exists(shot.get("path", "")), "Arquivo de screenshot não foi criado")
        print(f"[OK] Screenshot e Mouse: Cursor=({pos['x']},{pos['y']}), Tela={pos['screen_width']}x{pos['screen_height']}")

    def test_06_windows_mcp_dispatch(self):
        from mcp.windows_mcp import dispatch_mcp_tool
        res_info = dispatch_mcp_tool("get_system_info", {})
        self.assertTrue(res_info.get("success"), "MCP get_system_info falhou")

        res_telem = dispatch_mcp_tool("obter_telemetria_hardware", {})
        self.assertTrue(res_telem.get("success"), "MCP telemetria falhou")

        res_wins = dispatch_mcp_tool("list_windows", {})
        self.assertTrue(res_wins.get("success"), "MCP list_windows falhou")
        print("[OK] Despacho MCP Nativo validado com sucesso")

    def test_07_vision_engine_resilience(self):
        from vision import get_vision_engine
        v = get_vision_engine()
        st = v.get_status()
        self.assertIn("enabled", st)
        self.assertIn("gesture", st)
        print(f"[OK] Motor de Visão Computacional: Standby={not st.get('enabled')}, Câmera={st.get('camera_device')}")

    def test_08_laya_screen_subagent_resolution(self):
        from laya_screen_subagent import get_current_resolution, get_laya_agent
        w, h = get_current_resolution()
        self.assertGreater(w, 0)
        self.assertGreater(h, 0)
        agent = get_laya_agent()
        self.assertEqual(agent.name, "L.A.Y.A.")
        print(f"[OK] L.A.Y.A. Subagent: Resolução do Display={w}x{h}")

if __name__ == "__main__":
    unittest.main()
