"""
J.A.R.V.I.S. — ZimaOS Server Guardian
======================================================================
Monitoramento, diagnostico, administracao Docker e seguranca do ZimaOS.

Arquitetura:
- Coleta via SSH (paramiko) — SEM agente no servidor e SEM expor o
  socket Docker (principio do menor privilegio).
- Limites configuraveis: <JARVIS_HOME>/guardian/config.json
  (DEFAULT_LIMITS gravado na primeira leitura, editavel pelo usuario).
- Auditoria append-only: <JARVIS_HOME>/guardian/audit.jsonl
- Historico de alertas: <JARVIS_HOME>/guardian/history.json
- Aprovacoes vinculadas por HASH do comando exato (id = sha256 da
  acao+alvo+args): se o plano mudar, o id muda -> nova aprovacao.

Politicas de seguranca (secoes 4 e 8 do briefing):
- Comandos Docker construidos por whitelist, alvos validados por regex
  e args com shlex.quote — nada cru de mensagem vira shell.
- block_ip exige aprovacao PREVIA + rejeita redes privadas/ZeroTier
  (NEVER_BLOCK: jamais bloquear servicos legitimos, admin ou o proprio
  Jarvis).
- Acoes destrutivas (rm/pull/compose/remove de volume-rede-imagem,
  stop de container critico) so executam com approval_id conferido.
- Toda acao administrativa registrada em audit.jsonl.
- Reparo automatico restrito a baixo risco (servicos da safe-list,
  restart de container); nada destrutivo automatico.

Uso pela IA (tool zima_guardian): health / diagnose / docker / security /
report / history / repair / evaluate.
"""

import os
import re
import json
import time
import shlex
import hashlib
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("ZimaGuardian")

# --------------------------------------------------------------------------- #
# Configuracao                                                                 #
# --------------------------------------------------------------------------- #

GUARDIAN_DIR = Path(os.environ.get("JARVIS_HOME") or r"C:\JARVIS") / "guardian"
CONFIG_PATH = GUARDIAN_DIR / "config.json"
AUDIT_PATH = GUARDIAN_DIR / "audit.jsonl"
HISTORY_PATH = GUARDIAN_DIR / "history.json"

DEFAULT_LIMITS: Dict[str, Any] = {
    "enabled": True,
    "monitor_interval_s": 300,
    "alert_cooldown_min": 30,
    # particoes de sistema do ZimaOS: nunca sao 'falta de espaco' real
    # (overlay read-only, boot EFI, /usr do sistema imutavel)
    "disk_ignore_mounts": ["/mnt/", "/boot", "/etc", "/usr", "/sys"],
    # / raiz do ZimaOS e estavel (sistema imutavel) - alerta de disco
    # real merece no max 1x/12h, nao a cada30min
    "disk_alert_cooldown_min": 720,
    "cpu_pct": 90.0,
    "load_per_core": 2.0,
    "ram_pct": 90.0,
    "swap_pct": 85.0,
    "disk_pct": 90.0,
    "disk_free_gb_min": 5.0,
    "temp_c": 80.0,
    "container_cpu_pct": 80.0,
    "container_restart_count": 3,
}

# Containers cujo STOP exige aprovacao (dados/servicos criticos)
CRITICAL_CONTAINERS = {
    "postgresql", "nginxproxymanager", "redis-zimaos", "waha",
    "jarvis-hud", "jarvis-memory-core", "jellyfin", "n8n",
}

# Servicos que o reparo automatico PODE reiniciar (safe-list)
REPAIRABLE_SERVICES = {"rngd", "cups", "avahi-daemon"}

# Nunca bloquear estas redes (admin, Jarvis, ZeroTier, localhost)
NEVER_BLOCK_NETWORKS = ("127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12",
                        "192.168.0.0/16", "169.254.0.0/16")

# Processos tipicos de mineracao nao autorizada
_MINER_NAMES = re.compile(
    r"^(xmrig|xmr-stak|kdevtmpfsi|kinsing|nbminer|t-rex|phoenixminer|"
    r"ethminer|cgminer|bfgminer|lolminer|gminer|teamredminer)(\s|$)",
    re.I)

_audit_lock = threading.Lock()
_approvals_lock = threading.Lock()
# approval_id -> {"spec": ..., "created": ts, "expires": ts}
_APPROVALS: Dict[str, Dict[str, Any]] = {}
_APPROVAL_TTL = 900  # 15 min


def load_limits() -> Dict[str, Any]:
    """Le os limites do config; grava o default na primeira vez."""
    try:
        if CONFIG_PATH.is_file():
            dados = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            merged = dict(DEFAULT_LIMITS)
            merged.update({k: v for k, v in dados.items()
                           if k in DEFAULT_LIMITS})
            return merged
    except Exception as e:
        logger.warning("[Guardian] config ilegivel, usando default: %s", e)
    try:
        GUARDIAN_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(DEFAULT_LIMITS, indent=2,
                                          ensure_ascii=False),
                               encoding="utf-8")
    except OSError:
        pass
    return dict(DEFAULT_LIMITS)


# --------------------------------------------------------------------------- #
# SSH (unica porta de entrada ao ZimaOS)                                       #
# --------------------------------------------------------------------------- #

def _credenciais_ssh() -> List[Tuple[str, int, str, str]]:
    """(host, porta, usuario, senha) em ordem de tentativa: env -> fallback."""
    opts: List[Tuple[str, int, str, str]] = []
    ip = os.environ.get("ZIMA_IP", "").strip()
    user = os.environ.get("ZIMA_USER", "root").strip() or "root"
    senha_env = os.environ.get("ZIMA_PASS", "").strip()
    porta_env = os.environ.get("ZIMA_SSH_PORT", "").strip()
    if ip and senha_env:
        try:
            opts.append((ip, int(porta_env or 22), user, senha_env))
        except ValueError:
            opts.append((ip, 22, user, senha_env))
    # fallback conhecido (mesmo do deploy_zimaos.py)
    opts.append(("45.167.187.80", 28222, "root", "We12wi25k#3912*"))
    # dedup preservando ordem
    visto = set()
    uniq = []
    for o in opts:
        if o not in visto:
            visto.add(o)
            uniq.append(o)
    return uniq


def run_ssh(cmd: str, timeout: int = 30) -> Tuple[int, str, str]:
    """Executa um comando no ZimaOS via SSH. Retorna (rc, stdout, stderr).

    Todas as chamadas do guardian passam por aqui (ponto unico facilita
    auditoria, mock nos testes e troca de credenciais).
    """
    import paramiko  # import local: sobe so quando usado
    ultimo_erro = "sem credenciais"
    for host, porta, user, senha in _credenciais_ssh():
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            ssh.connect(host, port=porta, username=user, password=senha,
                        timeout=10)
            _, out, err = ssh.exec_command(cmd, timeout=timeout)
            stdout = out.read().decode("utf-8", errors="replace")
            stderr = err.read().decode("utf-8", errors="replace")
            rc = out.channel.recv_exit_status()
            ssh.close()
            return rc, stdout, stderr
        except Exception as e:
            ultimo_erro = f"{type(e).__name__}: {e}"
            try:
                ssh.close()
            except Exception:
                pass
    return 1, "", f"SSH indisponivel: {ultimo_erro}"


# --------------------------------------------------------------------------- #
# Auditoria (append-only)                                                      #
# --------------------------------------------------------------------------- #

def audit(event: str, details: Optional[Dict[str, Any]] = None) -> None:
    """Registra toda acao administrativa/detecao em audit.jsonl."""
    registro = {
        "ts": time.time(),
        "evento": event,
        "detalhes": details or {},
    }
    with _audit_lock:
        try:
            GUARDIAN_DIR.mkdir(parents=True, exist_ok=True)
            with AUDIT_PATH.open("a", encoding="utf-8") as f:
                f.write(json.dumps(registro, ensure_ascii=False) + "\n")
        except OSError as e:
            logger.warning("[Guardian] falha ao auditar: %s", e)
    logger.info("[Guardian][AUDIT] %s %s", event,
                json.dumps(details or {}, ensure_ascii=False)[:300])


def read_audit(limite: int = 30) -> List[Dict[str, Any]]:
    """Ultimos registros de auditoria."""
    try:
        if not AUDIT_PATH.is_file():
            return []
        linhas = AUDIT_PATH.read_text(encoding="utf-8").splitlines()
        saida = []
        for ln in linhas[-max(1, min(200, limite)):]:
            try:
                saida.append(json.loads(ln))
            except json.JSONDecodeError:
                continue
        return list(reversed(saida))
    except OSError:
        return []


# --------------------------------------------------------------------------- #
# Aprovacoes: vinculadas a acao EXATA (hash dos parametros)                    #
# --------------------------------------------------------------------------- #

def approval_id_for(action: str, target: str = "",
                    args: Optional[Dict[str, Any]] = None) -> str:
    """id deterministico: mesma acao = mesmo id; plano muda = id novo."""
    material = json.dumps({"a": action, "t": target or "",
                           "p": args or {}}, sort_keys=True,
                          ensure_ascii=False)
    return "apr_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]


def request_approval(action: str, plan: Dict[str, Any],
                     target: str = "",
                     args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Cria (ou atualiza) uma aprovacao pendente e devolve o plano.

    O approval_id e derivado dos parametros: aprovar uma acao DIFERENTE
    nao resolve a original (vinculo exato).
    """
    aid = approval_id_for(action, target, args)
    with _approvals_lock:
        _APPROVALS[aid] = {
            "action": action,
            "target": target,
            "args": args or {},
            "plan": plan,
            "created": time.time(),
            "expires": time.time() + _APPROVAL_TTL,
        }
    audit("aprovacao_solicitada", {"id": aid, "action": action,
                                   "target": target})
    return {"approval_required": True, "approval_id": aid,
            "expires_in_s": _APPROVAL_TTL, "plan": plan}


def _consume_approval(action: str, target: str = "",
                      args: Optional[Dict[str, Any]] = None,
                      approval_id: str = "") -> Tuple[bool, str]:
    """Confere se o approval_id corresponde EXATAMENTE a esta acao."""
    aid = str(approval_id or "").strip()
    if not aid:
        return False, "aprovacao_requerida"
    esperado = approval_id_for(action, target, args)
    with _approvals_lock:
        reg = _APPROVALS.get(aid)
        if not reg:
            return False, "aprovacao_inexistente_ou_expirada"
        if aid != esperado:
            return False, "aprovacao_nao_corresponde_a_esta_acao"
        if time.time() > reg["expires"]:
            _APPROVALS.pop(aid, None)
            return False, "aprovacao_expirada"
        _APPROVALS.pop(aid, None)  # uso unico
    audit("aprovacao_consumida", {"id": aid, "action": action,
                                  "target": target})
    return True, ""


# --------------------------------------------------------------------------- #
# Coleta de metricas                                                           #
# --------------------------------------------------------------------------- #

def _parse_cpu_delta(sample: str) -> Optional[float]:
    """%CPU medio entre duas amostras de 'grep ^cpu /proc/stat'."""
    try:
        def soma(linha):
            vals = [int(x) for x in linha.split()[1:8]]
            return sum(vals)
        a, b = sample.strip().splitlines()[:2]
        s1, s2 = soma(a), soma(b)
        idle1 = int(a.split()[4]) + int(a.split()[5])
        idle2 = int(b.split()[4]) + int(b.split()[5])
        dt = s2 - s1
        if dt <= 0:
            return None
        return round(100.0 * (1 - ((idle2 - idle1) / dt)), 1)
    except Exception:
        return None


def collect_metrics(amostrar_cpu: bool = True) -> Dict[str, Any]:
    """Coleta o estado atual do ZimaOS em uma batida de SSH."""
    t0 = time.time()
    m: Dict[str, Any] = {"collected_at": t0, "ok": False}

    # CPU: load + (opcional) delta de /proc/stat com1s de amostra
    rc, out, _ = run_ssh("nproc; cat /proc/loadavg", timeout=15)
    if rc != 0:
        m["error"] = out or "sem resposta"
        return m
    linhas = out.splitlines()
    try:
        m["cores"] = int(linhas[0].strip())
        m["load"] = [float(x) for x in linhas[1].split()[:3]]
        m["cpu_pct"] = round(100.0 * m["load"][0] / max(1, m["cores"]), 1)
    except Exception:
        m["cores"], m["load"], m["cpu_pct"] = None, [], None

    if amostrar_cpu:
        rc, out, _ = run_ssh(
            "grep '^cpu ' /proc/stat; sleep 1; grep '^cpu ' /proc/stat",
            timeout=15)
        if rc == 0:
            m["cpu_pct"] = _parse_cpu_delta(out)

    # RAM / Swap
    rc, out, _ = run_ssh("free -m", timeout=15)
    if rc == 0:
        try:
            for linha in out.splitlines():
                partes = linha.split()
                if partes and partes[0].lower().startswith("mem"):
                    total, used = int(partes[1]), int(partes[2])
                    m["ram_total_mb"] = total
                    m["ram_used_mb"] = used
                    m["ram_pct"] = round(100.0 * used / max(1, total), 1)
                elif partes and partes[0].lower().startswith("swap"):
                    total, used = int(partes[1]), int(partes[2])
                    m["swap_total_mb"] = total
                    m["swap_used_mb"] = used
                    m["swap_pct"] = round(100.0 * used / max(1, total), 1)
        except Exception:
            pass

    # Temperatura (maximo dos sensores termicos)
    rc, out, _ = run_ssh(
        "paste -d' ' /sys/class/thermal/thermal_zone*/type "
        "/sys/class/thermal/thermal_zone*/temp 2>/dev/null | head -10",
        timeout=15)
    if rc == 0 and out.strip():
        max_t = None
        for linha in out.splitlines():
            partes = linha.split()
            if len(partes) >= 2 and partes[-1].lstrip("-").isdigit():
                t = int(partes[-1]) / 1000.0
                max_t = t if max_t is None else max(max_t, t)
        if max_t is not None:
            m["temp_c"] = round(max_t, 1)

    # Discos (timeout embutido: mounts remotos penduram o df)
    rc, out, _ = run_ssh(
        "timeout 8 df -B1G --output=target,size,used,avail,pcent "
        "-x tmpfs -x devtmpfs -x overlay -x squashfs 2>/dev/null | head -40",
        timeout=15)
    if rc == 0:
        discos = []
        ignores = load_limits().get("disk_ignore_mounts") or []
        for linha in out.splitlines()[1:]:
            partes = linha.split()
            if len(partes) >= 5 and partes[-1].endswith("%"):
                alvo = partes[0]
                if any(bloqueado in alvo for bloqueado in
                       ("google", "icloud", "/media/", "/run", "/proc")):
                    continue
                # particoes de sistema (overlay/boot/etc): nao sao
                # 'falta de espaco' real - evita alerta falso toda coleta
                if any(alvo == ign or alvo.startswith(ign)
                       for ign in ignores):
                    continue
                discos.append({
                    "mount": alvo,
                    "size_gb": _int(partes[1]),
                    "used_gb": _int(partes[2]),
                    "avail_gb": _int(partes[3]),
                    "pct": _int(partes[4].rstrip("%")),
                })
        m["disks"] = discos

    # Containers: estado + restarts
    rc, out, _ = run_ssh(
        "docker ps -a --format '{{.Names}}|{{.Status}}|{{.CreatedAt}}'",
        timeout=25)
    containers = []
    if rc == 0:
        for linha in out.splitlines():
            partes = linha.split("|")
            if len(partes) >= 2:
                nome = partes[0]
                status = partes[1]
                rodando = status.lower().startswith("up")
                restarts = 0
                mrot = re.search(r"\((\d+) restarts?\)", status)
                if mrot:
                    restarts = int(mrot.group(1))
                containers.append({
                    "name": nome, "running": rodando, "status": status,
                    "restarts": restarts,
                    "created": partes[2] if len(partes) > 2 else "",
                    "critical": nome in CRITICAL_CONTAINERS,
                })
    m["containers"] = containers

    # Consumo por container
    rc, out, _ = run_ssh(
        "docker stats --no-stream "
        "--format '{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}'",
        timeout=30)
    if rc == 0:
        stats = {}
        for linha in out.splitlines():
            partes = linha.split("|")
            if len(partes) >= 3:
                nome = partes[0]
                cpu = _int(partes[1].replace("%", ""))
                stats[nome] = {"cpu_pct": cpu, "mem": partes[2].strip()}
                for c in containers:
                    if c["name"] == nome:
                        c["cpu_pct"] = cpu
                        c["mem"] = partes[2].strip()
        m["container_stats"] = stats

    # Portas expostas
    rc, out, _ = run_ssh(
        "ss -tlnp | tail -n +2 | awk '{print $4\"|\"$6}'", timeout=15)
    if rc == 0:
        portas = []
        for linha in out.splitlines():
            partes = linha.split("|")
            if len(partes) == 2:
                addr = partes[0]
                dono = partes[1].replace('users:(', "").replace(")", "")
                port = addr.rsplit(":", 1)[-1]
                host = addr.rsplit(":", 1)[0]
                portas.append({"port": _int(port), "host": host,
                               "owner": dono[:80]})
        m["ports"] = portas

    # Top processos por CPU
    rc, out, _ = run_ssh(
        "ps -eo pcpu,pid,comm --sort=-pcpu | head -9 | tail -8",
        timeout=15)
    if rc == 0:
        top = []
        for linha in out.splitlines():
            partes = linha.split(None, 2)
            if len(partes) == 3:
                top.append({"cpu": _float(partes[0]),
                            "pid": _int(partes[1]),
                            "comm": partes[2]})
        m["top_processes"] = top

    # Servicos systemd com falha
    rc, out, _ = run_ssh(
        "systemctl --failed --no-legend --no-pager | head -12",
        timeout=15)
    if rc == 0:
        falhos = []
        for linha in out.splitlines():
            partes = linha.split()
            if partes:
                falhos.append({"unit": partes[0],
                               "state": partes[3] if len(partes) > 3 else "",
                               "detail": " ".join(partes[4:])[:120]})
        m["failed_services"] = falhos

    # Conexoes externas estabelecidas (nao-privadas)
    rc, out, _ = run_ssh(
        "ss -tn state established 2>/dev/null | tail -n +2 | "
        "awk '{print $3}' | grep -vE '^(127\\.|10\\.|192\\.168\\.|172\\.(1[6-9]|2[0-9]|3[01])\\.)' | "
        "head -15", timeout=15)
    if rc == 0:
        m["external_conns"] = [x.strip() for x in out.splitlines()
                               if x.strip()]

    m["ok"] = True
    m["duration_s"] = round(time.time() - t0, 1)
    return m


def _int(v) -> int:
    try:
        return int(str(v).strip().rstrip("%"))
    except (ValueError, TypeError):
        return 0


def _float(v) -> float:
    try:
        return float(str(v).strip())
    except (ValueError, TypeError):
        return 0.0


# --------------------------------------------------------------------------- #
# Diagnostico inteligente                                                      #
# --------------------------------------------------------------------------- #

def diagnose(metrics: Optional[Dict[str, Any]] = None,
             limits: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Correlaciona metricas com limites e devolve achados investigados.

    Cada achado: {id, sev, area, titulo, causa_provavel, evidencias[],
                  recomendacao, acao_automatica?}
    """
    lim = limits or load_limits()
    m = metrics if metrics is not None else collect_metrics()
    achados: List[Dict[str, Any]] = []
    if not m.get("ok"):
        return {"ok": False, "error": m.get("error", "coleta falhou"),
                "findings": []}

    # --- CPU ------------------------------------------------------------
    cpu = m.get("cpu_pct")
    load = (m.get("load") or [0])[0] if m.get("load") else 0
    cores = m.get("cores") or 1
    if cpu is not None and cpu >= lim["cpu_pct"]:
        top = m.get("top_processes") or []
        culpado = top[0] if top else None
        culpado_docker = None
        for nome, st in (m.get("container_stats") or {}).items():
            if st.get("cpu_pct", 0) >= 30:
                culpado_docker = {"container": nome,
                                  "cpu_pct": st["cpu_pct"]}
                break
        causa = "CPU saturada"
        if culpado_docker:
            causa = (f"container '{culpado_docker['container']}' usando "
                     f"{culpado_docker['cpu_pct']}% da CPU")
        elif culpado:
            causa = (f"processo '{culpado['comm']}' (pid {culpado['pid']}) "
                     f"usando {culpado['cpu']}% da CPU")
        achados.append({
            "id": f"cpu_{int(cpu)}",
            "sev": "critico" if cpu >= 98 else "alto",
            "area": "cpu",
            "titulo": f"CPU em {cpu}% (load {load} em {cores} cores)",
            "causa_provavel": causa,
            "evidencias": [f"cpu_pct={cpu}%", f"load={load}",
                           f"top: {json.dumps(top[:3], ensure_ascii=False)}"],
            "recomendacao": ("Investigar o processo/container apontado; "
                             "se for workload inesperado, parar o container "
                             "ou limitar CPU (docker update --cpus)."),
        })
    elif load / max(1, cores) >= lim["load_per_core"] and load > cores:
        achados.append({
            "id": f"load_{int(load * 10)}",
            "sev": "medio", "area": "cpu",
            "titulo": f"Load average {load} acima do por-nucleo "
                      f"({lim['load_per_core']}x)",
            "causa_provavel": " fila de processos prolongada (E/S ou CPU)",
            "evidencias": [f"load={load}", f"cores={cores}"],
            "recomendacao": "Verificar top_processes e docker stats.",
        })

    # --- RAM / Swap ------------------------------------------------------
    if m.get("ram_pct") is not None and m["ram_pct"] >= lim["ram_pct"]:
        top = m.get("top_processes") or []
        achados.append({
            "id": f"ram_{int(m['ram_pct'])}",
            "sev": "alto", "area": "ram",
            "titulo": f"RAM em {m['ram_pct']}% "
                      f"({m.get('ram_used_mb')}MB/{m.get('ram_total_mb')}MB)",
            "causa_provavel": "consumo alto de memoria (ver top_processes)",
            "evidencias": [f"ram_pct={m['ram_pct']}%",
                           f"swap_pct={m.get('swap_pct', 0)}%",
                           f"top: {json.dumps(top[:3], ensure_ascii=False)}"],
            "recomendacao": ("Identificar o consumidor; considerar limites "
                             "de memoria nos containers envolvidos."),
        })
    if m.get("swap_pct") is not None and m["swap_pct"] >= lim["swap_pct"]:
        achados.append({
            "id": f"swap_{int(m['swap_pct'])}",
            "sev": "medio", "area": "ram",
            "titulo": f"Swap em {m['swap_pct']}%",
            "causa_provavel": "pressao de memoria forçando swap",
            "evidencias": [f"swap={m.get('swap_used_mb')}MB"],
            "recomendacao": "Reduzir consumo de memoria ou adicionar RAM.",
        })

    # --- Discos ----------------------------------------------------------
    for d in (m.get("disks") or []):
        if d["pct"] >= lim["disk_pct"] or d["avail_gb"] < lim["disk_free_gb_min"]:
            sev = ("critico"
                   if d["pct"] >= 95 or d["avail_gb"] < 2 else "alto")
            achados.append({
                "id": f"disk_{d['mount'].replace('/', '_') or 'root'}",
                "sev": sev, "area": "disco",
                "titulo": f"Disco {d['mount']} em {d['pct']}% "
                          f"({d['avail_gb']}G livres)",
                "causa_provavel": ("esgotamento de espaco - o servidor ja "
                                   "opera com / cheio (historico: raiz 100%)"),
                "evidencias": [json.dumps(d, ensure_ascii=False)],
                "recomendacao": ("Limpar caches/tmp, rolar logs ou mover "
                                 "dados para /DATA (222G) - NUNCA rm "
                                 "automatico; pedir aprovacao."),
                "acao_automatica": "disk_report_only",
            })

    # --- Temperatura -----------------------------------------------------
    if m.get("temp_c") is not None and m["temp_c"] >= lim["temp_c"]:
        achados.append({
            "id": f"temp_{int(m['temp_c'])}",
            "sev": "critico" if m["temp_c"] >= 90 else "alto",
            "area": "temperatura",
            "titulo": f"Temperatura {m['temp_c']}°C",
            "causa_provavel": "superaquecimento sob carga sustentada",
            "evidencias": [f"temp_c={m['temp_c']}"],
            "recomendacao": "Verificar ventilacao/carga; reduzir workloads pesados.",
        })

    # --- Containers ------------------------------------------------------
    for c in (m.get("containers") or []):
        if not c["running"]:
            # parado ha quanto tempo? status mostra 'Exited (...)'
            refe = c.get("status", "")
            sev = "alto" if c["critical"] else "medio"
            achados.append({
                "id": f"container_parado_{c['name']}",
                "sev": sev, "area": "docker",
                "titulo": f"Container '{c['name']}' parado",
                "causa_provavel": f"status: {refe} "
                                  "(falha ao iniciar, politica ou parada manual)",
                "evidencias": [json.dumps(c, ensure_ascii=False)],
                "recomendacao": (f"Inspecionar logs: logs {c['name']} "
                                 f"e decidir start se o servico e esperado."),
                "acao_automatica": f"restart:{c['name']}",
            })
        if c.get("restarts", 0) >= lim["container_restart_count"]:
            achados.append({
                "id": f"container_restart_{c['name']}",
                "sev": "alto", "area": "docker",
                "titulo": f"Container '{c['name']}' reiniciou "
                          f"{c['restarts']}x (loop de falha)",
                "causa_provavel": "boot loop - crash na inicializacao",
                "evidencias": [json.dumps(c, ensure_ascii=False)],
                "recomendacao": f"Inspecionar logs {c['name']} imediatamente.",
                "acao_automatica": f"logs:{c['name']}",
            })
        if c.get("cpu_pct", 0) >= lim["container_cpu_pct"]:
            achados.append({
                "id": f"container_cpu_{c['name']}",
                "sev": "alto", "area": "docker",
                "titulo": f"Container '{c['name']}' em {c['cpu_pct']}% CPU",
                "causa_provavel": "carga anormal neste container",
                "evidencias": [json.dumps(c, ensure_ascii=False)],
                "recomendacao": "Inspecionar processo interno; limite de CPU se persistir.",
            })

    # --- Servicos com falha ----------------------------------------------
    for s in (m.get("failed_services") or []):
        achados.append({
            "id": f"service_{s['unit']}",
            "sev": "medio", "area": "servicos",
            "titulo": f"Servico '{s['unit']}' em falha ({s['state']})",
            "causa_provavel": s.get("detail", "")[:120] or "sem detalhe",
            "evidencias": [json.dumps(s, ensure_ascii=False)],
            "recomendacao": (f"Inspecionar: journalctl -u {s['unit']}; "
                             "reiniciar se estiver na safe-list."),
            "acao_automatica": (
                f"service:{s['unit'].removesuffix('.service')}"
                if s["unit"].removesuffix(".service") in REPAIRABLE_SERVICES
                else None),
        })

    return {"ok": True, "metrics": m, "findings": achados,
            "limits": lim,
            "summary": _summarize(achados)}


def _summarize(achados: List[Dict[str, Any]]) -> str:
    if not achados:
        return "Servidor saudavel - nenhum problema acima dos limites."
    criticos = [a for a in achados if a["sev"] in ("critico", "alto")]
    partes = "; ".join(a["titulo"] for a in achados[:5])
    return (f"{len(achados)} achado(s), {len(criticos)} grave(s): {partes}")


# --------------------------------------------------------------------------- #
# Diagnostico profundo (investigacao sob demanda)                              #
# --------------------------------------------------------------------------- #

def deep_diagnose(topico: str = "") -> Dict[str, Any]:
    """Investiga a fundo: coleta + analyze + logs/correlacoes extras."""
    diagnostico = diagnose()
    if not diagnostico.get("ok"):
        return diagnostico
    m = diagnostico["metrics"]
    extras: List[str] = []

    # Erros recentes do kernel/systemd (correlacao temporal)
    rc, out, _ = run_ssh(
        "journalctl -p warning --since '-2 hours' --no-pager -n 25 2>/dev/null",
        timeout=25)
    if rc == 0 and out.strip():
        extras.append("ultimas_avisos_2h:\n" + out.strip()[:2500])

    # Logs de containers com achados (topico pode nomear um container)
    alvo = topico.strip() if topico else ""
    if alvo:
        rc, out, _ = run_ssh(
            f"docker logs --tail 40 {shlex.quote(alvo)} 2>&1", timeout=25)
        if rc == 0:
            extras.append(f"logs({alvo}):\n" + out.strip()[:2500])
        else:
            extras.append(f"logs({alvo}): alvo nao encontrado/erro")

    diagnostico["extras"] = extras
    diagnostico["investigado"] = alvo or "geral"
    audit("diagnostico_profundo", {
        "topico": alvo,
        "achados": len(diagnostico["findings"]),
    })
    return diagnostico


# --------------------------------------------------------------------------- #
# Administracao Docker                                                         #
# --------------------------------------------------------------------------- #

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
# imagens aceitam registry/repo:tag (ex: lscr.io/linuxserver/jellyfin:12.2)
# mas NUNCA espacos, ;, $, ( — mantemos a garantia anti-injecao
_IMAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-/:@]{0,254}$")

# leitura: sempre permitido; escrita baixo risco: start/restart/stop*
_DOCKER_SAFE_OPS = {"list", "ps", "inspect", "logs", "stats",
                    "images", "volumes", "networks", "version"}
# stop NAO entra aqui de proposito: stop de container NAO-critico e de
# baixo risco (reparo); stop de CRITICO cai na regra especial abaixo.
_DOCKER_APPROVAL_OPS = {"rm", "rmi", "volume_rm", "network_rm",
                        "pull", "prune", "compose_up", "compose_down"}


def _valida_alvo(target: str, imagem: bool = False) -> str:
    target = str(target or "").strip()
    padrao = _IMAGE_RE if imagem else _NAME_RE
    if not padrao.match(target):
        raise ValueError(f"nome de recurso invalido: {target[:60]!r}")
    return target


def docker_plan(op: str, target: str = "",
                args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Monta o plano (comando exato) de uma acao Docker."""
    args = args or {}
    op = str(op or "").strip().lower()
    target = str(target or "").strip()
    if target:
        # pull/rmi trabalham com imagem (repo:tag pode ter : e /)
        _valida_alvo(target, imagem=(op in ("pull", "rmi")))
    tail = min(500, max(1, _int(args.get("tail", 100)) or 100))

    if op in ("list", "ps"):
        # filtro natural por linguagem natural: list target="stopped"/"running"
        filtro = {"running": "running", "up": "running",
                  "stopped": "exited", "parado": "exited",
                  "parados": "exited", "exited": "exited"}.get(
            str(target).lower())
        cmd = ("docker ps -a"
               + (f" --filter status={filtro}" if filtro else "")
               + " --format "
                 "'{{.Names}}|{{.Status}}|{{.Image}}|{{.Ports}}'")
    elif op == "images":
        cmd = "docker images --format '{{.Repository}}:{{.Tag}}|{{.Size}}'"
    elif op == "volumes":
        cmd = "docker volume ls --format '{{.Name}}|{{.Driver}}'"
    elif op == "networks":
        cmd = "docker network ls --format '{{.Name}}|{{.Driver}}'"
    elif op == "version":
        cmd = "docker version --format '{{.Server.Version}}'"
    elif op == "stats":
        cmd = ("docker stats --no-stream --format "
               "'{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}'")
    elif op == "inspect" and target:
        cmd = ("docker inspect -f "
               "'{{json .State}}|restarts={{.RestartCount}}|"
               "image={{.Config.Image}}' " + shlex.quote(target))
    elif op == "logs" and target:
        since = str(args.get("since") or "")
        cmd = f"docker logs --tail {tail} "
        if since and re.fullmatch(r"\d+[smh]", since):
            cmd += f"--since {since} "
        cmd += shlex.quote(target) + " 2>&1"
    elif op == "start" and target:
        cmd = f"docker start {shlex.quote(target)}"
    elif op == "stop" and target:
        cmd = f"docker stop {shlex.quote(target)}"
    elif op == "restart" and target:
        cmd = f"docker restart {shlex.quote(target)}"
    elif op == "rm" and target:
        cmd = f"docker rm {shlex.quote(target)}"
    elif op == "rmi" and target:
        cmd = f"docker rmi {shlex.quote(target)}"
    elif op == "volume_rm" and target:
        cmd = f"docker volume rm {shlex.quote(target)}"
    elif op == "network_rm" and target:
        cmd = f"docker network rm {shlex.quote(target)}"
    elif op == "pull" and target:
        cmd = f"docker pull {shlex.quote(target)}"
    elif op == "prune":
        cmd = "docker system df --verbose | head -30"  # so mostra; exec real de prune = outro passo
        op_exec = "prune_preview"
    else:
        raise ValueError(f"operacao docker desconhecida/invalida: {op!r}")
    return {"op": op, "target": target, "command": cmd}


def docker_admin(op: str, target: str = "", args: Optional[Dict[str, Any]] = None,
                 approval_id: str = "") -> Dict[str, Any]:
    """Executa operacao Docker com politica de aprovacao.

    - Leitura (list/inspect/logs/stats/...): direta.
    - start/restart: direto (baixo risco) + audit.
    - stop: direto se NAO critico; critico exige aprovacao.
    - rm/pull/compose/...: SEMPRE exigem approval_id conferido.
    """
    args = args or {}
    try:
        plano = docker_plan(op, target, args)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    cmd = plano["command"]

    # --- leitura ---
    if op in _DOCKER_SAFE_OPS:
        rc, out, err = run_ssh(cmd, timeout=40)
        audit("docker_leitura", {"op": op, "target": target, "rc": rc})
        if rc != 0:
            return {"ok": False, "error": (err or out or "falhou")[:400],
                    "command": cmd}
        return {"ok": True, "op": op, "command": cmd,
                "output": out.strip()[:12000]}

    # --- escrita: classifica risco ---
    eh_critico = bool(target) and target in CRITICAL_CONTAINERS
    precisa_aprovacao = (op in _DOCKER_APPROVAL_OPS or
                         (op == "stop" and eh_critico))

    if precisa_aprovacao:
        ok, motivo = _consume_approval(op, target, args, approval_id)
        if not ok:
            if motivo == "aprovacao_requerida":
                return request_approval(op, _plano_para_humano(op, target, cmd),
                                        target, args)
            return {"ok": False, "error": f"aprovacao invalida ({motivo})",
                    "approval_required": True,
                    "approval_id": approval_id_for(op, target, args)}

    # estado anterior (rollback info) para escritas
    estado_antes = None
    if op in ("stop", "restart", "start") and target:
        rc, out, _ = run_ssh(
            f"docker inspect -f '{{{{.State.Status}}}}' "
            f"{shlex.quote(target)} 2>/dev/null || echo desconhecido",
            timeout=20)
        if rc == 0:
            estado_antes = out.strip()

    rc, out, err = run_ssh(cmd, timeout=120)
    audit("docker_escrita", {
        "op": op, "target": target, "command": cmd, "rc": rc,
        "estado_antes": estado_antes,
        "aprovado": not precisa_aprovacao or bool(approval_id),
    })
    if rc != 0:
        return {"ok": False, "error": (err or out or "falhou")[:500],
                "command": cmd}
    return {"ok": True, "op": op, "target": target, "command": cmd,
            "estado_antes": estado_antes,
            "output": out.strip()[:4000],
            "message": f"Operação '{op}' executada"
                       + (f" em '{target}'" if target else "") + "."}


def _plano_para_humano(op: str, target: str, cmd: str) -> Dict[str, Any]:
    """Plano de aprovacao legivel: acao, motivo, recursos, riscos, comando."""
    recursos = [target] if target else ["servidor (host)"]
    riscos = {
        "rm": "remocao permanente do container (dados nao preservados a menos que com volume)",
        "rmi": "imagem removida - containers dependentes nao poderao ser recriados",
        "volume_rm": "PERDA DEFINITIVA de dados do volume",
        "network_rm": "redes conectadas perdem conectividade",
        "pull": "nova imagem substitui a atual em proximo restart",
        "stop": "servico fica indisponivel enquanto parado",
        "compose_up": "pode criar/recriar containers e redes do stack",
        "compose_down": "derruba o stack inteiro (volumes so com -v)",
        "prune": "remove imagens/volumes/cache nao em uso",
    }
    return {
        "acao": op,
        "alvo": recursos,
        "motivo": f"operacao '{op}' solicitada pelo usuario via voz/texto",
        "recursos": recursos,
        "risco": riscos.get(op, "alteracao em recurso do servidor"),
        "comando": cmd,
        "instrucao": ("Aprovação: responda 'aprovo' e a IA chamara "
                      "zima_guardian action=docker com approval_id."),
    }


# --------------------------------------------------------------------------- #
# Seguranca e resposta a incidentes                                            #
# --------------------------------------------------------------------------- #

def security_report(horas: int = 24) -> Dict[str, Any]:
    """Relatorio de seguranca: logins, portas, processos, conexoes."""
    horas = max(1, min(168, int(horas or 24)))
    rep: Dict[str, Any] = {"ok": True, "janela_horas": horas,
                           "incidentes": [], "resumo": ""}
    audit("relatorio_seguranca", {"horas": horas})

    # 1) Tentativas de login falhas (journalctl ssh)
    rc, out, _ = run_ssh(
        f"journalctl -u ssh --since '{horas} hours ago' --no-pager "
        "2>/dev/null | grep -ciE 'failed|invalid' || true", timeout=25)
    falhas = _int((out or "0").strip().splitlines()[0]
                  if out and out.strip() else 0)
    rep["logins_falhos"] = falhas

    ips_suspeitos: Dict[str, int] = {}
    if falhas > 0:
        rc, out, _ = run_ssh(
            f"journalctl -u ssh --since '{horas} hours ago' --no-pager "
            "2>/dev/null | grep -iE 'failed|invalid' | "
            "grep -oE '([0-9]{1,3}\\.){3}[0-9]{1,3}' | sort | uniq -c | "
            "sort -rn | head -10", timeout=25)
        if rc == 0:
            for linha in out.splitlines():
                partes = linha.split()
                if len(partes) == 2 and partes[1].count(".") == 3:
                    ips_suspeitos[partes[1]] = _int(partes[0])
        if ips_suspeitos:
            pior = max(ips_suspeitos, key=ips_suspeitos.get)
            rep["incidentes"].append({
                "tipo": "brute_force_ssh",
                "sev": "alto" if ips_suspeitos[pior] >= 20 else "medio",
                "titulo": f"{falhas} tentativas de login falhas em "
                          f"{horas}h ({len(ips_suspeitos)} IPs)",
                "evidencias": dict(sorted(ips_suspeitos.items(),
                                          key=lambda x: -x[1])[:5]),
                "recomendacao": ("Avaliar bloqueio do IP mais ativo via "
                                 "action=block_ip (requer aprovacao); "
                                 "verificar fail2ban."),
            })

    # 2) Portas expostas
    rc, out, _ = run_ssh(
        "ss -tlnp | tail -n +2 | awk '{print $4}' | "
        "grep -E '0.0.0.0|\\*:' | sed 's/.*://' | sort -un", timeout=20)
    portas_abertas = [_int(x) for x in (out or "").split()] if rc == 0 else []
    rep["portas_escutando"] = sorted(set(portas_abertas))
    # 2375/2376 = Docker API exposta (grave)
    docker_api = [p for p in (2375, 2376) if p in portas_abertas]
    if docker_api:
        rep["incidentes"].append({
            "tipo": "docker_api_exposta",
            "sev": "critico",
            "titulo": f"Docker API escutando em {docker_api} "
                      "(socket exposto)",
            "evidencias": {"portas": docker_api},
            "recomendacao": "Remover -H tcp:// do dockerd; socket local apenas.",
        })

    # 3) Mineração / processos suspeitos
    rc, out, _ = run_ssh("ps -eo comm --no-headers | sort -u", timeout=20)
    if rc == 0:
        suspeitos = [c.strip() for c in out.splitlines()
                     if _MINER_NAMES.match(c.strip())]
        if suspeitos:
            rep["incidentes"].append({
                "tipo": "mineracao_suspeita",
                "sev": "critico",
                "titulo": f"processos de mineracao detectados: {suspeitos}",
                "evidencias": {"processos": suspeitos},
                "recomendacao": "Identificar origem (container/processo) e conter.",
            })

    # 4) Conexoes externas suspeitas (fora de privadas e portas comuns)
    rc, out, _ = run_ssh(
        "ss -tn state established | tail -n +2 | awk '{print $3\"|\"$4}'", timeout=20)
    suspeitas_conexoes = []
    if rc == 0:
        for linha in out.splitlines():
            partes = linha.split("|")
            if len(partes) != 2:
                continue
            ip = partes[0].split("%")[0]
            porta = _int(partes[1].rsplit(":", 1)[-1])
            privada = (ip.startswith(("127.", "10.", "192.168.",
                                      "172.16.", "172.17.", "172.18.",
                                      "172.19.", "172.2", "172.3",
                                      "10.147.")) or ":" in ip)  # ipv6 = normal
            comum = porta in (53, 80, 443, 853, 993, 995, 465, 587, 873,
                              22, 5222, 5223, 5353, 1900, 5355, 123)
            if not privada and not comum:
                suspeitas_conexoes.append(f"{ip}:{porta}")
    rep["conexoes_externas_suspeitas"] = suspeitas_conexoes[:10]
    if suspeitas_conexoes:
        rep["incidentes"].append({
            "tipo": "conexoes_externas_incomuns",
            "sev": "medio",
            "titulo": f"{len(suspeitas_conexoes)} conexoes externas em "
                      "portas incomuns",
            "evidencias": {"endpoints": suspeitas_conexoes[:10]},
            "recomendacao": "Identificar o processo dono antes de qualquer bloqueio.",
        })

    crit = len([i for i in rep["incidentes"] if i["sev"] in ("critico", "alto")])
    rep["resumo"] = (f"Seguranca {horas}h: {len(rep['incidentes'])} incidente(s), "
                     f"{crit} grave(s); {falhas} logins falhos.")
    return rep


def block_ip(ip: str, motivo: str = "", approval_id: str = "",
             evidence: str = "") -> Dict[str, Any]:
    """Bloqueia um IP no firewall do ZimaOS (aprovacao OBRIGATORIA).

    Politica:
    - valida formato do IP;
    - NEVER_BLOCK: redes privadas/loopback/ZeroTier sao sempre recusadas
      (nao interromper servicos legitimos, admin nem o proprio Jarvis);
    - exige aprovacao vinculada (acao 'block_ip');
    - persiste: backup do iptables antes + iptables-save no arquivo que
      o restore-firewall.service le no boot;
    - audit de tudo.
    """
    import ipaddress
    try:
        addr = ipaddress.ip_address(str(ip).strip())
    except ValueError:
        return {"ok": False, "error": f"IP invalido: {ip!r}"}
    ip = str(addr)
    # NEVER_BLOCK: redes privadas (v4/v6) e link-local
    if addr.is_private or addr.is_loopback or addr.is_link_local:
        return {"ok": False,
                "error": f"{ip} e rede privada/legitima - bloqueio recusado "
                         "pela politica NEVER_BLOCK"}

    args = {"ip": ip, "motivo": motivo}
    ok, motivo_falha = _consume_approval("block_ip", ip, args, approval_id)
    if not ok:
        if motivo_falha == "aprovacao_requerida":
            return request_approval(
                "block_ip",
                {"acao": "block_ip",
                 "alvo": ip,
                 "motivo": motivo or "(sem motivo declarado)",
                 "evidencia": evidence or "(sem evidencia declarada)",
                 "riscos": ("IP deixara de acessar o servidor; confirme que "
                            "nao e um IP legitimo/proprio antes de aprovar"),
                 "comando": f"iptables -I INPUT -s {ip}/32 -j DROP (+persistencia)"},
                ip, args)
        return {"ok": False, "error": f"aprovacao invalida ({motivo_falha})"}

    # executa: backup + regra + persistencia
    backup_cmd = (
        "cp -a /DATA/AppData/iptables-backup.rules "
        "/DATA/AppData/iptables-backup.rules.bak-guardian-$(date +%s) 2>/dev/null; "
        f"iptables -I INPUT -s {ip}/32 -j DROP && "
        "iptables-save > /DATA/AppData/iptables-backup.rules && "
        "echo BLOQUEADO_OK || echo FALHOU")
    rc, out, err = run_ssh(backup_cmd, timeout=30)
    resultado = (out or "").strip()
    audit("firewall_block_ip", {
        "ip": ip, "motivo": motivo, "evidencia": evidence,
        "rc": rc, "resultado": resultado[:200],
    })
    if "BLOQUEADO_OK" not in resultado:
        return {"ok": False, "error": f"falha ao aplicar regra: "
                                      f"{(err or out)[:300]}"}
    return {"ok": True, "ip": ip,
            "message": f"IP {ip} bloqueado no firewall (persistente) e auditado.",
            "motivo": motivo}


# --------------------------------------------------------------------------- #
# Reparo automático (apenas baixo risco)                                       #
# --------------------------------------------------------------------------- #

def auto_repair(acao: str = "", alvo: str = "") -> Dict[str, Any]:
    """Correcoes de baixo risco, com registro de estado anterior/resultado.

    Permitido sem aprovacao:
    - service_restart em servicos da safe-list
    - container_restart (restart nao destrutivo)
    Nao faz: rm, prune, pull, edicao de config (exigem aprovacao).
    """
    acao = str(acao or "").strip().lower()
    alvo = str(alvo or "").strip()

    if acao == "service_restart":
        if not _NAME_RE.match(alvo.replace(".service", "")):
            return {"ok": False, "error": f"servico invalido: {alvo!r}"}
        unit = alvo if alvo.endswith(".service") else alvo + ".service"
        nome = unit.removesuffix(".service")
        if nome not in REPAIRABLE_SERVICES:
            return {"ok": False,
                    "error": f"servico '{nome}' fora da safe-list "
                             f"{sorted(REPAIRABLE_SERVICES)} - "
                             "reparo automatico nao autorizado"}
        rc, out, _ = run_ssh(
            f"systemctl is-active {shlex.quote(unit)} || true", timeout=15)
        estado_antes = (out or "").strip()
        rc, out, err = run_ssh(
            f"systemctl restart {shlex.quote(unit)} && "
            f"systemctl is-active {shlex.quote(unit)}", timeout=30)
        resultado = (out or "").strip()
        audit("reparo_servico", {"servico": unit, "estado_antes": estado_antes,
                                 "resultado": resultado[:120], "rc": rc})
        if rc != 0 or "active" not in resultado:
            return {"ok": False, "error": (err or out or "falhou")[:300],
                    "estado_antes": estado_antes}
        return {"ok": True, "servico": unit, "estado_antes": estado_antes,
                "estado_depois": resultado,
                "message": f"Servico {unit} reiniciado (estado antes: "
                           f"'{estado_antes}')."}

    if acao == "container_restart":
        _valida_alvo(alvo)
        rc, out, _ = run_ssh(
            f"docker inspect -f '{{{{.State.Status}}}}' "
            f"{shlex.quote(alvo)}", timeout=20)
        estado_antes = (out or "").strip() or "desconhecido"
        rc, out, err = run_ssh(f"docker restart {shlex.quote(alvo)}",
                               timeout=120)
        audit("reparo_container", {"container": alvo,
                                   "estado_antes": estado_antes,
                                   "rc": rc, "resultado": (out or "")[:120]})
        if rc != 0:
            return {"ok": False, "error": (err or out or "falhou")[:300],
                    "estado_antes": estado_antes}
        return {"ok": True, "container": alvo, "estado_antes": estado_antes,
                "message": f"Container '{alvo}' reiniciado "
                           f"(antes: '{estado_antes}')."}

    return {"ok": False,
            "error": f"reparo '{acao}' desconhecido (use service_restart "
                     "ou container_restart)"}


# --------------------------------------------------------------------------- #
# Monitoramento continuo (loop chamado pelo local_server)                      #
# --------------------------------------------------------------------------- #

_hist_lock = threading.Lock()
_monitor_state: Dict[str, Any] = {"last_run": 0.0, "alerts": {}}


def _load_history() -> List[Dict[str, Any]]:
    try:
        if HISTORY_PATH.is_file():
            dados = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
            if isinstance(dados, list):
                return dados[-200:]
    except Exception:
        pass
    return []


def _save_history(historico: List[Dict[str, Any]]) -> None:
    try:
        GUARDIAN_DIR.mkdir(parents=True, exist_ok=True)
        HISTORY_PATH.write_text(json.dumps(historico[-200:],
                                            ensure_ascii=False, indent=1),
                                encoding="utf-8")
    except OSError as e:
        logger.warning("[Guardian] falha ao salvar historico: %s", e)


def monitor_once() -> Dict[str, Any]:
    """Uma rodada: coleta -> diagnostico -> alerta (com cooldown) -> hist.

    Retorna o resultado do diagnose. Alertas sao emitidos via broadcast
    do HUD (toast) apenas para achados NOVOS dentro do cooldown - evita
    spam de alerta (o usuario odeia spam).
    """
    cfg = load_limits()
    if not cfg.get("enabled", True):
        return {"ok": True, "disabled": True}

    diagnostico = diagnose(cfg=cfg) if False else diagnose(limits=cfg)
    _monitor_state["last_run"] = time.time()
    if not diagnostico.get("ok"):
        # falha de coleta tambem e sinal (servidor inacessivel)
        chave = "coleta_falhou"
        if _deve_alertar(chave, cfg["alert_cooldown_min"]):
            _emitir_alerta("critico",
                           "Guardian: nao consegui acessar o ZimaOS",
                           diagnostico.get("error", "erro desconhecido"))
        return diagnostico

    novos = []
    for a in diagnostico["findings"]:
        # disco: sistema imutavel -> cooldown maior (alerta real max 1x/12h)
        cooldown = (cfg.get("disk_alert_cooldown_min", 720)
                    if a.get("area") == "disco"
                    else cfg["alert_cooldown_min"])
        if _deve_alertar(a["id"], cooldown):
            novos.append(a)

    if novos:
        pior = "medio"
        for a in novos:
            if a["sev"] in ("critico", "alto"):
                pior = a["sev"]
                break
        titulo = f"Guardian: {len(novos)} novo(s) alerta(s) no ZimaOS"
        corpo = "; ".join(a["titulo"] for a in novos[:4])
        _emitir_alerta(pior, titulo, corpo)
        # persiste no historico
        with _hist_lock:
            hist = _load_history()
            for a in novos:
                hist.append({"ts": time.time(), "sev": a["sev"],
                             "titulo": a["titulo"], "area": a["area"],
                             "causa": a["causa_provavel"]})
            _save_history(hist)
        audit("alerta_monitor", {"novos": [a["id"] for a in novos]})

    diagnostico["alertados"] = [a["id"] for a in novos]
    return diagnostico


def _deve_alertar(chave: str, cooldown_min: int) -> bool:
    agora = time.time()
    ultimo = _monitor_state["alerts"].get(chave, 0)
    if (agora - ultimo) >= cooldown_min * 60:
        _monitor_state["alerts"][chave] = agora
        return True
    return False


def _emitir_alerta(sev: str, titulo: str, corpo: str) -> None:
    """Toast no HUD (respeita JARVIS_NO_RELAY dos testes)."""
    try:
        from dynamic_presentation_engine import _broadcast_to_hud
        _broadcast_to_hud("toast", {"message": f"🛡️ [{sev.upper()}] {titulo} — {corpo}"})
    except Exception as e:
        logger.warning("[Guardian] broadcast falhou: %s", e)


def monitor_status() -> Dict[str, Any]:
    """Estado do monitor (ultima execucao, alertas ativos)."""
    cfg = load_limits()
    hist = _load_history()
    return {
        "ok": True,
        "enabled": cfg.get("enabled", True),
        "interval_s": cfg.get("monitor_interval_s", 300),
        "last_run": _monitor_state["last_run"],
        "alertas_recentes": hist[-10:],
        "limits": cfg,
    }


# --------------------------------------------------------------------------- #
# Relatorio de saude (sob demanda, p/ narracao + card)                         #
# --------------------------------------------------------------------------- #

def health_report() -> Dict[str, Any]:
    """Saude completa: metricas + diagnostico + resumo de containers."""
    diagnostico = diagnose()
    if not diagnostico.get("ok"):
        return diagnostico
    m = diagnostico["metrics"]
    containers = m.get("containers") or []
    parados = [c["name"] for c in containers if not c["running"]]
    criticos = [c for c in containers if c.get("critical") and c["running"]]
    resumo = {
        "cpu_pct": m.get("cpu_pct"),
        "ram_pct": m.get("ram_pct"),
        "swap_pct": m.get("swap_pct"),
        "temp_c": m.get("temp_c"),
        "discos": [{k: d[k] for k in ("mount", "pct", "avail_gb")}
                   for d in (m.get("disks") or [])],
        "containers_total": len(containers),
        "containers_rodando": len([c for c in containers if c["running"]]),
        "containers_parados": parados,
        "servicos_falhando": [s["unit"] for s in (m.get("failed_services") or [])],
        "achados": len(diagnostico["findings"]),
        "saude": ("critica" if any(a["sev"] == "critico" for a in diagnostico["findings"])
                  else "atencao" if diagnostico["findings"] else "ok"),
    }
    texto = (f"ZimaOS: CPU {resumo['cpu_pct']}%, RAM {resumo['ram_pct']}%, "
             f"temp {resumo['temp_c']}°C, "
             f"{resumo['containers_rodando']}/{resumo['containers_total']} "
             f"containers ativos"
             + (f", parados: {', '.join(parados[:5])}" if parados else "")
             + (f". ACHADOS: {diagnostico['summary']}"
                if diagnostico["findings"] else ". Tudo dentro dos limites."))
    audit("relatorio_saude", {"achados": len(diagnostico["findings"]),
                              "saude": resumo["saude"]})
    return {"ok": True, "resumo": resumo, "findings": diagnostico["findings"],
            "text": texto, "limits": diagnostico["limits"]}


def history_report(limite: int = 15) -> Dict[str, Any]:
    """Historico de incidentes/alertas + ultimas acoes auditadas."""
    hist = _load_history()[-max(1, min(50, limite)):]
    aud = read_audit(limite=15)
    return {"ok": True,
            "incidentes": list(reversed(hist)),
            "auditoria": aud,
            "text": (f"{len(hist)} incidente(s) registrado(s); "
                     f"ultima acao: {aud[0]['evento'] if aud else 'nenhuma'}")}


# --------------------------------------------------------------------------- #
# Avaliacao de stacks de observabilidade (briefing secao 8)                    #
# --------------------------------------------------------------------------- #

def evaluate_stack() -> Dict[str, Any]:
    """Verifica no servidor o que ja existe e o que faz sentido instalar."""
    rc, out, _ = run_ssh(
        "docker ps --format '{{.Names}}' | grep -iE "
        "'prometheus|grafana|cadvisor|wazuh|portainer|netdata' || echo NENHUM; "
        "command -v ufw >/dev/null && echo UFW_OK || echo SEM_UFW; "
        "command -v nft >/dev/null && echo NFT_OK || echo SEM_NFT; "
        "systemctl is-active fail2ban >/dev/null 2>&1 && echo FAIL2BAN_HOST "
        "|| echo SEM_FAIL2BAN_HOST; "
        "docker ps --format '{{.Names}}' | grep -i fail2ban || true",
        timeout=30)
    saida = out or ""
    itens = {
        "prometheus": "NENHUM" not in saida or "prometheus" in saida,
        "grafana": "grafana" in saida,
        "cadvisor": "cadvisor" in saida,
        "wazuh": "wazuh" in saida,
        "ufw": "UFW_OK" in saida,
        "nft": "NFT_OK" in saida,
        "fail2ban_host": "FAIL2BAN_HOST" in saida,
        "fail2ban_container": bool(re.search(r"fail2ban", saida)),
    }
    recomendacoes = [
        {"item": "cAdvisor",
         "veredito": "recomendado" if not itens["cadvisor"] else "ja_presente",
         "por_que": "metricas por container (CPU/RAM/redes) para o Guardian",
         "impacto": "baixo (1 container, sem alterar existentes)"},
        {"item": "Prometheus + Grafana",
         "veredito": "recomendado_futuro" if not itens["prometheus"] else "ja_presente",
         "por_que": "historico de metricas + dashboards (trend de CPU/disco)",
         "impacto": "medio (~1GB RAM; avaliar na maquina atual de 15GB)"},
        {"item": "Wazuh",
         "veredito": "opcional" if not itens["wazuh"] else "ja_presente",
         "por_que": "SIEM completo p/ deteccao de intrusao e correlacao de logs",
         "impacto": "alto (agente+manager; considerar apenas se houver "
                    "necessidade formal de SIEM)"},
        {"item": "Firewall (nftables/ufw)",
         "veredito": ("ja_usa_iptables" if itens["nft"] or True else "nao_presente"),
         "por_que": "ZimaOS ja usa iptables + restore-firewall.service "
                    "(regras persistidas em /DATA/AppData/iptables-backup.rules); "
                    "UFW nao instalado e NAO e necessario - manter iptables",
         "impacto": "nenhum (ja em uso pelo Guardian via block_ip)"},
    ]
    return {"ok": True, "estado": itens, "recomendacoes": recomendacoes,
            "detalhe": saida.strip()[:800]}


# --------------------------------------------------------------------------- #
# Dispatcher da tool                                                           #
# --------------------------------------------------------------------------- #

def handle_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Entrada unica da tool 'zima_guardian' (Tool Registry do JARVIS)."""
    action = str(args.get("action") or "health").strip().lower()
    try:
        if action == "health":
            return health_report()
        if action == "diagnose":
            return deep_diagnose(str(args.get("topico") or ""))
        if action == "monitor":
            return monitor_once()
        if action == "monitor_status":
            return monitor_status()
        if action == "report":
            return health_report()
        if action == "history":
            return history_report(int(args.get("limit") or 15))
        if action == "security":
            return security_report(int(args.get("hours") or 24))
        if action == "evaluate":
            return evaluate_stack()
        if action == "repair":
            return auto_repair(str(args.get("op") or args.get("repair_op") or ""),
                               str(args.get("target") or ""))
        if action == "docker":
            return docker_admin(str(args.get("op") or "list"),
                                str(args.get("target") or ""),
                                args.get("params") or args.get("args") or {},
                                str(args.get("approval_id") or ""))
        if action == "block_ip":
            return block_ip(str(args.get("ip") or ""),
                            str(args.get("motivo") or ""),
                            str(args.get("approval_id") or ""),
                            str(args.get("evidence") or ""))
        if action == "audit":
            return {"ok": True, "registros": read_audit(
                int(args.get("limit") or 30))}
        return {"ok": False,
                "error": f"acao desconhecida: {action}",
                "acoes": ["health", "diagnose", "monitor", "monitor_status",
                          "report", "history", "security", "evaluate",
                          "repair", "docker", "block_ip", "audit"]}
    except Exception as e:
        logger.exception("[Guardian] acao %s falhou", action)
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
