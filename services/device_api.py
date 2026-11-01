"""
J.A.R.V.I.S. Device API — rotas HTTP compartilhadas (painel ZimaOS e servidor local Windows).

Contrato (JSON):
  GET    /api/devices                 -> lista dispositivos + grupos + estado ligado/desligado
  GET    /api/devices/registry        -> nomes/grupos sem segredos (usado na sincronização do Windows)
  POST   /api/devices/rename          {id, name, aliases?}
  POST   /api/devices/control         {target, action: on|off|toggle}   (target = dispositivo, alias ou grupo)
  POST   /api/groups                  {name, members[], aliases?, id?}  (cria/atualiza)
  DELETE /api/groups/<id>

Cada função retorna (status_http, dict) ou None quando a rota não pertence a este módulo.
"""

import json
import logging
from typing import Any, Dict, Optional, Tuple
from urllib.parse import unquote, urlparse

logger = logging.getLogger("DeviceAPI")

Response = Tuple[int, Dict[str, Any]]


def _parse_body(body: Optional[bytes]) -> Dict[str, Any]:
    if not body:
        return {}
    try:
        data = json.loads(body.decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except (ValueError, UnicodeDecodeError):
        raise ValueError("Corpo JSON inválido.")


def is_device_route(path: str) -> bool:
    p = urlparse(path).path
    return p.startswith("/api/devices") or p.startswith("/api/groups")


def handle(method: str, path: str, body: Optional[bytes] = None) -> Optional[Response]:
    from services.tuya_service import tuya_service as svc

    p = urlparse(path).path.rstrip("/")
    method = method.upper()
    try:
        if method == "GET" and p == "/api/devices":
            return 200, svc.list_devices(with_status=True)
        if method == "GET" and p == "/api/devices/registry":
            return 200, {"success": True, **svc.registry()}

        if method == "POST" and p == "/api/devices/rename":
            d = _parse_body(body)
            res = svc.rename_device(str(d.get("id", "")), str(d.get("name", "")), d.get("aliases"))
            return (200 if res.get("success") else 400), res

        if method == "POST" and p == "/api/groups":
            d = _parse_body(body)
            res = svc.save_group(str(d.get("name", "")), d.get("members"), d.get("aliases"), str(d.get("id", "")))
            return (200 if res.get("success") else 400), res

        if method == "DELETE" and p.startswith("/api/groups/"):
            res = svc.delete_group(unquote(p.split("/api/groups/", 1)[1]))
            return (200 if res.get("success") else 404), res

        if method == "POST" and p == "/api/devices/control":
            d = _parse_body(body)
            action = str(d.get("action", "toggle")).lower()
            target = str(d.get("target", d.get("device_id", "all")))
            if action not in ("on", "off", "toggle"):
                return 400, {"success": False, "error": "Ação inválida (use on, off ou toggle)."}
            fn = {"on": svc.turn_on, "off": svc.turn_off, "toggle": svc.toggle}[action]
            res = fn(target)
            return (200 if res.get("success") else 502), res
    except ValueError as e:
        return 400, {"success": False, "error": str(e)}
    except Exception as e:  # noqa: BLE001 - erro reportado ao cliente e registrado
        logger.exception("Falha na Device API")
        return 500, {"success": False, "error": str(e)}
    return None
