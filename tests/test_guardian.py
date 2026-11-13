"""
Testes do ZimaOS Server Guardian.

- Unitarios com run_ssh mockado (fixtures realistas da auditoria real)
- 1 teste LIVE que valida a coleta contra o ZimaOS de verdade
  (o briefing exige verificar implementacao E funcionamento)
"""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import zima_guardian as g


def setUpModule():
    os.environ["JARVIS_NO_RELAY"] = "1"


def tearDownModule():
    os.environ.pop("JARVIS_NO_RELAY", None)


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #

METRICAS_OK = {
    "ok": True, "cores": 4, "load": [0.5, 0.4, 0.3], "cpu_pct": 12.0,
    "ram_pct": 40.0, "ram_total_mb": 15880, "ram_used_mb": 6300,
    "swap_pct": 10.0, "temp_c": 41.0,
    "disks": [{"mount": "/DATA", "size_gb": 222, "used_gb": 177,
               "avail_gb": 45, "pct": 80}],
    "containers": [
        {"name": "waha", "running": True, "status": "Up 3 days",
         "restarts": 0, "critical": True, "cpu_pct": 6},
    ],
    "container_stats": {"waha": {"cpu_pct": 6, "mem": "2.5GiB"}},
    "top_processes": [{"cpu": 15.7, "pid": 1, "comm": "znet"}],
    "failed_services": [], "ports": [], "external_conns": [],
}

METRICAS_CRITICA = {
    "ok": True, "cores": 4, "load": [9.5, 9.0, 8.0], "cpu_pct": 99.2,
    "ram_pct": 96.0, "ram_total_mb": 15880, "ram_used_mb": 15200,
    "swap_pct": 90.0, "temp_c": 85.0,
    "disks": [
        {"mount": "/", "size_gb": 1, "used_gb": 1, "avail_gb": 0, "pct": 100},
        {"mount": "/DATA", "size_gb": 222, "used_gb": 177,
         "avail_gb": 45, "pct": 80},
    ],
    "containers": [
        {"name": "campainha-web", "running": False,
         "status": "Exited (255) 4 days ago", "restarts": 0,
         "critical": False},
        {"name": "postgresql", "running": False,
         "status": "Exited (137) 2 hours ago (5 restarts)",
         "restarts": 5, "critical": True},
        {"name": "piper", "running": True, "status": "Up 2 hours",
         "restarts": 0, "critical": False, "cpu_pct": 92},
    ],
    "container_stats": {"piper": {"cpu_pct": 92, "mem": "6MiB"}},
    "top_processes": [
        {"cpu": 95.0, "pid": 666, "comm": "kworker/evil"},
        {"cpu": 41.9, "pid": 777, "comm": "python3"},
    ],
    "failed_services": [{"unit": "rngd.service", "state": "failed",
                         "detail": "Hardware RNG Entropy Gatherer Daemon"}],
    "ports": [], "external_conns": [],
}


def _fake_ssh_factory(respostas):
    """Cria um run_ssh fake roteando por regex no comando."""
    import re as _re

    def fake(cmd, timeout=30):
        for padrao, saida in respostas:
            if _re.search(padrao, cmd):
                if callable(saida):
                    return saida(cmd)
                rc, out, err = (saida + ("", ""))[:3] if isinstance(saida, tuple) \
                    else (0, saida, "")
                return rc, out, err
        return 0, "", ""
    return fake


# --------------------------------------------------------------------------- #
# Config                                                                      #
# --------------------------------------------------------------------------- #

class TestGuardianConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="guardian_cfg_")
        self._old = os.environ.get("JARVIS_HOME")
        os.environ["JARVIS_HOME"] = self.tmp
        self._paths = (g.GUARDIAN_DIR, g.CONFIG_PATH, g.AUDIT_PATH,
                       g.HISTORY_PATH)
        base = Path(self.tmp)
        g.GUARDIAN_DIR = base / "guardian"
        g.CONFIG_PATH = g.GUARDIAN_DIR / "config.json"
        g.AUDIT_PATH = g.GUARDIAN_DIR / "audit.jsonl"
        g.HISTORY_PATH = g.GUARDIAN_DIR / "history.json"

    def tearDown(self):
        (g.GUARDIAN_DIR, g.CONFIG_PATH, g.AUDIT_PATH, g.HISTORY_PATH) = \
            self._paths
        if self._old is None:
            os.environ.pop("JARVIS_HOME", None)
        else:
            os.environ["JARVIS_HOME"] = self._old
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_load_limits_cria_config_padrao(self):
        lim = g.load_limits()
        self.assertTrue(g.CONFIG_PATH.is_file(),
                        "config.json padrao nao foi gravado")
        dados = json.loads(g.CONFIG_PATH.read_text(encoding="utf-8"))
        self.assertEqual(dados["cpu_pct"], g.DEFAULT_LIMITS["cpu_pct"])
        self.assertEqual(lim["monitor_interval_s"], 300)

    def test_load_limits_mergeia_edicao_do_usuario(self):
        g.GUARDIAN_DIR.mkdir(parents=True, exist_ok=True)
        g.CONFIG_PATH.write_text(json.dumps({"cpu_pct": 55}),
                                 encoding="utf-8")
        lim = g.load_limits()
        self.assertEqual(lim["cpu_pct"], 55)          # editado
        self.assertEqual(lim["ram_pct"], 90.0)         # default mantido

    def test_audit_append_only(self):
        g.audit("evento_a", {"x": 1})
        g.audit("evento_b", {"y": 2})
        registros = g.read_audit()
        self.assertEqual([r["evento"] for r in registros],
                         ["evento_b", "evento_a"])  # mais recente primeiro
        self.assertTrue(g.AUDIT_PATH.is_file())


# --------------------------------------------------------------------------- #
# Diagnostico (metrics fixtures - sem SSH)                                     #
# --------------------------------------------------------------------------- #

class TestGuardianDiagnose(unittest.TestCase):
    def test_metrics_ok_sem_achados(self):
        r = g.diagnose(metrics=dict(METRICAS_OK))
        self.assertTrue(r["ok"])
        self.assertEqual(r["findings"], [])
        self.assertIn("saudavel", r["summary"])

    def test_cpu_critico_identifica_culpado(self):
        r = g.diagnose(metrics=dict(METRICAS_CRITICA))
        ids = [f["id"] for f in r["findings"]]
        cpu = next(f for f in r["findings"] if f["area"] == "cpu")
        self.assertEqual(cpu["sev"], "critico")
        # causa provavel aponta o processo/top
        self.assertIn("kworker/evil", cpu["causa_provavel"] +
                      cpu["evidencias"][2])

    def test_container_parado_e_restart_loop(self):
        r = g.diagnose(metrics=dict(METRICAS_CRITICA))
        parado = next(f for f in r["findings"]
                      if f["id"] == "container_parado_campainha-web")
        self.assertEqual(parado["sev"], "medio")
        loop = next(f for f in r["findings"]
                    if f["id"] == "container_restart_postgresql")
        # critico parado -> sev alto
        self.assertEqual(next(f for f in r["findings"]
                              if f["id"] == "container_parado_postgresql")["sev"],
                         "alto")
        self.assertIn("logs postgresql", loop["recomendacao"])

    def test_servico_falha_com_acao_automatica_apenas_safe_list(self):
        r = g.diagnose(metrics=dict(METRICAS_CRITICA))
        rngd = next(f for f in r["findings"] if f["id"] == "service_rngd.service")
        self.assertEqual(rngd["acao_automatica"], "service:rngd")
        # servico fora da safe-list nao ganha acao automatica
        metrics2 = dict(METRICAS_CRITICA)
        metrics2["failed_services"] = [{"unit": "sshd.service",
                                        "state": "failed", "detail": "x"}]
        r2 = g.diagnose(metrics=metrics2)
        sshd = next(f for f in r2["findings"]
                    if f["id"] == "service_sshd.service")
        self.assertIsNone(sshd.get("acao_automatica"))

    def test_ram_temp_e_discos(self):
        r = g.diagnose(metrics=dict(METRICAS_CRITICA))
        areas = {f["area"] for f in r["findings"]}
        for esperado in ("cpu", "ram", "disco", "temperatura", "docker",
                         "servicos"):
            self.assertIn(esperado, areas, f"area '{esperado}' sem achado")
        # / critico marcado
        disk_root = next(f for f in r["findings"]
                         if f["id"] == "disk__")
        self.assertEqual(disk_root["sev"], "critico")


# --------------------------------------------------------------------------- #
# Docker: whitelist, aprovacao, acoes seguras                                 #
# --------------------------------------------------------------------------- #

class TestGuardianDocker(unittest.TestCase):
    def _run(self, op, target="", args=None, approval_id="", saidas=None):
        fake = _fake_ssh_factory(saidas or [
            (r"^docker rm", (0, "removido", "")),
            (r"^docker stop", (0, "parado", "")),
            (r"^docker start", (0, "iniciado", "")),
            (r"^docker restart", (0, "reiniciado", "")),
            (r"^docker inspect", (0, "running", "")),
            (r"^docker ps -a", (0, "c1|Up 1 day|img|:80/tcp", "")),
            (r"^docker logs", (0, "linha de log", "")),
            (r"^docker images", (0, "img:latest|1GB", "")),
        ])
        with patch.object(g, "run_ssh", side_effect=fake):
            return g.docker_admin(op, target, args or {}, approval_id)

    def test_leitura_direta_sem_aprovacao(self):
        r = self._run("list")
        self.assertTrue(r.get("ok"), r)
        self.assertIn("c1", r["output"])

    def test_injecao_no_alvo_e_recusada(self):
        for alvo_malicioso in ("x; rm -rf /", "x$(evil)", "a b",
                               "container name com espaco"):
            r = self._run("rm", alvo_malicioso)
            self.assertFalse(r.get("ok"), f"aceitou alvo {alvo_malicioso!r}")
            self.assertIn("invalido", r.get("error", ""))

    def test_rm_sem_aprovacao_devolve_plano(self):
        r = self._run("rm", "meu-container")
        self.assertFalse(r.get("ok"))
        self.assertTrue(r.get("approval_required"))
        self.assertTrue(r["approval_id"].startswith("apr_"))
        plano = r["plan"]
        for campo in ("acao", "alvo", "motivo", "recursos", "risco",
                      "comando"):
            self.assertIn(campo, plano, f"plano sem '{campo}'")
        self.assertEqual(plano["comando"], "docker rm meu-container")

    def test_rm_com_aprovacao_certa_executa(self):
        r1 = self._run("rm", "meu-container")
        aid = r1["approval_id"]
        r2 = self._run("rm", "meu-container", approval_id=aid)
        self.assertTrue(r2.get("ok"), r2)
        self.assertEqual(r2["command"], "docker rm meu-container")

    def test_aprovacao_de_outra_acao_nao_serve(self):
        # aprovacao para 'rm' nao autoriza 'rmi' nem outro alvo (acao exata)
        r1 = self._run("rm", "container-a")
        aid = r1["approval_id"]
        r2 = self._run("rmi", "container-a", approval_id=aid)
        self.assertFalse(r2.get("ok"))
        r3 = self._run("rm", "container-b", approval_id=aid)
        self.assertFalse(r3.get("ok"))

    def test_stop_de_critico_exige_aprovacao(self):
        r = self._run("stop", "postgresql")
        self.assertFalse(r.get("ok"))
        self.assertTrue(r.get("approval_required"))
        # stop de nao critico executa direto
        r2 = self._run("stop", "campainha-web")
        self.assertTrue(r2.get("ok"), r2)

    def test_pull_exige_aprovacao(self):
        r = self._run("pull", "nginx:alpine")
        self.assertFalse(r.get("ok"))
        self.assertTrue(r.get("approval_required"))

    def test_logs_com_parametro_tail(self):
        r = self._run("logs", "c1", {"tail": 50})
        self.assertTrue(r.get("ok"), r)


# --------------------------------------------------------------------------- #
# Seguranca: block_ip com politica NEVER_BLOCK + aprovacao                     #
# --------------------------------------------------------------------------- #

class TestGuardianSeguranca(unittest.TestCase):
    def test_ip_invalido_recusado(self):
        r = g.block_ip("nao-e-ip")
        self.assertFalse(r.get("ok"))
        self.assertIn("invalido", r["error"])

    def test_ip_privado_nunca_bloqueado(self):
        # NEVER_BLOCK: nao pode interromper servicos legitimos/admin/Jarvis
        for ip in ("192.168.1.10", "10.147.20.1", "127.0.0.1",
                   "172.22.0.2"):
            r = g.block_ip(ip, approval_id="apr_qualquer")
            self.assertFalse(r.get("ok"), f"bloqueou IP privado {ip}")
            self.assertIn("NEVER_BLOCK", r["error"])

    def test_ip_publico_sem_aprovacao_devolve_plano(self):
        r = g.block_ip("185.22.11.44", motivo="brute force")
        self.assertFalse(r.get("ok"))
        self.assertTrue(r.get("approval_required"))
        self.assertEqual(r["plan"]["acao"], "block_ip")
        self.assertEqual(r["plan"]["alvo"], "185.22.11.44")
        self.assertIn("iptables", r["plan"]["comando"])
        self.assertTrue(r["plan"]["evidencia"])

    def test_ip_publico_com_aprovacao_bloqueia_e_persiste(self):
        r1 = g.block_ip("185.22.11.44", motivo="37 tentativas")
        aid = r1["approval_id"]
        fake = _fake_ssh_factory([(r"iptables", (0, "BLOQUEADO_OK", ""))])
        with patch.object(g, "run_ssh", side_effect=fake):
            r2 = g.block_ip("185.22.11.44", motivo="37 tentativas",
                            approval_id=aid)
        self.assertTrue(r2.get("ok"), r2)
        self.assertIn("bloqueado", r2["message"])

    def test_security_report_parseia_logins(self):
        journal = (
            "Nov 13 03:00:01 zima sshd[1]: Failed password for root "
            "from 185.22.11.44 port 51000\n"
            "Nov 13 03:00:02 zima sshd[1]: Failed password for root "
            "from 185.22.11.44 port 51002\n"
            "Nov 13 03:00:05 zima sshd[1]: Invalid user admin from "
            "91.240.118.7 port 4444\n"
            "Nov 13 03:01:00 zima sshd[1]: Accepted password for root "
            "from 10.147.20.5 port 2222\n"
        )
        ips = ("  2 185.22.11.44\n  1 91.240.118.7")
        fake = _fake_ssh_factory([
            (r"grep -ciE", (0, "3", "")),
            (r"grep -oE", (0, ips, "")),
            # o comando real ja extrai so NUMEROS de porta (awk+sed)
            (r"ss -tlnp", (0, "22\n2375\n28222", "")),
            (r"ps -eo comm", (0, "bash\nsystemd\ncurl", "")),
            (r"ss -tn", (0, "", "")),
            (r"journalctl", (0, journal, "")),
        ])
        with patch.object(g, "run_ssh", side_effect=fake):
            rep = g.security_report(24)
        self.assertTrue(rep["ok"])
        self.assertEqual(rep["logins_falhos"], 3)
        bf = next(i for i in rep["incidentes"]
                  if i["tipo"] == "brute_force_ssh")
        self.assertEqual(bf["evidencias"]["185.22.11.44"], 2)
        # 2375 exposta = docker api grave
        docker_inc = next(i for i in rep["incidentes"]
                          if i["tipo"] == "docker_api_exposta")
        self.assertEqual(docker_inc["sev"], "critico")

    def test_security_sem_mineracao(self):
        fake = _fake_ssh_factory([
            (r"grep -ciE", (0, "0", "")),
            (r"ss -tlnp", (0, "0.0.0.0:22", "")),
            (r"ps -eo comm", (0, "bash\ndockerd", "")),
            (r"ss -tn", (0, "", "")),
            (r"journalctl", (0, "", "")),
        ])
        with patch.object(g, "run_ssh", side_effect=fake):
            rep = g.security_report(24)
        tipos = [i["tipo"] for i in rep["incidentes"]]
        self.assertNotIn("mineracao_suspeita", tipos)


# --------------------------------------------------------------------------- #
# Reparo de baixo risco                                                        #
# --------------------------------------------------------------------------- #

class TestGuardianReparo(unittest.TestCase):
    def test_reparo_servico_safe_list(self):
        # ancoras: o comando de restart CONTEM "is-active" no final
        # (systemctl restart X && systemctl is-active X)
        fake = _fake_ssh_factory([
            (r"^systemctl restart rngd", (0, "active", "")),
            (r"^systemctl is-active rngd", (0, "inactive", "")),
        ])
        with patch.object(g, "run_ssh", side_effect=fake):
            r = g.auto_repair("service_restart", "rngd")
        self.assertTrue(r.get("ok"), r)
        self.assertEqual(r["estado_antes"], "inactive")
        self.assertEqual(r["estado_depois"], "active")

    def test_reparo_servico_fora_da_safe_list(self):
        r = g.auto_repair("service_restart", "sshd")
        self.assertFalse(r.get("ok"))
        self.assertIn("safe-list", r["error"])

    def test_reparo_container_restart(self):
        fake = _fake_ssh_factory([
            (r"docker inspect", (0, "exited", "")),
            (r"docker restart", (0, "c1", "")),
        ])
        with patch.object(g, "run_ssh", side_effect=fake):
            r = g.auto_repair("container_restart", "campainha-web")
        self.assertTrue(r.get("ok"), r)
        self.assertEqual(r["estado_antes"], "exited")

    def test_reparo_nao_faz_coisa_destrutiva(self):
        for acao in ("rm", "prune", "wipe", ""):
            r = g.auto_repair(acao, "qualquer")
            self.assertFalse(r.get("ok"))


# --------------------------------------------------------------------------- #
# Monitor: alerta com cooldown (sem spam)                                      #
# --------------------------------------------------------------------------- #

class TestGuardianMonitor(unittest.TestCase):
    def test_alerta_uma_vez_dentro_do_cooldown(self):
        g._monitor_state["alerts"].clear()
        emitidos = []
        # side_effect devolve um dict NOVO por chamada: com return_value o
        # mesmo dict seria compartilhado e a r2 sobrescreveria alertados
        # (r1 aponta para o mesmo objeto -> leitura lixo no assert)
        base = {"ok": True,
                "findings": [{"id": "cpu_99", "sev": "critico",
                              "area": "cpu", "titulo": "CPU em 99%",
                              "causa_provavel": "x", "evidencias": [],
                              "recomendacao": "y"}],
                "summary": "1 achado"}
        with patch.object(g, "diagnose",
                          side_effect=lambda *a, **k: dict(base)), \
             patch.object(g, "_emitir_alerta",
                          side_effect=lambda *a: emitidos.append(a)):
            r1 = g.monitor_once()
            r2 = g.monitor_once()   # cooldown: nao repete
        self.assertEqual(len(emitidos), 1, "alertou mais de uma vez (spam)")
        self.assertEqual(r1["alertados"], ["cpu_99"])
        self.assertEqual(r2["alertados"], [])

    def test_monitor_desativado_nao_faz_nada(self):
        with patch.object(g, "load_limits",
                          return_value=dict(g.DEFAULT_LIMITS,
                                            enabled=False)):
            r = g.monitor_once()
        self.assertTrue(r.get("disabled"))

    def test_monitor_status_formato(self):
        st = g.monitor_status()
        for campo in ("enabled", "interval_s", "last_run",
                      "alertas_recentes", "limits"):
            self.assertIn(campo, st)


# --------------------------------------------------------------------------- #
# Dispatcher da tool                                                           #
# --------------------------------------------------------------------------- #

class TestGuardianTool(unittest.TestCase):
    def test_dispatch_health(self):
        fake_health = {"ok": True, "text": "saude ok"}
        with patch.object(g, "health_report", return_value=fake_health):
            r = g.handle_tool({"action": "health"})
        self.assertEqual(r["text"], "saude ok")

    def test_dispatch_docker(self):
        with patch.object(g, "docker_admin",
                          return_value={"ok": True, "op": "list"}) as m:
            r = g.handle_tool({"action": "docker", "op": "list"})
        self.assertTrue(r["ok"])
        m.assert_called_once_with("list", "", {}, "")

    def test_acao_desconhecida_lista_opcoes(self):
        r = g.handle_tool({"action": "voar"})
        self.assertFalse(r["ok"])
        self.assertIn("health", r["acoes"])


# --------------------------------------------------------------------------- #
# LIVE: funcionamento real contra o ZimaOS                                     #
# --------------------------------------------------------------------------- #

class TestGuardianLive(unittest.TestCase):
    """Verificacao real: coleta + diagnostico contra o servidor de verdade."""

    def test_health_real_zimaos(self):
        r = g.health_report()
        self.assertTrue(r.get("ok"),
                        f"coleta real falhou: {r.get('error')}")
        resumo = r["resumo"]
        for campo in ("cpu_pct", "ram_pct", "temp_c", "containers_total",
                      "saude", "containers_rodando"):
            self.assertIn(campo, resumo)
        self.assertGreater(resumo["containers_total"], 5,
                           "esperava dezenas de containers no ZimaOS")
        self.assertIsInstance(r["findings"], list)
        self.assertTrue(r["text"].startswith("ZimaOS:"))

    def test_docker_list_real(self):
        r = g.docker_admin("list")
        self.assertTrue(r.get("ok"), r)
        self.assertIn("waha", r["output"])

    def test_aprovacao_vinculada_id_deterministico(self):
        a1 = g.approval_id_for("rm", "x", {})
        a2 = g.approval_id_for("rm", "x", {})
        a3 = g.approval_id_for("rm", "y", {})
        self.assertEqual(a1, a2, "mesma acao deve gerar o mesmo id")
        self.assertNotEqual(a1, a3, "acao diferente = id diferente")


if __name__ == "__main__":
    unittest.main()
