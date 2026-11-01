"""
J.A.R.V.I.S. Tuya Lighting Service (LAN v3.4 + Tuya OpenAPI Direct)
Padrão Permanente de Engenharia de Software Sênior

Controla de forma 100% independente os interruptores/lâmpadas Tuya do ecossistema
("Setup" eb36293864e8ca3484qifm e "Quarto werik" eb8b0726824352aae25fgl),
operando tanto via TCP v3.4 direto na LAN quanto via Tuya OpenAPI v1.0 HMAC-SHA256
com cache de token em memória (contornando isolamento ARP entre Ethernet cabeada e Wi-Fi 2.4GHz).
"""

import os
import re
import json
import time
import uuid
import socket
import struct
import hmac
import hashlib
import logging
import threading
import unicodedata
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, List, Optional

try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
except ImportError:
    Cipher = None

try:
    import tinytuya
except ImportError:
    tinytuya = None

logger = logging.getLogger("TuyaService")

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "tuya_devices.json")
GROUPS_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "tuya_groups.json")

# Hub central (painel ZimaOS) = fonte da verdade de nomes e grupos. O Windows sincroniza
# periodicamente, mantendo cópia local para operar offline (autonomia do HUD Windows).
HUB_URL = os.environ.get("JARVIS_HUB_URL", "http://45.167.187.80:8095").rstrip("/")  # router :8095 expõe /api/devices/registry (somente leitura)
HUB_SYNC_TTL = 60.0

# Palavras que significam "todos os dispositivos"
ALL_KEYWORDS = {
    "all", "tudo", "todas", "todos", "todas as luzes", "todas as lampadas", "ambas", "ambos",
    "casa toda", "luz", "luzes", "lampada", "lampadas", "iluminacao", "",
}


def _norm(text: str) -> str:
    """Normaliza texto: minúsculas, sem acentos, espaços colapsados."""
    t = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode("ascii")
    return " ".join(t.lower().replace("_", " ").replace("-", " ").split())

TUYA_API_REGION = os.environ.get("TUYA_API_REGION", "us")
TUYA_API_KEY = os.environ.get("TUYA_API_KEY", "ckavrpcrr8qhwfy3ku4s")
TUYA_API_SECRET = os.environ.get("TUYA_API_SECRET", "8478c589465643f7bf2ea5a6a825e886")
TUYA_OPENAPI_BASE = "https://openapi.tuyaus.com"

DEFAULT_DEVICES = [
    {
        "id": "setup",
        "name": "Setup",
        "device_id": "eb36293864e8ca3484qifm",
        "ip": "192.168.10.20",
        "mac": "38:2c:e5:47:a5:6f",
        "local_key": "3M$VFV6sEREkgS0H",
        "version": 3.4,
        "type": "outlet",
    },
    {
        "id": "quarto",
        "name": "Quarto werik",
        "device_id": "eb8b0726824352aae25fgl",
        "ip": "192.168.10.24",
        "mac": "38:2c:e5:47:4f:54",
        "local_key": "a92~t@$Gv7j9=|'5",
        "version": 3.4,
        "type": "outlet",
    },
]


class _TuyaOpenAPIClient:
    """Cliente Tuya OpenAPI v1.0 HMAC-SHA256 direto com cache de access_token."""

    def __init__(self, client_id: str, secret: str, base_url: str = TUYA_OPENAPI_BASE):
        self.client_id = client_id
        self.secret = secret.encode("utf-8")
        self.base_url = base_url.rstrip("/")
        self._access_token: Optional[str] = None
        self._token_expire_at: float = 0.0

    def _sign(self, method: str, path: str, body_bytes: bytes, access_token: str = "") -> Dict[str, str]:
        t = str(int(time.time() * 1000))
        nonce = uuid.uuid4().hex
        content_sha256 = hashlib.sha256(body_bytes).hexdigest()
        string_to_sign = f"{method.upper()}\n{content_sha256}\n\n{path}"
        sign_str = self.client_id + access_token + t + nonce + string_to_sign
        sig = hmac.new(self.secret, sign_str.encode("utf-8"), hashlib.sha256).hexdigest().upper()
        headers = {
            "client_id": self.client_id,
            "sign": sig,
            "t": t,
            "sign_method": "HMAC-SHA256",
            "nonce": nonce,
            "Content-Type": "application/json",
        }
        if access_token:
            headers["access_token"] = access_token
        return headers

    def _get_token(self, force: bool = False) -> Optional[str]:
        now = time.time()
        if not force and self._access_token and now < self._token_expire_at:
            return self._access_token
        path = "/v1.0/token?grant_type=1"
        headers = self._sign("GET", path, b"")
        req = urllib.request.Request(self.base_url + path, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("success") and data.get("result"):
            res = data["result"]
            self._access_token = res["access_token"]
            self._token_expire_at = now + float(res.get("expire_time", 7200)) - 120.0
            return self._access_token
        return None

    def send_switch(self, device_id: str, state: bool) -> Dict[str, Any]:
        body_bytes = json.dumps(
            {"commands": [{"code": "switch_1", "value": bool(state)}]},
            separators=(",", ":"),
        ).encode("utf-8")
        path = f"/v1.0/iot-03/devices/{device_id}/commands"
        for force_tok in (False, True):
            try:
                token = self._get_token(force=force_tok)
                if not token:
                    continue
                headers = self._sign("POST", path, body_bytes, access_token=token)
                req = urllib.request.Request(
                    self.base_url + path, data=body_bytes, headers=headers, method="POST"
                )
                with urllib.request.urlopen(req, timeout=4.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                if data.get("success"):
                    return {"success": True, "is_on": bool(state), "device_id": device_id, "mode": "openapi"}
                # Se token expirou (code 1010), renova na 2a iteracao
                if data.get("code") == 1010 and not force_tok:
                    continue
                return {"success": False, "error": str(data)}
            except Exception as e:
                if force_tok:
                    return {"success": False, "error": str(e)}
        return {"success": False, "error": "Falha ao autenticar na Tuya OpenAPI"}

    def get_switch_status(self, device_id: str) -> Dict[str, Any]:
        path = f"/v1.0/iot-03/devices/{device_id}/status"
        try:
            token = self._get_token(force=False)
            if not token:
                return {"success": False, "error": "Sem token Tuya"}
            headers = self._sign("GET", path, b"", access_token=token)
            req = urllib.request.Request(self.base_url + path, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if data.get("success") and isinstance(data.get("result"), list):
                for item in data["result"]:
                    if item.get("code") == "switch_1":
                        return {"success": True, "is_on": bool(item.get("value")), "device_id": device_id}
        except Exception as e:
            return {"success": False, "error": str(e)}
        return {"success": False, "error": "Status não retornado"}


_openapi_client = _TuyaOpenAPIClient(TUYA_API_KEY, TUYA_API_SECRET)


def _aes_ecb_encrypt(key: bytes, data: bytes, pad: bool = True) -> bytes:
    if pad:
        pad_len = 16 - (len(data) % 16)
        data = data + bytes([pad_len] * pad_len)
    cipher = Cipher(algorithms.AES(key), modes.ECB())
    enc = cipher.encryptor()
    return enc.update(data) + enc.finalize()


def _aes_ecb_decrypt(key: bytes, data: bytes) -> bytes:
    cipher = Cipher(algorithms.AES(key), modes.ECB())
    dec = cipher.decryptor()
    return dec.update(data) + dec.finalize()


def _pack_tuya34_packet(seqno: int, cmd: int, payload_enc: bytes, hmac_key: bytes) -> bytes:
    length = len(payload_enc) + 36
    header = struct.pack(">IIII", 0x000055AA, seqno, cmd, length) + payload_enc
    sig = hmac.new(hmac_key, header, hashlib.sha256).digest()
    return header + sig + struct.pack(">I", 0x0000AA55)


def _direct_tuya34_set(ip: str, local_key_str: str, state: bool, timeout: float = 0.28) -> Dict[str, Any]:
    """Tenta envio direto TCP v3.4 na LAN com timeout ultrarrápido (0.28s)."""
    if Cipher is None:
        return {"success": False, "error": "Cipher indisponível"}
    key = local_key_str.encode("utf-8")
    s = None
    try:
        s = socket.create_connection((ip, 6668), timeout=timeout)
        s.settimeout(0.8)
        local_nonce = os.urandom(16)
        step1_enc = _aes_ecb_encrypt(key, local_nonce, pad=True)
        s.sendall(_pack_tuya34_packet(1, 3, step1_enc, key))

        resp = s.recv(256)
        if len(resp) < 120:
            raise RuntimeError(f"Handshake curto ({len(resp)} bytes)")

        dec = _aes_ecb_decrypt(key, resp[20:84])
        remote_nonce = dec[:16]

        rkey_hmac = hmac.new(key, remote_nonce, hashlib.sha256).digest()
        step3_enc = _aes_ecb_encrypt(key, rkey_hmac, pad=True)
        s.sendall(_pack_tuya34_packet(2, 5, step3_enc, key))

        xor_nonce = bytes(a ^ b for a, b in zip(local_nonce, remote_nonce))
        session_key = _aes_ecb_encrypt(key, xor_nonce, pad=False)

        payload_json = json.dumps(
            {"protocol": 5, "t": int(time.time()), "data": {"dps": {"1": bool(state)}}},
            separators=(",", ":"),
        ).encode("utf-8")
        ctrl_raw = b"3.4" + (b"\x00" * 12) + payload_json
        ctrl_enc = _aes_ecb_encrypt(session_key, ctrl_raw, pad=True)
        s.sendall(_pack_tuya34_packet(3, 13, ctrl_enc, session_key))
        try:
            s.settimeout(0.25)
            s.recv(256)
        except Exception:
            pass
        s.close()
        return {"success": True, "is_on": bool(state), "mode": "lan_34"}
    except Exception as e:
        if s:
            try:
                s.close()
            except Exception:
                pass
        return {"success": False, "error": str(e)}


class TuyaService:
    def __init__(self, config_path: str = CONFIG_PATH, groups_path: str = GROUPS_PATH):
        self.config_path = os.path.abspath(config_path)
        self.groups_path = os.path.abspath(groups_path)
        self._lock = threading.RLock()
        self.devices_config = self._load_config()
        self.groups = self._load_groups()
        self._last_known_state = False
        self._last_sync = 0.0
        self._syncing = False

    # ------------------------------------------------------------------ persistência
    def _load_config(self) -> List[Dict[str, Any]]:
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list) and len(data) >= 1:
                        return data
            except Exception as e:
                logger.error(f"Erro ao carregar tuya_devices.json: {e}")
        return [dict(d) for d in DEFAULT_DEVICES]

    def _load_groups(self) -> List[Dict[str, Any]]:
        if os.path.exists(self.groups_path):
            try:
                with open(self.groups_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return [g for g in data if isinstance(g, dict) and g.get("id")]
            except Exception as e:
                logger.error(f"Erro ao carregar tuya_groups.json: {e}")
        return []

    @staticmethod
    def _atomic_write(path: str, data: Any) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    def _save(self) -> None:
        self._atomic_write(self.config_path, self.devices_config)
        self._atomic_write(self.groups_path, self.groups)

    # ------------------------------------------------------------------ registro (nomes e grupos)
    @staticmethod
    def _slug(text: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", _norm(text)).strip("_") or uuid.uuid4().hex[:6]

    @staticmethod
    def _clean_aliases(aliases: Any) -> List[str]:
        if isinstance(aliases, str):
            aliases = aliases.split(",")
        out: List[str] = []
        for a in aliases or []:
            a = str(a).strip()
            if a and a not in out:
                out.append(a[:40])
        return out[:12]

    def _label_conflict(self, labels: List[str], ignore_device: str = "", ignore_group: str = "") -> Optional[str]:
        """Retorna o rótulo que já pertence a outro dispositivo/grupo (evita ambiguidade por voz)."""
        wanted = {_norm(x) for x in labels if x}
        for d in self.devices_config:
            if d["id"] == ignore_device:
                continue
            own = {_norm(d["id"]), _norm(d.get("name", ""))} | {_norm(a) for a in d.get("aliases", [])}
            hit = wanted & own
            if hit:
                return sorted(hit)[0]
        for g in self.groups:
            if g["id"] == ignore_group:
                continue
            own = {_norm(g["id"]), _norm(g.get("name", ""))} | {_norm(a) for a in g.get("aliases", [])}
            hit = wanted & own
            if hit:
                return sorted(hit)[0]
        reserved = wanted & {k for k in ALL_KEYWORDS if k}
        return sorted(reserved)[0] if reserved else None

    def registry(self) -> Dict[str, Any]:
        """Visão pública (sem segredos) de dispositivos e grupos."""
        with self._lock:
            devs = [
                {
                    "id": d["id"],
                    "name": d.get("name", d["id"]),
                    "aliases": list(d.get("aliases", [])),
                    "device_id": d.get("device_id", ""),
                    "type": d.get("type", "outlet"),
                }
                for d in self.devices_config
            ]
            grps = [
                {
                    "id": g["id"],
                    "name": g.get("name", g["id"]),
                    "aliases": list(g.get("aliases", [])),
                    "members": list(g.get("members", [])),
                }
                for g in self.groups
            ]
        return {"devices": devs, "groups": grps}

    def list_devices(self, with_status: bool = True) -> Dict[str, Any]:
        reg = self.registry()
        if with_status and reg["devices"]:
            def _st(d):
                r = _openapi_client.get_switch_status(d["device_id"])
                return r.get("is_on") if r.get("success") else None
            with ThreadPoolExecutor(max_workers=len(reg["devices"])) as ex:
                states = list(ex.map(_st, reg["devices"]))
            for d, st in zip(reg["devices"], states):
                d["is_on"] = st
        return {"success": True, **reg}

    def rename_device(self, dev_id: str, name: str, aliases: Any = None) -> Dict[str, Any]:
        name = (name or "").strip()[:40]
        if not name:
            return {"success": False, "error": "Nome não pode ser vazio."}
        with self._lock:
            dev = next((d for d in self.devices_config if d["id"] == dev_id), None)
            if not dev:
                return {"success": False, "error": f"Dispositivo '{dev_id}' não encontrado."}
            new_aliases = self._clean_aliases(aliases) if aliases is not None else list(dev.get("aliases", []))
            clash = self._label_conflict([name] + new_aliases, ignore_device=dev_id)
            if clash:
                return {"success": False, "error": f"O nome '{clash}' já está em uso por outro dispositivo/grupo."}
            dev["name"] = name
            dev["aliases"] = new_aliases
            self._save()
        return {"success": True, **self.registry()}

    def save_group(self, name: str, members: Any, aliases: Any = None, group_id: str = "") -> Dict[str, Any]:
        name = (name or "").strip()[:40]
        if not name:
            return {"success": False, "error": "Nome do grupo não pode ser vazio."}
        with self._lock:
            valid = {d["id"] for d in self.devices_config}
            members = [m for m in dict.fromkeys(members or []) if m in valid]
            if not members:
                return {"success": False, "error": "Selecione ao menos um dispositivo válido para o grupo."}
            gid = group_id or self._slug(name)
            existing = next((g for g in self.groups if g["id"] == gid), None)
            if not existing and gid in valid:
                gid = f"grupo_{gid}"
            al = self._clean_aliases(aliases)
            clash = self._label_conflict([name] + al, ignore_group=gid)
            if clash:
                return {"success": False, "error": f"O nome '{clash}' já está em uso por outro dispositivo/grupo."}
            group = {"id": gid, "name": name, "aliases": al, "members": members}
            if existing:
                existing.update(group)
            else:
                self.groups.append(group)
            self._save()
        return {"success": True, **self.registry()}

    def delete_group(self, group_id: str) -> Dict[str, Any]:
        with self._lock:
            before = len(self.groups)
            self.groups = [g for g in self.groups if g["id"] != group_id]
            if len(self.groups) == before:
                return {"success": False, "error": f"Grupo '{group_id}' não encontrado."}
            self._save()
        return {"success": True, **self.registry()}

    def apply_registry(self, reg: Dict[str, Any]) -> None:
        """Aplica nomes/aliases/grupos vindos do hub, preservando credenciais locais."""
        if not isinstance(reg, dict):
            return
        with self._lock:
            by_id = {d["id"]: d for d in reg.get("devices", []) if isinstance(d, dict) and d.get("id")}
            for d in self.devices_config:
                src = by_id.get(d["id"])
                if src:
                    d["name"] = src.get("name", d.get("name"))
                    d["aliases"] = self._clean_aliases(src.get("aliases", []))
            valid = {d["id"] for d in self.devices_config}
            groups = []
            for g in reg.get("groups", []):
                if isinstance(g, dict) and g.get("id"):
                    mem = [m for m in g.get("members", []) if m in valid]
                    if mem:
                        groups.append({"id": g["id"], "name": g.get("name", g["id"]),
                                       "aliases": self._clean_aliases(g.get("aliases", [])), "members": mem})
            self.groups = groups
            self._save()

    def sync_from_hub(self, force: bool = False) -> bool:
        """Windows: puxa nomes/grupos do painel ZimaOS (timeout curto; falha silenciosa registrada em log)."""
        if os.name != "nt" and not force:
            return False
        try:
            req = urllib.request.Request(f"{HUB_URL}/api/devices/registry", headers={"X-Jarvis-Client": "desktop_windows"})
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if data.get("success"):
                self.apply_registry(data)
                self._last_sync = time.time()
                return True
        except Exception as e:
            logger.warning(f"[TUYA] Sync do hub indisponível, usando registro local: {e}")
            self._last_sync = time.time()
        return False

    def _maybe_sync(self) -> None:
        if os.name != "nt" or self._syncing or time.time() - self._last_sync < HUB_SYNC_TTL:
            return
        self._syncing = True

        def _run():
            try:
                self.sync_from_hub()
            finally:
                self._syncing = False

        threading.Thread(target=_run, daemon=True, name="TuyaHubSync").start()

    # ------------------------------------------------------------------ resolução de alvos
    def resolve_target(self, target: str) -> Dict[str, Any]:
        """Resolve 'lâmpada x', 'quarto', 'todas' etc. para dispositivos. Nunca cai em 'todos' por engano."""
        self._maybe_sync()
        raw = (target or "").strip()
        t = _norm(raw)
        with self._lock:
            devices = list(self.devices_config)
            groups = list(self.groups)
        if t in ALL_KEYWORDS:
            return {"devices": devices, "label": "todos os dispositivos", "kind": "all"}
        for g in groups:
            if t in {_norm(g["id"]), _norm(g.get("name", ""))} | {_norm(a) for a in g.get("aliases", [])}:
                mem = [d for d in devices if d["id"] in g.get("members", [])]
                if mem:
                    return {"devices": mem, "label": f"grupo {g.get('name', g['id'])}", "kind": "group"}
        exact = [
            d for d in devices
            if t in {_norm(d["id"]), _norm(d.get("device_id", "")), _norm(d.get("name", ""))}
            | {_norm(a) for a in d.get("aliases", [])}
        ]
        if exact:
            return {"devices": exact[:1], "label": exact[0].get("name", exact[0]["id"]), "kind": "device"}
        # Correspondência parcial (ex.: "luz do quarto" contém "quarto")
        padded = f" {t} "
        for g in groups:
            names = [_norm(g.get("name", ""))] + [_norm(a) for a in g.get("aliases", [])]
            if any(n and f" {n} " in padded for n in names):
                mem = [d for d in devices if d["id"] in g.get("members", [])]
                if mem:
                    return {"devices": mem, "label": f"grupo {g.get('name', g['id'])}", "kind": "group"}
        partial = []
        for d in devices:
            names = [_norm(d["id"]), _norm(d.get("name", ""))] + [_norm(a) for a in d.get("aliases", [])]
            if any(n and f" {n} " in padded for n in names):
                partial.append(d)
        if len(partial) == 1:
            return {"devices": partial, "label": partial[0].get("name", partial[0]["id"]), "kind": "device"}
        return {"devices": [], "label": raw, "kind": "none"}

    def _resolve_targets(self, target: str) -> List[Dict[str, Any]]:
        return self.resolve_target(target)["devices"]

    def _set_single_device(self, dev: Dict[str, Any], state: bool) -> Dict[str, Any]:
        # 1. Tuya OpenAPI v1.0 HMAC-SHA256 direto (~0.4s com token em cache, contorna isolamento ARP Ethernet->Wi-Fi)
        cloud_res = _openapi_client.send_switch(dev["device_id"], state)
        if cloud_res.get("success"):
            return cloud_res
        # 2. Fallback LAN v3.4 direto (caso sem internet)
        lan_res = _direct_tuya34_set(dev["ip"], dev["local_key"], state, timeout=0.5)
        if lan_res.get("success"):
            return lan_res
        # 3. Fallback tinytuya.Cloud se disponível
        if tinytuya is not None:
            try:
                c = tinytuya.Cloud(apiRegion=TUYA_API_REGION, apiKey=TUYA_API_KEY, apiSecret=TUYA_API_SECRET)
                r = c.sendcommand(dev["device_id"], {"commands": [{"code": "switch_1", "value": bool(state)}]})
                if isinstance(r, dict) and r.get("success"):
                    return {"success": True, "is_on": bool(state), "device_id": dev["device_id"], "mode": "tinytuya_cloud"}
            except Exception as e:
                return {"success": False, "error": str(e)}
        return cloud_res

    def get_status(self, target: str = "all") -> Dict[str, Any]:
        """Consulta o status atual (ligado/desligado) do dispositivo."""
        devs = self._resolve_targets(target)
        if not devs:
            return {"success": False, "error": f"Dispositivo ou grupo '{target}' não encontrado."}
        first = devs[0]
        st = _openapi_client.get_switch_status(first["device_id"])
        if st.get("success"):
            self._last_known_state = bool(st["is_on"])
            return st
        return {
            "success": True,
            "is_on": self._last_known_state,
            "device_id": first["id"],
            "cached": True,
        }

    def turn_on(self, target: str = "all") -> Dict[str, Any]:
        """Liga a(s) lâmpada(s) em paralelo."""
        res_t = self.resolve_target(target)
        devs = res_t["devices"]
        if not devs:
            return {"success": False, "error": f"Dispositivo ou grupo '{target}' não encontrado."}
        with ThreadPoolExecutor(max_workers=max(1, len(devs))) as ex:
            results = list(ex.map(lambda d: self._set_single_device(d, True), devs))
        any_ok = any(r.get("success") for r in results)
        if any_ok:
            self._last_known_state = True
            logger.info(f"[TUYA] Lâmpada(s) LIGADA(S) ({[d['name'] for d in devs]})")
            return {"success": True, "is_on": True, "label": res_t["label"], "count": len(devs), "results": results}
        return {"success": False, "error": results[0].get("error", "Falha ao ligar lâmpada"), "results": results}

    def turn_off(self, target: str = "all") -> Dict[str, Any]:
        """Desliga a(s) lâmpada(s) em paralelo."""
        res_t = self.resolve_target(target)
        devs = res_t["devices"]
        if not devs:
            return {"success": False, "error": f"Dispositivo ou grupo '{target}' não encontrado."}
        with ThreadPoolExecutor(max_workers=max(1, len(devs))) as ex:
            results = list(ex.map(lambda d: self._set_single_device(d, False), devs))
        any_ok = any(r.get("success") for r in results)
        if any_ok:
            self._last_known_state = False
            logger.info(f"[TUYA] Lâmpada(s) DESLIGADA(S) ({[d['name'] for d in devs]})")
            return {"success": True, "is_on": False, "label": res_t["label"], "count": len(devs), "results": results}
        return {"success": False, "error": results[0].get("error", "Falha ao desligar lâmpada"), "results": results}

    def toggle(self, target: str = "all") -> Dict[str, Any]:
        """Alterna o estado atual (toggle) consultando o estado real na nuvem/LAN."""
        st = self.get_status(target)
        if st.get("success") and not st.get("cached"):
            next_state = not bool(st.get("is_on", False))
        else:
            next_state = not self._last_known_state
        return self.turn_on(target) if next_state else self.turn_off(target)


# Instância global singleton
tuya_service = TuyaService()


if __name__ == "__main__":
    import sys
    action = sys.argv[1] if len(sys.argv) > 1 else "status"
    target_arg = sys.argv[2] if len(sys.argv) > 2 else "all"
    if action == "on":
        print(tuya_service.turn_on(target_arg))
    elif action == "off":
        print(tuya_service.turn_off(target_arg))
    elif action == "toggle":
        print(tuya_service.toggle(target_arg))
    else:
        print(tuya_service.get_status(target_arg))
