import os
import sys
import time
from typing import Dict, Any, Optional

# Garante acesso à ponte do Windows
try:
    from desktop.windows_bridge import bridge
except Exception:
    sys.path.insert(0, r"c:\JARVIS")
    from desktop.windows_bridge import bridge

import hardware_control as hc
from .config import VisionConfig

class WindowsActions:
    """
    Decoupled Windows Action Controller for Jarvis Vision & OpenClaw.
    - Delegado diretamente para o WindowsBridge (Win32 API + Mark-LV controls).
    - Validação de segurança: Safe (execução direta) vs High-Risk (requer confirmação).
    """

    def __init__(self, config: Optional[VisionConfig] = None):
        self.config = config or VisionConfig()

    def execute(self, action_name: str, target: str = "", risk_level: str = "low", force_confirmed: bool = False) -> Dict[str, Any]:
        """
        Executa uma ação no Windows com validação de segurança e retorno estruturado.
        """
        action = action_name.lower().strip()
        
        # 1. VALIDAÇÃO DE SEGURANÇA
        dangerous_ops = self.config.get("security", "require_confirmation_for", default=[])
        is_dangerous = any(d in action for d in dangerous_ops) or risk_level == "high"

        if is_dangerous and not force_confirmed:
            print(f"[SECURITY ALERT] Ação de alto risco '{action}' bloqueada: requer confirmação explícita!")
            return {
                "status": "requires_confirmation",
                "action": action,
                "message": f"Ação de segurança '{action}' requer confirmação explícita do Senhor Werik ou do OpenClaw."
            }

        result = {"status": "ok", "action": action, "message": ""}

        try:
            # 2. EXECUÇÃO VIA WINDOWS BRIDGE (Nativo Win32 API)
            if action in ["open_app", "launch", "abrir"]:
                app_target = target or "chrome"
                res = bridge.launch_app(app_target)
                result["message"] = f"Aplicativo '{app_target}' iniciado com sucesso."
                result["details"] = res
            else:
                res = bridge.execute(action, app=target, text=target)
                result["status"] = res.get("status", "ok")
                result["details"] = res
                
                # Mensagens amigáveis em português
                msg_map = {
                    "play_pause": "Mídia pausada ou retomada (Play/Pause).",
                    "media_play_pause": "Mídia pausada ou retomada (Play/Pause).",
                    "next_track": "Avançado para a próxima faixa multimídia.",
                    "prev_track": "Retornado para a faixa anterior.",
                    "volume_up": "Volume principal aumentado.",
                    "volume_down": "Volume principal reduzido.",
                    "volume_mute": "Áudio do sistema silenciado ou restaurado.",
                    "mute": "Áudio do sistema silenciado ou restaurado.",
                    "minimize_all": "Todas as janelas minimizadas. Área de trabalho visível.",
                    "switch_window": "Alternando para a próxima janela ativa.",
                    "lock_screen": "Estação de trabalho Windows bloqueada com segurança.",
                    "confirm": "Ação confirmada por gesto.",
                    "cancel": "Ação cancelada por gesto.",
                    "scroll_up": "Página rolada para cima.",
                    "scroll_down": "Página rolada para baixo.",
                    "zoom_in": "Zoom aumentado.",
                    "zoom_out": "Zoom reduzido."
                }
                result["message"] = msg_map.get(action, res.get("message", f"Ação '{action}' executada."))

        except Exception as e:
            result["status"] = "error"
            result["message"] = f"Erro ao executar '{action}': {e}"
            print(f"[WindowsActions] Erro: {e}")

        hc.record_local_action(action)
        return result
