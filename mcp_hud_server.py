#!/usr/bin/env python3
"""
J.A.R.V.I.S. HUD Model Context Protocol (MCP) Server
Permite que o Agente Jarvis no OpenClaw controle a interface holográfica HUD em tempo real.
Totalmente empacotável em Docker e Docker-Compose.
"""

import os
import re
import json
import urllib.request
import time
import hardware_control as hc
from mcp.server.fastmcp import FastMCP

HUD_SERVER_URL = os.environ.get("HUD_SERVER_URL", "http://localhost:8080")
MCP_PORT = int(os.environ.get("MCP_PORT", "8081"))
MASTER_KEY = os.environ.get("MASTER_ACCESS_KEY", "")

mcp = FastMCP("jarvis-hud", host="0.0.0.0", port=MCP_PORT)

def send_master_request(path: str, payload: dict = None, method: str = "POST") -> dict:
    """Chama o Core Server com a chave mestre (endpoints administrativos RBAC/WoL)."""
    try:
        url = f"{HUD_SERVER_URL}{path}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {
            "Content-Type": "application/json",
            "X-Master-Key": MASTER_KEY,
            "User-Agent": "JarvisMCP/1.0"
        }
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"status": "error", "error": f"Falha na comunicação com o Core ({path}): {e}"}

def send_hud_event(payload: dict) -> dict:
    try:
        url = f"{HUD_SERVER_URL}/api/hud/control"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"status": "error", "message": f"Erro de comunicação com o HUD ({HUD_SERVER_URL}): {e}"}

BRIDGE_SECRET = os.environ.get("BRIDGE_SECRET", os.environ.get("OPENCLAW_GATEWAY_TOKEN"))

def windows_via_bridge(action: str, params: dict = None, wait_seconds: float = 15.0, node_id: str = "") -> dict:
    """Executa uma ação de controle no PC Windows do Senhor Werik via Ponte de Comandos.
    Enfileira no Core Server, aguarda o desktop app executar e devolve o resultado.
    node_id vazio = qualquer PC online; informe 'jarvis-pc-<hostname>' para direcionar um PC específico."""
    try:
        req = urllib.request.Request(
            f"{HUD_SERVER_URL}/api/remote/enqueue",
            data=json.dumps({"action": action, "params": params or {}, "node_id": node_id}).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-Bridge-Secret": BRIDGE_SECRET}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            enqueue = json.loads(resp.read().decode("utf-8"))
        cmd_id = str(enqueue.get("id", ""))
        if not cmd_id:
            return {"success": False, "error": f"Fila não aceitou o comando: {enqueue}"}
        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            time.sleep(0.8)
            r = urllib.request.Request(
                f"{HUD_SERVER_URL}/api/remote/result?id={cmd_id}",
                headers={"X-Bridge-Secret": BRIDGE_SECRET}
            )
            with urllib.request.urlopen(r, timeout=8) as resp:
                entry = json.loads(resp.read().decode("utf-8"))
            if not entry.get("pending", True):
                return {"success": bool(entry.get("ok")), "command": action, "result": entry.get("result")}
        return {"success": False, "error": "PC Windows não respondeu a tempo (ponte offline ou comando longo)."}
    except Exception as e:
        return {"success": False, "error": f"Falha na ponte de comandos: {e}"}

@mcp.tool()
def executar_comando_windows(acao: str, params_json: str = "{}", node_id: str = "") -> str:
    """Executa QUALQUER ação de controle no PC Windows do Senhor Werik (mídia, volume, apps, janelas, teclado, mouse, clipboard, screenshot, telemetry e comandos de sistema).

    Args:
        acao: Ação namespaced. Exemplos VÁLIDOS:
            - 'audio.set_volume' (params: {"percent": 40})
            - 'audio.volume_up' / 'audio.volume_down' / 'audio.mute' (params: {"mute": true})
            - 'media.play_pause' / 'media.next' / 'media.prev'
            - 'application.open' (params: {"application": "chrome"})
            - 'application.close' (params: {"application": "chrome.exe"})
            - 'windows.focus_window' (params: {"title": "Word"})
            - 'windows.close_window' / 'windows.minimize_window' / 'windows.maximize_window'
            - 'keyboard.type_text' (params: {"text": "..."})
            - 'keyboard.press_key' (params: {"key": "enter"}) / 'keyboard.press_hotkey' (params: {"keys": "ctrl+s"})
            - 'mouse.click' / 'mouse.double_click' / 'mouse.right_click' / 'mouse.move' (params: {"x": 900, "y": 500}) / 'mouse.scroll' (params: {"clicks": -5})
            - 'clipboard.get' / 'clipboard.set' (params: {"text": "..."})
            - 'screen.snapshot' (params: {"monitor": 0} — não use no replicado: captura REAL)
            - 'system.info' (telemetria: GPU, CPU, RAM)
            - 'system.run' (params: {"command": "dir C:\\Users"}) — PowerShell/CMD no PC
        params_json: JSON com os parâmetros da ação (ex: '{"percent": 40}').
        node_id: OPCIONAL — deixe vazio quando só existe um PC. Com múltiplos PCs, informe o destino
            ('jarvis-pc-<hostname>', ex: 'jarvis-pc-werik'); vazio = o comando vai para o primeiro PC online.
    """
    try:
        params = json.loads(params_json) if params_json and params_json.strip() else {}
    except Exception:
        return f"params_json inválido: {params_json}"
    res = windows_via_bridge(acao, params, node_id=node_id)
    if res.get("success"):
        return f"AÇÃO EXECUTADA NO WINDOWS: {json.dumps(res.get('result'), ensure_ascii=False)[:600]}"
    return f"A execução falhou: {res.get('error')} | Detalhe: {res.get('command', '')}"


@mcp.tool()
def spotify_controlar(acao: str, valor: str = "", musica: str = "", dispositivo: str = "") -> str:
    """Controla a reprodução do Spotify do Senhor Werik (conta conectada) via Spotify Web API.

    Args:
        acao: 'play' (tocar — use com 'musica'), 'pause', 'toggle' (pausa/despausa),
            'next' (próxima), 'previous' (anterior), 'volume', 'seek', 'now_playing',
            'devices' (lista os aparelhos Spotify disponíveis: PC, Alexa, celular...).
        valor: Só para 'volume' (0-100) e 'seek' (ms). Ex: "40".
        musica: Nome da música/artista para 'play'. Ex: "Back in Black AC/DC".
        dispositivo: Aparelho onde tocar (trecho do nome). Ex: "PC", "Werik", "Alexa".
            Deixe vazio para tocar no dispositivo ativo (abre o Spotify no PC se necessário).
    """
    def _call():
        body = {"action": acao}
        if valor not in (None, ""):
            try:
                body["value"] = int(valor)
            except Exception:
                body["value"] = valor
        if musica:
            body["query"] = musica
        if dispositivo:
            body["device"] = dispositivo
        req = urllib.request.Request(f"{HUD_SERVER_URL}/api/spotify/control",
                                     data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))

    try:
        res = _call()
        a = acao.lower().strip()
        is_play = a in ("play", "tocar", "tocar_musica", "play_music")

        # Se pediu para tocar e NÃO há dispositivo ativo: se o alvo é o PC (ou vazio),
        # abre o Spotify no Windows e tenta de novo (API assume a faixa certa).
        alvo_pc = (not dispositivo) or any(w in str(dispositivo).lower() for w in ["pc", "windows", "computador", "werik", "desktop"])
        if is_play and (not res.get("ok")) and alvo_pc and "dispositivo" in str(res.get("error", "")).lower():
            try:
                windows_via_bridge("application.open", {"application": "spotify"}, wait_seconds=6.0)
            except Exception:
                pass
            time.sleep(9)  # aguarda o Spotify abrir e registrar como dispositivo
            res = _call()

        if res.get("ok"):
            if a in ("now_playing", "status", "tocando", "atual"):
                return (f"Spotify: {'TOCANDO' if res.get('playing') else 'PAUSADO'} — "
                        f"'{res.get('title')}' de {res.get('artist')} (álbum {res.get('album')}, aparelho {res.get('device')}).")
            if a in ("devices", "dispositivos", "aparelhos"):
                ds = res.get("devices") or []
                return "Aparelhos Spotify: " + ", ".join(f"{d.get('name')}{' (ATIVO)' if d.get('active') else ''}" for d in ds)
            if is_play:
                return f"Spotify tocando: {res.get('track')} no aparelho {res.get('device')}."
            return f"Spotify: ação '{acao}' executada." + (f" (valor: {res.get('volume', res.get('position_ms', ''))})" if valor else "")
        return f"Falha no Spotify: {res.get('error')} | Aparelhos: {res.get('devices')}"
    except Exception as e:
        return f"Erro ao controlar o Spotify: {e}"

@mcp.tool()
def abrir_tela_hud(tela: str, destaque: str = "", parecer: str = "") -> str:
    """Abre ou destaca uma tela/card no HUD holográfico do usuário em tempo real enquanto você fala.
    
    Args:
        tela: Nome da tela a ser exibida: 'financas', 'clima', 'noticias', 'servidor'.
        destaque: Opcional. Item ou valor específico para dar destaque neon (ex: 'santander', 'mei', 'temperatura').
        parecer: Opcional. Análise ou texto a ser exibido no card de finanças enquanto você fala.
    """
    payload = {
        "action": "open_screen",
        "screen": tela.lower().strip(),
        "highlight": destaque.lower().strip()
    }
    if parecer:
        payload["parecer"] = parecer
    res = send_hud_event(payload)
    return f"Tela '{tela}' projetada no HUD com sucesso."

@mcp.tool()
def exibir_na_esfera(titulo: str, mensagem: str, botao1: str = "", botao2: str = "") -> str:
    """Exibe um card/mensagem na tela da Esfera física J.A.R.V.I.S. (o dispositivo redondo com display na mesa do usuário).

    Use quando o usuário pedir para MOSTRAR/EXIBIR algo NA ESFERA, ou quando fizer sentido apresentar uma
    informação curta no display físico (clima, recado, status, resposta de um comando).

    Args:
        titulo: Título curto do card (ex: 'PREVISÃO', 'RECADO', 'ALERTA', 'SPOTIFY').
        mensagem: Texto principal exibido no display da esfera. Seja CONCISO — a tela é pequena (~240px), use no máximo ~80 caracteres.
        botao1: Opcional. Rótulo do primeiro botão de toque (ex: 'OK'). Deixe vazio se não houver.
        botao2: Opcional. Rótulo do segundo botão de toque (ex: 'Cancelar'). Deixe vazio se não houver.
    """
    screen = {
        "title": titulo,
        "message": mensagem,
        "button1_id": "btn1" if botao1 else "",
        "button1_label": botao1,
        "button2_id": "btn2" if botao2 else "",
        "button2_label": botao2,
    }
    try:
        req = urllib.request.Request(
            f"{HUD_SERVER_URL}/api/esfera/show_screen",
            data=json.dumps({"screen": screen}).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "JarvisMCP/1.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            res = json.loads(resp.read().decode("utf-8"))
        if res.get("status") == "success":
            return f"Card '{titulo}' exibido na tela da esfera."
        return f"Falha ao exibir na esfera: {res.get('message', res)}"
    except Exception as e:
        return f"Erro ao exibir na esfera: {e}"

@mcp.tool()
def mostrar_rosto_esfera(emocao: str = "happy") -> str:
    """Muda a expressão (rostinho robô) na tela da Esfera física J.A.R.V.I.S.

    Args:
        emocao: 'happy' (feliz/ciano), 'sad' (triste/azul), 'angry' (bravo/vermelho), 'spotify' (player de música) ou 'standby' (relógio/standby).
    """
    try:
        req = urllib.request.Request(
            f"{HUD_SERVER_URL}/api/esfera/emotion",
            data=json.dumps({"emotion": emocao}).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "JarvisMCP/1.0"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            res = json.loads(resp.read().decode("utf-8"))
        if res.get("status") == "success":
            return f"Rosto da esfera alterado para '{emocao}'."
        return f"Falha ao mudar o rosto da esfera: {res.get('message', res)}"
    except Exception as e:
        return f"Erro ao mudar o rosto da esfera: {e}"

@mcp.tool()
def atualizar_firmware_esfera_ota(url_firmware: str = "") -> str:
    """Dispara a atualizacao de firmware sem fio (OTA - Over-The-Air) para a Esfera ESP32-S3.

    Use quando o usuario pedir para 'atualizar a esfera', 'atualizar firmware via OTA', ou 'gravar o novo firmware na esfera'.
    A esfera recebera a instrucao via WebSocket, baixara o binario diretamente pelo Wi-Fi (exibindo a porcentagem no display),
    gravara na memoria flash e reiniciara automaticamente.

    Args:
        url_firmware: Opcional. URL HTTP ou HTTPS completa do firmware (.bin). Se vazio, usa o firmware oficial padrao ('http://45.167.187.80:8095/firmware.bin').
    """
    target_url = url_firmware.strip() if url_firmware.strip() else "http://45.167.187.80:8095/firmware.bin"
    payload = {"url": target_url}

    send_hud_event({
        "type": "alert",
        "title": "ATUALIZACAO OTA INICIADA",
        "message": f"Disparando atualizacao sem fio (OTA) para a Esfera ({target_url})...",
        "level": "aviso",
        "timestamp": time.time()
    })

    endpoints = [
        f"{HUD_SERVER_URL}/api/esfera/ota",
        "http://jarvis-screen-router:8095/api/jarvis/ota/trigger",
        "http://127.0.0.1:8095/api/jarvis/ota/trigger",
        "http://45.167.187.80:8095/api/jarvis/ota/trigger"
    ]

    for ep in endpoints:
        try:
            req = urllib.request.Request(
                ep,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "User-Agent": "JarvisMCP/1.0"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                res = json.loads(resp.read().decode("utf-8"))
            if res.get("status") in ("success", "ok"):
                return f"Atualizacao OTA da Esfera disparada com sucesso! A Esfera iniciou o download do firmware em '{target_url}' e reiniciara assim que concluir."
        except Exception:
            continue

    return f"Falha ao contatar os servicos de OTA da Esfera. Verifique se o jarvis-screen-router ou jarvis-hud estao ativos."


@mcp.tool()
def projetar_card_financeiro(parecer: str) -> str:
    """Projeta a tela de finanças reais no painel HUD holográfico do usuário e insere seu parecer técnico/análise diretamente no card em tempo real.
    
    Args:
        parecer: O texto explicativo ou análise que você quer que apareça escrito dentro do card de finanças reais no HUD.
    """
    res = send_hud_event({
        "action": "open_screen",
        "screen": "finance",
        "parecer": parecer
    })
    return "Card de finanças reais projetado no HUD com seu parecer."

@mcp.tool()
def obter_dados_financeiros_reais() -> str:
    """Consulta os dados financeiros e bancários reais do usuário diretamente da API Pluggy Open Finance.
    Retorna os saldos exatos das contas reais: Banco Inter Conta Corrente e Banco Inter Cartão MEI.
    """
    try:
        url = f"{HUD_SERVER_URL}/api/status"
        req = urllib.request.Request(url, headers={"User-Agent": "JarvisHUD/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            finance = data.get("finance", {})
            accounts = finance.get("accounts", [])
            if not accounts:
                return "Nenhuma conta sincronizada na API Pluggy no momento."
            
            lines = ["Contas Reais Conectadas (Pluggy Open Finance):"]
            for idx, a in enumerate(accounts, 1):
                name = a.get("name", "CONTA")
                bal = a.get("balance", 0.0)
                tipo = "Fatura Atual" if "MEI" in name or a.get("type") == "CREDIT" else "Saldo Disponível"
                lines.append(f"{idx}. {name}: {tipo} R$ {bal:.2f}".replace('.', ','))
            lines.append(f"Sincronização: {finance.get('updated_at', 'Recente')}")
            return "\n".join(lines)
    except Exception as e:
        return f"Falha ao consultar Pluggy Open Finance: {e}"


@mcp.tool()
def mudar_estagio_apresentacao(estagio: int) -> str:
    """Altera o estágio do layout dinâmico dos cards no HUD holográfico.
    
    Args:
        estagio: Estágio desejado: 1 (Foco Clima Catanduva), 2 (Finanças Pluggy & E-mails), 3 (Radar de Notícias).
    """
    res = send_hud_event({
        "action": "set_stage",
        "stage": int(estagio)
    })
    return f"Layout do HUD alterado para o estágio {estagio}."

@mcp.tool()
def exibir_alerta_hud(titulo: str, mensagem: str, nivel: str = "aviso") -> str:
    """Exibe um banner holográfico de alerta imediato no topo da tela do HUD do usuário.
    
    Args:
        titulo: Título curto do alerta (ex: 'Atenção Fatura', 'Alerta Servidor').
        mensagem: Descrição detalhada do alerta.
        nivel: Gravidade do alerta: 'info', 'aviso', ou 'critico'.
    """
    res = send_hud_event({
        "action": "alert",
        "title": titulo,
        "message": mensagem,
        "level": nivel
    })
    return f"Alerta '{titulo}' projetado no HUD."

@mcp.tool()
def iniciar_timer_hud(minutos: float, rotulo: str = "TIMER") -> str:
    """Inicia um cronômetro regressivo visual holográfico animado em tempo real no HUD do usuário (ex: quando o usuário pedir 'inicia um timer de 5 min').
    
    Args:
        minutos: Tempo em minutos (ex: 5 para 5 minutos, 10 para 10 minutos, 2.5 para 2m30s).
        rotulo: Descrição ou nome do timer (ex: 'Foco', 'Pausa', 'Cozinha', 'Alarme').
    """
    segundos = int(float(minutos) * 60)
    res = send_hud_event({
        "action": "custom_card",
        "title": f"TIMER: {int(minutos) if float(minutos).is_integer() else minutos} MINUTOS",
        "subtitle": rotulo.upper(),
        "content": f"Cronômetro regressivo ativado pelo Jarvis para {minutos} minutos.",
        "card_type": "timer",
        "duration": segundos
    })
    return f"Cronômetro de {minutos} minutos ({segundos} segundos) projetado no HUD."

@mcp.tool()
def criar_card_customizado(titulo: str, subtitulo: str, conteudo: str, tipo: str = "padrao", duracao_segundos: int = 0) -> str:
    """Projeta um novo card customizado dinâmico no HUD holográfico para qualquer informação, timer, tarefa, cálculo ou análise sob demanda solicitada pelo usuário.
    
    Args:
        titulo: Título principal do card (ex: 'RESUMO DIÁRIO', 'TIMER DE FOCO', 'LISTA DE TAREFAS').
        subtitulo: Subtítulo ou categoria (ex: 'PROCESSO ATIVO', 'CONTAGEM REGRESSIVA').
        conteudo: Texto ou resumo explicativo formatado.
        tipo: Tipo do card: 'padrao', 'timer' (ativa cronômetro digital animado com barra de progresso).
        duracao_segundos: Opcional. Duração em segundos se for um timer (ex: 300 para 5 minutos).
    """
    res = send_hud_event({
        "action": "custom_card",
        "title": titulo,
        "subtitle": subtitulo,
        "content": conteudo,
        "card_type": tipo,
        "duration": int(duracao_segundos)
    })
    return f"Card customizado '{titulo}' projetado no HUD holográfico."

@mcp.tool()
def obter_temperatura_real_catanduva() -> str:
    """Consulta os dados meteorológicos reais e exatos de Catanduva / SP diretamente da estação Open-Meteo.
    Retorna a temperatura atual real, umidade, vento, mínimas e máximas do dia.
    """
    try:
        url = "https://api.open-meteo.com/v1/forecast?latitude=-21.1378&longitude=-48.9728&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m&daily=temperature_2m_max,temperature_2m_min&timezone=America%2FSao_Paulo"
        req = urllib.request.Request(url, headers={"User-Agent": "JarvisHUD/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            curr = data.get("current", {})
            daily = data.get("daily", {})
            temp = curr.get("temperature_2m")
            hum = curr.get("relative_humidity_2m")
            wind = curr.get("wind_speed_10m")
            t_max_list = daily.get("temperature_2m_max", [])
            t_min_list = daily.get("temperature_2m_min", [])
            t_max = t_max_list[0] if t_max_list else "--"
            t_min = t_min_list[0] if t_min_list else "--"
            return (
                f"Meteorologia Real de Catanduva / SP:\n"
                f"- Temperatura Atual: {temp}°C\n"
                f"- Umidade do Ar: {hum}%\n"
                f"- Vento: {wind} km/h\n"
                f"- Máxima Prevista: {t_max}°C | Mínima: {t_min}°C"
            )
    except Exception as e:
        return f"Catanduva / SP: Dados meteorológicos indisponíveis no momento ({e})"

@mcp.tool()
def projetar_hardware_hud() -> str:
    """Projeta o card holográfico de telemetria da máquina física local no HUD (GPU NVIDIA GeForce GTX 1660 Ti, CPU, Memória RAM e SSD C:)."""
    try:
        url = f"{HUD_SERVER_URL}/api/hardware"
        req = urllib.request.Request(url, headers={"User-Agent": "JarvisHUD/1.0"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            hw = json.loads(resp.read().decode('utf-8'))
    except Exception:
        hw = {}
    send_hud_event({
        "action": "open_screen",
        "screen": "hardware",
        "metrics": hw
    })
    return "Card de telemetria de hardware local (GPU GTX 1660 Ti, CPU, RAM) projetado no HUD."

@mcp.tool()
def tocar_youtube_hud(termo_ou_musica: str) -> str:
    """Busca e inicia a reprodução de um vídeo ou música no YouTube diretamente no player holográfico do HUD (Zero Contas).
    
    Args:
        termo_ou_musica: Nome da música, artista ou vídeo para reproduzir (ex: 'Back in Black AC/DC', 'musica lofi relaxante').
    """
    import hardware_control as hc
    yt = hc.search_youtube_video(termo_ou_musica)
    if yt:
        send_hud_event({
            "action": "play_youtube",
            "video_id": yt["video_id"],
            "title": yt["title"],
            "embed_url": yt["embed_url"]
        })
        return f"Reprodução de '{yt['title']}' iniciada no player do HUD."
    return f"Nenhum vídeo encontrado no YouTube para '{termo_ou_musica}'. Tente refinar o termo de busca."
@mcp.tool()
def projetar_canvas_interativo(
    titulo: str,
    categoria: str = "TÁTICO",
    layout: str = "sidebar",
    subtitulo: str = "",
    blocks_json: str = "[]"
) -> str:
    """Projeta um canvas holográfico interativo com blocos estruturados e dados 100% reais no HUD.
    
    Args:
        titulo: Título principal do canvas (ex: 'RADAR DE CONTAINERS', 'TRANSAÇÕES REAIS').
        categoria: Categoria tática (ex: 'INFRAESTRUTURA', 'FINANCEIRO', 'DIAGNÓSTICO').
        layout: Modo de visualização: 'sidebar' (painel lateral direito), 'center' (card centralizado) ou 'modal' (janela cheia).
        subtitulo: Subtítulo descritivo.
        blocks_json: String JSON contendo array de blocos tipados (metric_grid, interactive_table, action_buttons, code_terminal).
    """
    try:
        blocks = json.loads(blocks_json) if isinstance(blocks_json, str) else blocks_json
    except Exception:
        blocks = []
    
    canvas_payload = {
        "title": titulo,
        "subtitle": subtitulo,
        "category": categoria,
        "layout_mode": layout,
        "blocks": blocks
    }
    
    send_hud_event({
        "action": "canvas_projection",
        "canvas": canvas_payload
    })
    return f"Canvas interativo '{titulo}' projetado no HUD no modo '{layout}'."

@mcp.tool()
def projetar_radar_containers_zimaos() -> str:
    """Projeta a tabela tática interativa com todos os 39 containers reais do servidor ZimaOS (127.0.0.1) com status real e botões de reinicialização e logs."""
    try:
        url = f"{HUD_SERVER_URL}/api/canvas/action"
        req = urllib.request.Request(url, data=json.dumps({"action": "refresh_canvas_containers"}).encode("utf-8"), headers={"Content-Type": "application/json", "User-Agent": "JarvisHUD/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return "Matriz interativa de containers reais do ZimaOS projetada com sucesso no HUD."
    except Exception as e:
        return f"Falha ao carregar radar de containers do ZimaOS: {e}"

@mcp.tool()
def projetar_processos_windows_reais() -> str:
    """Projeta o gerenciador tático de processos ativos do Windows com consumo real de CPU e memória RAM (psutil)."""
    try:
        url = f"{HUD_SERVER_URL}/api/canvas/action"
        req = urllib.request.Request(url, data=json.dumps({"action": "refresh_windows_processes"}).encode("utf-8"), headers={"Content-Type": "application/json", "User-Agent": "JarvisHUD/1.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return "Matriz de processos do Windows projetada com sucesso no HUD."
    except Exception as e:
        return f"Falha ao carregar processos do Windows: {e}"

@mcp.tool()
def projetar_extrato_pluggy_real() -> str:
    """Projeta a tabela com todas as transações reais da fatura do cartão MEI e conta corrente do Banco Inter via Pluggy Open Finance."""
    try:
        url = f"{HUD_SERVER_URL}/api/canvas/action"
        req = urllib.request.Request(url, data=json.dumps({"action": "refresh_pluggy"}).encode("utf-8"), headers={"Content-Type": "application/json", "User-Agent": "JarvisHUD/1.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return "Extrato real consolidado Pluggy projetado com sucesso no HUD."
    except Exception as e:
        return f"Falha ao carregar extrato Pluggy: {e}"

@mcp.tool()
def projetar_radar_conectividade() -> str:
    """Projeta o radar com latência TCP real (ping em ms) para ZimaOS SSH, Nginx, n8n, WAHA e DNS Cloudflare."""
    try:
        url = f"{HUD_SERVER_URL}/api/canvas/action"
        req = urllib.request.Request(url, data=json.dumps({"action": "refresh_connectivity"}).encode("utf-8"), headers={"Content-Type": "application/json", "User-Agent": "JarvisHUD/1.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return "Radar de conectividade e ping em tempo real projetado com sucesso no HUD."
    except Exception as e:
        return f"Falha ao medir conectividade: {e}"

@mcp.tool()
def projetar_noticia_hud(
    titulo: str,
    conteudo: str,
    fonte: str = "PORTAL REGIONAL",
    imagem_url: str = "",
    url_origem: str = "",
    categoria: str = "CATANDUVA & REGIÃO"
) -> str:
    """Projeta o card holográfico de notícias com imagem real, manchete e teleprompter no HUD.
    
    Args:
        titulo: Manchete principal da matéria.
        conteudo: Texto detalhado ou parágrafos da notícia.
        fonte: Nome do portal de notícias ou fonte oficial.
        imagem_url: Opcional. URL da foto da matéria.
        url_origem: Opcional. Link oficial para ler no navegador.
        categoria: Categoria editorial (ex: 'CATANDUVA & REGIÃO', 'TECNOLOGIA & IA').
    """
    send_hud_event({
        "action": "open_screen",
        "screen": "news",
        "news": {
            "title": titulo,
            "headline": titulo,
            "body": conteudo,
            "full_text": conteudo,
            "source": fonte,
            "image_url": imagem_url or "https://images.unsplash.com/photo-1504711434969-e33886168f5c?q=80&w=1000&auto=format&fit=crop",
            "url": url_origem,
            "category": categoria
        },
        "title": titulo,
        "content": conteudo
    })
    return f"Card de notícia '{titulo}' projetado no HUD com teleprompter ativo."

@mcp.tool()
def projetar_openclaw_hud() -> str:
    """Projeta a telemetria, status do container, modelo Gemini 3.8 Flash e logs em tempo real do OpenClaw no HUD."""
    try:
        url = f"{HUD_SERVER_URL}/api/canvas/action"
        req = urllib.request.Request(url, data=json.dumps({"action": "refresh_openclaw"}).encode("utf-8"), headers={"Content-Type": "application/json", "User-Agent": "JarvisHUD/1.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return "Painel do OpenClaw projetado com sucesso no HUD."
    except Exception as e:
        return f"Falha ao carregar painel do OpenClaw: {e}"

@mcp.tool()
def ativar_webcam_visao(ativar: bool = True) -> str:
    """Liga ou desliga a visão computacional e tracking por webcam do J.A.R.V.I.S.
    
    Args:
        ativar: True para ligar a câmera e rastrear gestos, False para desligar e entrar em standby (0% CPU).
    """
    try:
        endpoint = "/api/vision/enable" if ativar else "/api/vision/disable"
        url = f"{HUD_SERVER_URL}{endpoint}"
        req = urllib.request.Request(url, data=b"{}", headers={"Content-Type": "application/json", "User-Agent": "JarvisMCP/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            estado = "ATIVADA" if ativar else "DESATIVADA (Standby)"
            return f"Visão computacional e webcam do J.A.R.V.I.S. {estado} com sucesso."
    except Exception as e:
        return f"Erro ao alternar visão computacional: {e}"

@mcp.tool()
def obter_status_visao() -> str:
    """Consulta a telemetria em tempo real do motor de visão computacional local: status da câmera, FPS real, presença do usuário, último gesto e confiança."""
    try:
        url = f"{HUD_SERVER_URL}/api/vision/status"
        req = urllib.request.Request(url, headers={"User-Agent": "JarvisMCP/1.0"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            s = json.loads(resp.read().decode('utf-8'))
            ativo = "Ativa (Capturando)" if s.get("enabled") else "Em espera (Standby)"
            pres = "Detectado diante da câmera" if s.get("user_present") else "Não detectado"
            return (
                f"Status da Visão Computacional J.A.R.V.I.S.:\n"
                f"- Câmera: {s.get('camera_device', 'Padrão')} ({s.get('resolution', '640x480')}) | Estado: {ativo}\n"
                f"- Taxa de Frames: {s.get('fps', 0.0)} FPS\n"
                f"- Presença do Usuário: {pres}\n"
                f"- Mão Detectada: {s.get('hand', 'Nenhuma')}\n"
                f"- Gesto Atual: {s.get('gesture_emoji', '')} {s.get('gesture', 'none')} ({s.get('confidence_pct', 0)}% confiança)\n"
                f"- Último Evento: {s.get('last_event_summary', 'Nenhum')} às {s.get('last_event_time', '--:--:--')}\n"
                f"- Conexão OpenClaw: {'Conectado' if s.get('openclaw_connected') else 'Desconectado'}"
            )
    except Exception as e:
        return f"Erro ao consultar status da visão: {e}"

@mcp.tool()
def configurar_gesto_acao(gesto: str, acao: str, alvo: str = "", nivel_risco: str = "low") -> str:
    """Configura ou altera o mapeamento entre um gesto da mão e uma ação automatizada no Windows.
    
    Args:
        gesto: Nome do gesto (ex: 'thumbs_up', 'fist', 'open_hand', 'point_up', 'point_down', 'peace_sign', 'swipe_left', 'swipe_right').
        acao: Ação a executar (ex: 'volume_up', 'volume_down', 'media_play_pause', 'media_next', 'minimize_all', 'lock_workstation', 'open_app').
        alvo: Parâmetro opcional para a ação (ex: nome do aplicativo como 'notepad' para open_app).
        nivel_risco: 'low' para execução imediata ou 'high' para ações que exigem confirmação.
    """
    try:
        url = f"{HUD_SERVER_URL}/api/vision/config"
        payload = {
            "gesture_mappings": {
                gesto: {
                    "action": acao,
                    "target": alvo,
                    "risk_level": nivel_risco
                }
            }
        }
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers={"Content-Type": "application/json", "User-Agent": "JarvisMCP/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return f"Mapeamento configurado: gesto '{gesto}' -> ação '{acao}' (risco: {nivel_risco})."
    except Exception as e:
        return f"Erro ao configurar mapeamento de gesto: {e}"

@mcp.tool()
def criar_painel_personalizado(
    titulo: str,
    conteudo_markdown: str,
    posicao: str = "center",
    categoria: str = "PERSONALIZADO",
    subtitulo: str = "",
    metricas_json: str = "[]",
    tabela_json: str = "{}"
) -> str:
    """Cria e projeta no HUD qualquer widget ou painel dinâmico e personalizado sob medida para o pedido do usuário (notícias específicas, agenda, extrato personalizado, tarefas, etc).
    
    Args:
        titulo: Título principal do painel (ex: 'AGENDA DE HOJE', 'NOTÍCIA: AVANÇOS EM IA', 'SALDO BANCO INTER').
        conteudo_markdown: Texto formatado, tópicos ou detalhes em Markdown.
        posicao: Onde exibir na tela: 'center' (card central holográfico), 'sidebar' (painel lateral tático), 'modal' (janela cheia), 'top-right', 'bottom-left'.
        categoria: Categoria tática (ex: 'AGENDA', 'NOTÍCIAS', 'FINANÇAS', 'PERSONALIZADO').
        subtitulo: Subtítulo descritivo.
        metricas_json: Opcional. String JSON ou lista de métricas: [{"label": "...", "value": "...", "color": "cyan"|"emerald"|"rose"|"amber"}].
        tabela_json: Opcional. String JSON ou objeto de tabela: {"columns": [...], "rows": [{"cells": [...]}]}.
    """
    blocks = []
    
    # 1. Grid de métricas se fornecido
    if metricas_json:
        try:
            m_items = json.loads(metricas_json) if isinstance(metricas_json, str) else metricas_json
            if m_items and isinstance(m_items, list):
                blocks.append({
                    "type": "metric_grid",
                    "columns": min(len(m_items), 3),
                    "items": m_items
                })
        except Exception:
            pass

    # 2. Conteúdo em Markdown
    if conteudo_markdown:
        blocks.append({
            "type": "markdown",
            "content": conteudo_markdown
        })
        
    # 3. Tabela interativa se fornecida
    if tabela_json:
        try:
            t_obj = json.loads(tabela_json) if isinstance(tabela_json, str) else tabela_json
            if t_obj and isinstance(t_obj, dict) and t_obj.get("columns"):
                blocks.append({
                    "type": "interactive_table",
                    "table_id": f"table_{int(time.time())}",
                    "columns": t_obj.get("columns", []),
                    "rows": t_obj.get("rows", [])
                })
        except Exception:
            pass

    canvas_payload = {
        "title": titulo,
        "subtitle": subtitulo,
        "category": categoria,
        "layout_mode": posicao,
        "blocks": blocks
    }
    
    send_hud_event({
        "action": "canvas_projection",
        "canvas": canvas_payload
    })
    return f"Painel personalizado '{titulo}' projetado no HUD na posição '{posicao}'."

@mcp.tool()
def buscar_e_projetar_noticia(
    tema: str = "tecnologia e inovação",
    posicao: str = "center"
) -> str:
    """Pesquisa as últimas notícias reais em tempo real sobre qualquer assunto solicitado e projeta um painel dinâmico no HUD.
    
    Args:
        tema: Assunto da notícia (ex: 'inteligência artificial', 'catanduva sp', 'mercado financeiro', 'tecnologia').
        posicao: Onde exibir: 'center' (card central holográfico), 'sidebar' (painel lateral) ou 'modal'.
    """
    news_items = hc.search_realtime_news(tema, max_results=3)
    if not news_items:
        return f"Nenhuma notícia encontrada para '{tema}' no momento."
    
    top = news_items[0]
    blocks = []
    
    # Imagem se disponível
    if top.get("image_url"):
        blocks.append({
            "type": "html",
            "content": f'<div class="relative w-full h-44 rounded-xl overflow-hidden mb-3 border border-sky-400/40 bg-slate-950"><img src="{top["image_url"]}" class="w-full h-full object-cover"><div class="absolute bottom-2 left-2 px-2 py-0.5 rounded bg-black/70 border border-cyan-400/40 text-[10px] text-cyan-300 font-mono-code">{top.get("source", "FONTE")}</div></div>'
        })
        
    full_text = f"### {top['title']}\n\n"
    if top.get("paragraphs"):
        full_text += "\n\n".join(top["paragraphs"])
    else:
        full_text += top.get("body", "")
        
    if len(news_items) > 1:
        full_text += "\n\n---\n**OUTRAS MANCHETES NO RADAR:**\n"
        for other in news_items[1:]:
            full_text += f"- **{other['title']}** ({other.get('source', 'Fonte')})\n"
            
    blocks.append({
        "type": "markdown",
        "content": full_text
    })
    
    canvas_payload = {
        "title": top["title"][:50].upper(),
        "subtitle": f"RADAR DE NOTÍCIAS • {tema.upper()}",
        "category": "INFORMAÇÃO EM TEMPO REAL",
        "layout_mode": posicao,
        "blocks": blocks
    }
    
    send_hud_event({
        "action": "canvas_projection",
        "canvas": canvas_payload
    })
    return f"Notícia sobre '{tema}' encontrada: '{top['title']}'. Painel holográfico projetado no modo '{posicao}'. Resumo: {top.get('body', '')[:200]}"

@mcp.tool()
def projetar_painel_visao_hud() -> str:
    """Projeta a seção de Visão Computacional e telemetria dos gestos no HUD holográfico."""
    send_hud_event({
        "action": "open_screen",
        "screen": "vision"
    })
    return "Painel de Visão Computacional projetado no HUD."

@mcp.tool()
def desligar_computador(delay_segundos: int = 30, forcar: bool = False, motivo: str = "Solicitado pelo J.A.R.V.I.S.") -> str:
    """Inicia o desligamento do computador Windows com timer e aviso holográfico na tela.
    
    Args:
        delay_segundos: Tempo em segundos antes de desligar (padrão 30s para dar tempo de salvar ou cancelar). Use 0 para imediato.
        forcar: Se True, força o fechamento de aplicativos abertos.
        motivo: Mensagem exibida pelo Windows ao desligar.
    """
    try:
        if os.name != "nt":
            cmd = f'shutdown /s /t {max(0, int(delay_segundos))}' + (' /f' if forcar else '') + f' /c "{motivo}"'
            res = windows_via_bridge("system.run", {"command": cmd}, wait_seconds=6.0)
            send_hud_event({
                "action": "alert",
                "title": "DESLIGAMENTO DO SISTEMA",
                "message": f"Desligamento do Windows agendado para daqui a {delay_segundos} segundos. Diga 'cancelar desligamento' para abortar.",
                "level": "aviso"
            })
            return f"Protocolo de desligamento enviado ao PC Windows via ponte. Resultado: {json.dumps(res, ensure_ascii=False)[:300]}"
        from desktop.windows_bridge import bridge as win_bridge
        res = win_bridge.shutdown_pc(delay=delay_segundos, force=forcar, message=motivo)
        send_hud_event({
            "action": "alert",
            "title": "DESLIGAMENTO DO SISTEMA",
            "message": f"Desligamento do Windows agendado para daqui a {delay_segundos} segundos. Diga 'cancelar desligamento' para abortar.",
            "level": "aviso"
        })
        return f"Protocolo de desligamento iniciado com sucesso no Windows. Timer: {delay_segundos} segundos."
    except Exception as e:
        return f"Erro ao executar ordem de desligamento: {e}"

@mcp.tool()
def reiniciar_computador(delay_segundos: int = 30, forcar: bool = False) -> str:
    """Reinicia o computador Windows com timer e aviso holográfico.
    
    Args:
        delay_segundos: Tempo em segundos antes de reiniciar (padrão 30s).
        forcar: Se True, força o fechamento de aplicativos.
    """
    try:
        if os.name != "nt":
            cmd = f'shutdown /r /t {max(0, int(delay_segundos))}' + (' /f' if forcar else '')
            res = windows_via_bridge("system.run", {"command": cmd}, wait_seconds=6.0)
            send_hud_event({
                "action": "alert",
                "title": "REINICIALIZAÇÃO DO SISTEMA",
                "message": f"Reinicialização do Windows agendada para {delay_segundos}s.",
                "level": "aviso"
            })
            return f"Protocolo de reinicialização enviado ao PC via ponte. Resultado: {json.dumps(res, ensure_ascii=False)[:300]}"
        from desktop.windows_bridge import bridge as win_bridge
        res = win_bridge.restart_pc(delay=delay_segundos, force=forcar)
        send_hud_event({
            "action": "alert",
            "title": "REINICIALIZAÇÃO DO SISTEMA",
            "message": f"Reinicialização agendada para {delay_segundos}s.",
            "level": "aviso"
        })
        return f"Protocolo de reinicialização iniciado. Timer: {delay_segundos} segundos."
    except Exception as e:
        return f"Erro ao reiniciar: {e}"

@mcp.tool()
def cancelar_desligamento() -> str:
    """Cancela imediatamente qualquer ordem de desligamento ou reinício agendada no Windows."""
    try:
        if os.name != "nt":
            res = windows_via_bridge("system.run", {"command": "shutdown /a"}, wait_seconds=6.0)
            send_hud_event({
                "action": "alert",
                "title": "DESLIGAMENTO CANCELADO",
                "message": "A ordem de desligamento foi abortada pelo operador.",
                "level": "sucesso"
            })
            return f"Cancelamento enviado ao PC via ponte. Resultado: {json.dumps(res, ensure_ascii=False)[:300]}"
        from desktop.windows_bridge import bridge as win_bridge
        res = win_bridge.abort_shutdown()
        send_hud_event({
            "action": "alert",
            "title": "DESLIGAMENTO CANCELADO",
            "message": "A ordem de desligamento foi abortada pelo operador.",
            "level": "sucesso"
        })
        return "Ordem de desligamento cancelada com sucesso no Windows."
    except Exception as e:
        return f"Erro ao cancelar desligamento: {e}"

@mcp.tool()
def suspender_computador() -> str:
    """Coloca o computador Windows em modo de suspensão / suspende a sessão."""
    try:
        if os.name != "nt":
            res = windows_via_bridge("system.run", {"command": "rundll32.exe powrprof.dll,SetSuspendState 0,1,0"}, wait_seconds=6.0)
            return f"Suspensão enviada ao PC via ponte. Resultado: {json.dumps(res, ensure_ascii=False)[:300]}"
        from desktop.windows_bridge import bridge as win_bridge
        res = win_bridge.sleep_pc()
        return "Computador colocado em modo de suspensão."
    except Exception as e:
        return f"Erro ao suspender sistema: {e}"

@mcp.tool()
def projetar_graficos_hardware(modo: str = "sidebar") -> str:
    """Projeta os gráficos de telemetria de hardware (GPU GTX 1660 Ti, CPU, RAM) diretamente no Canvas aberto do usuário.
    
    Args:
        modo: 'sidebar' para o painel lateral direito ou 'modal' para janela inteira expandida.
    """
    try:
        url = f"{HUD_SERVER_URL}/api/canvas/action"
        req = urllib.request.Request(
            url,
            data=json.dumps({"action": "refresh_hardware_charts", "target": modo}).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "JarvisHUD/1.0"}
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return "Gráficos de telemetria de hardware projetados no Canvas com sucesso."
    except Exception as e:
        return f"Falha ao projetar gráficos: {e}"

@mcp.tool()
def projetar_triagem_jev_laya(modo: str = "sidebar") -> str:
    """Projeta no HUD holográfico a matriz de Sistema 1 do JEV & Laya (TypeSafe AI) com latência, confiança e auditoria JEV Guard.
    
    Args:
        modo: 'sidebar', 'center' ou 'modal'.
    """
    try:
        from jev_laya import jev_engine
        telemetry = jev_engine.get_telemetry()
        res = send_hud_event({
            "action": "custom_card",
            "title": "JEV & LAYA (TYPESAFE AI) • SISTEMA 1",
            "subtitle": f"LATÊNCIA MÉDIA: {telemetry['avg_latency_ms']} ms | DECISÕES TIPADAS",
            "content": (
                f"### NÚCLEO SISTEMA 1 — TRIAGEM E JEV GUARD\n\n"
                f"- **Motor:** {telemetry['engine']} ({telemetry['version']})\n"
                f"- **Latência Média de Avaliação:** `{telemetry['avg_latency_ms']} ms` (Meta ~33ms)\n"
                f"- **Total de Decisões Tipadas:** `{telemetry['total_triages']}`\n"
                f"- **Auditorias JEV Guard:** `{telemetry['total_guards']}`\n\n"
                f"#### Distribuição de Agentes:\n"
                f"- 📅 **Lúcia (Agendamento):** {telemetry['distribution']['lucia']}\n"
                f"- 📈 **AdPilot (Tráfego):** {telemetry['distribution']['adpilot']}\n"
                f"- 🎨 **Designer (Criativos):** {telemetry['distribution']['designer']}\n"
                f"- 🤖 **JARVIS (Operações/Core):** {telemetry['distribution']['jarvis']}\n\n"
                f"#### Topologia Híbrida:\n"
                f"- **ZimaOS:** `{telemetry['zimaos_host']['address']}` (Core i5-2400 AVX/SSE isolado em `/DATA/AppData/ollaya`)\n"
                f"- **Windows:** `{telemetry['windows_host']['gpu']}` (Aceleração AVX2/CUDA)\n"
                f"- **Sistema 2:** `9Router (:20128)`\n"
            ),
            "card_type": "padrao",
            "duration": 0
        })
        return "Painel de telemetria do JEV & Laya projetado no HUD com sucesso."
    except Exception as e:
        return f"Erro ao projetar painel JEV: {e}"

@mcp.tool()
def avaliar_intencao_sistema_um(mensagem: str) -> str:
    """Executa a triagem rápida de Sistema 1 do JEV & Laya para uma mensagem e retorna a decisão estritamente tipada.
    
    Args:
        mensagem: A frase ou instrução a ser classificada.
    """
    try:
        from jev_laya import jev_engine
        decision = jev_engine.triage(mensagem)
        return json.dumps(decision.to_dict(), ensure_ascii=False, indent=2)
    except Exception as e:
        return f"Erro na triagem do Sistema 1: {e}"

# ==============================================================================
# RBAC - FERRAMENTAS DE OPERADORES E PERMISSÕES (USO DO PROPRIETÁRIO)
# ==============================================================================

@mcp.tool()
def listar_operadores_permissoes() -> str:
    """Lista todos os operadores biométricos cadastrados no J.A.R.V.I.S. com seus papéis, permissões efetivas e histórico de login."""
    res = send_master_request("/api/operators", payload=None, method="GET")
    if res.get("status") == "forbidden" or "operators" not in res:
        return f"Falha ao listar operadores: {res.get('error', res)}"
    lines = ["Operadores biométricos cadastrados e permissões efetivas:"]
    for op in res.get("operators", []):
        perms_on = [k for k, v in (op.get("permissions") or {}).items() if v]
        lines.append(
            f"- {op.get('name')} ({op.get('role')}) | Logins: {op.get('login_count', 0)} | "
            f"Último: {op.get('last_login') or 'nunca'} | Permissões ativas: {', '.join(perms_on) or 'nenhuma'}"
        )
    return "\n".join(lines)

@mcp.tool()
def configurar_permissoes_operador(nome: str, permissoes_json: str, papel: str = "") -> str:
    """Define as permissões de um operador biométrico (reservado ao Proprietário Werik).
    
    Args:
        nome: Nome do operador cadastrado (ex: 'Willian').
        permissoes_json: JSON com as permissões e valores true/false. Campos: full_access, chat, voice_commands, media_control, windows_control, clipboard, screen_capture, power_control, infra_control, finance_view, wake_on_lan.
        papel: Opcional. Novo papel do operador: 'Proprietário', 'Operador Autorizado' ou 'Convidado'.
    """
    try:
        perms = json.loads(permissoes_json) if isinstance(permissoes_json, str) else permissoes_json
    except Exception:
        return "JSON de permissões inválido. Use algo como {\"media_control\": true, \"chat\": true}."
    payload = {"name": nome, "permissions": perms}
    if papel:
        payload["role"] = papel
    res = send_master_request("/api/operators", payload)
    if res.get("success"):
        prof = res.get("profile", {})
        return (
            f"Permissões de '{nome}' atualizadas com sucesso. Papel: {prof.get('role', papel or 'inalterado')}. "
            f"Permissões efetivas: {json.dumps(prof.get('permissions', {}), ensure_ascii=False)}"
        )
    return f"Falha ao atualizar permissões de '{nome}': {res.get('error', res)}"

# ==============================================================================
# WAKE-ON-LAN - FERRAMENTAS PARA LIGAR PCs REMOTAMENTE
# ==============================================================================

@mcp.tool()
def enviar_wake_on_lan(dispositivo_ou_mac: str, ip_broadcast: str = "", porta: int = 9) -> str:
    """Liga um PC via Wake-on-LAN enviando o pacote mágico (mesma rede ou rede remota com IP fixo).
    
    Args:
        dispositivo_ou_mac: Nome do dispositivo cadastrado (ex: 'pc-escritorio') OU o MAC direto (ex: 'AA:BB:CC:DD:EE:FF').
        ip_broadcast: Opcional. IP de broadcast da rede alvo (ex: '192.168.0.255' na mesma rede ou '200.100.50.255' em rede remota com broadcast dirigido liberado no roteador). Padrão: 255.255.255.255.
        porta: Porta UDP do WoL (padrão 9; alternativas comuns: 7 ou 0).
    """
    is_mac = bool(re.fullmatch(r"[0-9a-fA-F:\-\s]{12,19}", str(dispositivo_ou_mac or "")))
    payload = {"action": "wake", "port": int(porta)}
    if ip_broadcast:
        payload["ip"] = ip_broadcast
    if is_mac:
        payload["mac"] = dispositivo_ou_mac
    else:
        payload["name"] = dispositivo_ou_mac
    res = send_master_request("/api/wol", payload)
    if res.get("success"):
        return res.get("message", "Pacote mágico Wake-on-LAN enviado com sucesso.")
    return f"Falha no Wake-on-LAN: {res.get('error', res)}"

@mcp.tool()
def listar_dispositivos_wol() -> str:
    """Lista todos os dispositivos cadastrados no registro Wake-on-LAN do J.A.R.V.I.S. (nome, MAC, IP de broadcast e porta)."""
    res = send_master_request("/api/wol", payload=None, method="GET")
    if res.get("status") == "forbidden" or "devices" not in res:
        return f"Falha ao listar dispositivos WoL: {res.get('error', res)}"
    devices = res.get("devices", [])
    if not devices:
        return "Nenhum dispositivo Wake-on-LAN cadastrado. Use cadastrar_dispositivo_wol(nome, mac)."
    lines = ["Dispositivos Wake-on-LAN cadastrados:"]
    for d in devices:
        lines.append(f"- {d.get('name')}: MAC {d.get('mac')} | Broadcast {d.get('ip', '255.255.255.255')}:{d.get('port', 9)}")
    return "\n".join(lines)

@mcp.tool()
def cadastrar_dispositivo_wol(nome: str, mac: str, ip_broadcast: str = "255.255.255.255", porta: int = 9) -> str:
    """Cadastra ou atualiza um dispositivo no registro Wake-on-LAN do J.A.R.V.I.S.
    
    Args:
        nome: Nome amigável do dispositivo (ex: 'pc-escritorio', 'servidor-casa').
        mac: Endereço MAC da interface de rede do PC alvo (ex: 'AA:BB:CC:DD:EE:FF').
        ip_broadcast: IP de broadcast da rede alvo. Mesma rede: '192.168.0.255'. Rede remota com IP fixo: broadcast da subnet remota com directed broadcast liberado.
        porta: Porta UDP do WoL (padrão 9).
    """
    payload = {"action": "add", "name": nome, "mac": mac, "ip": ip_broadcast, "port": int(porta)}
    res = send_master_request("/api/wol", payload)
    if res.get("success"):
        return f"Dispositivo '{nome}' cadastrado com sucesso para Wake-on-LAN (MAC {mac} via {ip_broadcast}:{porta})."
    return f"Falha ao cadastrar dispositivo: {res.get('error', res)}"

if __name__ == "__main__":
    print(f"[*] Servidor MCP do JARVIS HUD rodando em SSE na porta {MCP_PORT} (http://0.0.0.0:{MCP_PORT}/sse)...")
    mcp.run(transport="sse")
