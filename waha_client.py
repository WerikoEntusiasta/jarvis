"""
J.A.R.V.I.S. — WAHA Client (WhatsApp via ZimaOS)
===================================================================
Integra com a instancia WAHA self-hosted (ZimaOS) para:
- status das sessions (pessoal / comercial)
- QR code de pareamento (base64 -> dataURL)
- mensagens NAO LIDAS (diretas, nao grupos)
- leitura de conversa e envio de mensagens

Sessions fixas do JARVIS:
  - "jarvis"    -> WhatsApp pessoal (aguardando escaneamento)
  - "Businees"  -> WhatsApp comercial (Werik Oliveira Marketing)

Credenciais: WAHA_URL / WAHA_KEY (env), com defaults do ZimaOS.
Nunca expor a API key ao frontend - tudo via endpoints do local_server.
"""

import os
import json
import time
import base64
import logging
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional

logger = logging.getLogger("WahaClient")

WAHA_URL = os.environ.get("WAHA_URL", "http://45.167.187.80:9455").rstrip("/")
WAHA_KEY = os.environ.get("WAHA_KEY", "owklM4tm3EdKhQSho5ReuLnt7C2FgxpH")

# Sessions do JARVIS (nome -> papel)
SESSIONS = {
    "jarvis": "pessoal",
    "Businees": "comercial",
}
DEFAULT_SESSION = "Businees"  # a que ja esta WORKING

# Tipos de midia -> emoji/rotulo p/ o card
_MEDIA_LABELS = {
    "image": "📷 imagem",
    "ptt": "🎤 áudio",
    "audio": "🎵 áudio",
    "video": "🎬 vídeo",
    "sticker": "🏷️ adesivo",
    "document": "📄 documento",
    "location": "📍 localização",
    "contact": "👤 contato",
    "gif": "🎞️ gif",
    "revoked": "🚫 apagada",
}

_CACHE: Dict[str, tuple] = {}
_CACHE_TTL = 20.0  # 20s p/ mensagens (quase tempo real)


def _cached(key: str):
    hit = _CACHE.get(key)
    if hit and (time.time() - hit[0]) < _CACHE_TTL:
        return hit[1]
    return None


def _put(key: str, value):
    _CACHE[key] = (time.time(), value)
    return value


def _api(path: str, method: str = "GET",
         payload: Optional[Dict[str, Any]] = None,
         timeout: int = 25, raw: bool = False):
    """Chamada autenticada a API do WAHA."""
    url = f"{WAHA_URL}{path}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"X-Api-Key": WAHA_KEY}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            if raw:
                return resp.status, body, resp.headers.get("Content-Type", "")
            try:
                return resp.status, json.loads(body.decode("utf-8", errors="replace")), ""
            except Exception:
                return resp.status, body.decode("utf-8", errors="replace")[:500], ""
    except urllib.error.HTTPError as e:
        try:
            corpo = e.read().decode(errors="replace")[:400]
        except Exception:
            corpo = ""
        return e.code, corpo, "err"
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}", "err"


def _chat_id(c: Dict[str, Any]) -> str:
    cid = c.get("id")
    if isinstance(cid, dict):
        return str(cid.get("_serialized") or cid.get("user") or "")
    return str(cid or "")


def _fmt_ts(ts) -> str:
    try:
        ts = int(ts)
        if ts > 10 ** 12:  # milissegundos
            ts //= 1000
        return time.strftime("%d/%m %H:%M", time.localtime(ts))
    except Exception:
        return ""


def _last_msg_label(chat: Dict[str, Any]) -> str:
    """Rotulo da ultima mensagem (texto ou tipo de midia)."""
    lm = chat.get("lastMessage")
    if not isinstance(lm, dict):
        return ""
    body = str(lm.get("body") or "").strip()
    if body:
        return body[:200]
    mtype = str(lm.get("type") or "").lower()
    if mtype in _MEDIA_LABELS:
        return _MEDIA_LABELS[mtype]
    if lm.get("hasMedia"):
        return "📎 mídia"
    return "(sem conteúdo)"


# --------------------------------------------------------------------------- #
# API publica do modulo
# --------------------------------------------------------------------------- #

def get_sessions() -> Dict[str, Any]:
    """Status de todas as sessions, com papel (pessoal/comercial)."""
    key = "sessions"
    hit = _cached(key)
    if hit is not None:
        return hit

    st, data, _ = _api("/api/sessions")
    if st != 200 or not isinstance(data, list):
        return {"ok": False, "error": f"WAHA indisponivel (HTTP {st})"}

    saida = []
    for s in data:
        name = str(s.get("name") or "")
        saida.append({
            "name": name,
            "role": SESSIONS.get(name, "outra"),
            "status": str(s.get("status") or "UNKNOWN"),
            "push_name": ((s.get("me") or {}).get("pushName")
                          or (s.get("me") or {}).get("id") or ""),
        })
    # garante que as 2 sessions do JARVIS aparecam mesmo se nao existirem
    existentes = {s["name"] for s in saida}
    for name, role in SESSIONS.items():
        if name not in existentes:
            saida.append({"name": name, "role": role,
                          "status": "NOT_CREATED", "push_name": ""})
    return _put(key, {"ok": True, "sessions": saida})


def _recover_session(session: str) -> str:
    """Recupera uma session FAILED/STOPPED (conexao quebrou no pareamento).

    Sequencia validada empiricamente contra o WAHA:
      - POST /api/sessions/stop {name}  -> 201 (remove a session parada;
        restart/nao-existente sao erros inofensivos aqui)
      - POST /api/sessions/start {name} -> 201 STARTING -> SCAN_QR_CODE
    Retorna o novo status ou 'ERRO:<http>'.
    """
    _api("/api/sessions/stop", method="POST", payload={"name": session})
    st, data, _ = _api("/api/sessions/start", method="POST",
                       payload={"name": session})
    _CACHE.pop("sessions", None)  # invalida o cache de status
    if st in (200, 201):
        if isinstance(data, dict) and data.get("status"):
            return str(data["status"])
        return "STARTING"
    return f"ERRO:{st}"


def get_qr(session: str = "jarvis") -> Dict[str, Any]:
    """QR de pareamento da session como dataURL pronto p/ <img src>.

    AUTO-RECOVERY: se a session esta FAILED/STOPPED (pareamento falhou ou
    foi parada), reinicia sozinha (stop+start) e devolve 'STARTING' - o
    polling do painel entao busca o QR novo automaticamente, sem travar
    no 'failed' sem saida.
    """
    session = str(session or "jarvis").strip() or "jarvis"

    # status primeiro (QR so existe escaneando)
    sess = get_sessions().get("sessions", [])
    atual = next((s for s in sess if s["name"] == session), None)
    status = (atual or {}).get("status", "UNKNOWN")

    if status == "WORKING":
        return {"ok": True, "session": session, "status": "WORKING",
                "connected": True,
                "push_name": (atual or {}).get("push_name", ""),
                "message": "Conectado - QR não necessário."}

    # AUTO-RECOVERY de session quebrada
    if status in ("FAILED", "STOPPED", "CONFLICT"):
        logger.warning(f"[WahaClient] session '{session}' em {status}; "
                       f"reiniciando (stop+start)...")
        status = _recover_session(session)
        if status.startswith("ERRO"):
            return {"ok": False, "session": session, "status": "FAILED",
                    "error": f"falha ao reiniciar a session (HTTP {status[5:]})"}
        # invalida o cache lido antes do recover
        _CACHE.pop("sessions", None)

    if status == "STARTING":
        return {"ok": True, "session": session, "status": "STARTING",
                "connected": False, "reconnecting": True,
                "message": "Reconectando a session... QR em instantes."}

    if status not in ("SCAN_QR_CODE", "NOT_CREATED"):
        return {"ok": False, "session": session, "status": status,
                "error": f"session {session} em estado {status}"}

    st, data, ct = _api(f"/api/{session}/auth/qr", raw=True)
    if st == 200 and isinstance(data, bytes):
        if "json" in (ct or ""):
            try:
                j = json.loads(data.decode(errors="replace"))
                raw_png = j.get("data") or ""
                mimetype = j.get("mimetype") or "image/png"
            except Exception:
                return {"ok": False, "error": "QR em formato desconhecido"}
        else:
            raw_png = base64.b64encode(data).decode()
            mimetype = "image/png"
        if not raw_png.startswith("data:"):
            dataurl = f"data:{mimetype};base64,{raw_png}"
        else:
            dataurl = raw_png
        return {"ok": True, "session": session, "status": status,
                "connected": False, "qr": dataurl}
    return {"ok": False, "session": session,
            "error": f"QR indisponivel (HTTP {st})"}


def get_unread(session: str = "", limite: int = 10) -> Dict[str, Any]:
    """Mensagens NAO LIDAS de chats diretos (nao grupos).

    Sem `session` varre as duas sessions do JARVIS.
    """
    alvos = [str(session).strip()] if session else list(SESSIONS.keys())
    limite = max(1, min(30, int(limite or 10)))

    key = f"unread:{','.join(alvos)}:{limite}"
    hit = _cached(key)
    if hit is not None:
        return hit

    todos: List[Dict[str, Any]] = []
    erros: List[str] = []

    for sess in alvos:
        st, data, _ = _api(f"/api/{sess}/chats?withMessages=true&limit=40")
        if st != 200 or not isinstance(data, list):
            erros.append(f"{sess}: HTTP {st}")
            continue
        for c in data:
            if c.get("isGroup") or c.get("isReadOnly"):
                continue
            unread = int(c.get("unreadCount") or 0)
            if unread <= 0:
                continue
            todos.append({
                "session": sess,
                "role": SESSIONS.get(sess, ""),
                "chat_id": _chat_id(c),
                "name": str(c.get("name") or c.get("pushName") or "Desconhecido"),
                "unread": unread,
                "label": _last_msg_label(c),
                "ts": _fmt_ts(c.get("timestamp")),
                "pinned": bool(c.get("pinned")),
            })

    todos.sort(key=lambda m: (not m["pinned"], -(m["ts"] != "")), reverse=False)
    todos = todos[:limite]

    if not todos and erros:
        return {"ok": False, "error": "; ".join(erros)}

    total = sum(m["unread"] for m in todos)
    if todos:
        resumo = (f"{total} mensagem(ns) não lida(s) de "
                  + ", ".join(f"{m['name']} ({m['unread']})" for m in todos[:4]))
    else:
        resumo = "Nenhuma mensagem não lida."

    return _put(key, {
        "ok": True,
        "messages": todos,
        "total_unread": total,
        "summary": resumo,
        "checked_sessions": alvos,
    })


def get_messages(session: str, chat_id: str,
                 limite: int = 10) -> Dict[str, Any]:
    """Ultimas mensagens de um chat especifico."""
    session = str(session or DEFAULT_SESSION).strip()
    chat_id = str(chat_id or "").strip()
    if not chat_id:
        return {"ok": False, "error": "chat_id vazio"}
    limite = max(1, min(50, int(limite or 10)))

    key = f"msgs:{session}:{chat_id}:{limite}"
    hit = _cached(key)
    if hit is not None:
        return hit

    st, data, _ = _api(f"/api/{session}/chats/{chat_id}/messages?limit={limite}")
    if st != 200 or not isinstance(data, list):
        return {"ok": False, "error": f"mensagens indisponiveis (HTTP {st})"}

    msgs = []
    for m in data:
        body = str(m.get("body") or "").strip()
        if not body and m.get("hasMedia"):
            mtype = str(m.get("type") or "").lower()
            body = _MEDIA_LABELS.get(mtype, "📎 mídia")
        msgs.append({
            "text": body[:600],
            "from_me": bool(m.get("fromMe")),
            "ts": _fmt_ts(m.get("timestamp")),
            "type": str(m.get("type") or ("text" if body else "media")),
        })

    return _put(key, {
        "ok": True,
        "session": session,
        "chat_id": chat_id,
        "messages": msgs,
        "count": len(msgs),
    })


def send_text(chat_id: str, text: str,
              session: str = "") -> Dict[str, Any]:
    """Envia mensagem de texto. Usa a session WORKING por padrao."""
    chat_id = str(chat_id or "").strip()
    text = str(text or "").strip()
    if not chat_id or not text:
        return {"ok": False, "error": "chat_id e texto sao obrigatorios"}

    session = str(session or "").strip()
    if not session:
        # escolhe automaticamente uma session WORKING
        sess = get_sessions().get("sessions", [])
        working = [s["name"] for s in sess if s["status"] == "WORKING"]
        if not working:
            return {"ok": False,
                    "error": "nenhuma session WORKING (pareie um WhatsApp)"}
        session = working[0]

    st, data, _ = _api("/api/sendText", method="POST", payload={
        "session": session, "chatId": chat_id, "text": text,
    })
    if st in (200, 201):
        return {"ok": True, "session": session, "chat_id": chat_id,
                "message": "Mensagem enviada."}
    return {"ok": False, "error": f"envio falhou (HTTP {st}): {str(data)[:200]}"}


def health() -> Dict[str, Any]:
    """Health check rapido (usado pelo local_server p/ endpoints do HUD)."""
    st, data, _ = _api("/api/sessions")
    if st == 200 and isinstance(data, list):
        working = [str(s.get("name")) for s in data
                   if str(s.get("status")) == "WORKING"]
        return {"ok": True, "waha": WAHA_URL, "sessions": len(data),
                "working": working}
    return {"ok": False, "waha": WAHA_URL, "error": f"HTTP {st}"}


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(json.dumps(get_sessions(), ensure_ascii=False, indent=1))
    qr = get_qr("jarvis")
    print("QR jarvis:", qr.get("ok"), "|",
          (qr.get("qr") or "")[:60] if qr.get("qr") else qr.get("error") or qr.get("message"))
    print(json.dumps(get_unread(), ensure_ascii=False, indent=1))
