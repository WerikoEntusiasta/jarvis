"""
J.A.R.V.I.S. — Módulo de Automação de Interface Windows via PyWinAuto
=============================================================================
Padrão Permanente de Engenharia de Software Sênior & Alta Confiabilidade.
Permite ao J.A.R.V.I.S. inspecionar, ler e interagir com janelas e controles nativos
do Windows através da árvore de acessibilidade (UIA / Win32).
"""

import os
import sys
import time
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("WinAutomationPyWinAuto")
logger.setLevel(logging.INFO)

def _switch_to_user_desktop():
    """Garante vinculação da thread ao desktop interativo WinSta0\\Default."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        GENERIC_ALL = 0x10000000
        hwinsta = user32.OpenWindowStationW("WinSta0", False, GENERIC_ALL)
        if hwinsta:
            user32.SetProcessWindowStation(hwinsta)
        hdesk = user32.OpenDesktopW("Default", 0, False, GENERIC_ALL)
        if hdesk:
            user32.SetThreadDesktop(hdesk)
    except Exception:
        pass

def is_pywinauto_available() -> bool:
    try:
        import pywinauto
        return True
    except ImportError:
        return False

def list_windows(visible_only: bool = True) -> List[Dict[str, Any]]:
    """Lista janelas ativas no desktop com título, classe e PID."""
    _switch_to_user_desktop()
    results = []
    try:
        from pywinauto import Desktop
        desktop = Desktop(backend="uia")
        windows = desktop.windows(visible_only=visible_only)
        for w in windows:
            try:
                title = w.window_text().strip()
                if visible_only and not title:
                    continue
                rect = w.rectangle()
                results.append({
                    "title": title,
                    "class_name": w.class_name(),
                    "process_id": w.process_id(),
                    "rect": {"left": rect.left, "top": rect.top, "right": rect.right, "bottom": rect.bottom},
                    "is_visible": w.is_visible(),
                    "is_enabled": w.is_enabled()
                })
            except Exception:
                continue
    except Exception as e:
        logger.error(f"[PyWinAuto] Erro ao listar janelas: {e}")
    return results

def inspect_controls(window_title: str, backend: str = "uia", max_depth: int = 2) -> Dict[str, Any]:
    """Inspeciona e lista os controles e elementos interativos de uma janela."""
    _switch_to_user_desktop()
    try:
        from pywinauto import Application
        app = Application(backend=backend).connect(title_re=f".*{window_title}.*", timeout=5)
        dlg = app.top_window()
        
        controls = []
        for ctrl in dlg.descendants()[:50]:  # Limite de segurança
            try:
                text = ctrl.window_text().strip()
                c_type = ctrl.friendly_class_name()
                auto_id = getattr(ctrl.element_info, "automation_id", "")
                if text or auto_id:
                    controls.append({
                        "control_type": c_type,
                        "text": text[:60],
                        "automation_id": auto_id,
                        "is_enabled": ctrl.is_enabled(),
                        "is_visible": ctrl.is_visible()
                    })
            except Exception:
                continue

        return {
            "ok": True,
            "window_title": dlg.window_text(),
            "controls_count": len(controls),
            "controls": controls
        }
    except Exception as e:
        return {"ok": False, "error": f"Falha ao inspecionar controles da janela '{window_title}': {e}"}

def type_into_window(window_title: str, text_to_type: str, control_title: Optional[str] = None, backend: str = "uia") -> Dict[str, Any]:
    """Digita texto diretamente em uma janela ou controle específico via PyWinAuto."""
    _switch_to_user_desktop()
    try:
        from pywinauto import Application
        app = Application(backend=backend).connect(title_re=f".*{window_title}.*", timeout=6)
        dlg = app.top_window()
        dlg.set_focus()
        time.sleep(0.3)

        if control_title:
            ctrl = dlg.child_window(title_re=f".*{control_title}.*")
            ctrl.type_keys(text_to_type, with_spaces=True)
        else:
            dlg.type_keys(text_to_type, with_spaces=True)

        return {"ok": True, "message": f"Texto enviado com sucesso para a janela '{window_title}'."}
    except Exception as e:
        # Fallback para backend alternativo win32 caso uia falhe
        if backend == "uia":
            logger.info("[PyWinAuto] Tentando fallback para backend win32...")
            return type_into_window(window_title, text_to_type, control_title, backend="win32")
        return {"ok": False, "error": f"Erro ao digitar na janela '{window_title}': {e}"}

def click_control_in_window(window_title: str, control_title: str, backend: str = "uia") -> Dict[str, Any]:
    """Clica em um controle ou botão específico de uma janela."""
    _switch_to_user_desktop()
    try:
        from pywinauto import Application
        app = Application(backend=backend).connect(title_re=f".*{window_title}.*", timeout=6)
        dlg = app.top_window()
        dlg.set_focus()
        time.sleep(0.2)

        ctrl = dlg.child_window(title_re=f".*{control_title}.*")
        ctrl.click_input()

        return {"ok": True, "message": f"Controle '{control_title}' clicado na janela '{window_title}'."}
    except Exception as e:
        if backend == "uia":
            return click_control_in_window(window_title, control_title, backend="win32")
        return {"ok": False, "error": f"Erro ao clicar em '{control_title}': {e}"}

def launch_app_and_focus(command_or_path: str, expected_title: str, timeout: int = 8) -> Dict[str, Any]:
    """Abre um aplicativo Windows e aguarda até que sua janela esteja pronta e focada."""
    _switch_to_user_desktop()
    try:
        from pywinauto import Application
        app = Application(backend="uia").start(command_or_path)
        time.sleep(1.0)
        
        dlg = app.window(title_re=f".*{expected_title}.*")
        dlg.wait("ready", timeout=timeout)
        dlg.set_focus()

        return {
            "ok": True,
            "pid": app.process,
            "window_title": dlg.window_text(),
            "message": f"Aplicativo '{expected_title}' iniciado e pronto para interação."
        }
    except Exception as e:
        return {"ok": False, "error": f"Erro ao iniciar aplicativo '{expected_title}': {e}"}

def close_window(window_title: str, backend: str = "uia") -> Dict[str, Any]:
    """Fecha com segurança uma janela do Windows pelo título."""
    _switch_to_user_desktop()
    try:
        from pywinauto import Application
        app = Application(backend=backend).connect(title_re=f".*{window_title}.*", timeout=5)
        dlg = app.top_window()
        dlg.close()
        return {"ok": True, "message": f"Janela '{window_title}' fechada com sucesso."}
    except Exception as e:
        return {"ok": False, "error": f"Erro ao fechar janela '{window_title}': {e}"}
