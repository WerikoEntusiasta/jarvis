"""
Decoupled Windows Action Controller for Jarvis Vision & Gestures.
Executa ações locais seguras no Windows através de system.win_controls e pc_automation.
Padrão Permanente de Engenharia de Software Sênior.
"""

import os
import sys
import time
from typing import Dict, Any, Optional
from pathlib import Path

# Garante inclusão de jarvis-windows no sys.path
_ROOT = Path(__file__).resolve().parent.parent
for p in [str(_ROOT), str(_ROOT / "jarvis-windows")]:
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from system import win_controls, pc_automation
except ImportError:
    try:
        from ..system import win_controls, pc_automation
    except Exception:
        win_controls = None
        pc_automation = None

from .config import VisionConfig

class WindowsActions:
    """
    Decoupled Windows Action Controller for Jarvis Vision & OpenClaw.
    - Delegado diretamente para win_controls e pc_automation.
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
            if not win_controls:
                return {"status": "error", "message": "Módulo de controle do Windows não disponível"}

            if action in ["open_app", "launch", "abrir"]:
                app_target = target or "chrome"
                res = win_controls.open_application(app_target)
                result["message"] = f"Aplicativo '{app_target}' iniciado com sucesso."
                result["details"] = res

            elif action in ["play_pause", "media_play_pause"]:
                res = win_controls.control_media("play_pause")
                result["message"] = "Mídia pausada ou retomada (Play/Pause)."
                result["details"] = res

            elif action in ["next_track", "proxima"]:
                res = win_controls.control_media("next")
                result["message"] = "Avançado para a próxima faixa multimídia."
                result["details"] = res

            elif action in ["prev_track", "anterior"]:
                res = win_controls.control_media("prev")
                result["message"] = "Retornado para a faixa anterior."
                result["details"] = res

            elif action in ["volume_up", "aumentar_volume"]:
                res = win_controls.control_volume("up", steps=5)
                result["message"] = "Volume principal aumentado."
                result["details"] = res

            elif action in ["volume_down", "diminuir_volume"]:
                res = win_controls.control_volume("down", steps=5)
                result["message"] = "Volume principal reduzido."
                result["details"] = res

            elif action in ["volume_mute", "mute", "silenciar"]:
                res = win_controls.control_volume("mute")
                result["message"] = "Áudio do sistema silenciado ou restaurado."
                result["details"] = res

            elif action in ["minimize_all", "minimizar"]:
                res = win_controls.minimize_all()
                result["message"] = "Todas as janelas minimizadas. Área de trabalho visível."
                result["details"] = res

            elif action in ["switch_window", "alternar_janela"]:
                res = win_controls.switch_window()
                result["message"] = "Alternando para a próxima janela ativa."
                result["details"] = res

            elif action in ["lock_screen", "bloquear_pc"]:
                res = win_controls.lock_workstation()
                result["message"] = "Estação de trabalho Windows bloqueada com segurança."
                result["details"] = res

            elif action in ["scroll_up", "rolar_cima"]:
                if pc_automation:
                    res = pc_automation.mouse_scroll(clicks=5, direction="up")
                    result["message"] = "Página rolada para cima."
                    result["details"] = res

            elif action in ["scroll_down", "rolar_baixo"]:
                if pc_automation:
                    res = pc_automation.mouse_scroll(clicks=5, direction="down")
                    result["message"] = "Página rolada para baixo."
                    result["details"] = res

            elif action in ["confirm"]:
                result["message"] = "Ação confirmada por gesto."

            elif action in ["cancel"]:
                result["message"] = "Ação cancelada por gesto."

            else:
                result["message"] = f"Ação '{action}' processada."

        except Exception as e:
            result["status"] = "error"
            result["message"] = f"Erro ao executar '{action}': {e}"
            print(f"[WindowsActions] Erro: {e}")

        try:
            import hardware_control as hc
            hc.record_local_action(action)
        except Exception:
            pass

        return result
