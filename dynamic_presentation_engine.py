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
        "smart_canvas", "canvas"
    }

    for idx, sc in enumerate(scenes):
        if not isinstance(sc, dict):
            continue
        c_type = str(sc.get("component_type") or sc.get("type") or "hologram_card").lower()
        if c_type not in valid_types:
            c_type = "hologram_card"

        scene_obj = {
            "scene_id": str(sc.get("scene_id") or f"scene_{idx + 1}"),
            "title": str(sc.get("title") or f"Cena {idx + 1}"),
            "subtitle": str(sc.get("subtitle", "")),
            "component_type": c_type,
            "content": str(sc.get("content", "")),
            "duration_sec": float(sc.get("duration_sec", 0)),
            "bullets": sc.get("bullets", []),
            "tags": sc.get("tags", []),
            "metrics": sc.get("metrics", []),
            "data": sc.get("data", {}),
            "media": sc.get("media", {}),
            "thumbnail": sc.get("thumbnail", ""),
            "caption": sc.get("caption", ""),
            "nodes": sc.get("nodes", []),
            "headers": sc.get("headers", []),
            "rows": sc.get("rows", []),
            "item_a": sc.get("item_a", {}),
            "item_b": sc.get("item_b", {}),
            "markers": sc.get("markers", []),
            "conclusion": sc.get("conclusion", ""),
            "summary_points": sc.get("summary_points", []),
            "actions": sc.get("actions", []),
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
