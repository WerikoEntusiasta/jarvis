"""
tv_lg_control.py — CONTROLE DA TV LG webOS do ambiente para o J.A.R.V.I.S.

Reescrito em 2026-11-13 apos mapeamento empirico COMPLETO do firmware
(webOS 4.5/Chromium 53 — ver C:/LGTV/CONTROLE_TV.md):

Transporte:
  - SSAP (WebSocket porta 3000): handshakes Python sao REJEITADOS pela TV
    (frame vazio + close) — todo SSAP agora passa por scripts Node
    (ssap_bridge.js / ssap_pair_bridge.js via subprocess).
  - Luna pub bus: via novacom (dev mode, :9922) com ares-novacom.js chamado
    do Node com argv exato (nova_luna.js) — Power do PowerShell mangava JSON.

Superficie REAL do firmware (testado):
  - LIGAR: Wake-on-LAN nativo Python (magic packet 3 destinos x 2 portas).
  - ABRIR APP: ssap://system.launcher/open payload {"id": app_id} — funciona
    com o manifest assinado LG (chave de pareamento); `?target=` e 404.
  - VOLUME/GET: luna://com.webos.audio volumeUp/volumeDown/getVolume — funciona
    no pub bus (grupo audio do usuario prisoner); SSAP audio e 401.
  - MUDO: setVolume aceita APENAS {"volume":N} (sem mute no schema) — mute
    funcional = guardar volume atual e setar 0; unmute restaura.
  - DESLIGAR: BLOQUEADO POR FIRMWARE. SSAP turnOff/turnOffScreen = 401 em
    qualquer manifest (inclui assinatura oficial LG); luna pub bus nega
    categoria /power; sleepTimer via preferences escreve mas nao surte efeito
    (espelho da UI); settingsservice negado; escalacao root fechada (nosuid).
    A acao 'off' tenta SSAP turnOff (caso firmware futuro libere) e retorna
    ok=False honesto com alternativas (controle fisico / timer da TV).
  - Pareamento 1a vez: register PROMPT (Node) — o Senhor aperta OK na TV e a
    chave fica salva em C:/LGTV/ssap_key.json para sempre.

Config por variaveis de ambiente (defaults = ambiente real):
  TV_LG_IP=192.168.3.9  TV_LG_MAC=78:dd:12:38:4f:8e  TV_LG_SSAP_PORT=3000
  TV_LG_BIND_IP=192.168.3.50  TV_LG_KEY_FILE=C:/LGTV/ssap_key.json
  TV_LG_DEFAULT_APP=com.lgtv.purpleflix  TV_LG_BROADCAST=192.168.3.255
  TV_LG_NODE_DIR=C:/LGTV   TV_LG_NODE=node
  TV_LG_OFF_MINUTES=10 (sleep timer ao desligar)
"""

import json
import os
import shutil
import socket
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional

# --------------------------------------------------------------------------- #
# Configuração (lida a cada chamada => pode mudar por env sem restart)
# --------------------------------------------------------------------------- #

def _cfg() -> Dict[str, str]:
    return {
        "ip": os.environ.get("TV_LG_IP", "192.168.3.9"),
        "mac": os.environ.get("TV_LG_MAC", "78:dd:12:38:4f:8e"),
        "ssap_port": os.environ.get("TV_LG_SSAP_PORT", "3000"),
        "bind_ip": os.environ.get("TV_LG_BIND_IP", "192.168.3.50"),
        "key_file": os.environ.get("TV_LG_KEY_FILE", r"C:\LGTV\ssap_key.json"),
        "default_app": os.environ.get("TV_LG_DEFAULT_APP", "com.lgtv.purpleflix"),
        "broadcast": os.environ.get("TV_LG_BROADCAST", "192.168.3.255"),
        "node_dir": os.environ.get("TV_LG_NODE_DIR", r"C:\LGTV"),
        "node": os.environ.get("TV_LG_NODE", "node"),
        "off_minutes": os.environ.get("TV_LG_OFF_MINUTES", "10"),
    }


def _node_script(name: str) -> Optional[str]:
    """Caminho absoluto de um script Node de ponte; None se node/nao existe."""
    node = _cfg()["node"]
    path = os.path.join(_cfg()["node_dir"], name)
    if shutil.which(node) and os.path.isfile(path):
        return path
    return None


# Estado do pareamento em background (uma unica instancia por vez)
_PAIR_LOCK = threading.Lock()
_PAIR_STATE: Dict[str, Any] = {"running": False, "started_at": 0.0,
                               "last_error": "", "confirmed": False}


# --------------------------------------------------------------------------- #
# LIGAR — Wake-on-LAN nativo (mesma redundância do tv_control.js)
# --------------------------------------------------------------------------- #

def _magic_packet(mac: str) -> bytes:
    """Magic packet: 6x FF + 16x MAC. Aceita ':', '-' ou nada como separador."""
    mac = mac.replace(":", "").replace("-", "").strip().lower()
    if len(mac) != 12:
        raise ValueError(f"MAC invalido: {mac!r}")
    return b"\xff" * 6 + bytes.fromhex(mac) * 16


def _send_wol(mac: str, bind_ip: str, targets: List[str], ports: List[int]) -> int:
    """Envia o magic packet para todos os destinos/portas; retorna nº de envios."""
    pkt = _magic_packet(mac)
    sent = 0
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            s.bind((bind_ip, 0))
        except Exception:
            pass  # interface pode ter mudado; deixa o SO escolher
        s.settimeout(1.0)
        for target in targets:
            for port in ports:
                try:
                    s.sendto(pkt, (target, port))
                    sent += 1
                except Exception:
                    continue
    return sent


def turn_on() -> Dict[str, Any]:
    """Liga a TV via WoL e confirma subindo (porta SSAP responde)."""
    c = _cfg()
    if is_on():
        return {"ok": True, "already_on": True,
                "message": "TV ja esta ligada."}
    targets = ["255.255.255.255", c["broadcast"], c["ip"]]
    sent = _send_wol(c["mac"], c["bind_ip"], targets, [9, 7])
    # Confirma em ate ~20s (Quick Start+ sobe rapido)
    deadline = time.time() + 20
    while time.time() < deadline:
        time.sleep(2)
        if is_on():
            return {"ok": True, "sent": sent,
                    "message": "TV ligada (confirmada na rede)."}
    return {"ok": False, "sent": sent,
            "error": "TV nao respondeu apos WoL (aguarde Quick Start+ e tente de novo)"}


def is_on(timeout: float = 2.0) -> bool:
    """TV ligada? Porta SSAP aberta = webOS no ar (mais confiavel que ping)."""
    c = _cfg()
    try:
        with socket.create_connection((c["ip"], int(c["ssap_port"])), timeout=timeout):
            return True
    except Exception:
        return False


def _load_key() -> str:
    try:
        with open(_cfg()["key_file"], "r", encoding="utf-8") as f:
            return str(json.load(f).get("clientKey", "") or "")
    except Exception:
        return ""


def status() -> Dict[str, Any]:
    c = _cfg()
    on = is_on()
    key = _load_key()
    return {"ok": True, "tv_on": on, "ip": c["ip"], "mac": c["mac"],
            "paired": bool(key), "can_power_off": False,
            "power_blocked": True,
            "pairing_running": bool(_PAIR_STATE.get("running")),
            "off_method": "firmware_blocked",
            "message": ("TV ligada e pareada: controle total." if on and key
                        else "TV ligada, SEM chave: abrir app pede pareamento "
                             "(OK na TV)." if on
                        else "TV desligada ou fora da rede.")}


# --------------------------------------------------------------------------- #
# SSAP via ponte Node (handshake Python e rejeitado pela TV)
# --------------------------------------------------------------------------- #

def _ssap_bridge(requests: List[Dict[str, Any]], timeout: float = 10.0) -> Dict[str, Any]:
    """Executa requisicoes SSAP via ssap_bridge.js (subprocess, stdin JSON)."""
    c = _cfg()
    script = _node_script("ssap_bridge.js")
    if script is None:
        return {"ok": False, "error": "ponte Node indisponivel (node/C:/LGTV)"}
    entrada = {"ip": c["ip"], "port": int(c["ssap_port"]), "key": _load_key(),
               "requests": requests, "timeout_ms": int(timeout * 1000)}
    try:
        proc = subprocess.run([c["node"], script], input=json.dumps(entrada),
                              capture_output=True, text=True, encoding="utf-8",
                              timeout=timeout + 15)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout da ponte SSAP"}
    out = (proc.stdout or "").strip()
    if not out:
        return {"ok": False, "error": f"ponte SSAP sem saida (rc={proc.returncode})"
                + (f": {proc.stderr.strip()[:120]}" if proc.stderr else "")}
    try:
        return json.loads(out.splitlines()[-1])
    except Exception as e:
        return {"ok": False, "error": f"ponte SSAP invalida: {e}: {out[:120]}"}


def _launch_ssap(app_id: str, timeout: float = 10.0) -> Dict[str, Any]:
    """Abre app: ssap://system.launcher/open payload {id} (formato que funciona)."""
    res = _ssap_bridge([{"uri": "ssap://system.launcher/open",
                         "payload": {"id": app_id}}], timeout=timeout)
    if res.get("ok"):
        res["app_id"] = app_id
        res["message"] = f"App {app_id} acionado na TV."
    return res


# --------------------------------------------------------------------------- #
# Luna pub bus via nova_luna.js (volume; sleep timer p/ desligar)
# --------------------------------------------------------------------------- #

def _luna(method: str, payload: str, timeout: float = 30.0) -> Dict[str, Any]:
    """Chama luna-send-pub na TV via nova_luna.js. Ex: _luna('com.webos.audio/getVolume', '{}')."""
    c = _cfg()
    script = _node_script("nova_luna.js")
    if script is None:
        return {"ok": False, "error": "ponte luna indisponivel (node/C:/LGTV)"}
    try:
        proc = subprocess.run([c["node"], script, method, payload],
                              capture_output=True, text=True, encoding="utf-8",
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout da ponte luna"}
    out = (proc.stdout or "").strip()
    if not out:
        return {"ok": False, "error": f"luna sem resposta (rc={proc.returncode})"
                + (f": {proc.stderr.strip()[:120]}" if proc.stderr else "")}
    try:
        data = json.loads(out.splitlines()[-1])
    except Exception as e:
        return {"ok": False, "error": f"luna invalida: {e}: {out[:120]}"}
    ok = bool(data.get("returnValue", True))
    if not ok:
        return {"ok": False, "error": str(data.get("errorText", "erro luna")),
                "raw": data}
    return {"ok": True, "data": data}


# --- volume ---------------------------------------------------------------- #

def get_volume() -> Dict[str, Any]:
    res = _luna("com.webos.audio/getVolume", "{}")
    if res.get("ok"):
        d = res.pop("data")
        res.update({"volume": int(d.get("volume", 0)),
                    "muted": bool(d.get("muted", False)),
                    "message": f"Volume da TV: {d.get('volume', 0)}."})
    return res


def volume_up() -> Dict[str, Any]:
    res = _luna("com.webos.audio/volumeUp", "{}")
    if res.get("ok"):
        res["message"] = "Volume +1."
    return res


def volume_down() -> Dict[str, Any]:
    res = _luna("com.webos.audio/volumeDown", "{}")
    if res.get("ok"):
        res["message"] = "Volume -1."
    return res


def set_volume(level: int) -> Dict[str, Any]:
    level = max(0, min(100, int(level)))
    res = _luna("com.webos.audio/setVolume", json.dumps({"volume": level}))
    if res.get("ok"):
        res["volume"] = level
        res["message"] = f"Volume da TV: {level}."
    return res


# --- mute funcional (schema do setVolume nao aceita 'muted') ---------------- #

_MUTE_FILE = os.path.join(os.environ.get("TEMP", os.environ.get("TMP", "/tmp")),
                          "jarvis_tv_mute.json")


def set_mute(muted: bool = True) -> Dict[str, Any]:
    """Mudo funcional: guarda o volume e seta 0; unmute restaura o guardado."""
    vol = get_volume()
    atual = int(vol.get("volume", 20)) if vol.get("ok") else 20
    if muted:
        if atual == 0:
            return {"ok": True, "muted": True, "message": "TV ja esta muda."}
        try:
            with open(_MUTE_FILE, "w", encoding="utf-8") as f:
                json.dump({"volume": atual}, f)
        except Exception:
            pass
        res = set_volume(0)
        if res.get("ok"):
            res["muted"] = True
            res["message"] = "TV no mudo (volume 0; unmute restaura)."
        return res
    try:
        with open(_MUTE_FILE, "r", encoding="utf-8") as f:
            restaurar = int(json.load(f).get("volume", 20))
    except Exception:
        restaurar = 20 if atual == 0 else atual
    res = set_volume(restaurar if atual == 0 else atual)
    if res.get("ok"):
        res["muted"] = False
        res["message"] = f"Som da TV restaurado (volume {res.get('volume')})."
    return res


# --------------------------------------------------------------------------- #
# DESLIGAR — firmware BLOQUEIA power a terceiros (mapeado exaustivamente)
# --------------------------------------------------------------------------- #

def turn_off() -> Dict[str, Any]:
    """Desliga a TV — ATENCAO: o firmware webOS 4.5 desta TV NEGA power a
    terceiros em todas as vias testadas (13/11/2026):
      - SSAP system/turnOff e tvpower/turnOffScreen: 401 em TODO manifest
        (inclui assinatura oficial de teste da LG e identidade com.lge.hosen).
      - luna pub bus: categoria /power negada ao usuario prisoner.
      - sleepTimer via com.palm.systemservice/preferences: escreve e le de
        volta, mas NAO tem efeito (espelho da UI; quem agenda e negado).
      - com.webos.settingsservice: Access denied.
      - Escalacao root: luna-send e 0700 root; SUID desativado (nosuid);
        login/busybox.suid inuteis; SSH root negado.
    A acao tenta o SSAP turnOff (por se um firmware futuro liberar) e, se
    negado, retorna ok=False com instrucao honesta ao Senhor.
    """
    if not is_on():
        return {"ok": False, "tv_on": False,
                "error": "TV desligada ou fora da rede (ligue primeiro com action='on')"}
    res = _ssap_bridge([{"uri": "ssap://system/turnOff"}], timeout=8.0)
    if res.get("ok"):
        return {"ok": True, "message": "Comando de desligar aceito pela TV (SSAP)."}
    return {"ok": False, "firmware_blocked": True,
            "error": "O firmware da TV bloqueia desligar a terceiros (401 power).",
            "alternatives": [
                "Botao fisico do controle remoto",
                "Sleep timer pela propria TV: Configuracoes > Geral > "
                "Sistema > Timer > Sleep",
            ],
            "detail": res.get("error", "401")}


def power_blocked_info() -> Dict[str, Any]:
    """Diagnostico consolidado do bloqueio de power (para o HUD/voz)."""
    return {"ok": True, "blocked": True,
            "tested": ["ssap://system/turnOff (401 todos os manifests)",
                       "ssap://com.webos.service.tvpower/power/turnOffScreen (401)",
                       "luna pub bus categoria /power (denied ao prisoner)",
                       "sleepTimer via preferences (escrito mas sem efeito)",
                       "settingsservice (Access denied)",
                       "escalacao root (luna-send 0700; nosuid; ssh root negado)"],
            "working": ["ligar via WoL", "abrir apps via SSAP launcher",
                        "volume via luna pub bus", "mute funcional via setVolume 0"]}


# --------------------------------------------------------------------------- #
# Pareamento 1a vez — PROMPT via Node (o Senhor aperta OK na TV)
# --------------------------------------------------------------------------- #

def _pair_loop(max_wait_s: float = 300.0) -> None:
    """Pareamento em background: node ssap_pair_bridge.js (PROMPT); salva a chave."""
    c = _cfg()
    script = _node_script("ssap_pair_bridge.js")
    if script is None:
        _PAIR_STATE["last_error"] = "ponte Node indisponivel (node/C:/LGTV)"
        _PAIR_STATE["running"] = False
        return
    entrada = json.dumps({"ip": c["ip"], "port": int(c["ssap_port"]),
                          "wait_ms": int(max_wait_s * 1000)})
    try:
        proc = subprocess.run([c["node"], script, entrada],
                              capture_output=True, text=True, encoding="utf-8",
                              timeout=max_wait_s + 30)
        out = (proc.stdout or "").strip()
        if out:
            data = json.loads(out.splitlines()[-1])
            if data.get("ok") and data.get("key"):
                with open(c["key_file"], "w", encoding="utf-8") as f:
                    json.dump({"clientKey": data["key"]}, f, indent=2)
                _PAIR_STATE["confirmed"] = True
            else:
                _PAIR_STATE["last_error"] = str(data.get("error", "pareamento falhou"))
        else:
            _PAIR_STATE["last_error"] = (f"ponte de pareamento sem saida "
                                         f"(rc={proc.returncode})")
    except Exception as e:
        _PAIR_STATE["last_error"] = f"{e.__class__.__name__}: {e}"
    _PAIR_STATE["running"] = False


def start_pairing() -> Dict[str, Any]:
    """Inicia pareamento PROMPT em background (aparece 'Permitir' na TV)."""
    with _PAIR_LOCK:
        if _PAIR_STATE.get("running"):
            started = int(time.time() - _PAIR_STATE.get("started_at", time.time()))
            return {"ok": True, "pairing_started": True,
                    "message": f"Pareamento ja em andamento ha {started}s. "
                               f"OLHE PARA A TV e aperte OK/PERMITIR."}
        _PAIR_STATE.update({"running": True, "started_at": time.time(),
                            "last_error": "", "confirmed": False})
        threading.Thread(target=_pair_loop, daemon=True,
                         name="JarvisSsapPair").start()
    return {"ok": True, "pairing_started": True,
            "message": "OLHE PARA A TV: aparecera 'Permitir LG Remote App?' - "
                       "aperte OK/PERMITIR no controle em ate 5 min. Ao confirmar, "
                       "o JARVIS guarda a chave."}


def pair_status() -> Dict[str, Any]:
    return {"ok": True, **{k: _PAIR_STATE.get(k) for k in
                           ("running", "confirmed", "last_error", "started_at")},
            "paired": bool(_load_key()),
            "elapsed_s": int(time.time() - _PAIR_STATE["started_at"])
            if _PAIR_STATE.get("running") else 0}


# --------------------------------------------------------------------------- #
# Apps
# --------------------------------------------------------------------------- #

def launch_app(app_id: str = "") -> Dict[str, Any]:
    """Abre um app na TV (padrao: PurpleFlix) — launcher com a chave pareada."""
    c = _cfg()
    app_id = str(app_id or c["default_app"]).strip()
    if not _load_key():
        res = {"ok": False, "paired": False,
               "error": "sem chave de pareamento: rode action='pair' e aperte OK na TV"}
        return res
    return _launch_ssap(app_id)


def list_apps() -> Dict[str, Any]:
    """Lista apps instalados (pode ser negado pelo firmware — 401)."""
    res = _ssap_bridge([{"uri": "ssap://com.webos.applicationManager/listApps"}])
    if res.get("ok"):
        last = res.get("last", {})
        items = last.get("items") or []
        res["apps"] = [{"id": a.get("id"), "title": a.get("title")}
                       for a in items][:30]
        if not items:
            res["ok"] = False
            res["error"] = res.get("error") or "TV negou listApps (401)"
    return res


# --------------------------------------------------------------------------- #
# Ponte de ferramenta (mesma convencao de zima_guardian.handle_tool)
# --------------------------------------------------------------------------- #

def handle_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Executa 'tv_lg'. Acoes: status/on/off/power_info/pair/pair_status/
    volume_up/volume_down/set_volume/get_volume/mute/unmute/launch/list_apps."""
    action = str(args.get("action", "status")).lower()

    if action == "status":
        return status()
    if action == "on":
        return turn_on()
    if action == "off":
        return turn_off()
    if action == "power_info":
        return power_blocked_info()
    if action == "pair":
        return start_pairing()
    if action == "pair_status":
        return pair_status()
    if action == "volume_up":
        return volume_up()
    if action == "volume_down":
        return volume_down()
    if action == "set_volume":
        return set_volume(int(args.get("level", 20)))
    if action == "get_volume":
        return get_volume()
    if action == "mute":
        return set_mute(True)
    if action == "unmute":
        return set_mute(False)
    if action == "launch":
        return launch_app(str(args.get("app_id", "")))
    if action == "list_apps":
        return list_apps()
    return {"ok": False,
            "error": (f"acao desconhecida '{action}' (status/on/off/power_info/pair/"
                      "pair_status/volume_up/volume_down/set_volume/get_volume/"
                      "mute/unmute/launch/list_apps)")}
