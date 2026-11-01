"""
Servidor e Despachador de Ferramentas MCP Nativas do Windows
Permite ao J.A.R.V.I.S. e OpenClaw executarem ferramentas locais do Windows.
"""

from typing import Dict, Any, List
try:
    from system import win_controls, hardware_monitor, pc_automation
except ImportError:
    from ..system import win_controls, hardware_monitor, pc_automation

WINDOWS_MCP_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "executar_comando_windows",
        "description": "Executa um comando ou script PowerShell no Windows e retorna o output.",
        "parameters": {
            "type": "object",
            "properties": {
                "comando": {"type": "string", "description": "Comando PowerShell a ser executado"}
            },
            "required": ["comando"]
        }
    },
    {
        "name": "abrir_programa_windows",
        "description": "Abre um aplicativo ou site no Windows (ex: chrome, spotify, notepad, vscode, calc).",
        "parameters": {
            "type": "object",
            "properties": {
                "aplicativo": {"type": "string", "description": "Nome do programa ou URL"}
            },
            "required": ["aplicativo"]
        }
    },
    {
        "name": "fechar_programa_windows",
        "description": "Encerra um processo em execução no Windows.",
        "parameters": {
            "type": "object",
            "properties": {
                "processo": {"type": "string", "description": "Nome do processo (ex: notepad.exe, chrome.exe)"}
            },
            "required": ["processo"]
        }
    },
    {
        "name": "controlar_volume_windows",
        "description": "Ajusta ou silencia o volume do Windows.",
        "parameters": {
            "type": "object",
            "properties": {
                "acao": {"type": "string", "enum": ["up", "down", "mute"], "description": "Aumentar, diminuir ou mutar"}
            },
            "required": ["acao"]
        }
    },
    {
        "name": "controlar_midia_windows",
        "description": "Controla a reprodução de música/vídeo (Spotify, YouTube, VLC).",
        "parameters": {
            "type": "object",
            "properties": {
                "acao": {"type": "string", "enum": ["play_pause", "next", "prev", "stop"], "description": "Comando de reprodução"}
            },
            "required": ["acao"]
        }
    },
    {
        "name": "obter_telemetria_hardware",
        "description": "Retorna o uso em tempo real de CPU %, RAM %, GPU NVIDIA (temperatura, VRAM, util) e disco do Windows.",
        "parameters": {"type": "object", "properties": {}}
    }
]

def dispatch_mcp_tool(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    tool = tool_name.lower().strip()
    args = arguments or {}

    if tool in ["executar_comando_windows", "powershell", "system_command"]:
        return win_controls.run_powershell(args.get("comando", ""))

    elif tool in ["abrir_programa_windows", "abrir_app", "open_app"]:
        target = args.get("aplicativo", "") or args.get("nome", "") or args.get("target", "")
        return win_controls.open_application(target)

    elif tool in ["google_search", "pesquisar_google", "pesquisa_web", "web_search", "buscar_google"]:
        query = str(args.get("query", "") or args.get("termo", "") or args.get("busca", "") or args.get("q", ""))
        open_b = bool(args.get("open_browser", True))
        return win_controls.google_search(query, open_browser=open_b)

    elif tool in ["fechar_programa_windows", "fechar_app", "close_app"]:
        target = args.get("processo", "") or args.get("nome", "") or args.get("target", "") or args.get("app", "")
        return win_controls.close_application(target)

    elif tool in ["controlar_volume_windows", "volume", "volume_set", "pc_volume"]:
        action = args.get("action", args.get("acao", "up"))
        steps = int(args.get("steps", args.get("passos", 5)))
        return win_controls.control_volume(action, steps)

    elif tool in ["controlar_midia_windows", "media", "spotify_control", "pc_media"]:
        action = args.get("action", args.get("acao", "play_pause"))
        return win_controls.control_media(action)

    elif tool in ["self_reload_hud", "reload_hud", "reload"]:
        try:
            from self_evolution import self_reload_hud
            return self_reload_hud()
        except Exception as e:
            return {"ok": False, "erro": str(e)}

    elif tool in ["generate_and_show_screen", "laya_screen"]:
        try:
            from laya_screen_subagent import get_laya_agent
            laya = get_laya_agent()
            prompt = str(args.get("prompt", ""))
            hint = str(args.get("context_hint", ""))
            full_prompt = f"{prompt} | Contexto: {hint}" if hint else prompt
            screen_res = laya.generate_screen(full_prompt)
            if screen_res.get("ok"):
                laya.broadcast_to_hud(screen_res["screen"])
                return {"ok": True, "info": f"Tela '{screen_res['screen'].get('title')}' gerada no HUD."}
            return {"ok": False, "erro": screen_res.get("error")}
        except Exception as e:
            return {"ok": False, "erro": str(e)}

    elif tool in ["close_screen"]:
        try:
            from laya_screen_subagent import get_laya_agent
            get_laya_agent().close_screen()
            return {"ok": True, "info": "Tela LAYA fechada."}
        except Exception as e:
            return {"ok": False, "erro": str(e)}

    elif tool in ["obter_telemetria_hardware", "telemetria", "hardware"]:
        return {"success": True, "telemetry": hardware_monitor.get_system_telemetry()}

    elif tool in ["lock", "lock_pc", "bloquear_pc", "lock_workstation"]:
        return win_controls.lock_workstation()

    elif tool in ["system_power", "power", "shutdown", "restart", "sleep", "desligar_pc", "reiniciar_pc"]:
        act = str(args.get("action", "") or args.get("comando", "") or tool).lower()
        if "shut" in act or "deslig" in act:
            return win_controls.shutdown_pc()
        elif "rest" in act or "reini" in act:
            return win_controls.restart_pc()
        elif "sleep" in act or "susp" in act:
            return win_controls.sleep_pc()
        elif "lock" in act or "bloq" in act:
            return win_controls.lock_workstation()
        return win_controls.shutdown_pc()

    elif tool in ["minimize", "minimize_all", "minimizar", "minimizar_janelas"]:
        return win_controls.minimize_all()

    elif tool in ["tuya", "iluminacao", "luz", "lampada", "light", "controlar_luz"]:
        from services.tuya_service import tuya_service
        act = args.get("action", "") or args.get("acao", "") or args.get("estado", "")
        state = args.get("state", None)
        target = args.get("target", "setup") or args.get("device_id", "setup")
        if act == "on" or state is True:
            return tuya_service.turn_on(target)
        elif act == "off" or state is False:
            return tuya_service.turn_off(target)
        return tuya_service.toggle(target)

    # --------------------------------------------------------------------------
    # CONTROLE DE MOUSE (MOVIMENTO, CLIQUES, ROLAGEM, ARRASTO)
    # --------------------------------------------------------------------------
    elif tool in ["mouse_move", "mover_mouse"]:
        x = args.get("x", 0)
        y = args.get("y", 0)
        duration = float(args.get("duration", args.get("duracao", 0.2)))
        return pc_automation.mouse_move(x, y, duration)

    elif tool in ["mouse_move_rel", "mover_mouse_relativo"]:
        dx = args.get("dx", 0)
        dy = args.get("dy", 0)
        duration = float(args.get("duration", args.get("duracao", 0.2)))
        return pc_automation.mouse_move_rel(dx, dy, duration)

    elif tool in ["mouse_click", "clicar", "clique"]:
        btn = args.get("button", args.get("botao", "left"))
        clicks = int(args.get("clicks", args.get("cliques", 1)))
        interval = float(args.get("interval", 0.1))
        x = args.get("x")
        y = args.get("y")
        return pc_automation.mouse_click(button=btn, clicks=clicks, interval=interval, x=x, y=y)

    elif tool in ["mouse_double_click", "duplo_clique"]:
        x = args.get("x")
        y = args.get("y")
        return pc_automation.mouse_click(button="left", clicks=2, x=x, y=y)

    elif tool in ["mouse_right_click", "clique_direito"]:
        x = args.get("x")
        y = args.get("y")
        return pc_automation.mouse_click(button="right", clicks=1, x=x, y=y)

    elif tool in ["mouse_drag", "arrastar_mouse"]:
        x = args.get("x", 0)
        y = args.get("y", 0)
        duration = float(args.get("duration", 0.5))
        button = args.get("button", "left")
        return pc_automation.mouse_drag(x, y, duration, button)

    elif tool in ["mouse_scroll", "rolar_tela", "scroll"]:
        clicks = int(args.get("clicks", args.get("amount", args.get("passos", 5))))
        direction = args.get("direction", args.get("direcao", "down"))
        return pc_automation.mouse_scroll(clicks=clicks, direction=direction)

    elif tool in ["mouse_position", "posicao_mouse", "mouse_status"]:
        return pc_automation.get_mouse_position()

    # --------------------------------------------------------------------------
    # CONTROLE DE TECLADO (DIGITAÇÃO, TECLAS, ATALHOS)
    # --------------------------------------------------------------------------
    elif tool in ["keyboard_type", "digitar", "escrever"]:
        text = args.get("text", args.get("texto", ""))
        interval = float(args.get("interval", 0.01))
        return pc_automation.keyboard_type(text, interval)

    elif tool in ["keyboard_press", "pressionar_tecla", "tecla"]:
        key = args.get("key", args.get("tecla", "enter"))
        return pc_automation.keyboard_press(key)

    elif tool in ["keyboard_hotkey", "atalho", "hotkey"]:
        keys = args.get("keys", args.get("atalho", []))
        if isinstance(keys, str):
            keys = [k.strip() for k in keys.replace("+", " ").split()]
        return pc_automation.keyboard_hotkey(*keys)

    # --------------------------------------------------------------------------
    # CAPTURA DE TELA & ÁREA DE TRANSFERÊNCIA
    # --------------------------------------------------------------------------
    elif tool in ["screenshot", "captura_tela", "print", "tirar_print"]:
        save_path = args.get("path", args.get("caminho", None))
        return_b64 = bool(args.get("base64", False))
        return pc_automation.take_screenshot(save_path=save_path, return_base64=return_b64)

    elif tool in ["clipboard_copy", "copiar"]:
        text = args.get("text", args.get("texto", ""))
        return pc_automation.clipboard_copy(text)

    elif tool in ["clipboard_read", "ler_clipboard"]:
        return pc_automation.clipboard_read()

    elif tool in ["clipboard_paste", "colar"]:
        return pc_automation.clipboard_paste()

    # --------------------------------------------------------------------------
    # MOTOR DE MACROS / SEQUÊNCIAS AUTOMATIZADAS
    # --------------------------------------------------------------------------
    elif tool in ["macro", "pc_macro", "executar_macro", "sequencia_acoes"]:
        steps = args.get("steps", args.get("acoes", []))
        if not isinstance(steps, list):
            steps = [steps]
        return pc_automation.execute_macro(steps)

    return {"success": False, "error": f"Ferramenta MCP desconhecida: {tool_name}"}
