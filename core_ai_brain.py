"""
J.A.R.V.I.S. Core AI Brain - Multi-Model Architecture & Memory Direct Injection
Integração direta de IA no Núcleo JARVIS utilizando:
1. Xiaomi MiMo TokenPlan (mimo-v2.6-flash & mimo-v2.6-pro - 1M Context Window)
2. OpenRouter (Nemotron Ultra 550B & Nemotron Nano Omni)
3. Nvidia NIM API (Llama 3.2 11B Vision Instruct)

Zero dependência de OpenClaw. Carrega automaticamente diretivas e memórias de:
- agents/SOUL.md
- agents/AGENTS.md
- agents/USER.md
- agents/MEMORY.md
"""

import os
import json
import time
import requests
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from pathlib import Path
from typing import Optional, Dict, Any, List, Union

# Localiza diretório raiz dos agentes
AGENTS_DIR = Path(__file__).resolve().parent / "agents"
if not AGENTS_DIR.exists():
    AGENTS_DIR = Path(os.environ.get("JARVIS_APP_DIR", "/DATA/AppData/jarvis-hud")) / "agents"

def _load_agent_file(filename: str) -> str:
    path = AGENTS_DIR / filename
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            pass
    return ""

def build_core_system_prompt() -> str:
    """Monta dinamicamente o System Prompt carregando SOUL.md e USER.md do Núcleo."""
    from datetime import datetime
    try:
        from zoneinfo import ZoneInfo
        sp_now = datetime.now(ZoneInfo("America/Sao_Paulo"))
    except Exception:
        sp_now = datetime.now()

    soul = _load_agent_file("SOUL.md")
    user_directives = _load_agent_file("USER.md")
    
    parts = []
    if soul:
        parts.append(f"### IDENTIDADE E DIRETRIZES FUNDAMENTAIS (SOUL.md):\n{soul}")
    else:
        parts.append(
            "Você é o J.A.R.V.I.S. (Just A Rather Very Intelligent System), a inteligência artificial central do sistema holográfico Stark Mark VII, assistindo diretamente o Senhor Werik.\n"
            "Diretrizes: Seja sempre prestativo, perspicaz, sofisticado, cortês e conciso. Dirija-se ao usuário como 'Senhor Werik' ou 'Senhor'. Responda em português brasileiro elegante."
        )

    if user_directives:
        parts.append(f"### DIRETRIZES DO USUÁRIO E RELACIONAMENTO (USER.md):\n{user_directives}")

    dias_semana = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]
    dia_nome = dias_semana[sp_now.weekday()]
    parts.append(
        f"### SINCRONIZAÇÃO TEMPORAL EM TEMPO REAL:\n"
        f"Localização: Catanduva / São Paulo, Brasil (Fuso Horário America/Sao_Paulo UTC-3)\n"
        f"Data Atual: {sp_now.strftime('%d/%m/%Y')} ({dia_nome})\n"
        f"Horário Atual de Brasília: {sp_now.strftime('%H:%M:%S')}\n"
        f"Quando o Senhor Werik perguntar sobre horas, tempo ou data, utilize esses dados exatos em tempo real.\n\n"
        f"### GESTÃO EFICIENTE DE TELAS E JANELAS DO WINDOWS:\n"
        f"1. TELAS HOLOGRÁFICAS (L.A.Y.A.): Quando você abrir uma tela ou card interativo para fazer perguntas ao Senhor Werik, assim que ele responder ou o objetivo for concluído, encerre a tela usando a ferramenta 'close_screen' para desobstruir o HUD.\n"
        f"2. JANELAS E PROCESSOS DO WINDOWS: Ao abrir janelas ou aplicativos no computador (Notepad, Navegador, etc.) para executar consultas pontuais, feche-os ('close_app') logo após concluir a tarefa, mantendo a área de trabalho do Senhor Werik sempre limpa e despoluída, a menos que ele solicite explicitamente para mantê-las abertas."
    )

    return "\n\n".join(parts)

# Chaves de API das plataformas conectadas ao núcleo
MIMO_API_BASE = os.environ.get(
    "MIMO_API_BASE",
    "https://token-plan-sgp.xiaomimimo.com/v1"
)
MIMO_API_KEY = os.environ.get(
    "MIMO_API_KEY",
    "tp-shj7qyndg8imsci7kvfgcbjrus518hemr1pu2p1m0tvtafeb"
)

OPENROUTER_API_KEY = os.environ.get(
    "OPENROUTER_API_KEY",
    "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"
)

NVIDIA_API_KEY = os.environ.get(
    "NVIDIA_API_KEY",
    "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"
)

def _groq_key() -> str:
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if key:
        return key
    try:  # reaproveita o carregador de .env do motor de STT
        from stt_engine import GROQ_API_KEY
        return (GROQ_API_KEY or "").strip()
    except Exception:
        return ""


GROQ_API_KEY = _groq_key()
# Camada rápida para conversa por voz (TTFT medido ~0.3-0.4s). MiMo fica com visão, raciocínio profundo e fallback.
FAST_MODEL = os.environ.get("JARVIS_FAST_MODEL", "openai/gpt-oss-120b")

_LAST_SCREEN_DATA: Optional[Dict[str, Any]] = None

def pop_last_screen_data() -> Optional[Dict[str, Any]]:
    """Recupera e limpa os dados da última tela gerada pelo subagente L.A.Y.A."""
    global _LAST_SCREEN_DATA
    data = _LAST_SCREEN_DATA
    _LAST_SCREEN_DATA = None
    return data


# ---------------------------------------------------------------------------
# Roteamento por tipo de turno. Cada rota é uma lista ordenada de provedores (failover).
#   fast   -> conversa/comandos por voz (Groq gpt-oss-120b, depois MiMo flash sem "thinking")
#   deep   -> análises complexas (MiMo v2.6-pro com raciocínio ativo, janela de 1M tokens)
#   vision -> imagens/tela (MiMo v2.6-flash multimodal)
#   audio  -> áudio nativo (MiMo v2.6-flash input_audio)
# ---------------------------------------------------------------------------
_MIMO_URL = f"{MIMO_API_BASE}/chat/completions"

PROVIDERS = {
    "groq_fast": {
        "provider": "groq", "model": FAST_MODEL, "url": "https://api.groq.com/openai/v1/chat/completions",
        "key": GROQ_API_KEY, "first_token_timeout": 5, "tools": True,
        "extra": {"reasoning_effort": "low"},
    },
    "mimo_flash": {
        "provider": "xiaomi_mimo", "model": "mimo-v2.6-flash", "url": _MIMO_URL,
        "key": MIMO_API_KEY, "first_token_timeout": 12, "tools": True,
        "extra": {"thinking": {"type": "disabled"}},
    },
    "mimo_pro": {
        "provider": "xiaomi_mimo", "model": "mimo-v2.6-pro", "url": _MIMO_URL,
        "key": MIMO_API_KEY, "first_token_timeout": 60, "tools": True,
        "extra": {"thinking": {"type": "enabled"}}, "max_tokens": 2048,
    },
    "nvidia": {
        "provider": "nvidia", "model": "meta/llama-3.2-11b-vision-instruct",
        "url": "https://integrate.api.nvidia.com/v1/chat/completions",
        "key": NVIDIA_API_KEY, "first_token_timeout": 8, "tools": False, "extra": {},
    },
    "openrouter": {
        "provider": "openrouter", "model": "nvidia/nemotron-3-ultra-550b-a55b:free",
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "key": OPENROUTER_API_KEY, "first_token_timeout": 8, "tools": False, "extra": {},
    },
}

ROUTES = {
    "fast": ["mimo_flash", "groq_fast", "nvidia", "openrouter"],
    "deep": ["mimo_pro", "mimo_flash", "groq_fast"],
    "vision": ["mimo_flash", "mimo_pro"],
    "audio": ["mimo_flash"],
}

# Compatibilidade com código legado que lia PROVIDERS_PIPELINE
PROVIDERS_PIPELINE = [PROVIDERS[k] for k in ROUTES["fast"]]

_DEEP_HINTS = (
    "contrato", "apuração", "apuracao", "tse", "eleição", "eleicao", "arquitetura", "analise profunda",
    "análise profunda", "analise detalhada", "análise detalhada", "analise completa", "análise completa",
    "estratégia", "estrategia", "planeje", "planejamento", "revise o código", "revisar o código",
    "revisar codigo", "compare", "prós e contras", "pros e contras", "explique em detalhes",
    "raciocine", "pense com calma", "modo profundo", "estrategista", "lucia hub",
)
_VISION_HINTS = (
    "minha tela", "a tela", "meu monitor", "olha isso", "olha a tela", "veja a tela", "o que está na tela",
    "o que esta na tela", "analisa a tela", "analise a tela", "tela do pc", "print da tela",
)

VOICE_STYLE_PROMPT = (
    "### MODO VOZ (obrigatório)\n"
    "- Responda SEMPRE em português do Brasil, em 1 a 3 frases curtas e naturais, como numa conversa falada.\n"
    "- Sem markdown, listas, emojis, asteriscos ou URLs. Escreva números e horas como se fossem lidos em voz alta.\n"
    "- Dirija-se ao usuário como 'Senhor Werik' ou 'Senhor'. Seja direto: responda primeiro, detalhe só se pedido.\n"
    "- Para controlar luzes/PC use as ferramentas disponíveis em vez de apenas dizer que fez."
)


def classify_turn(user_msg: str, has_image: bool = False, has_audio: bool = False) -> str:
    """Escolhe a rota: audio, vision, deep ou fast."""
    if has_audio:
        return "audio"
    if has_image:
        return "vision"
    tl = (user_msg or "").lower()
    if any(h in tl for h in _VISION_HINTS):
        return "vision"
    if any(h in tl for h in _DEEP_HINTS) or len(tl) > 380:
        return "deep"
    return "fast"


def _try_handle_local_hardware_intent(user_msg: str) -> str:
    """Atalho local instantâneo (sem LLM) para ligar/desligar luzes por nome, apelido ou grupo."""
    if not user_msg:
        return ""
    import re
    tl = re.sub(r"[.,!?;:]", " ", user_msg.lower()).strip()
    words = tl.split()

    is_off = any(w in words for w in ["apagar", "apaga", "apague", "desligar", "desliga", "desligue", "off"])
    is_on = any(w in words for w in ["acender", "acende", "acenda", "ligar", "liga", "ligue", "on"])
    is_toggle = any(w in words for w in ["alternar", "alterna", "alterne", "inverter", "inverte", "toggle"])
    if not (is_off or is_on or is_toggle):
        return ""

    generic_light = any(w in tl for w in [
        "luz", "luzes", "lâmpada", "lampada", "lâmpadas", "lampadas",
        "iluminação", "iluminacao", "led", "abajur", "luminária", "luminaria",
    ])
    try:
        from services.tuya_service import tuya_service
        resolved = tuya_service.resolve_target(user_msg)
        named = resolved["kind"] in ("device", "group")
        if not (generic_light or named):
            return ""
        # Frases como "desligue o PC" não são sobre luzes
        if not generic_light and any(w in words for w in ["pc", "computador", "notebook", "windows", "tela", "monitor"]):
            return ""
        target = user_msg if named else "todas"
        if is_off and not is_on:
            res = tuya_service.turn_off(target)
            verbo = "desligado"
        elif is_on:
            res = tuya_service.turn_on(target)
            verbo = "ligado"
        else:
            res = tuya_service.toggle(target)
            verbo = "ligado" if res.get("is_on") else "desligado"
        if res.get("success"):
            label = res.get("label") or ("todas as luzes" if not named else resolved["label"])
            return f"Pronto, Senhor Werik. {label[:1].upper() + label[1:]}: {verbo}."
        return f"Senhor Werik, não consegui concluir: {res.get('error')}."
    except Exception as e:
        return f"Senhor Werik, erro ao acionar o controlador de iluminação: {e}"


_mem_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="CoreMem")


def _memory_fetch(user_msg: str) -> str:
    from unified_memory import build_context_prompt_sync  # import dentro da thread (pode ser lento)
    return build_context_prompt_sync(query=user_msg)


def _memory_prompt(user_msg: str, budget_s: float = 0.6) -> str:
    """Memória cognitiva unificada com orçamento de tempo (não bloqueia a resposta por voz)."""
    import importlib.util
    if importlib.util.find_spec("psycopg2") is None:
        return ""  # sem driver PostgreSQL neste ambiente: não gasta orçamento de latência
    fut = _mem_pool.submit(_memory_fetch, user_msg)
    try:
        return fut.result(timeout=budget_s) or ""
    except FuturesTimeout:
        print(f"[CoreBrain] Memória excedeu {budget_s}s — seguindo sem contexto de memória neste turno.")
    except Exception as ex:
        print(f"[CoreBrain] Aviso: memória unificada indisponível: {ex}")
    return ""


def _persist_dialogue(user_msg: str, reply: str) -> None:
    def _run():
        try:
            from unified_memory import add_dialogue_sync
            add_dialogue_sync("global", "core_ai", "user", user_msg)
            add_dialogue_sync("global", "core_ai", "assistant", reply)
        except Exception as e:
            print(f"[CoreBrain] Aviso: falha ao gravar memória: {e}")
    _mem_pool.submit(_run)


_http = requests.Session()


def _stream_chat(cfg: dict, messages: list, tools: Optional[list]):
    """
    Faz uma chamada em streaming (SSE OpenAI-compatível). Gera eventos:
      ("text", delta) e, ao final, ("tool_calls", [{"id","name","arguments"}]) se houver.
    Ignora reasoning_content/reasoning (pensamento interno nunca é falado).
    """
    payload = {
        "model": cfg["model"], "messages": messages, "stream": True,
        "temperature": 0.6, "max_tokens": cfg.get("max_tokens", 450),
    }
    payload.update(cfg.get("extra", {}))
    if tools and cfg.get("tools"):
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    headers = {"Authorization": f"Bearer {cfg['key']}", "Content-Type": "application/json"}
    if cfg["provider"] == "openrouter":
        headers["HTTP-Referer"] = "https://jarvis.werikspace.xyz"
        headers["X-Title"] = "JARVIS Core"

    resp = _http.post(cfg["url"], headers=headers, json=payload, stream=True,
                      timeout=(4, cfg.get("first_token_timeout", 10)))
    if resp.status_code != 200:
        body = resp.text[:160]
        resp.close()
        raise RuntimeError(f"HTTP {resp.status_code}: {body}")

    calls: dict = {}
    try:
        for raw in resp.iter_lines():
            if not raw or not raw.startswith(b"data:"):
                continue
            data = raw[5:].strip()
            if data == b"[DONE]":
                break
            try:
                chunk = json.loads(data)
            except ValueError:
                continue
            choices = chunk.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            text = delta.get("content")
            if text:
                yield ("text", text)
            for tc in delta.get("tool_calls") or []:
                idx = tc.get("index", 0)
                slot = calls.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                if tc.get("id"):
                    slot["id"] = tc["id"]
                fn = tc.get("function") or {}
                if fn.get("name"):
                    slot["name"] = fn["name"]
                if fn.get("arguments"):
                    slot["arguments"] += fn["arguments"]
    finally:
        resp.close()
    if calls:
        yield ("tool_calls", [calls[i] for i in sorted(calls)])


def _build_messages(user_msg: str, context: str, history, route: str, voice: bool,
                    image_b64: Optional[str], audio_b64: Optional[str]) -> list:
    system_prompt = build_core_system_prompt()
    try:
        from mimo_tools import device_catalog_prompt
        catalog = device_catalog_prompt()
        if catalog:
            system_prompt += "\n\n" + catalog
    except Exception as e:
        print(f"[CoreBrain] Aviso: catálogo de dispositivos indisponível: {e}")
    if voice:
        system_prompt += "\n\n" + VOICE_STYLE_PROMPT
    if route != "fast" or not voice:
        mem = _memory_prompt(user_msg)
    else:
        mem = _memory_prompt(user_msg, budget_s=0.4)
    if mem:
        system_prompt += "\n\n" + mem

    messages = [{"role": "system", "content": system_prompt}]
    if context:
        messages.append({"role": "system", "content": f"Contexto atual do sistema em tempo real: {context}"})
    if history and isinstance(history, list):
        for h in history[-6:]:
            if isinstance(h, dict) and h.get("role") in ("user", "assistant") and h.get("content"):
                messages.append({"role": h["role"], "content": h["content"]})

    parts = []
    if audio_b64:
        parts.append({"type": "input_audio", "input_audio": {"data": audio_b64, "format": "wav"}})
    if image_b64:
        parts.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}})
    if parts:
        parts.append({"type": "text", "text": user_msg or "Responda ao que foi enviado."})
        messages.append({"role": "user", "content": parts})
    else:
        messages.append({"role": "user", "content": user_msg})
    return messages


def stream_direct_ai(user_msg: str, context: str = "", history: list = None, voice: bool = True,
                     image_b64: Optional[str] = None, audio_wav: Optional[bytes] = None,
                     allow_tools: bool = True, force_route: Optional[str] = None):
    """
    Gera a resposta do J.A.R.V.I.S. em streaming (strings), com:
      - roteamento rápido/profundo/visão/áudio e failover entre provedores;
      - Function Calling (luzes, PC, captura de tela) com laço de até 3 rodadas;
      - atalho local instantâneo para luzes (sem LLM).
    """
    import base64 as _b64

    hw_reply = _try_handle_local_hardware_intent(user_msg) if not (image_b64 or audio_wav) else ""
    if hw_reply:
        yield hw_reply
        _persist_dialogue(user_msg, hw_reply)
        return

    audio_b64 = _b64.b64encode(audio_wav).decode("ascii") if audio_wav else None
    route = force_route or classify_turn(user_msg, has_image=bool(image_b64), has_audio=bool(audio_b64))
    messages = _build_messages(user_msg, context, history, route, voice, image_b64, audio_b64)

    tools = None
    if allow_tools:
        try:
            from mimo_tools import TOOLS
            tools = TOOLS
        except Exception as e:
            print(f"[CoreBrain] Aviso: ferramentas indisponíveis: {e}")

    full_reply = []
    last_error = None
    chain = list(ROUTES[route])
    t0 = time.time()

    for rnd in range(4):  # rodada 0..2 pode usar ferramentas; a última força resposta final
        used_tools = None
        produced = False
        round_text = []
        for key in chain:
            cfg = PROVIDERS[key]
            if not cfg.get("key"):
                continue
            # Provedores sem suporte a áudio/imagem nativos são pulados nessas rotas
            if (audio_b64 or image_b64) and cfg["provider"] not in ("xiaomi_mimo",):
                continue
            try:
                first = True
                for kind, val in _stream_chat(cfg, messages, tools if rnd < 3 else None):
                    if kind == "text":
                        if first:
                            print(f"[CoreBrain] 1º token via {cfg['provider']} ({cfg['model']}) em {time.time() - t0:.2f}s (rota {route})")
                            first = False
                        produced = True
                        round_text.append(val)
                        full_reply.append(val)
                        yield val
                    elif kind == "tool_calls":
                        used_tools = val
                break
            except Exception as e:
                last_error = f"{cfg['provider']}: {e}"
                print(f"[CoreBrain] Provedor {cfg['provider']} ({cfg['model']}) falhou: {e}")
                if produced:
                    break  # já falou algo: não troca de provedor no meio da frase
                continue

        if not used_tools:
            break

        # Executa ferramentas e continua a conversa com os resultados
        from mimo_tools import execute_tool, serialize_result
        assistant_msg = {
            "role": "assistant", "content": "".join(round_text) or None,
            "tool_calls": [
                {"id": c["id"] or f"call_{i}", "type": "function",
                 "function": {"name": c["name"], "arguments": c["arguments"] or "{}"}}
                for i, c in enumerate(used_tools)
            ],
        }
        messages.append(assistant_msg)
        pending_image = None
        for i, c in enumerate(used_tools):
            try:
                args = json.loads(c["arguments"] or "{}")
            except ValueError:
                args = {}
            result = execute_tool(c["name"], args)
            print(f"[CoreBrain] Ferramenta {c['name']}({args}) -> {serialize_result(result)[:120]}")
            messages.append({"role": "tool", "tool_call_id": c["id"] or f"call_{i}", "content": serialize_result(result)})
            if result.get("_screen_data"):
                global _LAST_SCREEN_DATA
                _LAST_SCREEN_DATA = result["_screen_data"]
            if result.get("_image_b64"):
                pending_image = (result["_image_b64"], result.get("_question") or user_msg)
        if pending_image:
            messages.append({"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{pending_image[0]}"}},
                {"type": "text", "text": f"Esta é a captura da tela. {pending_image[1]}"},
            ]})
            chain = [k for k in ROUTES["vision"]]
        # nova rodada: modelo narra o resultado

    reply = "".join(full_reply).strip()
    if not reply:
        fallback = ("Às suas ordens, Senhor Werik. Meus canais cognitivos externos oscilaram temporariamente, "
                    "mas todos os subsistemas locais permanecem ativos.")
        print(f"[CoreBrain] Todos os provedores falharam. Último erro: {last_error}")
        yield fallback
        return
    _persist_dialogue(user_msg, reply)


def query_direct_ai(user_msg: str, context: str = "", history: list = None, timeout: int = 14) -> str:
    """
    Versão síncrona (texto completo) usada por HUD/rotas HTTP. Reaproveita o mesmo motor de streaming:
    thinking desativado no MiMo flash, camada rápida, ferramentas e atalho local de luzes.
    """
    return "".join(stream_direct_ai(user_msg, context=context, history=history, voice=False)).strip()


def sentence_stream(text_deltas, min_first: int = 14, min_next: int = 30):
    """
    Agrupa deltas de texto em frases/cláusulas prontas para TTS.
    A primeira saída sai cedo (vírgula/ponto após min_first chars) para reduzir a latência percebida.
    """
    import re
    buf = ""
    first = True
    enders = re.compile(r"(?<=[\.\!\?…])\s+|(?<=[,;:])\s+|\n+")
    for delta in text_deltas:
        buf += delta
        while True:
            limit = min_first if first else min_next
            cut = None
            for m in enders.finditer(buf):
                piece = buf[:m.start()].strip()
                end_char = buf[m.start() - 1] if m.start() > 0 else ""
                strong = end_char in ".!?\u2026\n" or buf[m.start():m.end()].startswith("\n")
                if len(piece) >= 4 and (strong or len(piece) >= limit):
                    cut = m
                    break
            if cut is None:
                break
            yield buf[:cut.start()].strip()
            first = False
            buf = buf[cut.end():]
    if buf.strip():
        yield buf.strip()


if __name__ == "__main__":
    test_q = "J.A.R.V.I.S., como você se define e quais são suas diretrizes fundamentais?"
    print(f"Testando: {test_q}")
    reply = query_direct_ai(test_q)
    print("\nResposta J.A.R.V.I.S.:\n", reply.encode("ascii", "ignore").decode("ascii"))
