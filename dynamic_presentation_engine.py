"""
J.A.R.V.I.S. — Dynamic Presentation Engine (Backend & Orchestrator)
=============================================================================
Camada de orquestração multimodal que transforma respostas e relatórios do J.A.R.V.I.S.
em roteiros estruturados de cenas dinâmicas executadas no HUD em tempo real.
"""

import os
import sys
import time
import json
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("DynamicPresentationEngine")

_ACTIVE_PRESENTATION: Optional[Dict[str, Any]] = None

def _broadcast_to_hud(event_type: str, data: dict) -> bool:
    """Envia evento para o barramento SSE do HUD local com tolerância ao path de execução."""
    try:
        try:
            from core.local_server import broadcast_hud_event
            broadcast_hud_event(event_type, data)
            return True
        except ImportError:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            jw_dir = os.path.join(base_dir, "jarvis-windows")
            if jw_dir not in sys.path:
                sys.path.insert(0, jw_dir)
            from core.local_server import broadcast_hud_event
            broadcast_hud_event(event_type, data)
            return True
    except Exception as e:
        logger.debug(f"[PresentationEngine] Falha no broadcast SSE: {e}")
        return False

def get_active_presentation() -> Optional[Dict[str, Any]]:
    """Retorna a apresentação ativa na memória."""
    global _ACTIVE_PRESENTATION
    return _ACTIVE_PRESENTATION

def validate_presentation_script(script: Dict[str, Any]) -> Dict[str, Any]:
    """Valida e normaliza o roteiro estruturado de apresentação multimodal de forma resiliente."""
    if not isinstance(script, dict):
        script = {}

    title = str(script.get("title") or "Apresentação J.A.R.V.I.S.")
    subtitle = str(script.get("subtitle") or "Stark Mark VII · Núcleo Soberano")
    scenes = script.get("scenes")

    # Se não houver cenas ou formato inválido, auto-gera cena inicial de alta tecnologia
    if not isinstance(scenes, list) or len(scenes) == 0:
        content_text = script.get("content") or script.get("description") or f"Apresentação executiva e telemetria: {title}."
        scenes = [{
            "scene_id": "scene_1",
            "title": title,
            "subtitle": subtitle,
            "component_type": "hologram_card",
            "content": content_text,
            "tags": ["J.A.R.V.I.S.", "Stark Mark VII", "Tempo Real"],
            "metrics": [
                {"label": "Status", "value": "ONLINE"},
                {"label": "Núcleo", "value": "Soberano Direct"}
            ]
        }]

    sanitized_scenes = []
    valid_types = {
        "hologram_card", "video", "gallery", "chart", "table", 
        "map", "diagram", "comparison", "metric_grid", "conclusion",
        "smart_canvas", "canvas", "network", "graph",
        # Cards universais: resposta em texto, noticias e previsao do tempo
        "text", "answer", "response", "news", "noticia",
        "weather", "tempo", "clima",
        # WhatsApp (mensagens nao lidas do WAHA)
        "whatsapp", "zap",
    }

    for idx, sc in enumerate(scenes):
        if not isinstance(sc, dict):
            continue
        c_type = str(sc.get("component_type") or sc.get("type") or "hologram_card").lower()
        if c_type not in valid_types:
            c_type = "hologram_card"

        # Conteudo estruturado (dict) do modelo: distribui nos campos da cena
        # em vez de serializar o dict como string (lixo no card).
        raw_content = sc.get("content", "")
        rich = raw_content if isinstance(raw_content, dict) else {}
        if rich:
            content_text = str(rich.get("text") or rich.get("summary") or rich.get("description") or rich.get("heading") or "")
            bullets = sc.get("bullets") or rich.get("bullets") or []
            badges = rich.get("badges") or []
            metrics = sc.get("metrics") or rich.get("metrics") or []
            nodes = sc.get("nodes") or rich.get("nodes") or []
            edges = sc.get("edges") or sc.get("links") or rich.get("edges") or rich.get("links") or []
            data = dict(sc.get("data") or {})
            for k in ("chart_type", "series", "categories", "x_label", "y_label"):
                if k in rich and k not in data:
                    data[k] = rich[k]
        else:
            content_text = str(raw_content)
            bullets = sc.get("bullets", [])
            badges = []
            metrics = sc.get("metrics", [])
            nodes = sc.get("nodes", [])
            edges = sc.get("edges", [])
            data = sc.get("data", {})

        # Campos estruturados que o modelo manda DENTRO do content (dict):
        # table (columns/rows), comparison (items), conclusion, map (markers)...
        # Sem isto, tabelas/comparacoes chegam vazias ao HUD.
        def _pick(*keys, default=None):
            for src in (sc, rich):
                for k in keys:
                    v = src.get(k)
                    if v not in (None, "", [], {}):
                        return v
            return default

        headers = _pick("headers", "columns", default=[]) or []
        rows = _pick("rows", default=[]) or []
        items = _pick("items", default=[]) or []
        markers = _pick("markers", default=[]) or []
        days = _pick("days", "forecast", default=[]) or []
        conclusion = str(_pick("conclusion", default="") or "")
        copy_text = str(_pick("copy_text", "answer", default="") or "")
        summary_points = _pick("summary_points", default=[]) or []
        actions = _pick("actions", default=[]) or []
        media = _pick("media", default={}) or {}
        caption = str(_pick("caption", default="") or "")
        thumbnail = str(_pick("thumbnail", default="") or "")
        item_a = _pick("item_a", default={}) or {}
        item_b = _pick("item_b", default={}) or {}
        # WhatsApp: mensagens nao lidas
        wa_messages = _pick("messages", default=[]) or []
        wa_total = _pick("total_unread", default=0) or 0
        wa_role = str(_pick("role", default="") or "")

        scene_obj = {
            "scene_id": str(sc.get("scene_id") or f"scene_{idx + 1}"),
            "title": str(sc.get("title") or rich.get("heading") or f"Cena {idx + 1}"),
            "subtitle": str(sc.get("subtitle") or rich.get("subtitle") or ""),
            "component_type": c_type,
            "content": content_text,
            "duration_sec": float(sc.get("duration_sec", 0)),
            "bullets": bullets,
            "tags": sc.get("tags", []),
            "metrics": metrics,
            "data": data,
            "nodes": nodes,
            "edges": edges,
            "badges": badges,
            "headers": headers,
            "rows": rows,
            "items": items,
            "days": days,
            "copy_text": copy_text,
            "item_a": item_a,
            "item_b": item_b,
            "markers": markers,
            "conclusion": conclusion,
            "summary_points": summary_points,
            "actions": actions,
            "media": media,
            "caption": caption,
            "thumbnail": thumbnail,
            "messages": wa_messages,
            "total_unread": wa_total,
            "role": wa_role,
            "canvas_elements": sc.get("canvas_elements") or sc.get("elements", []),
            "canvas_connections": sc.get("canvas_connections") or sc.get("connections", []),
            "canvas_width": int(sc.get("canvas_width") or 800),
            "canvas_height": int(sc.get("canvas_height") or 480)
        }
        sanitized_scenes.append(scene_obj)

    return {
        "id": str(script.get("id") or f"pres_{int(time.time())}"),
        "title": title,
        "subtitle": str(script.get("subtitle", "")),
        "speech_sync": bool(script.get("speech_sync", True)),
        "scenes": sanitized_scenes,
        "created_at": time.time()
    }

def start_dynamic_presentation(script_or_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Inicia uma apresentação multimodal cinematográfica no HUD."""
    global _ACTIVE_PRESENTATION
    try:
        validated = validate_presentation_script(script_or_dict)
        _ACTIVE_PRESENTATION = validated

        # Dispara evento SSE para o HUD e conexões ativas
        _broadcast_to_hud("presentation_start", validated)
        _broadcast_to_hud("toast", {"message": f"🎬 Apresentação Dinâmica: {validated['title']}"})

        logger.info(f"[PresentationEngine] Apresentação iniciada com {len(validated['scenes'])} cenas.")
        return {
            "ok": True,
            "presentation_id": validated["id"],
            "title": validated["title"],
            "total_scenes": len(validated["scenes"]),
            "message": f"Apresentação '{validated['title']}' iniciada no HUD com {len(validated['scenes'])} cenas."
        }
    except Exception as e:
        logger.error(f"[PresentationEngine] Erro ao iniciar apresentação: {e}")
        return {"ok": False, "error": str(e)}

def update_presentation_scene(scene_data: Dict[str, Any]) -> Dict[str, Any]:
    """Injeta ou altera dinamicamente uma cena na apresentação ativa."""
    global _ACTIVE_PRESENTATION
    try:
        if not isinstance(scene_data, dict):
            return {"ok": False, "error": "scene_data deve ser um dicionário."}

        _broadcast_to_hud("presentation_scene", scene_data)
        return {"ok": True, "message": "Cena enviada ao HUD com sucesso."}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def control_presentation(action: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Controla a apresentação ativa: pause, resume, next, prev, jump, close."""
    global _ACTIVE_PRESENTATION
    act = action.strip().lower()
    valid_actions = {"pause", "resume", "next", "prev", "jump", "close", "stop"}
    if act not in valid_actions:
        return {"ok": False, "error": f"Ação inválida: {action}. Use {valid_actions}"}

    payload = {"action": act, "params": params or {}}
    _broadcast_to_hud("presentation_control", payload)

    if act in {"close", "stop"}:
        _ACTIVE_PRESENTATION = None

    return {"ok": True, "action": act, "message": f"Comando '{act}' enviado à apresentação com sucesso."}

def get_presentation_status() -> Dict[str, Any]:
    """Retorna o estado da apresentação multimodal ativa."""
    global _ACTIVE_PRESENTATION
    return {
        "ok": True,
        "is_active": _ACTIVE_PRESENTATION is not None,
        "presentation": _ACTIVE_PRESENTATION
    }

def handle_speech_event(event_name: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Sincroniza a apresentacao com o motor de voz (Piper TTS / Whisper).
    Eventos suportados:
      - speech.started: Inicia ou foca apresentacao
      - speech.segment.started: Sincroniza trecho falado
      - speech.segment.completed: Avanca cena se speech_sync=True
      - speech.interrupted: Pausa/cancela visual anterior imediatamente
      - speech.completed: Finaliza ciclo de apresentacao
    """
    global _ACTIVE_PRESENTATION
    event = str(event_name).strip().lower()
    data = payload or {}

    logger.info(f"[PresentationEngine] Evento de voz recebido: {event}")

    if event == "speech.interrupted":
        _broadcast_to_hud("presentation_control", {"action": "pause", "reason": "speech_interrupted"})
        return {"ok": True, "action": "paused", "event": event}

    elif event in {"speech.segment.completed", "speech.next_topic"}:
        if _ACTIVE_PRESENTATION and _ACTIVE_PRESENTATION.get("speech_sync", True):
            _broadcast_to_hud("presentation_control", {"action": "next"})
            return {"ok": True, "action": "next_scene", "event": event}

    elif event == "speech.completed":
        logger.info("[PresentationEngine] Fala completada.")
        return {"ok": True, "action": "completed", "event": event}

    return {"ok": True, "event": event}

# =============================================================================
# SPATIAL INTELLIGENCE & INDEPENDENT COMPONENT WORKSPACE ENGINE
# =============================================================================
_ACTIVE_SPATIAL_WORKSPACE: Optional[Dict[str, Any]] = None

# The workspace uses normalized viewport percentages rather than a card grid.
# Legacy col_span payloads remain accepted, but are mapped to intentionally
# asymmetrical positions so old callers do not regress into a dashboard.
_SPATIAL_FALLBACKS = {
    "relationship_map": (18, 12, 62, 72, 4, 6),
    "power_triptych": (18, 12, 62, 72, 4, 6),
    "echarts": (72, 60, 25, 31, 2, 4),
    "hero_card": (4, 9, 27, 31, 2, 5),
    "narrative": (4, 9, 27, 31, 2, 5),
    "metric_dock": (4, 66, 25, 25, 2, 4),
    "data_table": (4, 42, 25, 21, 1, 3),
    "annotation": (77, 14, 18, 16, 2, 7),
    "media": (73, 28, 23, 28, 2, 4),
    "three_view": (51, 51, 47, 46, 2, 4),
    "topology_map": (51, 51, 47, 46, 2, 4),
    "three_view": (20, 9, 60, 76, 4, 6),
    "smart_canvas": (14, 10, 72, 78, 3, 5),
}
_VALID_SPATIAL_TYPES = set(_SPATIAL_FALLBACKS) | {"chart", "canvas", "signal_list"}


def _number(value: Any, fallback: float, minimum: float, maximum: float) -> float:
    """Returns a finite, bounded number without trusting streamed payloads."""
    try:
        return max(minimum, min(maximum, float(value)))
    except (TypeError, ValueError):
        return fallback


def _normalize_spatial_position(component_type: str, position: Optional[Dict[str, Any]], index: int) -> Dict[str, Any]:
    """Normalizes freeform viewport geometry and keeps each element visible."""
    fallback = _SPATIAL_FALLBACKS.get(component_type, (34 + (index * 13) % 42, 12 + (index * 17) % 52, 24, 22, 1, 3))
    source = position if isinstance(position, dict) else {}
    width = _number(source.get("width"), fallback[2], 8, 96)
    height = _number(source.get("height"), fallback[3], 8, 88)
    return {
        "x": _number(source.get("x"), fallback[0], 0, 100 - width),
        "y": _number(source.get("y"), fallback[1], 0, 100 - height),
        "width": width,
        "height": height,
        "depth": _number(source.get("depth"), fallback[4], 0, 10),
        "zIndex": int(_number(source.get("zIndex"), fallback[5], 0, 99)),
        "layer": str(source.get("layer") or "content"),
        "importance": str(source.get("importance") or "secondary"),
        "responsive": source.get("responsive") if isinstance(source.get("responsive"), dict) else {"mobile": "stack"},
        "allowOverlap": bool(source.get("allowOverlap", False)),
    }

def get_spatial_workspace() -> Optional[Dict[str, Any]]:
    """Retorna o estado do Spatial Workspace ativo na memória."""
    global _ACTIVE_SPATIAL_WORKSPACE
    return _ACTIVE_SPATIAL_WORKSPACE

def create_spatial_workspace(title: str = "Spatial Workspace", subtitle: str = "", layout: str = "freeform", options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Cria e inicializa um novo Spatial Workspace persistente."""
    global _ACTIVE_SPATIAL_WORKSPACE
    ws_id = f"workspace_{int(time.time())}"
    _ACTIVE_SPATIAL_WORKSPACE = {
        "id": ws_id,
        "title": title,
        "subtitle": subtitle,
        "layout": "freeform" if layout in {"", "fluid_grid", "grid"} else layout,
        "mode": "spatial",
        "options": options or {},
        "components": {},
        "connections": [],
        "groups": {},
        "created_at": time.time(),
        "updated_at": time.time()
    }
    _broadcast_to_hud("spatial_workspace_created", _ACTIVE_SPATIAL_WORKSPACE)
    _broadcast_to_hud("toast", {"message": f"🌐 Spatial Workspace: {title}"})
    logger.info(f"[SpatialEngine] Workspace '{ws_id}' criado com sucesso.")
    return {"ok": True, "workspace_id": ws_id, "layout": layout, "message": "Spatial Workspace ativo."}

def add_spatial_component(component_id: str, component_type: str, position: Dict[str, Any], props: Dict[str, Any]) -> Dict[str, Any]:
    """Adiciona um componente independente e vivo ao Spatial Workspace."""
    global _ACTIVE_SPATIAL_WORKSPACE
    if not _ACTIVE_SPATIAL_WORKSPACE:
        create_spatial_workspace(title="Spatial Visual Hub")

    cid = str(component_id or "").strip()
    if not cid:
        return {"ok": False, "error": "component_id é obrigatório."}
    c_type = str(component_type).strip().lower()
    if c_type not in _VALID_SPATIAL_TYPES:
        c_type = "annotation"

    component_data = {
        "id": cid,
        "type": c_type,
        "position": _normalize_spatial_position(c_type, position, len(_ACTIVE_SPATIAL_WORKSPACE["components"])),
        "props": props or {},
        "relationships": [],
        "group": None,
        "state": "visible",
        "created_at": time.time(),
        "updated_at": time.time()
    }

    _ACTIVE_SPATIAL_WORKSPACE["components"][cid] = component_data
    _ACTIVE_SPATIAL_WORKSPACE["updated_at"] = time.time()

    _broadcast_to_hud("spatial_component_added", component_data)
    logger.info(f"[SpatialEngine] Componente '{cid}' ({c_type}) adicionado ao Workspace.")
    return {"ok": True, "component_id": cid, "type": c_type}

def update_spatial_component(component_id: str, updates: Dict[str, Any], animate: bool = True) -> Dict[str, Any]:
    """Atualiza exclusivamente um componente específico sem reconstruir o Workspace."""
    global _ACTIVE_SPATIAL_WORKSPACE
    if not _ACTIVE_SPATIAL_WORKSPACE or component_id not in _ACTIVE_SPATIAL_WORKSPACE["components"]:
        return {"ok": False, "error": f"Componente '{component_id}' não encontrado no Workspace ativo."}

    comp = _ACTIVE_SPATIAL_WORKSPACE["components"][component_id]
    if "props" in updates:
        comp["props"].update(updates["props"])
    if "position" in updates:
        merged_position = dict(comp.get("position") or {})
        merged_position.update(updates["position"] or {})
        comp["position"] = _normalize_spatial_position(comp.get("type", "annotation"), merged_position, 0)
    for k, v in updates.items():
        if k not in {"props", "position"}:
            comp[k] = v

    comp["updated_at"] = time.time()
    payload = {"component_id": component_id, "updates": updates, "animate": animate}
    _broadcast_to_hud("spatial_component_updated", payload)
    return {"ok": True, "component_id": component_id}


def apply_spatial_operation(component_id: str, operation: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Applies a single streamed spatial operation without rebuilding the workspace."""
    global _ACTIVE_SPATIAL_WORKSPACE
    if not _ACTIVE_SPATIAL_WORKSPACE or component_id not in _ACTIVE_SPATIAL_WORKSPACE["components"]:
        return {"ok": False, "error": f"Componente '{component_id}' não encontrado no Workspace ativo."}
    operation = str(operation or "").strip().lower()
    params = params or {}
    component = _ACTIVE_SPATIAL_WORKSPACE["components"][component_id]

    if operation in {"move", "resize", "reposition"}:
        position = dict(component.get("position") or {})
        position.update(params.get("position") if isinstance(params.get("position"), dict) else params)
        return update_spatial_component(component_id, {"position": position}, bool(params.get("animate", True)))
    if operation in {"focus", "expand", "minimize"}:
        state = "expanded" if operation == "expand" else "minimized" if operation == "minimize" else "focused"
        updates = {"state": state, "focus": operation == "focus"}
        if operation == "expand":
            position = dict(component.get("position") or {})
            position.update({"x": 12, "y": 8, "width": 76, "height": 78, "zIndex": 20})
            updates["position"] = position
        return update_spatial_component(component_id, updates, True)
    if operation in {"group", "separate"}:
        group = None if operation == "separate" else str(params.get("group") or params.get("group_id") or "default")
        component["group"] = group
        if group:
            _ACTIVE_SPATIAL_WORKSPACE["groups"].setdefault(group, [])
            if component_id not in _ACTIVE_SPATIAL_WORKSPACE["groups"][group]:
                _ACTIVE_SPATIAL_WORKSPACE["groups"][group].append(component_id)
        return update_spatial_component(component_id, {"group": group}, True)
    if operation == "connect":
        target = str(params.get("target") or params.get("target_id") or "").strip()
        if not target or target not in _ACTIVE_SPATIAL_WORKSPACE["components"]:
            return {"ok": False, "error": "connect exige um target_id existente."}
        link = {"from": component_id, "to": target, "kind": str(params.get("kind") or "relationship")}
        if link not in _ACTIVE_SPATIAL_WORKSPACE["connections"]:
            _ACTIVE_SPATIAL_WORKSPACE["connections"].append(link)
            component.setdefault("relationships", []).append(link)
        _broadcast_to_hud("spatial_connection_created", link)
        return {"ok": True, "connection": link}
    return {"ok": False, "error": f"Operação espacial desconhecida: {operation}"}

def remove_spatial_component(component_id: str) -> Dict[str, Any]:
    """Remove um componente individual do Workspace mantendo os demais intactos."""
    global _ACTIVE_SPATIAL_WORKSPACE
    if not _ACTIVE_SPATIAL_WORKSPACE or component_id not in _ACTIVE_SPATIAL_WORKSPACE["components"]:
        return {"ok": False, "error": f"Componente '{component_id}' não existe."}

    del _ACTIVE_SPATIAL_WORKSPACE["components"][component_id]
    _ACTIVE_SPATIAL_WORKSPACE["updated_at"] = time.time()
    _broadcast_to_hud("spatial_component_removed", {"component_id": component_id})
    return {"ok": True, "component_id": component_id}

def highlight_spatial_component(component_id: str, duration_sec: float = 3.0) -> Dict[str, Any]:
    """Destaca temporariamente um componente específico (sincronização com narração de fala)."""
    _broadcast_to_hud("spatial_component_highlighted", {"component_id": component_id, "duration": duration_sec})
    return {"ok": True, "component_id": component_id, "highlighted": True}

def clear_spatial_workspace() -> Dict[str, Any]:
    """Limpa e desativa o Spatial Workspace."""
    global _ACTIVE_SPATIAL_WORKSPACE
    _ACTIVE_SPATIAL_WORKSPACE = None
    _broadcast_to_hud("spatial_workspace_cleared", {})
    return {"ok": True, "message": "Spatial Workspace limpo com sucesso."}

def compose_spatial_scene(title: str, subtitle: str = "", components: List[Dict[str, Any]] = None, layout: str = "freeform") -> Dict[str, Any]:
    """
    Constrói de uma só vez uma composição espacial rica com múltiplos componentes
    coexistindo de forma harmoniosa no Spatial Workspace.
    """
    create_spatial_workspace(title=title, subtitle=subtitle, layout=layout)
    comps = components or []
    for c in comps:
        cid = c.get("id") or f"comp_{int(time.time()*1000)}"
        c_type = c.get("type") or "hero_card"
        pos = c.get("position") or {}
        props = c.get("props") or c
        add_spatial_component(cid, c_type, pos, props)

    return {
        "ok": True,
        "title": title,
        "total_components": len(comps),
        "message": f"Cena espacial '{title}' composta com {len(comps)} elementos vivos."
    }
