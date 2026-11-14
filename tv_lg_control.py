"""
tv_lg_control.py — CONTROLE DA TV LG webOS do ambiente para o J.A.R.V.I.S.

Baseado no guia testado (C:/LGTV/CONTROLE_TV.md, 2026-11-13):

- LIGAR: Wake-on-LAN nativo em Python (magic packet p/ 3 destinos x 2 portas,
  bind na interface local correta) — mesma redundância do tv_control.js.
- DESLIGAR: SSAP (WebSocket porta 3000) com client-key pareado.
  * 1a vez: pareamento PROMPT — exige o Senhor apertar OK/PERMITIR no controle
    da TV em ate 5 min (loop em background salva a chave em ssap_key.json e
    desliga a TV na hora em que for confirmado).
  * Depois: turnOff direto com a chave salva (sem prompt, sem pareamento).
- VOLUME/MUTE, ABRIR APP (PurpleFlix etc.), LISTAR APPS: SSAP com a chave.
- STATUS: TV ligada? (porta SSAP responde) + chave de pareamento existe?

Armadilhas respeitadas do guia:
  - luna-send de power / systemctl / UPnP NAO funcionam nesta TV (webOS 4.5) —
    o caminho e SSAP pareado; nada de variantes luna.
  - webOS 4.5 (Chromium 53) limita o app, mas nao afeta este modulo (rede pura).

Configuracao por variaveis de ambiente (defaults = ambiente real):
  TV_LG_IP=192.168.3.9  TV_LG_MAC=78:dd:12:38:4f:8e  TV_LG_SSAAP_PORT=3000
  TV_LG_BIND_IP=192.168.3.50  TV_LG_KEY_FILE=C:/LGTV/ssap_key.json
  TV_LG_DEFAULT_APP=com.lgtv.purpleflix
"""

import json
import os
import socket
import struct
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

try:
    import websocket  # websocket-client (sincrono)
except Exception:  # pragma: no cover
    websocket = None

# --------------------------------------------------------------------------- #
# Configuração (lida a cada chamada => pode mudar por env sem restart)
# --------------------------------------------------------------------------- #

def _cfg() -> Dict[str, str]:
    return {
        "ip": os.environ.get("TV_LG_IP", "192.168.3.9"),
        "mac": os.environ.get("TV_LG_MAC", "78:dd:12:38:4f:8e"),
        "ssap_port": os.environ.get("TV_LG_SSAAP_PORT", "3000"),
        "bind_ip": os.environ.get("TV_LG_BIND_IP", "192.168.3.50"),
        "key_file": os.environ.get("TV_LG_KEY_FILE", r"C:\LGTV\ssap_key.json"),
        "default_app": os.environ.get("TV_LG_DEFAULT_APP", "com.lgtv.purpleflix"),
        "broadcast": os.environ.get("TV_LG_BROADCAST", "192.168.3.255"),
    }


APP_ID_REquiere = None  # marcador de intento; apps validados na TV

SSAP_MANIFEST = {
    "manifestVersion": 1,
    "appVersion": "1.0",
    "signed": {
        "created": "20261108",
        "appId": "com.antigravity.remote",
        "vendorId": "antigravity",
        "localizedAppNames": {"": "Antigravity Remote"},
        "permissions": [
            "CONTROL_POWER", "READ_INSTALLED_APPS", "CONTROL_AUDIO",
            "READ_INPUT_DEVICE_LIST", "READ_CURRENT_CHANNEL", "READ_RUNNING_APPS",
        ],
    },
}

# Estado do pareamento em background (uma unica instancia por vez)
_PAIR_LOCK = threading.Lock()
_PAIR_STATE: Dict[str, Any] = {"running": False, "started_at": 0.0,
                               "last_error": "", "confirmed": False}


# --------------------------------------------------------------------------- #
# LIGAR — Wake-on-LAN nativo (sem Node, mesma redundância do tv_control.js)
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
            "paired": bool(key), "can_power_off": bool(key),
            "pairing_running": bool(_PAIR_STATE.get("running")),
            "message": ("TV ligada e pareada: controle total." if on and key
                        else "TV ligada, SEM chave de pareamento: desligar exige "
                             "OK na TV (use action='off')." if on
                        else "TV desligada ou fora da rede." if not key
                        else "TV desligada (chave pareada salva: liga via WoL e "
                             "desliga sem prompt).")}


# --------------------------------------------------------------------------- #
# Cliente SSAP (websocket porta 3000) com a chave salva
# --------------------------------------------------------------------------- #

def _register_frame(client_key: str, pairing: str = "") -> Dict[str, Any]:
    payload: Dict[str, Any] = {"forcePairing": False, "manifest": SSAP_MANIFEST}
    if pairing:
        payload["pairingType"] = pairing
    payload["client-key"] = client_key or ""
    return {"type": "register", "id": f"reg_{uuid.uuid4().hex[:8]}", "payload": payload}


def _request_frame(uri: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"type": "request", "id": f"req_{uuid.uuid4().hex[:8]}",
            "uri": uri, "payload": payload or {}}


def _recv_json(ws, deadline: float) -> Optional[Dict[str, Any]]:
    """Recebe frames ate chegar um JSON valido.

    webOS envia 'earth' (texto puro) ao abrir o WebSocket ANTES de qualquer
    JSON — JSONDecodeError nele e normal e NAO e erro: so pule o frame.
    """
    while time.time() < deadline:
        try:
            raw = ws.recv()
        except Exception:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "replace")
        try:
            msg = json.loads(raw)
        except Exception:
            continue  # frame nao-JSON ('earth', ping) — ignora
        if isinstance(msg, dict):
            return msg
    return None


def _ssap_exchange(requests: List[Dict[str, Any]], use_prompt: bool = False,
                   timeout: float = 10.0) -> Dict[str, Any]:
    """Abre SSAP, registra (com chave salva, ou PROMPT se pareamento) e executa
    as requisicoes em sequencia. Retorna a ultima resposta + client-key se novo.
    """
    if websocket is None:
        return {"ok": False, "error": "websocket-client indisponivel"}
    c = _cfg()
    key = _load_key()
    url = f"ws://{c['ip']}:{c['ssap_port']}"
    try:
        ws = websocket.create_connection(url, timeout=timeout)
    except Exception as e:
        return {"ok": False, "error": f"TV inalcancavel ({e.__class__.__name__})",
                "tv_on": False}
    try:
        ws.send(json.dumps(_register_frame(key, "PROMPT" if use_prompt else "")))
        new_key = ""
        results: List[Dict[str, Any]] = []
        pending = list(requests)
        deadline = time.time() + timeout + 3
        sent_pending = False
        while time.time() < deadline:
            msg = _recv_json(ws, deadline)
            if msg is None:
                break
            mtype = msg.get("type", "")
            if mtype == "error":
                return {"ok": False,
                        "error": f"SSAP erro {msg.get('error')}: {msg.get('message', '')}"}
            if mtype == "registered":
                new_key = str(msg.get("payload", {}).get("client-key", "") or "")
                if use_prompt and not new_key:
                    return {"ok": False, "awaiting_user": True,
                            "error": "PROMPT enviado; aguardando OK na TV"}
                for req in pending:
                    try:
                        ws.send(json.dumps(req))
                    except Exception:
                        break
                sent_pending = True
                continue
            if mtype == "response" and sent_pending:
                results.append(msg.get("payload", {}))
                if pending and len(results) >= len(pending):
                    break
        last = results[-1] if results else {}
        return {"ok": True, "new_client_key": new_key, "responses": results,
                "last": last}
    finally:
        try:
            ws.close()
        except Exception:
            pass


def _paired_request(uri: str, payload: Optional[Dict[str, Any]] = None,
                    timeout: float = 8.0) -> Dict[str, Any]:
    """Requisicao SSAP usando a chave salva (sem prompt)."""
    if not _load_key():
        return {"ok": False, "paired": False,
                "error": "sem chave de pareamento (rode action='off' 1a vez com "
                         "o Senhor apertando OK na TV)"}
    return _ssap_exchange([_request_frame(uri, payload)], timeout=timeout)


# --------------------------------------------------------------------------- #
# DESLIGAR — pareamento PROMPT em background (humano confirma na TV)
# --------------------------------------------------------------------------- #

def _pair_loop(max_wait_s: float = 300.0, retry_s: float = 25.0) -> None:
    """Loop de pareamento: PROMPT a cada retry ate confirmar; salva a chave e
    desliga a TV imediatamente apos o registro (comportamento do ssap_client.js).
    """
    c = _cfg()
    url = f"ws://{c['ip']}:{c['ssap_port']}"
    deadline = time.time() + max_wait_s
    while time.time() < deadline and _PAIR_STATE.get("running"):
        if websocket is None:
            _PAIR_STATE["last_error"] = "websocket-client indisponivel"
            break
        try:
            ws = websocket.create_connection(url, timeout=retry_s + 5)
            confirmed = False
            try:
                ws.send(json.dumps(_register_frame("", "PROMPT")))
                # recebe ate um JSON valido ('earth' do webOS vem antes e e
                # texto puro - ignorar, NAO e erro de parse)
                msg = _recv_json(ws, time.time() + retry_s + 5)
                if msg is None:
                    _PAIR_STATE["last_error"] = "sem resposta JSON da TV (timeout)"
                elif msg.get("type") == "registered":
                    key = str(msg.get("payload", {}).get("client-key", "") or "")
                    if key:
                        with open(c["key_file"], "w", encoding="utf-8") as f:
                            json.dump({"clientKey": key}, f, indent=2)
                        ws.send(json.dumps(_request_frame("ssap://system/turnOff")))
                        _PAIR_STATE["confirmed"] = True
                        confirmed = True
                elif msg.get("type") == "error":
                    _PAIR_STATE["last_error"] = str(msg.get("message", "erro SSAP"))
            finally:
                try:
                    ws.close()
                except Exception:
                    pass
            if confirmed:
                break
        except Exception as e:
            _PAIR_STATE["last_error"] = f"{e.__class__.__name__}: {e}"
        time.sleep(retry_s)
    _PAIR_STATE["running"] = False


def turn_off() -> Dict[str, Any]:
    """Desliga a TV. Pareada => direto; senao inicia pareamento PROMPT em
    background (o Senhor precisa apertar OK/PERMITIR no controle da TV em ate
    5 min; ao confirmar, a TV desliga e a chave fica salva para sempre)."""
    if not is_on():
        return {"ok": False, "tv_on": False,
                "error": "TV desligada ou fora da rede (ligue primeiro com action='on')"}
    if _load_key():
        res = _paired_request("ssap://system/turnOff")
        if res.get("ok") and not res.get("error"):
            return {"ok": True, "message": "Comando de desligar enviado pela TV (SSAP)."}
        return {"ok": False, "error": res.get("error", "falha SSAP"),
                "hint": "chave pode ter expirado: rode action='pair'"}
    # 1a vez: pareamento precisa de humano na TV
    with _PAIR_LOCK:
        if _PAIR_STATE.get("running"):
            started = int(time.time() - _PAIR_STATE.get("started_at", time.time()))
            return {"ok": True, "pairing_started": True,
                    "message": f"Pareamento ja em andamento ha {started}s. OLHE PARA A "
                               f"TV e aperte OK/PERMITIR em 'Permitir Antigravity Remote?'."}
        _PAIR_STATE.update({"running": True, "started_at": time.time(),
                            "last_error": "", "confirmed": False})
        threading.Thread(target=_pair_loop, daemon=True,
                         name="JarvisSsapPair").start()
    return {"ok": True, "pairing_started": True,
            "message": "OLHE PARA A TV: aparecera 'Permitir Antigravity Remote?' - "
                       "aperte OK/PERMITIR no controle em ate 5 min. Ao confirmar, "
                       "a TV desliga sozinha e o JARVIS guarda a chave."}


def pair_status() -> Dict[str, Any]:
    return {"ok": True, **{k: _PAIR_STATE.get(k) for k in
                           ("running", "confirmed", "last_error", "started_at")},
            "paired": bool(_load_key()),
            "elapsed_s": int(time.time() - _PAIR_STATE["started_at"])
            if _PAIR_STATE.get("running") else 0}


# --------------------------------------------------------------------------- #
# Volume / mute / apps (SSAP pareado)
# --------------------------------------------------------------------------- #

def volume_up() -> Dict[str, Any]:
    return _paired_request("ssap://audio/volumeUp")


def volume_down() -> Dict[str, Any]:
    return _paired_request("ssap://audio/volumeDown")


def set_volume(level: int) -> Dict[str, Any]:
    level = max(0, min(100, int(level)))
    return _paired_request("ssap://audio/setVolume", {"volume": level})


def get_volume() -> Dict[str, Any]:
    return _paired_request("ssap://audio/getVolume")


def set_mute(muted: bool = True) -> Dict[str, Any]:
    return _paired_request("ssap://audio/setMute", {"mute": bool(muted)})


def launch_app(app_id: str = "") -> Dict[str, Any]:
    """Abre um app na TV (padrao: PurpleFlix). Formato testado no guia:
    ssap://system.launcher/open?target=<appId>."""
    c = _cfg()
    app_id = str(app_id or c["default_app"]).strip()
    uri = f"ssap://system.launcher/open?target={app_id}"
    res = _paired_request(uri)
    if res.get("ok"):
        res["app_id"] = app_id
        res["message"] = f"App {app_id} acionado na TV."
    return res


def list_apps() -> Dict[str, Any]:
    res = _paired_request("ssap://com.webos.applicationManager/listApps")
    if res.get("ok"):
        items = res.get("last", {}).get("items") or res.get("responses", [{}])[-1].get("items", [])
        apps = [{"id": a.get("id"), "title": a.get("title")} for a in items][:30]
        res["apps"] = apps
    return res


# --------------------------------------------------------------------------- #
# Ponte de ferramenta (mesma convencao de zima_guardian.handle_tool)
# --------------------------------------------------------------------------- #

def handle_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Executa 'tv_lg'. Acoes: status/on/off/pair_status/volume_up/volume_down/
    set_volume/get_volume/mute/unmute/launch/list_apps."""
    action = str(args.get("action", "status")).lower()

    if action == "status":
        return status()
    if action == "on":
        return turn_on()
    if action == "off":
        return turn_off()
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
            "error": (f"acao desconhecida '{action}' (status/on/off/pair_status/"
                      "volume_up/volume_down/set_volume/get_volume/mute/unmute/"
                      "launch/list_apps)")}
