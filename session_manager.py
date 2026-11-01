"""
J.A.R.V.I.S. Session & Pending Action Manager
Padrão Permanente de Engenharia de Software Sênior & Guia de Arquitetura

Gerencia:
1. Histórico conversacional multi-turno por dispositivo/sessão (Sliding Window com TTL).
2. Protocolo determinístico de confirmação de ações críticas (gating com PendingAction).
"""

import time
import threading
import logging
from typing import Dict, List, Any, Optional, Tuple

logger = logging.getLogger("SessionManager")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [SessionManager] %(message)s")

AFFIRMATIVE_TERMS = {
    "sim", "confirmo", "confirma", "confirmar", "pode confirmar", "pode fazer",
    "pode desligar", "pode executar", "afirmativo", "positivo", "com certeza",
    "prossiga", "executar", "manda ver", "vai", "ok", "pode ir", "autorizado",
    "autorizo", "pode apagar", "pode reiniciar", "sim confirmo", "sim por favor",
    "pode apagar a luz", "pode desligar a luz", "pode desligar o pc"
}

NEGATIVE_TERMS = {
    "não", "nao", "cancela", "cancelar", "abortar", "aborta", "esquece",
    "deixa pra lá", "deixa quieto", "negativo", "não quero", "nao quero",
    "cancela isso", "pare", "parar", "cancelado", "abortado"
}


class ConversationSessionManager:
    def __init__(self, ttl_seconds: int = 900, max_turns: int = 6):
        """
        ttl_seconds: 900s (15 min) de inatividade expira a sessão.
        max_turns: Mantém até 6 turnos (12 mensagens: 6 do usuário, 6 do assistente).
        """
        self.ttl = ttl_seconds
        self.max_turns = max_turns
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.pending_actions: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.Lock()

    def _normalize_session_id(self, session_id: Optional[str]) -> str:
        if not session_id:
            return "default_session"
        s = str(session_id).strip()
        return s if s else "default_session"

    def get_history(self, session_id: str) -> List[Dict[str, str]]:
        sid = self._normalize_session_id(session_id)
        now = time.time()
        with self.lock:
            sess = self.sessions.get(sid)
            if not sess:
                return []
            if now - sess.get("last_active", 0) > self.ttl:
                sess["history"] = []
                return []
            return [dict(m) for m in sess.get("history", [])]

    def add_turn(self, session_id: str, user_msg: str, assistant_reply: str):
        if not user_msg or not assistant_reply:
            return
        sid = self._normalize_session_id(session_id)
        now = time.time()
        with self.lock:
            if sid not in self.sessions:
                self.sessions[sid] = {"last_active": now, "history": []}
            sess = self.sessions[sid]
            sess["last_active"] = now
            hist = sess["history"]
            hist.append({"role": "user", "content": str(user_msg).strip()})
            hist.append({"role": "assistant", "content": str(assistant_reply).strip()})
            max_msgs = self.max_turns * 2
            if len(hist) > max_msgs:
                sess["history"] = hist[-max_msgs:]

    def set_pending_action(self, session_id: str, action: str, description: str,
                           payload: Optional[Dict[str, Any]] = None, timeout: int = 60):
        sid = self._normalize_session_id(session_id)
        now = time.time()
        with self.lock:
            self.pending_actions[sid] = {
                "action": action,
                "description": description,
                "payload": payload or {},
                "expires_at": now + timeout
            }
            logger.info(f"Ação pendente registrada para '{sid}': {action} ({description}), expira em {timeout}s")

    def get_pending_action(self, session_id: str) -> Optional[Dict[str, Any]]:
        sid = self._normalize_session_id(session_id)
        now = time.time()
        with self.lock:
            act = self.pending_actions.get(sid)
            if not act:
                return None
            if now > act.get("expires_at", 0):
                del self.pending_actions[sid]
                return None
            return dict(act)

    def clear_pending_action(self, session_id: str):
        sid = self._normalize_session_id(session_id)
        with self.lock:
            if sid in self.pending_actions:
                del self.pending_actions[sid]

    def check_intent_confirmation(self, session_id: str, user_msg: str) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """
        Verifica se há ação pendente para esta sessão e se o usuário respondeu afirmativa ou negativamente.
        Retorna (status, pending_action_info):
            status = 'confirmed' | 'cancelled' | None
        """
        sid = self._normalize_session_id(session_id)
        pending = self.get_pending_action(sid)
        if not pending:
            return None, None

        msg_clean = user_msg.lower().strip()
        for ch in ",.!?;:-_":
            msg_clean = msg_clean.replace(ch, " ")
        words = msg_clean.split()
        joined = " ".join(words)

        is_affirmative = (
            joined in AFFIRMATIVE_TERMS or
            any(w in AFFIRMATIVE_TERMS for w in words) or
            any(joined.startswith(t) or joined.endswith(t) for t in ["sim", "confirmo", "positivo", "afirmativo", "pode fazer", "pode desligar", "pode executar", "pode apagar"])
        )

        is_negative = (
            joined in NEGATIVE_TERMS or
            any(w in NEGATIVE_TERMS for w in words) or
            any(joined.startswith(t) or joined.endswith(t) for t in ["não", "nao", "cancela", "abortar", "esquece", "deixa"])
        )

        if is_affirmative:
            self.clear_pending_action(sid)
            logger.info(f"Ação pendente CONFIRMADA para '{sid}': {pending.get('action')}")
            return "confirmed", pending

        if is_negative:
            self.clear_pending_action(sid)
            logger.info(f"Ação pendente CANCELADA para '{sid}': {pending.get('action')}")
            return "cancelled", pending

        return None, pending


# Singleton global
session_manager = ConversationSessionManager(ttl_seconds=900, max_turns=6)
