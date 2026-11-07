"""
J.A.R.V.I.S. — Subagent & Parallel Task Execution Manager
Permite disparar subagentes assíncronos em segundo plano para executar múltiplas tarefas
simultaneamente (ex.: pesquisas, automação Windows, chamadas de ferramentas) enquanto
o núcleo principal continua conversando e atendendo o Senhor Werik.
"""

import threading
import time
import uuid
import logging
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Dict, Any, Optional, Callable, List

logger = logging.getLogger("JarvisSubagentManager")

class SubagentTask:
    def __init__(self, task_id: str, prompt: str, target: str = "general"):
        self.task_id = task_id
        self.prompt = prompt
        self.target = target
        self.created_at = time.time()
        self.completed_at: Optional[float] = None
        self.status = "running"  # running | completed | cancelled | failed
        self.result: Optional[str] = None
        self.future: Optional[Future] = None

class SubagentManager:
    def __init__(self):
        self._pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="SubagentWorker")
        self._active_tasks: Dict[str, SubagentTask] = {}
        self._lock = threading.Lock()

    def spawn_task(self, prompt: str, on_complete: Optional[Callable[[str, str], None]] = None) -> SubagentTask:
        """Dispara um subagente autônomo em thread paralela para executar a tarefa sem bloquear o fluxo principal."""
        task_id = f"sub_{uuid.uuid4().hex[:8]}"
        task = SubagentTask(task_id, prompt)

        def _worker():
            logger.info(f"[SubagentManager] Subagente {task_id} iniciando execução de: '{prompt}'")
            try:
                from core_ai_brain import query_direct_ai
                ctx = f"[TAREFA EXECUTADA EM SEGUNDO PLANO POR SUBAGENTE AUTÔNOMO: '{prompt}']"
                res = query_direct_ai(prompt, context=ctx)
                task.result = res
                task.status = "completed"
                task.completed_at = time.time()
                dur = round(task.completed_at - task.created_at, 1)
                logger.info(f"[SubagentManager] Subagente {task_id} concluiu tarefa em {dur}s: {res[:80]}...")

                # Notifica HUD via SSE e Toast
                try:
                    from core.local_server import broadcast_hud_event
                    broadcast_hud_event("toast", {"message": f"⚡ Subagente concluiu: {prompt[:35]}..."})
                    broadcast_hud_event("subagent_finished", {
                        "task_id": task_id,
                        "prompt": prompt,
                        "result": res,
                        "duration": dur
                    })
                except Exception:
                    pass

                if on_complete:
                    on_complete(task_id, res)
            except Exception as e:
                task.status = "failed"
                task.result = str(e)
                logger.error(f"[SubagentManager] Erro na execução do subagente {task_id}: {e}")

        with self._lock:
            task.future = self._pool.submit(_worker)
            self._active_tasks[task_id] = task

        # Dispara evento SSE avisando ao HUD que um subagente iniciou
        try:
            from core.local_server import broadcast_hud_event
            broadcast_hud_event("subagent_started", {"task_id": task_id, "prompt": prompt})
        except Exception:
            pass

        return task

    def cancel_all(self) -> int:
        """Interrompe e cancela todos os subagentes ativos."""
        count = 0
        with self._lock:
            for tid, t in list(self._active_tasks.items()):
                if t.status == "running":
                    t.status = "cancelled"
                    if t.future and not t.future.done():
                        t.future.cancel()
                    count += 1
            self._active_tasks.clear()

        if count > 0:
            try:
                from core.local_server import broadcast_hud_event
                broadcast_hud_event("toast", {"message": "🛑 Todas as tarefas e subagentes foram cancelados."})
                broadcast_hud_event("subagents_cancelled", {})
            except Exception:
                pass

        logger.info(f"[SubagentManager] {count} subagente(s) cancelado(s).")
        return count

    def get_active_tasks(self) -> List[Dict[str, Any]]:
        with self._lock:
            now = time.time()
            return [
                {
                    "task_id": t.task_id,
                    "prompt": t.prompt,
                    "status": t.status,
                    "duration": round(now - t.created_at, 1)
                }
                for t in self._active_tasks.values() if t.status == "running"
            ]

    def has_running_tasks(self) -> bool:
        with self._lock:
            return any(t.status == "running" for t in self._active_tasks.values())

_GLOBAL_MGR: Optional[SubagentManager] = None

def get_subagent_manager() -> SubagentManager:
    global _GLOBAL_MGR
    if _GLOBAL_MGR is None:
        _GLOBAL_MGR = SubagentManager()
    return _GLOBAL_MGR
