"""
agent_dynamic.py — CONFIGURAÇÃO DINÂMICA + AUTO-EDIÇÃO DOS AGENTES J.A.R.V.I.S.

Dois pilares (pedido do Senhor Werik, 2026-11-13):

1. CONFIGURAÇÃO DINÂMICA: as configurações dos agentes (instruções, API de IA
   para tarefas pesadas, sistema de voz, ferramentas) são lidas AO VIVO a cada
   chamada — sem restart. O Werik edita `agents/config.json` (global) ou
   `agents/<agente>/config.json` (por agente) e a próxima conversa já usa os
   novos valores. Novas APIs configuradas ali serão encontradas e usadas.

2. AUTO-EDIÇÃO COM APROVAÇÃO: durante uma conversa, o agente pode propor
   mudanças nos PRÓPRIOS arquivos (SOUL.md, USER.md, IDENTITY.md, MEMORY.md,
   config.json) quando o Senhor pede outro comportamento. A proposta NUNCA é
   aplicada direto: exige aprovação explícita (voz ou endpoint do HUD), gera
   backup automático e registra auditoria.

Arquivos de agente permitidos na auto-edição:
    SOUL.md / IDENTITY.md / USER.md / MEMORY.md  (persona e regras)
    config.json                                  (config dinâmica do agente)

Formato do config.json (global e por agente — o do agente vence):
    {
      "model": "mimo-v2.6-pro",            // modelo p/ tarefas pesadas (ou "auto")
      "api": {                              // API de IA própria (sobrepõe MiMo)
        "base": "https://.../v1",
        "key": "sk-...",
        "model": "..."
      },
      "voice": {"engine": "qwen"},          // sistema de voz preferido
      "tools": ["zima_guardian", "..."],    // ferramentas habilitadas
      "instructions": [                     // ordens permanentes do Senhor
        "Trate-me sempre por 'chefe' em vez de 'Senhor'."
      ]
    }
"""

import difflib
import hashlib
import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

logger_name = "AGENT-DYNAMIC"

# Arquivos que um agente pode editar em si (auto-edição com aprovação).
ALLOWED_FILES = ("SOUL.md", "IDENTITY.md", "USER.md", "MEMORY.md", "config.json")

# Teto de segurança para conteúdo proposto (evita estourar disco/memória).
MAX_CONTENT_CHARS = 256_000

# Quantos backups manter por arquivo de agente.
BACKUPS_KEEP = 5


# --------------------------------------------------------------------------- #
# Resolução de diretórios (lida a cada chamada => dinâmica, sem restart)
# --------------------------------------------------------------------------- #

def agents_dir() -> Path:
    """Diretório dos agentes (env > <raiz do repo>/agents). Reavaliado a cada chamada."""
    env = os.environ.get("JARVIS_AGENTS_DIR", "").strip()
    if env:
        return Path(env)
    return Path(__file__).resolve().parent / "agents"


def _agent_dir(agent_id: str) -> Optional[Path]:
    """Diretório do agente, se existir e tiver arquivos de configuração."""
    agent_id = str(agent_id or "").strip().strip("/")
    if not agent_id or agent_id.startswith("."):
        return None
    d = agents_dir() / agent_id
    if not d.is_dir():
        return None
    return d


def _known_agent(agent_id: str) -> bool:
    """Agente 'conhecido' = diretório com SOUL/IDENTITY/USER/MEMORY/AGENTS/config."""
    d = _agent_dir(agent_id)
    if d is None:
        return False
    names = {p.name.lower() for p in d.iterdir() if p.is_file()}
    return any(n in names for n in
               ("soul.md", "identity.md", "user.md", "memory.md",
                "agents.md", "config.json"))


def _audit_file() -> Path:
    return agents_dir() / "_audit" / "self_edit.jsonl"


def _audit(action: str, agent_id: str, file: str, approval_id: str,
           reason: str = "", ok: bool = True, extra: str = "") -> None:
    """Trilha de auditoria JSONL de toda tentativa de auto-edição."""
    try:
        f = _audit_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        reg = {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "action": action,
            "agent": agent_id,
            "file": file,
            "approval_id": approval_id,
            "reason": (reason or "")[:300],
            "ok": bool(ok),
        }
        if extra:
            reg["extra"] = extra[:300]
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(reg, ensure_ascii=False) + "\n")
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Pilar 1 — configuração dinâmica
# --------------------------------------------------------------------------- #

def _read_json(path: Path) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def global_config() -> Dict[str, Any]:
    """config.json GLOBAL dos agentes (lido ao vivo)."""
    return _read_json(agents_dir() / "config.json")


def effective_config(agent_id: str) -> Dict[str, Any]:
    """Config efetiva do agente = global + específica (específica vence).

    Lida AO VIVO a cada chamada: mudou no disco, vale na próxima conversa.
    """
    cfg = dict(global_config())
    d = _agent_dir(agent_id)
    if d is not None:
        per = _read_json(d / "config.json")
        for k, v in per.items():
            if k == "api" and isinstance(v, dict) and isinstance(cfg.get("api"), dict):
                merged = dict(cfg["api"]); merged.update(v); cfg["api"] = merged
            else:
                cfg[k] = v
    return cfg


def override_model(cfg: Dict[str, Any], default_flash: str, default_pro: str,
                   tier: str) -> str:
    """Modelo efetivo: config 'model' ou 'api.model' vence o roteador interno.

    Aceita 'flash'/'pro' (substituição por tier) ou nome completo de modelo.
    """
    raw = str(cfg.get("model") or "").strip()
    api = cfg.get("api") if isinstance(cfg.get("api"), dict) else {}
    api_model = str((api or {}).get("model") or "").strip()
    chosen = api_model or raw
    if not chosen or chosen.lower() in ("auto", "automatico", "automático"):
        return default_pro if tier == "pro" else default_flash
    low = chosen.lower()
    if low == "flash":
        return default_flash
    if low == "pro":
        return default_pro
    return chosen


def _fmt_section(title: str, items: List[str]) -> str:
    if not items:
        return ""
    body = "\n".join(f"  - {i}" for i in items if str(i).strip())
    return f"\n--- {title} ---\n{body}\n" if body.strip() else ""


def config_summary(agent_id: str) -> str:
    """Resumo legível da config dinâmica, para injeção no system prompt.

    O texto explica AO PRÓPRIO AGENTE como se autoconfigurar e como propor
    auto-edição, de modo que novas APIs/ordens escritas no config.json
    'saibam o que fazer' sem código novo.
    """
    cfg = effective_config(agent_id)
    lines: List[str] = []
    api = cfg.get("api") if isinstance(cfg.get("api"), dict) else {}
    if api.get("base"):
        lines.append(f"API de IA configurada: {api.get('base')} (modelo: {api.get('model') or cfg.get('model') or 'padrão'})")
    elif cfg.get("model"):
        lines.append(f"Modelo preferido: {cfg['model']}")
    voice = cfg.get("voice") if isinstance(cfg.get("voice"), dict) else {}
    if voice.get("engine"):
        lines.append(f"Sistema de voz preferido: {voice['engine']}")
    tools = cfg.get("tools")
    if isinstance(tools, list) and tools:
        lines.append("Ferramentas habilitadas: " + ", ".join(map(str, tools)))
    out = _fmt_section("CONFIGURAÇÃO DINÂMICA DO AGENTE (lida agora, valendo nesta conversa)", lines)
    out += _fmt_section("ORDENS PERMANENTES DO SENHOR (obrigatório cumprir)",
                        [str(i) for i in cfg.get("instructions", [])
                         if isinstance(cfg.get("instructions"), list)])
    out += (
        "\n--- AUTO-EDIÇÃO COM APROVAÇÃO ---\n"
        "Quando o Senhor Werik pedir para você mudar seu comportamento, tom, "
        "tratamento, prioridades ou 'fazer diferente daqui pra frente', NÃO apenas "
        "obedeça na resposta: registre a mudança de forma permanente propondo uma "
        "edição nos SEUS arquivos com a ferramenta 'agent_self_edit' "
        "(action='propose', file em SOUL.md/USER.md/IDENTITY.md/MEMORY.md/"
        "config.json, content=conteúdo COMPLETO novo do arquivo). A proposta "
        "devolve approval_required: apresente o que vai mudar e aguarde o "
        "approval_id ser aprovado (action='approve'); recusa = a edição é "
        "descartada. Mudanças nas ordens do Senhor vão sempre em USER.md ou "
        "instructions do config.json.\n"
    )
    return out


# --------------------------------------------------------------------------- #
# Pilar 2 — auto-edição com aprovação
# --------------------------------------------------------------------------- #

def _approval_id(agent_id: str, file: str, content: str) -> str:
    """ID determinístico: mesma proposta => mesmo ID (a IA pode re-chamar)."""
    h = hashlib.sha1(f"{agent_id.lower()}|{file}|{content}".encode("utf-8")).hexdigest()
    return f"aed_{h[:16]}"


def _pending_path(agent_id: str) -> Path:
    return agents_dir() / agent_id / ".pending_edit.json"


def _diff_summary(old: str, new: str) -> Dict[str, Any]:
    diff = list(difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm=""))
    add = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
    rem = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))
    sample = [l for l in diff if l.startswith(("+", "-"))
              and not l.startswith(("+++", "---"))][:8]
    return {"lines_added": add, "lines_removed": rem, "sample": sample}


def pending_edit(agent_id: str, include_content: bool = False) -> Optional[Dict[str, Any]]:
    p = _pending_path(agent_id)
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    if not include_content:
        data.pop("content", None)
    return data


def pending_all() -> List[Dict[str, Any]]:
    out = []
    base = agents_dir()
    if not base.is_dir():
        return out
    for d in base.iterdir():
        if d.is_dir() and not d.name.startswith(".") and not d.name.startswith("_"):
            pend = pending_edit(d.name)
            if pend:
                out.append(pend)
    return out


def propose_self_edit(agent_id: str, file: str, content: str,
                      reason: str = "") -> Dict[str, Any]:
    """Agente PROPÕE edição nos próprios arquivos — nunca aplica direto.

    Retorna approval_required=True + approval_id determinístico. Grava a
    proposta pendente (com snapshot do conteúdo atual), notifica o HUD e
    audita. Mesma proposta => mesmo approval_id (idempotente).
    """
    agent_id = str(agent_id or "").strip()
    file = str(file or "").strip()
    if not _known_agent(agent_id):
        _audit("propose", agent_id, file, "", reason, ok=False,
               extra="agente desconhecido")
        return {"ok": False, "error": f"agente desconhecido: '{agent_id}'"}
    if file not in ALLOWED_FILES:
        _audit("propose", agent_id, file, "", reason, ok=False,
               extra="arquivo fora da whitelist")
        return {"ok": False,
                "error": f"arquivo '{file}' fora da whitelist {list(ALLOWED_FILES)}"}
    content = str(content or "")
    if not content.strip():
        return {"ok": False, "error": "content vazio (edicao precisa do arquivo inteiro novo)"}
    if len(content) > MAX_CONTENT_CHARS:
        return {"ok": False,
                "error": f"content muito grande ({len(content)} > {MAX_CONTENT_CHARS} chars)"}
    if file == "config.json":
        try:
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                raise ValueError("config precisa ser um objeto JSON")
        except Exception as e:
            _audit("propose", agent_id, file, "", reason, ok=False,
                   extra=f"config.json invalido: {e}")
            return {"ok": False, "error": f"config.json invalido: {e}"}

    d = _agent_dir(agent_id)
    target = d / file
    old = ""
    if target.exists():
        try:
            with open(target, "r", encoding="utf-8", errors="replace") as f:
                old = f.read()
        except Exception:
            old = ""
    if content == old.strip() or content == old:
        return {"ok": False, "error": "proposta identica ao arquivo atual (nada a mudar)"}

    approval_id = _approval_id(agent_id, file, content)
    diff = _diff_summary(old, content)
    proposal = {
        "approval_id": approval_id,
        "agent": agent_id,
        "file": file,
        "reason": (reason or "").strip(),
        "proposed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "old_size": len(old),
        "new_size": len(content),
        "diff": diff,
        "content": content,
    }
    pend = _pending_path(agent_id)
    tmp = pend.with_suffix(".tmp")
    tmp.write_text(json.dumps(proposal, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    os.replace(tmp, pend)

    _audit("propose", agent_id, file, approval_id, reason, ok=True,
           extra=f"+{diff['lines_added']}/-{diff['lines_removed']} linhas")
    _notify_hud(agent_id, file, reason, approval_id)

    return {
        "ok": True,
        "approval_required": True,
        "approval_id": approval_id,
        "agent": agent_id,
        "file": file,
        "diff_summary": (f"+{diff['lines_added']} -{diff['lines_removed']} linhas"),
        "changed_preview": diff["sample"],
        "message": (f"Proposta registrada para {agent_id}/{file}. APRESENTE a "
                    f"mudanca ao Senhor e aguarde aprovacao; depois rechame com "
                    f"action='approve' e o approval_id EXATO."),
    }


def _find_pending(approval_id: str) -> Optional[Path]:
    approval_id = str(approval_id or "").strip()
    if not approval_id:
        return None
    base = agents_dir()
    if not base.is_dir():
        return None
    for d in base.iterdir():
        if not (d.is_dir() and not d.name.startswith(".") and not d.name.startswith("_")):
            continue
        p = d / ".pending_edit.json"
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    if json.load(f).get("approval_id") == approval_id:
                        return p
            except Exception:
                continue
    return None


def _backup_file(d: Path, file: str) -> Optional[Path]:
    target = d / file
    if not target.exists():
        return None
    bdir = d / "backups"
    bdir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    bpath = bdir / f"{file}.{stamp}.bak"
    try:
        bpath.write_bytes(target.read_bytes())
    except Exception:
        return None
    # prune: manter só BACKUPS_KEEP mais recentes deste arquivo
    olds = sorted(bdir.glob(f"{file}.*.bak"), key=lambda p: p.stat().st_mtime)
    for old in olds[:-BACKUPS_KEEP] if len(olds) > BACKUPS_KEEP else []:
        try:
            old.unlink()
        except Exception:
            pass
    return bpath


def approve_self_edit(approval_id: str) -> Dict[str, Any]:
    """APLICA a proposta aprovada: backup do atual + gravação atômica + auditoria."""
    p = _find_pending(approval_id)
    if p is None:
        _audit("approve", "", "", approval_id, ok=False, extra="proposta nao encontrada")
        return {"ok": False, "error": "proposta não encontrada (id inválido ou já resolvida)"}
    try:
        with open(p, "r", encoding="utf-8") as f:
            prop = json.load(f)
    except Exception as e:
        return {"ok": False, "error": f"proposta corrompida: {e}"}

    agent_id = prop.get("agent", "")
    file = prop.get("file", "")
    content = prop.get("content", "")
    d = _agent_dir(agent_id)
    if d is None or file not in ALLOWED_FILES:
        return {"ok": False, "error": "agente/arquivo não permitido"}
    if file == "config.json":
        try:
            if not isinstance(json.loads(content), dict):
                return {"ok": False, "error": "config.json precisa ser objeto JSON"}
        except Exception as e:
            return {"ok": False, "error": f"config.json invalido: {e}"}

    backup = _backup_file(d, file)
    target = d / file
    tmp = target.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, target)

    try:
        p.unlink()
    except Exception:
        pass

    _audit("approve", agent_id, file, approval_id,
           prop.get("reason", ""), ok=True,
           extra=f"backup={backup.name if backup else 'novo'}")
    _toast(f"✅ {agent_id}: {file} atualizado (auto-edição aprovada)")
    return {"ok": True, "agent": agent_id, "file": file,
            "backup": str(backup) if backup else None,
            "message": f"{file} de {agent_id} atualizado. Vale já na próxima conversa."}


def reject_self_edit(approval_id: str, motivo: str = "") -> Dict[str, Any]:
    """Descarta a proposta — arquivo permanece intocado."""
    p = _find_pending(approval_id)
    if p is None:
        return {"ok": False, "error": "proposta não encontrada"}
    try:
        with open(p, "r", encoding="utf-8") as f:
            prop = json.load(f)
    except Exception:
        prop = {}
    try:
        p.unlink()
    except Exception:
        pass
    _audit("reject", prop.get("agent", ""), prop.get("file", ""), approval_id,
           motivo or prop.get("reason", ""), ok=True)
    _toast(f"🚫 {prop.get('agent', 'agente')}: proposta de {prop.get('file', 'arquivo')} recusada")
    return {"ok": True, "message": "Proposta recusada. Nada foi alterado."}


# --------------------------------------------------------------------------- #
# Notificação ao HUD (cross-process, sempre best-effort)
# --------------------------------------------------------------------------- #

def _toast(message: str) -> None:
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:%d/api/hud/broadcast" % int(
                os.environ.get("JARVIS_LOCAL_PORT", "8085")),
            data=json.dumps({"event": "toast",
                             "data": {"message": message}}).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "User-Agent": "JARVIS-AgentDynamic/1.0"},
        )
        urllib.request.urlopen(req, timeout=2)
    except Exception:
        pass


def _notify_hud(agent_id: str, file: str, reason: str, approval_id: str) -> None:
    msg = (f"🧠 {agent_id} quer editar {file} — aprove (diga 'aprovado' ou "
           f"POST /api/agents/dynamic/approve)")
    _toast(msg)
    _toast_payload = {
        "event": "agent_edit_proposal",
        "data": {"agent": agent_id, "file": file, "reason": reason,
                 "approval_id": approval_id},
    }
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:%d/api/hud/broadcast" % int(
                os.environ.get("JARVIS_LOCAL_PORT", "8085")),
            data=json.dumps(_toast_payload).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "User-Agent": "JARVIS-AgentDynamic/1.0"},
        )
        urllib.request.urlopen(req, timeout=2)
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Ponte de ferramenta (mesma convenção do zima_guardian.handle_tool)
# --------------------------------------------------------------------------- #

def handle_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Executa 'agent_self_edit'. Acoes: propose/approve/reject/pending/status."""
    action = str(args.get("action", "status")).lower()
    agent_id = str(args.get("agent_id", "")).strip() or "jarvis"

    if action == "propose":
        return propose_self_edit(
            agent_id,
            str(args.get("file", "")),
            str(args.get("content", "")),
            str(args.get("reason", "")),
        )

    if action == "approve":
        return approve_self_edit(str(args.get("approval_id", "")))

    if action == "reject":
        return reject_self_edit(str(args.get("approval_id", "")),
                                str(args.get("motivo", "")))

    if action == "pending":
        pend = pending_edit(agent_id)
        return {"ok": True, "agent": agent_id, "pending": pend,
                "has_pending": pend is not None}

    if action == "status":
        cfg = effective_config(agent_id)
        cfg_public = dict(cfg)
        api = dict(cfg_public.get("api") or {})
        if api.get("key"):
            k = str(api["key"])
            api["key"] = (k[:6] + "..." + k[-4:]) if len(k) > 12 else "***"
        cfg_public["api"] = api
        return {"ok": True, "agent": agent_id, "config": cfg_public,
                "pending": pending_edit(agent_id),
                "allowed_files": list(ALLOWED_FILES)}

    return {"ok": False,
            "error": f"acao desconhecida '{action}' (propose/approve/reject/pending/status)"}
