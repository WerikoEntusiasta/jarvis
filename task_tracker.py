"""
J.A.R.V.I.S. Task Execution Tracker & Live Activity Logger
Gerenciador central do estado de tarefas em tempo real, etapas, métodos e logs visuais.
Padrão Permanente de Engenharia de Software Sênior.
"""

import time
import json
import logging
import threading
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger("TaskTracker")
logger.setLevel(logging.INFO)

_LOCK = threading.Lock()

_CURRENT_TASK: Dict[str, Any] = {
    "id": "idle",
    "title": "Aguardando Instruções",
    "status": "idle",             # idle, thinking, executing, verifying, completed, error
    "status_label": "STANDBY",
    "start_time": time.time(),
    "elapsed_seconds": 0.0,
    "current_step": 0,
    "total_steps": 0,
    "step_name": "Aguardando novo comando do Senhor Werik",
    "method": "Aguardando ativação",
    "progress_percent": 0,
    "summary": "",
    "logs": [
        {
            "time": datetime.now().strftime("%H:%M:%S"),
            "icon": "🟢",
            "message": "J.A.R.V.I.S. Online. Sistema pronto.",
            "type": "info"
        }
    ]
}

_RECENT_TASKS: List[Dict[str, Any]] = []
_MAX_LOGS = 60
_MAX_HISTORY = 15

# Callback opcional para emitir SSE via local_server
_DISPATCH_CALLBACK = None

def set_dispatch_callback(callback):
    """Define a função de callback para transmitir eventos SSE via local_server."""
    global _DISPATCH_CALLBACK
    _DISPATCH_CALLBACK = callback

def _notify_hud():
    """Notifica o HUD via SSE quando o estado muda."""
    notified = False
    if _DISPATCH_CALLBACK:
        try:
            with _LOCK:
                task_copy = dict(_CURRENT_TASK)
                task_copy["logs"] = list(_CURRENT_TASK.get("logs", []))[-25:]
            _DISPATCH_CALLBACK("task_event", task_copy)
            notified = True
        except Exception as e:
            logger.debug("Erro ao notificar HUD via callback: %s", e)

    if not notified:
        try:
            from core.local_server import broadcast_hud_event
            with _LOCK:
                task_copy = dict(_CURRENT_TASK)
                task_copy["logs"] = list(_CURRENT_TASK.get("logs", []))[-25:]
            broadcast_hud_event("task_event", task_copy)
            notified = True
        except Exception:
            pass

    # Sincroniza via HTTP se chamado de outro processo ou nó remoto
    def _http_sync():
        try:
            import urllib.request
            with _LOCK:
                payload = json.dumps(_CURRENT_TASK).encode("utf-8")
            req = urllib.request.Request(
                "http://127.0.0.1:8085/api/task/event",
                data=payload,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=0.25):
                pass
        except Exception:
            pass

    threading.Thread(target=_http_sync, daemon=True).start()


def start_task(title: str, description: str = "", total_steps: int = 1, method: str = "Processamento Cognitivo") -> Dict[str, Any]:
    """Inicia o rastreamento de uma nova tarefa em tempo real."""
    global _CURRENT_TASK
    now_str = datetime.now().strftime("%H:%M:%S")
    with _LOCK:
        task_id = f"task_{int(time.time() * 1000)}"
        _CURRENT_TASK = {
            "id": task_id,
            "title": title.strip() or "Tarefa em Execução",
            "description": description.strip(),
            "status": "executing",
            "status_label": "EXECUTANDO",
            "start_time": time.time(),
            "elapsed_seconds": 0.0,
            "current_step": 1,
            "total_steps": max(1, total_steps),
            "step_name": description.strip() or "Iniciando plano de execução",
            "method": method.strip() or "Processamento Neural",
            "progress_percent": 15,
            "summary": "",
            "logs": [
                {
                    "time": now_str,
                    "icon": "🚀",
                    "message": f"Iniciando: {title[:75]}",
                    "type": "start"
                }
            ]
        }
    _notify_hud()
    return _CURRENT_TASK


def update_step(step: int, total_steps: Optional[int] = None, step_name: str = "", method: str = "", status: str = "executing") -> Dict[str, Any]:
    """Atualiza o estágio atual da tarefa, método e percentual de conclusão."""
    global _CURRENT_TASK
    with _LOCK:
        if total_steps is not None and total_steps > 0:
            _CURRENT_TASK["total_steps"] = total_steps
        _CURRENT_TASK["current_step"] = step
        if step_name:
            _CURRENT_TASK["step_name"] = step_name
        if method:
            _CURRENT_TASK["method"] = method
        
        tot = _CURRENT_TASK.get("total_steps", 1) or 1
        pct = min(95, int((step / float(tot)) * 90))
        _CURRENT_TASK["progress_percent"] = pct
        _CURRENT_TASK["status"] = status
        
        status_labels = {
            "executing": "EXECUTANDO",
            "thinking": "RACIOCINANDO",
            "verifying": "INSPECIONANDO TELA",
            "completed": "CONCLUÍDO",
            "error": "FALHA / ALERTA"
        }
        _CURRENT_TASK["status_label"] = status_labels.get(status, "PROCESSANDO")
        _CURRENT_TASK["elapsed_seconds"] = round(time.time() - _CURRENT_TASK.get("start_time", time.time()), 1)
        
    _notify_hud()
    return _CURRENT_TASK


def add_log(message: str, icon: str = "⚡", log_type: str = "info", tool: Optional[str] = None) -> Dict[str, Any]:
    """Adiciona uma linha no feed de logs da tarefa em tempo real."""
    global _CURRENT_TASK
    now_str = datetime.now().strftime("%H:%M:%S")
    entry = {
        "time": now_str,
        "icon": icon,
        "message": message.strip(),
        "type": log_type,
        "tool": tool or ""
    }
    with _LOCK:
        logs = _CURRENT_TASK.setdefault("logs", [])
        logs.append(entry)
        if len(logs) > _MAX_LOGS:
            _CURRENT_TASK["logs"] = logs[-_MAX_LOGS:]
        _CURRENT_TASK["elapsed_seconds"] = round(time.time() - _CURRENT_TASK.get("start_time", time.time()), 1)
        
    _notify_hud()
    return entry


def finish_task(success: bool = True, summary: str = "") -> Dict[str, Any]:
    """Finaliza a tarefa ativa, marcando como concluída com sucesso ou erro."""
    global _CURRENT_TASK, _RECENT_TASKS
    now_str = datetime.now().strftime("%H:%M:%S")
    with _LOCK:
        elapsed = round(time.time() - _CURRENT_TASK.get("start_time", time.time()), 1)
        _CURRENT_TASK["elapsed_seconds"] = elapsed
        _CURRENT_TASK["progress_percent"] = 100
        _CURRENT_TASK["summary"] = summary.strip()
        
        if success:
            _CURRENT_TASK["status"] = "completed"
            _CURRENT_TASK["status_label"] = "CONCLUÍDO"
            _CURRENT_TASK["step_name"] = "Tarefa concluída com sucesso"
            _CURRENT_TASK.setdefault("logs", []).append({
                "time": now_str,
                "icon": "✅",
                "message": summary.strip() or f"Concluído com êxito em {elapsed}s",
                "type": "success"
            })
        else:
            _CURRENT_TASK["status"] = "error"
            _CURRENT_TASK["status_label"] = "ERRO"
            _CURRENT_TASK["step_name"] = "Falha na execução"
            _CURRENT_TASK.setdefault("logs", []).append({
                "time": now_str,
                "icon": "❌",
                "message": summary.strip() or f"Execução interrompida após {elapsed}s",
                "type": "error"
            })
            
        # Salva no histórico recente
        _RECENT_TASKS.insert(0, dict(_CURRENT_TASK))
        if len(_RECENT_TASKS) > _MAX_HISTORY:
            _RECENT_TASKS = _RECENT_TASKS[:_MAX_HISTORY]
            
    _notify_hud()
    return _CURRENT_TASK


def get_current_task() -> Dict[str, Any]:
    """Retorna o estado completo da tarefa em execução."""
    with _LOCK:
        res = dict(_CURRENT_TASK)
        if _CURRENT_TASK.get("status") in ("executing", "thinking", "verifying"):
            res["elapsed_seconds"] = round(time.time() - _CURRENT_TASK.get("start_time", time.time()), 1)
        res["logs"] = list(_CURRENT_TASK.get("logs", []))
        return res


def get_recent_history() -> List[Dict[str, Any]]:
    """Retorna a lista de tarefas concluídas recentemente."""
    with _LOCK:
        return [dict(t) for t in _RECENT_TASKS]
