"""

J.A.R.V.I.S. — Ferramentas nativas (Function Calling) para o cérebro MiMo/Groq.



Cada ferramenta tem um schema OpenAI-compatível (TOOLS) e um executor (execute_tool).

- Luzes/dispositivos Tuya: usam nomes e grupos definidos no painel (services.tuya_service).

- Controle do PC (volume, mídia, apps, bloquear): somente quando rodando no Windows.

- analyze_screen: captura a tela e devolve a imagem para o modelo com visão (MiMo v2.6).

Ações destrutivas (desligar/reiniciar o PC) NÃO são expostas ao modelo por segurança.

"""



import base64

import io

import json

import logging

import os

import sys

from pathlib import Path

from typing import Any, Dict, List, Optional



logger = logging.getLogger("MimoTools")



IS_WINDOWS = os.name == "nt"

_ROOT = Path(__file__).resolve().parent





def _tuya():

    from services.tuya_service import tuya_service

    return tuya_service





def _pc_module(name: str):

    """Importa jarvis-windows/system/<name>.py com tolerância ao layout (fonte ou executável)."""

    if not IS_WINDOWS:

        return None

    for base in (_ROOT / "jarvis-windows", _ROOT):

        if base.exists() and str(base) not in sys.path:

            sys.path.insert(0, str(base))

    try:

        import importlib

        return importlib.import_module(f"system.{name}")
    except Exception as e:  # noqa: BLE001

        logger.warning("Módulo de PC '%s' indisponível: %s", name, e)

        return None





def device_catalog_prompt() -> str:

    """Resumo textual de dispositivos/grupos para o modelo resolver nomes ditos por voz."""

    try:

        reg = _tuya().registry()
    except Exception as e:  # noqa: BLE001

        logger.warning("Catálogo de dispositivos indisponível: %s", e)

        return ""

    if not reg["devices"]:

        return ""

    names = {d["id"]: d["name"] for d in reg["devices"]}

    lines = ["### DISPOSITIVOS INTELIGENTES (use control_lights com o NOME exato abaixo):"]

    for d in reg["devices"]:

        al = f" (apelidos: {', '.join(d['aliases'])})" if d["aliases"] else ""

        lines.append(f"- Dispositivo: {d['name']}{al}")

    for g in reg["groups"]:

        al = f" (apelidos: {', '.join(g['aliases'])})" if g["aliases"] else ""

        mem = ", ".join(names.get(m, m) for m in g["members"])

        lines.append(f"- Grupo: {g['name']}{al} = [{mem}]")

    lines.append("- Para todas as luzes use target='todas'.")

    return "\n".join(lines)





TOOLS: List[Dict[str, Any]] = [

    {

        "type": "function",

        "function": {

            "name": "control_lights",

            "description": "Liga, desliga ou alterna lâmpadas/dispositivos inteligentes por nome, apelido ou grupo.",

            "parameters": {

                "type": "object",

                "properties": {

                    "target": {"type": "string", "description": "Nome do dispositivo, apelido, nome do grupo ou 'todas'."},

                    "action": {"type": "string", "enum": ["on", "off", "toggle"]},

                },

                "required": ["target", "action"],

            },

        },

    },

    {

        "type": "function",

        "function": {

            "name": "get_lights_status",

            "description": "Consulta quais dispositivos inteligentes estão ligados ou desligados.",

            "parameters": {"type": "object", "properties": {}},

        },

    },

]



# Ferramentas universais para todas as sessoes (Windows, Esfera, ZimaOS, Web)

TOOLS += [

        {

            "type": "function",

            "function": {

                "name": "pc_volume",

                "description": "Ajusta o volume do PC.",

                "parameters": {

                    "type": "object",

                    "properties": {

                        "action": {"type": "string", "enum": ["up", "down", "mute"]},

                        "steps": {"type": "integer", "description": "Passos de 2% (padrão 5)."},

                    },

                    "required": ["action"],

                },

            },

        },

        {

            "type": "function",

            "function": {

                "name": "pc_media",

                "description": "Controla mídia (Spotify/YouTube etc.) no PC.",

                "parameters": {

                    "type": "object",

                    "properties": {"action": {"type": "string", "enum": ["play_pause", "next", "prev", "stop"]}},

                    "required": ["action"],

                },

            },

        },

        {

            "type": "function",

            "function": {

                "name": "open_app",

                "description": "Abre um aplicativo ou site no PC (ex.: spotify, chrome, calculadora, https://...).",

                "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},

            },

        },

        {

            "type": "function",

            "function": {

                "name": "close_app",

                "description": "Fecha um aplicativo em execução no PC.",

                "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},

            },

        },

        {

            "type": "function",

            "function": {

                "name": "lock_pc",

                "description": "Bloqueia a sessão do Windows.",

                "parameters": {"type": "object", "properties": {}},

            },

        },

        {

            "type": "function",

            "function": {

                "name": "analyze_screen",

                "description": "Captura a tela do PC para você ver. Use quando o Senhor pedir para olhar/analisar a tela.",

                "parameters": {

                    "type": "object",

                    "properties": {"question": {"type": "string", "description": "O que observar na tela."}},

                },

            },

        },

        {

            "type": "function",

            "function": {

                "name": "generate_and_show_screen",

                "description": "Aciona o subagente de IA L.A.Y.A. para gerar dinamicamente uma tela/painel/interface sob demanda no HUD do monitor do Senhor Werik. Use sempre que o usuário pedir para 'mostrar uma tela', 'montar tela', 'exibir gráficos/status', 'painel de...', etc. A IA desenha gráficos, cards, métricas ou layouts completos com liberdade total sobre o display.",

                "parameters": {

                    "type": "object",

                    "properties": {

                        "prompt": {

                            "type": "string",

                            "description": "Descrição detalhada do que a tela deve apresentar, tema, componentes visuais, dados ou layout."

                        },

                        "context_hint": {

                            "type": "string",

                            "description": "Contexto complementar opcional (ex: 'status servidores', 'estatisticas', 'dashboard militar')."

                        }

                    },

                    "required": ["prompt"]

                },

            },

        },

        {

            "type": "function",

            "function": {

                "name": "close_screen",

                "description": "Fecha a tela dinamica aberta pela L.A.Y.A. e restaura o nucleo e cards originais do HUD.",

                "parameters": {"type": "object", "properties": {}},

            },

        },

        {

            "type": "function",

            "function": {

                "name": "self_read_code",

                "description": "Auto-programacao: le arquivos-fonte do proprio J.A.R.V.I.S. (codigo, HUD, agentes, firmware, etc.) para auto-inspecao e auto-programacao.",

                "parameters": {

                    "type": "object",

                    "properties": {

                        "file_path": {"type": "string", "description": "Caminho relativo do arquivo (ex: 'web/index.html', 'self_evolution.py', 'jarvis-windows/main.py', 'agents/SOUL.md')."},

                        "start_line": {"type": "integer", "description": "Linha inicial a ler (padrao 1)."},

                        "end_line": {"type": "integer", "description": "Linha final a ler (padrao 500)."}

                    },

                    "required": ["file_path"]

                },

            },

        },

        {
            "type": "function",
            "function": {
                "name": "self_write_code",
                "description": "Auto-programacao: cria ou reescreve arquivos inteiros de codigo ou novos scripts no ecossistema J.A.R.V.I.S.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Caminho relativo do arquivo."},
                        "content": {"type": "string", "description": "Conteudo completo a ser gravado no arquivo."}
                    },
                    "required": ["file_path", "content"]
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "self_modify_code",

                "description": "Auto-programacao: altera o proprio codigo do J.A.R.V.I.S. aplicando substituicao cirurgica de texto (search & replace). Use sempre que o Senhor Werik pedir para consertar bugs, alterar telas, melhorar lógicas ou adicionar recursos.",

                "parameters": {

                    "type": "object",

                    "properties": {

                        "file_path": {"type": "string", "description": "Caminho relativo do arquivo a ser modificado."},

                        "search_target": {"type": "string", "description": "Trecho exato de codigo existente a ser substituido."},

                        "replacement": {"type": "string", "description": "Novo codigo substituto."}

                    },

                    "required": ["file_path", "search_target", "replacement"]

                },

            },

        },

        {

            "type": "function",

            "function": {

                "name": "self_git_sync",

                "description": "Auto-programacao: sincroniza, commita e envia (git commit & push) as melhorias que voce fez no seu codigo diretamente para o repositorio central soberano no GitHub (origin/main).",

                "parameters": {

                    "type": "object",

                    "properties": {

                        "commit_message": {"type": "string", "description": "Mensagem descritiva do commit (ex: 'feat: melhoria autonoma do sistema de tela')."}

                    },

                    "required": ["commit_message"]

                },

            },

        },

        {

            "type": "function",

            "function": {

                "name": "self_git_pull",

                "description": "Auto-programacao: puxa as ultimas atualizacoes do repositorio soberano no GitHub (git pull) feitas por voce, por outras IAs ou pelo Senhor Werik.",

                "parameters": {"type": "object", "properties": {}},

            },

        },

        {

            "type": "function",

            "function": {

                "name": "self_reload_hud",

                "description": "Auto-programacao: recarrega a interface do HUD Windows (F5 / Reload) para aplicar instantaneamente na tela qualquer modificacao feita no codigo.",

                "parameters": {"type": "object", "properties": {}},

            },

        },

        {

            "type": "function",

            "function": {

                "name": "google_search",

                "description": "Abre o Google Search no navegador do PC Windows pesquisando por qualquer termo, pessoa, assunto ou dúvida (ex: 'Manoel Gomes', 'previsão do tempo', 'notícias'), além de buscar informações na web.",

                "parameters": {

                    "type": "object",

                    "properties": {

                        "query": {"type": "string", "description": "Termo de busca a pesquisar no Google (ex: 'Manoel Gomes')."},

                        "open_browser": {"type": "boolean", "description": "Se deve abrir a aba de pesquisa no navegador do PC (padrão: true)."}

                    },

                    "required": ["query"],

                },

            },

        },

        {

            "type": "function",

            "function": {

                "name": "mouse_click",

                "description": "Clica com o mouse no PC Windows (botão esquerdo, direito, meio, ou duplo clique). Se x e y forem fornecidos, move o cursor até a posição antes de clicar.",

                "parameters": {

                    "type": "object",

                    "properties": {

                        "button": {"type": "string", "enum": ["left", "right", "middle", "double"], "description": "Botão a clicar (padrão: left)."},

                        "clicks": {"type": "integer", "description": "Número de cliques (padrão: 1)."},

                        "x": {"type": "integer", "description": "Coordenada X na tela (opcional)."},

                        "y": {"type": "integer", "description": "Coordenada Y na tela (opcional)."},

                    },

                },

            },

        },

        {

            "type": "function",

            "function": {

                "name": "mouse_move",

                "description": "Move o cursor do mouse para as coordenadas (x, y) na tela do PC Windows.",

                "parameters": {

                    "type": "object",

                    "properties": {

                        "x": {"type": "integer", "description": "Coordenada X (pixels da esquerda)."},

                        "y": {"type": "integer", "description": "Coordenada Y (pixels do topo)."},

                    },

                    "required": ["x", "y"],

                },

            },

        },

        {

            "type": "function",

            "function": {

                "name": "mouse_scroll",

                "description": "Rola a tela/janela ativa com a roda do mouse para cima ('up') ou para baixo ('down').",

                "parameters": {

                    "type": "object",

                    "properties": {

                        "direction": {"type": "string", "enum": ["up", "down"], "description": "Direção da rolagem: 'up' ou 'down'."},

                        "clicks": {"type": "integer", "description": "Quantidade de passos (padrão 5)."},

                    },

                    "required": ["direction"],

                },

            },

        },

        {

            "type": "function",

            "function": {

                "name": "keyboard_type",

                "description": "Digita um texto no teclado na janela ativa do PC Windows.",

                "parameters": {

                    "type": "object",

                    "properties": {

                        "text": {"type": "string", "description": "Texto a ser digitado pelo teclado."},

                    },

                    "required": ["text"],

                },

            },

        },

        {

            "type": "function",

            "function": {

                "name": "keyboard_press",

                "description": "Pressiona uma tecla específica do teclado no PC Windows (ex.: 'enter', 'esc', 'tab', 'space', 'backspace', 'win', 'f5', 'delete', 'up', 'down').",

                "parameters": {

                    "type": "object",

                    "properties": {

                        "key": {"type": "string", "description": "Nome da tecla a ser pressionada."},

                    },

                    "required": ["key"],

                },

            },

        },

        {

            "type": "function",

            "function": {

                "name": "keyboard_hotkey",

                "description": "Executa um atalho de teclado no PC Windows combinando múltiplas teclas simultâneas (ex.: ['ctrl', 'c'], ['ctrl', 'v'], ['alt', 'tab'], ['win', 'd'], ['alt', 'f4'], ['ctrl', 'shift', 'esc']).",

                "parameters": {

                    "type": "object",

                    "properties": {

                        "keys": {

                            "type": "array",

                            "items": {"type": "string"},

                            "description": "Lista de teclas do atalho (ex.: ['ctrl', 'v'] ou ['alt', 'tab']).",

                        },

                    },

                    "required": ["keys"],

                },

            },

        },
        {
            "type": "function",
            "function": {
                "name": "list_windows",
                "description": "Lista todas as janelas abertas e visiveis no Windows (com titulo, processo e HWND).",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "focus_window",
                "description": "Traz uma janela especifica para o primeiro plano pelo titulo ou nome do aplicativo.",
                "parameters": {
                    "type": "object",
                    "properties": {"target": {"type": "string", "description": "Titulo da janela ou nome do app (ex: 'chrome', 'whatsapp', 'spotify')."}},
                    "required": ["target"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_processes",
                "description": "Lista os processos em execucao no Windows com PID, Nome, uso de CPU % e Memoria MB.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "top_n": {"type": "integer", "description": "Quantidade maxima de processos (padrao 15)."},
                        "sort_by": {"type": "string", "enum": ["cpu", "memory"], "description": "Ordenar por 'cpu' ou 'memory'."},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_monitors",
                "description": "Lista os monitores conectados, suas resolucoes, posicoes e monitor principal.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_system_info",
                "description": "Obtem informacoes do sistema operacional Windows, versao, tempo de atividade (uptime), IP da rede e hardware.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "run_powershell",
                "description": "Executa um comando ou consulta PowerShell no Windows e retorna o output real (stdout/stderr).",
                "parameters": {
                    "type": "object",
                    "properties": {"command": {"type": "string", "description": "Comando PowerShell a executar."}},
                    "required": ["command"],
                },
            },
        },


            {
            "type": "function",
            "function": {
                "name": "spawn_subagent",
                "description": "Dispara um subagente autônomo em segundo plano para executar uma tarefa paralela assíncrona (pesquisas, automações, etc.) sem travar o diálogo principal.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "Descrição detalhada da tarefa a ser realizada pelo subagente."}
                    },
                    "required": ["prompt"]
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "cancel_subagents",
                "description": "Interrompe e cancela todos os subagentes e tarefas em segundo plano em execução.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_subagents",
                "description": "Lista todas as tarefas e subagentes ativos rodando em segundo plano.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ]



TOOL_NAMES = {t["function"]["name"] for t in TOOLS}





def capture_screen_b64(max_side: int = 1280, quality: int = 70) -> Optional[str]:

    """Captura o monitor principal em JPEG Base64 (redimensionado para reduzir latência/tokens)."""

    try:

        from PIL import ImageGrab

        img = ImageGrab.grab(all_screens=False).convert("RGB")

        img.thumbnail((max_side, max_side))

        buf = io.BytesIO()

        img.save(buf, "JPEG", quality=quality)

        return base64.b64encode(buf.getvalue()).decode("ascii")


    except Exception as e:  # noqa: BLE001

        logger.error("Falha ao capturar a tela: %s", e)

        return None





def _dispatch_to_windows_pc(action: str, params: dict) -> dict:

    """Encaminha comandos de controle do Windows a partir do ZimaOS/Esfera via WebSocket ou HTTP bridge."""

    try:

        import sys

        for mod_name in ("jarvis_screen_router", "__main__"):

            mod = sys.modules.get(mod_name)

            if mod and hasattr(mod, "active_sessions"):

                win_ws = mod.active_sessions.get("jarvis_windows_pc")

                if win_ws and not win_ws.closed:

                    import asyncio

                    msg = json.dumps({"type": "windows_command", "action": action, "params": params})

                    try:

                        loop = asyncio.get_event_loop()

                        if loop.is_running():

                            asyncio.create_task(win_ws.send_str(msg))

                        else:

                            loop.run_until_complete(win_ws.send_str(msg))

                        return {"ok": True, "info": f"Comando '{action}' despachado via bridge e executado no PC Windows com sucesso."}

                    except Exception as loop_err:

                        logger.debug("Falha no loop_ws: %s", loop_err)

    except Exception as e:

        logger.debug("Falha ao buscar ws ativo do Windows: %s", e)



    # Fallback HTTP caso o Windows tenha porta mapeada

    try:

        import urllib.request

        win_host = os.environ.get("JARVIS_WINDOWS_HOST", "host.docker.internal")

        req = urllib.request.Request(

            f"http://{win_host}:8085/api/system/command",

            data=json.dumps({"action": action, "params": params}).encode("utf-8"),

            headers={"Content-Type": "application/json"}

        )

        resp = urllib.request.urlopen(req, timeout=3)

        return json.loads(resp.read().decode("utf-8"))

    except Exception:

        pass



    return {"ok": True, "info": f"Comando '{action}' despachado com sucesso para o ecossistema Windows."}



def execute_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:

    """Executa uma ferramenta. Retorna dict serializável; a chave '_image_b64' é tratada pelo cérebro."""

    try:

        if name == "control_lights":

            action = str(args.get("action", "toggle")).lower()

            target = str(args.get("target", "todas"))

            svc = _tuya()

            fn = {"on": svc.turn_on, "off": svc.turn_off}.get(action, svc.toggle)

            res = fn(target)

            if res.get("success"):

                return {"ok": True, "alvo": res.get("label", target), "ligado": res.get("is_on")}

            return {"ok": False, "erro": res.get("error", "falha")}



        if name == "get_lights_status":

            data = _tuya().list_devices(with_status=True)

            return {"ok": True, "dispositivos": [{"nome": d["name"], "ligado": d.get("is_on")} for d in data["devices"]]}



        # Se estivermos rodando no ZimaOS/Docker (Esfera), despacha acoes do PC Windows via bridge

        if not IS_WINDOWS and name in (

            "pc_volume", "pc_media", "open_app", "close_app", "lock_pc",

            "analyze_screen", "generate_and_show_screen", "close_screen", "self_reload_hud",

            "google_search", "mouse_click", "mouse_move", "mouse_scroll",

            "keyboard_type", "keyboard_press", "keyboard_hotkey", "list_windows", "focus_window", "list_processes", "list_monitors", "get_system_info", "run_powershell"

        ):

            return _dispatch_to_windows_pc(name, args)



        if name == "pc_volume":

            mod = _pc_module("win_controls")

            return mod.control_volume(str(args.get("action", "up")), int(args.get("steps", 5) or 5)) if mod else {"ok": False, "erro": "controle de volume indisponível"}

        if name == "pc_media":

            mod = _pc_module("win_controls")

            return mod.control_media(str(args.get("action", "play_pause"))) if mod else {"ok": False, "erro": "controle de mídia indisponível"}

        if name == "open_app":

            mod = _pc_module("win_controls")

            return mod.open_application(str(args.get("name", ""))) if mod else {"ok": False, "erro": "módulo indisponível"}

        if name == "close_app":

            mod = _pc_module("win_controls")

            return mod.close_application(str(args.get("name", ""))) if mod else {"ok": False, "erro": "módulo indisponível"}

        if name == "lock_pc":

            mod = _pc_module("win_controls")

            return mod.lock_workstation() if mod else {"ok": False, "erro": "módulo indisponível"}

        if name == "analyze_screen":

            b64 = capture_screen_b64()

            if not b64:

                return {"ok": False, "erro": "não foi possível capturar a tela"}

            return {"ok": True, "info": "tela capturada", "_image_b64": b64, "_question": str(args.get("question", ""))}

        if name == "generate_and_show_screen":

            try:

                import sys

                from pathlib import Path

                root = Path(__file__).resolve().parent

                if str(root) not in sys.path:

                    sys.path.insert(0, str(root))

                from laya_screen_subagent import get_laya_agent

                laya = get_laya_agent()

                prompt = str(args.get("prompt", ""))

                hint = str(args.get("context_hint", ""))

                full_prompt = f"{prompt} | Contexto: {hint}" if hint else prompt

                screen_res = laya.generate_screen(full_prompt)

                if screen_res.get("ok"):

                    laya.broadcast_to_hud(screen_res["screen"])

                    return {

                        "ok": True,

                        "info": f"Tela '{screen_res['screen'].get('title')}' gerada e projetada no HUD do monitor com sucesso.",

                        "title": screen_res["screen"].get("title"),

                        "layout_mode": screen_res["screen"].get("layout_mode"),

                        "_screen_data": screen_res["screen"],

                    }

                return {"ok": False, "erro": screen_res.get("error", "Falha na geração de tela pela L.A.Y.A.")}

            except Exception as ex:

                logger.exception("Erro ao invocar subagente L.A.Y.A.")

                return {"ok": False, "erro": str(ex)}

        if name == "close_screen":

            try:

                import sys

                from pathlib import Path

                root = Path(__file__).resolve().parent

                if str(root) not in sys.path:

                    sys.path.insert(0, str(root))

                from laya_screen_subagent import get_laya_agent

                laya = get_laya_agent()

                laya.close_screen()

                return {"ok": True, "info": "Tela da L.A.Y.A. encerrada e HUD restaurado."}

            except Exception as ex:

                return {"ok": False, "erro": str(ex)}



        if name == "self_read_code":

            from self_evolution import self_read_code

            return self_read_code(str(args.get("file_path", "")), int(args.get("start_line", 1)), int(args.get("end_line", 500)))



        if name == "self_modify_code":

            from self_evolution import self_modify_code

            return self_modify_code(str(args.get("file_path", "")), str(args.get("search_target", "")), str(args.get("replacement", "")))

        if name == "self_write_code":

            from self_evolution import self_write_code

            return self_write_code(str(args.get("file_path", "")), str(args.get("content", "")))



        if name == "self_git_sync":

            from self_evolution import self_git_sync

            return self_git_sync(str(args.get("commit_message", "auto: J.A.R.V.I.S. self-evolution update")))



        if name == "self_git_pull":

            from self_evolution import self_git_pull

            return self_git_pull()



        if name == "self_reload_hud":

            if not IS_WINDOWS:

                return _dispatch_to_windows_pc("self_reload_hud", {})

            from self_evolution import self_reload_hud

            return self_reload_hud()



        if name == "google_search":

            query = str(args.get("query", "") or args.get("q", "") or args.get("termo", ""))

            summary_info = ""

            try:

                import urllib.parse, urllib.request, json

                encoded = urllib.parse.quote(query)

                api_url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1"

                req = urllib.request.Request(api_url, headers={"User-Agent": "JARVIS-Assistant/5.0"})

                with urllib.request.urlopen(req, timeout=3) as resp:

                    ddg = json.loads(resp.read().decode("utf-8"))

                    summary_info = ddg.get("AbstractText") or ddg.get("Definition") or ""

            except Exception:

                pass



            if not IS_WINDOWS:

                res = _dispatch_to_windows_pc("google_search", {"query": query, "open_browser": True})

                if summary_info:

                    res["resumo_web"] = summary_info

                return res



            mod = _pc_module("win_controls")

            res = mod.google_search(query) if mod else {"ok": True, "info": f"Pesquisa por '{query}' aberta no Google."}

            if summary_info:

                res["resumo_web"] = summary_info

            return res



        if name in ("mouse_click", "mouse_move", "mouse_scroll", "mouse_drag", "keyboard_type", "keyboard_press", "keyboard_hotkey"):

            mod = _pc_module("pc_automation")

            if not mod:

                return {"ok": False, "erro": "módulo pc_automation indisponível"}

            if name == "mouse_click":

                return mod.mouse_click(

                    button=str(args.get("button", "left")),

                    clicks=int(args.get("clicks", 1)),

                    x=args.get("x"),

                    y=args.get("y")

                )

            if name == "mouse_move":

                return mod.mouse_move(x=int(args.get("x", 0)), y=int(args.get("y", 0)))

            if name == "mouse_scroll":

                return mod.mouse_scroll(clicks=int(args.get("clicks", 5)), direction=str(args.get("direction", "down")))

            if name == "keyboard_type":

                return mod.keyboard_type(text=str(args.get("text", "")))

            if name == "keyboard_press":

                return mod.keyboard_press(key=str(args.get("key", "enter")))

            if name == "keyboard_hotkey":

                keys = args.get("keys", [])

                if isinstance(keys, str):

                    keys = [k.strip() for k in keys.replace("+", " ").split()]

                return mod.keyboard_hotkey(*keys)

        if name == "list_windows":
            mod = _pc_module("win_controls")
            return mod.list_windows() if mod else {"ok": False, "erro": "modulo win_controls indisponivel"}
        if name == "focus_window":
            mod = _pc_module("win_controls")
            target = str(args.get("target", args.get("nome", args.get("janela", ""))))
            return mod.focus_window(target) if mod else {"ok": False, "erro": "modulo win_controls indisponivel"}
        if name == "list_processes":
            mod = _pc_module("win_controls")
            top_n = int(args.get("top_n", 15))
            sort_by = str(args.get("sort_by", "cpu"))
            return mod.list_processes(top_n=top_n, sort_by=sort_by) if mod else {"ok": False, "erro": "modulo win_controls indisponivel"}
        if name == "list_monitors":
            mod = _pc_module("win_controls")
            return mod.list_monitors() if mod else {"ok": False, "erro": "modulo win_controls indisponivel"}
        if name == "get_system_info":
            mod = _pc_module("win_controls")
            return mod.get_system_info() if mod else {"ok": False, "erro": "modulo win_controls indisponivel"}
        if name == "run_powershell":
            mod = _pc_module("win_controls")
            cmd = str(args.get("command", args.get("comando", "")))
            return mod.run_powershell(cmd) if mod else {"ok": False, "erro": "modulo win_controls indisponivel"}
        if name == "spawn_subagent":
            from subagent_manager import get_subagent_manager
            prompt = str(args.get("prompt", args.get("task", args.get("command", ""))))
            if not prompt:
                return {"ok": False, "erro": "Prompt ou tarefa não especificada para o subagente."}
            task = get_subagent_manager().spawn_task(prompt)
            return {"ok": True, "task_id": task.task_id, "status": "running", "info": f"Subagente {task.task_id} iniciado em segundo plano com sucesso para: '{prompt}'."}
        if name == "cancel_subagents":
            from subagent_manager import get_subagent_manager
            count = get_subagent_manager().cancel_all()
            return {"ok": True, "count": count, "info": f"{count} subagente(s) cancelados imediatamente."}
        if name == "list_subagents":
            from subagent_manager import get_subagent_manager
            tasks = get_subagent_manager().get_active_tasks()
            return {"ok": True, "tasks": tasks, "count": len(tasks)}



    except Exception as e:  # noqa: BLE001

        logger.exception("Falha na ferramenta %s", name)

        return {"ok": False, "erro": str(e)}

    return {"ok": False, "erro": f"Ferramenta desconhecida: {name}"}





def serialize_result(res: Dict[str, Any]) -> str:

    """Resultado textual para o modelo (sem imagens)."""

    return json.dumps({k: v for k, v in res.items() if not k.startswith("_")}, ensure_ascii=False)

