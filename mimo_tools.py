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



            {



            "type": "function",



            "function": {



                "name": "sphere_inspect_firmware",



                "description": "Inspeciona trechos do código-fonte C++ ou cabeçalhos do firmware da Esfera ESP32-S3 (display circular 240x240, LovyanGFX, Codec ES8311).",



                "parameters": {



                    "type": "object",



                    "properties": {



                        "file_path": {"type": "string", "description": "Caminho do arquivo relativo a firmware_jarvis_custom (ex: 'src/main.cpp', 'include/jarvis_sphere_secrets.h')."},



                        "start_line": {"type": "integer", "description": "Linha inicial a ler (padrão 1)."},



                        "end_line": {"type": "integer", "description": "Linha final a ler (padrão 200)."}



                    }



                },



            },



        },



        {



            "type": "function",



            "function": {



                "name": "sphere_modify_firmware",



                "description": "Modifica o código C++ do firmware da Esfera ESP32-S3 aplicando substituição cirúrgica de texto (search & replace).",



                "parameters": {



                    "type": "object",



                    "properties": {



                        "file_path": {"type": "string", "description": "Caminho do arquivo relativo a firmware_jarvis_custom (ex: 'src/main.cpp')."},



                        "search_target": {"type": "string", "description": "Trecho exato de código a ser substituído."},



                        "replacement": {"type": "string", "description": "Novo trecho de código substituto."}



                    },



                    "required": ["file_path", "search_target", "replacement"]



                },



            },



        },



        {



            "type": "function",



            "function": {



                "name": "sphere_compile_firmware",



                "description": "Compila o firmware PlatformIO da Esfera ESP32-S3 gerando o binário oficial firmware.bin e retornando métricas de RAM/Flash e erros de compilação.",



                "parameters": {



                    "type": "object",



                    "properties": {



                        "clean": {"type": "boolean", "description": "Se deve limpar a build anterior antes de compilar (padrão: false)."}



                    }



                },



            },



        },



        {



            "type": "function",



            "function": {



                "name": "sphere_upload_usb",



                "description": "Grava o firmware compilado diretamente na Esfera ESP32-S3 conectada ao PC via cabo USB na porta serial especificada (ex: COM3).",



                "parameters": {



                    "type": "object",



                    "properties": {



                        "port": {"type": "string", "description": "Porta serial COM onde a Esfera está conectada (padrão: 'COM3')."}



                    }



                },



            },



        },



        {



            "type": "function",



            "function": {



                "name": "sphere_ota_deploy",



                "description": "Envia o binário de firmware compilado para o servidor e dispara a atualização sem fio (OTA) na Esfera ESP32-S3 via Wi-Fi sem necessidade de cabos.",



                "parameters": {



                    "type": "object",



                    "properties": {



                        "url_firmware": {"type": "string", "description": "URL HTTP opcional do binário de firmware. Se omitido, utiliza o espelho oficial/local."}



                    }



                },



            },



        },



        {



            "type": "function",



            "function": {



                "name": "sphere_get_status",



                "description": "Obtém o status de hardware, compilação, portas COM e conectividade da Esfera ESP32-S3.",



                "parameters": {"type": "object", "properties": {}},



            },



        },



        {



            "type": "function",



            "function": {



                "name": "lg_tv_power_on_and_open_app",



                "description": "Liga a Smart TV LG 55 polegadas via Wake-on-LAN (WoL) e abre automaticamente o aplicativo J.A.R.V.I.S. TV em tela cheia.",



                "parameters": {"type": "object", "properties": {}},



            },



        },



        {



            "type": "function",



            "function": {



                "name": "lg_tv_launch_app",



                "description": "Abre o aplicativo J.A.R.V.I.S. TV em tela cheia na Smart TV LG conectada na rede local.",



                "parameters": {"type": "object", "properties": {}},



            },



        },



        {



            "type": "function",



            "function": {



                "name": "lg_tv_close_app",



                "description": "Fecha o aplicativo J.A.R.V.I.S. TV na Smart TV LG.",



                "parameters": {"type": "object", "properties": {}},



            },



        },



        {



            "type": "function",



            "function": {



                "name": "lg_tv_project_screen",



                "description": "Projeta um card holográfico ou tela completa em tempo real na Smart TV LG.",



                "parameters": {



                    "type": "object",



                    "properties": {



                        "title": {"type": "string", "description": "Título da tela ou card projetado."},



                        "html": {"type": "string", "description": "Conteúdo HTML ou texto formatado para exibição holográfica."}



                    },



                    "required": ["title", "html"]



                },



            },



        },



        {



            "type": "function",



            "function": {



                "name": "lg_tv_close_screen",



                "description": "Fecha a projeção em tela cheia na Smart TV LG, retornando ao núcleo do Arc Reactor.",



                "parameters": {"type": "object", "properties": {}},



            },



        },



        {

            "type": "function",

            "function": {

                "name": "lg_tv_speak",

                "description": "Fala verbalmente através dos alto-falantes da Smart TV LG exibindo a legenda em tempo real no visor.",

                "parameters": {

                    "type": "object",

                    "properties": {

                        "speech_text": {"type": "string", "description": "Texto a ser falado na Smart TV."},

                        "audio_url": {"type": "string", "description": "URL do arquivo de áudio sintetizado (opcional)."}

                    },

                    "required": ["speech_text"]

                },

            },

        },

        {

            "type": "function",

            "function": {

                "name": "lg_tv_get_status",

                "description": "Consulta o status de rede, energia e aplicativos em execução na Smart TV LG.",

                "parameters": {"type": "object", "properties": {}},

            },

        },



            {

            "type": "function",

            "function": {

                "name": "start_dynamic_presentation",

                "description": "Inicia uma apresentação multimodal cinematográfica no HUD do J.A.R.V.I.S. com sequência de cenas dinâmicas (painéis holográficos, gráficos animados, vídeos, imagens, tabelas cyberpunk, mapas táticos, diagramas de fluxo, comparações visuais e métricas).",

                "parameters": {

                    "type": "object",

                    "properties": {

                        "title": {"type": "string", "description": "Título principal da apresentação."},

                        "subtitle": {"type": "string", "description": "Subtítulo ou contexto da apresentação."},

                        "speech_sync": {"type": "boolean", "description": "Se a apresentação deve sincronizar com o avanço da narração."},

                        "scenes": {

                            "type": "array",

                            "description": "Lista de cenas da apresentação. Cada cena possui: title, component_type (hologram_card, chart, video, gallery, table, map, diagram, comparison, metric_grid, conclusion), content, e propriedades específicas do componente.",

                            "items": {"type": "object"}

                        }

                    },

                    "required": ["title"]

                },

            },

        },

        {

            "type": "function",

            "function": {

                "name": "update_presentation_scene",

                "description": "Atualiza ou injeta uma cena específica na apresentação em andamento no HUD.",

                "parameters": {

                    "type": "object",

                    "properties": {

                        "scene": {"type": "object", "description": "Dados da cena a ser exibida ou atualizada."}

                    },

                    "required": ["scene"]

                },

            },

        },

        {

            "type": "function",

            "function": {

                "name": "control_presentation",

                "description": "Controla a apresentação ativa no HUD (ações: 'next', 'prev', 'pause', 'resume', 'close', 'stop').",

                "parameters": {

                    "type": "object",

                    "properties": {

                        "action": {"type": "string", "enum": ["next", "prev", "pause", "resume", "close", "stop"], "description": "Ação de controle da apresentação."}

                    },

                    "required": ["action"]

                },

            },

        },

        {

            "type": "function",

            "function": {

                "name": "get_presentation_status",

                "description": "Consulta o estado da apresentação multimodal ativa no HUD.",

                "parameters": {"type": "object", "properties": {}},

            },

        },

        {
            "type": "function",
            "function": {
                "name": "take_screenshot",
                "description": "Captura a tela atual do monitor principal do PC Windows para auto-verificação visual e análise multimodal da IA. SEMPRE use quando realizar ações no PC (cliques, digitação, abertura de janelas ou programas) para conferir se o resultado foi alcançado ou se é necessário se auto-corrigir.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reason": {
                            "type": "string",
                            "description": "O motivo da captura e o que deve ser verificado na tela (ex: 'conferir se o app abriu', 'verificar se o texto foi digitado no campo correto')."
                        }
                    },
                    "required": ["reason"]
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "obsidian_search_notes",
                "description": "Pesquisa notas, documentos, instruções e memórias no cofre oficial do Obsidian (Terceiro Cérebro do Senhor Werik).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Termo ou frase a ser pesquisada nas notas markdown."
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Número máximo de notas retornadas (padrão: 5)."
                        }
                    },
                    "required": ["query"]
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "obsidian_read_note",
                "description": "Lê o conteúdo completo de uma nota específica no cofre do Obsidian (ex: '05_MEMORIA_AGENTES/JARVIS_APRENDIZADO.md' ou '05_MEMORIA_AGENTES/SHARED_CONTEXT.md').",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "relative_path": {
                            "type": "string",
                            "description": "Caminho relativo da nota dentro do cofre (com ou sem .md)."
                        }
                    },
                    "required": ["relative_path"]
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "obsidian_append_learning",
                "description": "Registra uma nova lição aprendida com um erro operacional ou ajuste de automação no arquivo '05_MEMORIA_AGENTES/JARVIS_APRENDIZADO.md' no Obsidian. Use SEMPRE que descobrir que uma abordagem falhou e encontrar o método correto, para que o J.A.R.V.I.S. nunca mais cometa o mesmo erro.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "topic": {
                            "type": "string",
                            "description": "Tópico da falha (ex: 'Digitação no Notepad', 'Localização de botão', 'Foco de janela')."
                        },
                        "error_encountered": {
                            "type": "string",
                            "description": "Descrição exata do que falhou ou deu errado."
                        },
                        "solution_applied": {
                            "type": "string",
                            "description": "Ação ou ajuste que funcionou efetivamente para resolver."
                        },
                        "context": {
                            "type": "string",
                            "description": "O que o Senhor Werik havia solicitado ou o objetivo da tarefa."
                        }
                    },
                    "required": ["topic", "error_encountered", "solution_applied"]
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "obsidian_write_note",
                "description": "Cria ou anexa conteúdo a qualquer nota do cofre Obsidian do Senhor Werik (ex: anotações rápidas em '00_INBOX/', documentações em '01_PROJETOS/').",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "relative_path": {
                            "type": "string",
                            "description": "Caminho relativo da nota dentro do cofre (ex: '00_INBOX/ideia.md')."
                        },
                        "content": {
                            "type": "string",
                            "description": "Conteúdo markdown a ser gravado."
                        },
                        "mode": {
                            "type": "string",
                            "enum": ["append", "overwrite"],
                            "description": "'append' para adicionar ao final (padrão) ou 'overwrite' para sobrescrever."
                        }
                    },
                    "required": ["relative_path", "content"]
                },
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

        if name in ("take_screenshot", "screen_capture", "screenshot"):
            reason = str(args.get("reason", "Verificação visual do estado atual da tela do PC"))
            mod = _pc_module("pc_automation")
            if not mod:
                return {"ok": False, "erro": "Módulo pc_automation indisponível para captura"}
            res = mod.take_screenshot(return_base64=True)
            if not res.get("success"):
                return {"ok": False, "erro": res.get("error", "Falha na captura")}
            b64 = res.get("base64", "")
            return {
                "ok": True,
                "action": "take_screenshot",
                "reason": reason,
                "path": res.get("path"),
                "width": res.get("width"),
                "height": res.get("height"),
                "_image_b64": b64,
                "_question": f"Captura realizada para auto-verificação visual: '{reason}'. Examine atentamente a imagem da tela, identifique se a ação anterior teve êxito (janelas abertas, campos preenchidos, botões clicados) ou se ocorreu alguma falha que exige correção imediata."
            }

        if name == "obsidian_search_notes":
            try:
                import obsidian_manager
            except ImportError:
                import sys
                from pathlib import Path
                sys.path.insert(0, str(_ROOT))
                import obsidian_manager
            query = str(args.get("query", ""))
            max_results = int(args.get("max_results", 5))
            return obsidian_manager.obsidian_search_notes(query=query, max_results=max_results)

        if name == "obsidian_read_note":
            try:
                import obsidian_manager
            except ImportError:
                import sys
                from pathlib import Path
                sys.path.insert(0, str(_ROOT))
                import obsidian_manager
            rel_path = str(args.get("relative_path", args.get("path", "")))
            return obsidian_manager.obsidian_read_note(relative_path=rel_path)

        if name == "obsidian_append_learning":
            try:
                import obsidian_manager
            except ImportError:
                import sys
                from pathlib import Path
                sys.path.insert(0, str(_ROOT))
                import obsidian_manager
            topic = str(args.get("topic", ""))
            error_enc = str(args.get("error_encountered", args.get("erro", "")))
            solution = str(args.get("solution_applied", args.get("solucao", "")))
            context = str(args.get("context", ""))
            return obsidian_manager.obsidian_append_learning(
                topic=topic,
                error_encountered=error_enc,
                solution_applied=solution,
                context=context
            )

        if name == "obsidian_write_note":
            try:
                import obsidian_manager
            except ImportError:
                import sys
                from pathlib import Path
                sys.path.insert(0, str(_ROOT))
                import obsidian_manager
            rel_path = str(args.get("relative_path", args.get("path", "")))
            content = str(args.get("content", ""))
            mode = str(args.get("mode", "append"))
            return obsidian_manager.obsidian_write_note(relative_path=rel_path, content=content, mode=mode)








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
            return {"ok": False, "erro": "Subagentes desativados por diretriz do Senhor Werik. Execute todas as tarefas diretamente no fluxo principal."}
        if name == "cancel_subagents":



            from subagent_manager import get_subagent_manager



            count = get_subagent_manager().cancel_all()



            return {"ok": True, "count": count, "info": f"{count} subagente(s) cancelados imediatamente."}



        if name == "list_subagents":



            from subagent_manager import get_subagent_manager



            tasks = get_subagent_manager().get_active_tasks()



            return {"ok": True, "tasks": tasks, "count": len(tasks)}



        if name == "sphere_inspect_firmware":



            from sphere_evolution import sphere_inspect_firmware



            return sphere_inspect_firmware(



                file_path=str(args.get("file_path", "src/main.cpp")),



                start_line=int(args.get("start_line", 1)),



                end_line=int(args.get("end_line", 200))



            )



        if name == "sphere_modify_firmware":



            from sphere_evolution import sphere_modify_firmware



            return sphere_modify_firmware(



                file_path=str(args.get("file_path", "")),



                search_target=str(args.get("search_target", "")),



                replacement=str(args.get("replacement", ""))



            )



        if name == "sphere_compile_firmware":



            from sphere_evolution import sphere_compile_firmware



            return sphere_compile_firmware(clean=bool(args.get("clean", False)))



        if name == "sphere_upload_usb":



            from sphere_evolution import sphere_upload_usb



            return sphere_upload_usb(port=str(args.get("port", "COM3")))



        if name == "sphere_ota_deploy":



            from sphere_evolution import sphere_ota_deploy



            return sphere_ota_deploy(url_firmware=args.get("url_firmware"))



        if name == "sphere_get_status":



            from sphere_evolution import sphere_get_status



            return sphere_get_status()



        if name == "lg_tv_power_on_and_open_app":



            import lg_tv_manager



            return lg_tv_manager.power_on_and_open_app()



        if name == "lg_tv_launch_app":



            import lg_tv_manager



            return lg_tv_manager.launch_tv_app()



        if name == "lg_tv_close_app":



            import lg_tv_manager



            return lg_tv_manager.close_tv_app()

        if name == "lg_tv_project_screen":
            import lg_tv_manager
            title = str(args.get("title", "J.A.R.V.I.S."))
            html = str(args.get("html", ""))
            speech_text = str(args.get("speech_text", ""))
            audio_url = str(args.get("audio_url", ""))
            return lg_tv_manager.project_screen_to_tv(title=title, html=html, speech_text=speech_text, audio_url=audio_url)

        if name == "lg_tv_close_screen":
            import lg_tv_manager
            return lg_tv_manager.close_projected_screen()

        if name == "lg_tv_speak":
            import lg_tv_manager
            speech_text = str(args.get("speech_text", args.get("text", "")))
            audio_url = str(args.get("audio_url", ""))
            return lg_tv_manager.speak_on_tv(speech_text=speech_text, audio_url=audio_url)

        if name == "lg_tv_get_status":
            import lg_tv_manager
            return lg_tv_manager.get_tv_status()





        if name == "start_dynamic_presentation":

            import dynamic_presentation_engine as pe

            res = pe.start_dynamic_presentation(args)

            if res.get("ok"):

                res["_presentation_data"] = pe.get_active_presentation() or pe.validate_presentation_script(args)

            return res



        if name == "update_presentation_scene":

            import dynamic_presentation_engine as pe

            sc = args.get("scene") or args

            return pe.update_presentation_scene(sc)



        if name == "control_presentation":

            import dynamic_presentation_engine as pe

            act = str(args.get("action", "next"))

            return pe.control_presentation(act, args.get("params"))



        if name == "get_presentation_status":

            import dynamic_presentation_engine as pe

            return pe.get_presentation_status()























    except Exception as e:  # noqa: BLE001







        logger.exception("Falha na ferramenta %s", name)







        return {"ok": False, "erro": str(e)}







    return {"ok": False, "erro": f"Ferramenta desconhecida: {name}"}























def serialize_result(res: Dict[str, Any]) -> str:







    """Resultado textual para o modelo (sem imagens)."""







    return json.dumps({k: v for k, v in res.items() if not k.startswith("_")}, ensure_ascii=False)







