"""
Servidor e Despachador de Ferramentas MCP Nativas do Windows
Permite ao J.A.R.V.I.S., OpenClaw e IAs executarem ferramentas locais do Windows.
Padrão Permanente de Engenharia de Software Sênior.
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
        "description": "Ajusta, define porcentagem ou silencia o volume do Windows.",
        "parameters": {
            "type": "object",
            "properties": {
                "acao": {"type": "string", "enum": ["up", "down", "mute", "set"], "description": "Aumentar, diminuir, mutar ou definir"},
                "pct": {"type": "integer", "description": "Porcentagem exata de 0 a 100 se ação for set"}
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
    },
    {
        "name": "listar_janelas",
        "description": "Lista todas as janelas reais visíveis no Windows com HWND, título e processo.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "focar_janela",
        "description": "Traz uma janela específica para o primeiro plano pelo título ou HWND.",
        "parameters": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Título da janela ou HWND"}
            },
            "required": ["target"]
        }
    },
    {
        "name": "listar_processos",
        "description": "Lista os processos em execução no Windows com PID, Nome, CPU % e Memória MB.",
        "parameters": {
            "type": "object",
            "properties": {
                "top_n": {"type": "integer", "description": "Quantidade máxima de processos (padrão 15)"},
                "sort_by": {"type": "string", "enum": ["cpu", "memory"], "description": "Critério de ordenação"}
            }
        }
    },
    {
        "name": "listar_monitores",
        "description": "Lista todos os monitores conectados, resoluções e coordenadas.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "obter_info_sistema",
        "description": "Retorna informações detalhadas do sistema operacional, uptime, arquitetura e IPs locais.",
        "parameters": {"type": "object", "properties": {}}
    }
]

def dispatch_mcp_tool(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    tool = tool_name.lower().strip()
    args = arguments or {}

    if tool in ["executar_comando_windows", "powershell", "system_command"]:
        return win_controls.run_powershell(args.get("comando", args.get("command", "")))

    elif tool in ["abrir_programa_windows", "abrir_app", "open_app", "launch"]:
        target = args.get("aplicativo", "") or args.get("nome", "") or args.get("target", "") or args.get("app", "")
        return win_controls.open_application(target)

    elif tool in ["google_search", "pesquisar_google", "pesquisa_web", "web_search", "buscar_google"]:
        query = str(args.get("query", "") or args.get("termo", "") or args.get("busca", "") or args.get("q", ""))
        open_b = bool(args.get("open_browser", True))
        return win_controls.google_search(query, open_browser=open_b)

    elif tool in ["fechar_programa_windows", "fechar_app", "close_app"]:
        target = args.get("processo", "") or args.get("nome", "") or args.get("target", "") or args.get("app", "")
        return win_controls.close_application(target)

    elif tool in ["controlar_volume_windows", "volume", "volume_set", "pc_volume", "set_volume", "volume_up", "volume_down", "mute"]:
        if "pct" in args or "percent" in args:
            pct = int(args.get("pct", args.get("percent", 50)))
            return win_controls.set_volume(pct)
        if tool == "volume_up":
            return win_controls.control_volume("up")
        elif tool == "volume_down":
            return win_controls.control_volume("down")
        elif tool == "mute":
            return win_controls.control_volume("mute")
        action = args.get("action", args.get("acao", "up"))
        steps = int(args.get("steps", args.get("passos", 5)))
        return win_controls.control_volume(action, steps)

    elif tool in ["abort_shutdown", "cancelar_desligamento"]:
        return win_controls.abort_shutdown()

    elif tool in ["switch_window", "alternar_janela"]:
        return win_controls.switch_window()

    elif tool in ["list_windows", "listar_janelas", "janelas_abertas", "janelas"]:
        return win_controls.list_windows()

    elif tool in ["focus_window", "focar_janela", "trazer_janela"]:
        target = args.get("target", args.get("janela", args.get("nome", args.get("hwnd", ""))))
        return win_controls.focus_window(target)

    elif tool in ["minimize_window", "minimizar_janela"]:
        target = args.get("target", args.get("janela", args.get("hwnd", "")))
        return win_controls.minimize_window(target)

    elif tool in ["maximize_window", "maximizar_janela"]:
        target = args.get("target", args.get("janela", args.get("hwnd", "")))
        return win_controls.maximize_window(target)

    elif tool in ["close_window", "fechar_janela"]:
        target = args.get("target", args.get("janela", args.get("hwnd", "")))
        return win_controls.close_window(target)

    elif tool in ["list_processes", "listar_processos", "processos"]:
        top_n = int(args.get("top_n", args.get("limite", 15)))
        sort_by = str(args.get("sort_by", args.get("ordenar_por", "cpu")))
        return win_controls.list_processes(top_n=top_n, sort_by=sort_by)

    elif tool in ["list_monitors", "listar_monitores", "monitores"]:
        return win_controls.list_monitors()

    elif tool in ["get_system_info", "system_info", "info_sistema", "dados_pc"]:
        return win_controls.get_system_info()

    elif tool in ["controlar_midia_windows", "media", "spotify_control", "pc_media", "play_pause", "next_track", "prev_track"]:
        action = args.get("action", args.get("acao", tool))
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
                return {"ok": True, "info": f"Tela '{screen_res['screen'].get('title')}' gerada no HUD.", "_screen_data": screen_res["screen"]}
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

    elif tool in ["lock", "lock_pc", "bloquear_pc", "lock_workstation", "lock_screen"]:
        return win_controls.lock_workstation()

    elif tool in ["system_power", "power", "shutdown", "restart", "sleep", "desligar_pc", "reiniciar_pc"]:
        act = str(args.get("action", "") or args.get("comando", "") or tool).lower()
        delay = int(args.get("delay", args.get("seconds", 30)))
        if "shut" in act or "deslig" in act:
            return win_controls.shutdown_pc(delay)
        elif "rest" in act or "reini" in act:
            return win_controls.restart_pc(delay)
        elif "sleep" in act or "susp" in act:
            return win_controls.sleep_pc()
        elif "lock" in act or "bloq" in act:
            return win_controls.lock_workstation()
        return win_controls.shutdown_pc(delay)

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
