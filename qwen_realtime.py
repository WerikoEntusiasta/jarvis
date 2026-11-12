"""
qwen_realtime.py - Conversacao de voz do J.A.R.V.I.S. com Qwen-Audio-3.0-Realtime-Plus.

ARQUITETURA (fala -> fala, pt-BR, baixa latencia):

    Esfera ESP32-S3 --PCM 16 kHz--> Qwen-Audio-3.0-Realtime-Plus --PCM 24 kHz--> Esfera
                                          |
                                          |  function calling
                                          v
                               Agente MiMo (core_ai_brain + mimo_tools)
                               - raciocinar() -> rota "deep"  (mimo-v2.6-pro)
                               - executar()   -> rota "fast"  (mimo-v2.6-flash)
                                                 + ~50 ferramentas (PC, luzes, HUD)

PAPEL DE CADA MODELO:
  - Qwen-Audio-3.0-Realtime-Plus: conversa por VOZ em portugues do Brasil
    (entende fala e responde falando - STT+LLM+TTS nativos, sem etapas intermediarias).
  - Agente MiMo: quando a fala exigir raciocinio profundo ou execucao de acoes,
    o Qwen chama as ferramentas `raciocinar` / `executar` e este modulo despacha
    a chamada para o core_ai_brain (modelos MiMo), devolvendo o resultado para o
    Qwen falar a resposta final em pt-BR.

PROTOCOLO (WebSocket, formato Cubicspaces / DashScope realtime):
  - entrada : PCM s16le mono 16 kHz  (input_audio_buffer.append)
  - saida   : PCM s16le mono 24 kHz  (response.audio.delta) -> reamostrado p/ 16 kHz
  - turno   : modo MANUAL (turn_detection: null). O VAD/wake-word da esfera
              (sphere_voice.AudioTurnGate) ja delimita os turnos; aqui apenas
              commit + response.create por uteracao.
  - tools   : response.function_call_arguments.done -> executa -> conversation.item.create
              (function_call_output) -> response.create (o Qwen fala o resultado).

CONFIG (.env):
  QWEN_REALTIME_API_KEY   chave da API (aceita tambem CUBICSPACES_API_KEY / DASHSCOPE_API_KEY)
  QWEN_REALTIME_URL       padrao: wss://cubicspaces.cloud/v1/realtime
  QWEN_REALTIME_MODEL     padrao: qwen-audio-3.0-realtime-plus
  QWEN_REALTIME_VOICE     padrao: longanqian (voz pt-BR do 3.0 Plus)
  QWEN_REALTIME_TURN_TIMEOUT  timeout por turno em segundos (padrao: 90)

FALLBACK: qualquer falha aqui retorna False e o server.py usa o pipeline
classico STT -> LLM -> TTS. Nenhum audio e gravado em disco.
"""

import asyncio
import base64
import inspect
import json
import os
import time
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

import numpy as np

try:
    import websockets
except Exception:  # pragma: no cover - dependencia ausente desliga o modulo
    websockets = None


def _load_env_fallback() -> None:
    """Carrega .env da raiz do projeto sem sobrescrever variaveis ja existentes."""
    from pathlib import Path

    env_file = Path(__file__).resolve().parent / ".env"
    if not env_file.exists():
        return
    try:
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    if k.strip() not in os.environ:
                        os.environ[k.strip()] = v.strip()
    except Exception:
        pass


_load_env_fallback()


async def _open_ws():
    """Abre o WebSocket realtime (compativel com websockets 10.x e 12+)."""
    if websockets is None:
        raise RuntimeError("websockets indisponivel")
    url = f"{realtime_url()}?model={realtime_model()}"
    # websockets 10.x exige pares (nome, valor); 12+ tambem aceita esse formato.
    headers = [("Authorization", "Bearer " + api_key())]
    kwargs: Dict[str, Any] = {"open_timeout": 20, "max_size": 8 * 1024 * 1024}
    params = inspect.signature(websockets.connect).parameters
    chave_header = "additional_headers" if "additional_headers" in params else "extra_headers"
    kwargs[chave_header] = headers
    return await websockets.connect(url, **kwargs)


# --------------------------------------------------------------------------- #
# Configuracao (lida em tempo de execucao para permitir testes e reload)       #
# --------------------------------------------------------------------------- #

def realtime_url() -> str:
    return os.environ.get(
        "QWEN_REALTIME_URL",
        "wss://token-plan.ap-southeast-1.maas.aliyuncs.com/api-ws/v1/realtime",
    ).strip()


def realtime_model() -> str:
    return os.environ.get("QWEN_REALTIME_MODEL", "qwen-audio-3.0-realtime-plus").strip()


def realtime_voice() -> str:
    return os.environ.get("QWEN_REALTIME_VOICE", "longanqian").strip()


def api_key() -> str:
    return (
        os.environ.get("QWEN_REALTIME_API_KEY")
        or os.environ.get("CUBICSPACES_API_KEY")
        or os.environ.get("DASHSCOPE_API_KEY")
        or ""
    ).strip()


def turn_timeout() -> float:
    try:
        return float(os.environ.get("QWEN_REALTIME_TURN_TIMEOUT", "90"))
    except ValueError:
        return 90.0


def is_enabled() -> bool:
    """True quando ha chave configurada e a lib de WebSocket disponivel."""
    return bool(api_key()) and websockets is not None


INPUT_RATE = 16000    # audio que chega da esfera (PCM s16le mono)
OUTPUT_RATE = 24000   # audio que o Qwen devolve (PCM s16le mono)
FRAME_BYTES = 640     # 20 ms @ 16 kHz (frame da esfera)
FRAME_SLEEP = 0.019   # pacing do playback da esfera (ver sphere_audio_bridge)
APPEND_CHUNK = 3200   # 100 ms por input_audio_buffer.append
MAX_TOOL_RESULT_CHARS = 4000
SESSION_TTL_SECONDS = 30 * 60


JARVIS_REALTIME_INSTRUCTIONS = (
    "Voce e o J.A.R.V.I.S. (Just A Rather Very Intelligent System), a inteligencia "
    "artificial pessoal e tatica do Senhor Werik. "
    "REGRAS: "
    "(1) Responda SEMPRE em portugues do Brasil, com voz natural, tom cortes, "
    "sofisticado e direto, chamando o usuario de 'Senhor' ou 'Senhor Werik'. "
    "(2) Como esta e uma conversa por VOZ, mantenha as respostas curtas: 1 a 3 frases. "
    "(3) CONVERSA DIRETA: para conversa casual responda sem chamar ferramentas. "
    "(4) COMANDOS VOCE EXECUTA DIRETO: qualquer pedido de acao (abrir/fechar apps, "
    "volume, midia, teclado, mouse, luzes, telas, apresentacoes, TV LG, Obsidian, "
    "buscas, PowerShell, telemetria) use a ferramenta correspondente DIRETAMENTE, "
    "sem delegar a nenhum agente. Nunca invente resultado de acao: execute a "
    "ferramenta e fale apenas o resultado real que ela retornar. "
    "(5) EXPLICACOES GERAM CANVAS: quando pedirem uma explicacao, demonstracao ou "
    "analise de qualquer assunto, monte uma apresentacao visual com a ferramenta "
    "'start_dynamic_presentation'. CADA topico da fala vira um card NOVO e unico "
    "- o motor nunca reaproveita card anterior; o conteudo de cada card deve ser "
    "criado na hora e especifico do que esta sendo falado no momento. Use "
    "componentes variados conforme o conteudo (hologram_card, chart, table, "
    "metric_grid, comparison, diagram, conclusion e 'network' com nodes/edges "
    "para redes de relacoes como aliancas ou influencia) e conduza a explicacao "
    "falada por cima da apresentacao, avancando cenas com "
    "'update_presentation_scene' (cada cena = card novo) e encerrando com "
    "'control_presentation'. "
    "(6) RACIOCINIO COMPLEXO: use 'raciocinar' somente para analises muito "
    "profundas, longas ou dificeis de resolver direto. "
    "(7) SUBAGENTE: use 'subagente' somente para tarefas complexas multi-etapa ou "
    "operacoes sensiveis que exigem cuidado extra."
)


# --------------------------------------------------------------------------- #
# Ferramentas: comandos EXECUTADOS PELO MODELO DE CONVERSA + delegacao MiMo    #
# --------------------------------------------------------------------------- #

# Delegadas ao subagente MiMo: operacoes sensiveis/complexas (multi-etapa,
# auto-modificacao de codigo, firmware da esfera, automacao pesada).
_TOOLS_DELEGADAS = {
    "self_write_code",
    "self_modify_code",
    "self_git_sync",
    "self_git_pull",
    "sphere_modify_firmware",
    "sphere_compile_firmware",
    "sphere_upload_usb",
    "sphere_ota_deploy",
    "run_powershell",
    "web_automation_playwright",
    "win_automation_pywinauto",
}

# Delegacoes ao agente MiMo: somente raciocinio profundo e tarefas complexas.
QWEN_AGENT_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "raciocinar",
            "description": (
                "Raciocinio profundo com o agente MiMo Pro. Use SOMENTE quando a "
                "pergunta exigir analise muito longa, calculo complexo, planejamento "
                "profundo ou decisao dificil demais para responder direto."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pergunta": {
                        "type": "string",
                        "description": "A pergunta ou tarefa completa, em portugues.",
                    }
                },
                "required": ["pergunta"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "subagente",
            "description": (
                "Delega uma tarefa complexa multi-etapa ou operacao sensivel ao "
                "agente MiMo (com todas as ferramentas internas, incluindo edicao "
                "de codigo, firmware da esfera, PowerShell e automacoes pesadas). "
                "Use SOMENTE para o que for complexo demais para as ferramentas diretas."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tarefa": {
                        "type": "string",
                        "description": "A tarefa completa, em portugues, com contexto.",
                    }
                },
                "required": ["tarefa"],
            },
        },
    },
]


def carregar_tools_conversa() -> List[Dict[str, Any]]:
    """Comandos diretos do mimo_tools + as duas delegacoes ao MiMo.

    O modelo de conversa executa os comandos do dia a dia (luzes, volume, apps,
    telas, apresentacoes, midia, telemetria...) diretamente, sem LLM no meio.
    Ferramentas sensiveis/complexas continuam disponiveis via 'subagente'.
    """
    try:
        from mimo_tools import TOOLS as _MIMO_TOOLS
    except Exception as exc:
        print(f"[QWEN REALTIME] mimo_tools indisponivel ({type(exc).__name__})")
        _MIMO_TOOLS = []
    diretas = [
        t for t in _MIMO_TOOLS
        if t.get("function", {}).get("name") not in _TOOLS_DELEGADAS
    ]
    return list(diretas) + QWEN_AGENT_TOOLS


def build_function_call_output(call_id: str, text: str) -> Dict[str, Any]:
    """Monta o item function_call_output (o campo output precisa ser JSON string)."""
    return {
        "type": "function_call_output",
        "call_id": call_id,
        "output": json.dumps({"resultado": text}, ensure_ascii=False),
    }


def build_session_config(
    turn_detection: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Configuracao da sessao realtime: voz pt-BR e ferramentas.

    turn_detection=None -> turno manual (commit + response.create por uteracao);
    turn_detection={"type": "smart_turn"|"server_vad"} -> deteccao no servidor
    (conversa ao vivo: o modelo responde quando o usuario para de falar).
    """
    try:
        from zoneinfo import ZoneInfo

        agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
    except Exception:
        agora = datetime.now()
    return {
        "modalities": ["text", "audio"],
        "voice": realtime_voice(),
        "instructions": (
            f"{JARVIS_REALTIME_INSTRUCTIONS} "
            f"Data e hora atuais: {agora.strftime('%d/%m/%Y %H:%M')} (horario de Brasilia)."
        ),
        "turn_detection": turn_detection,
        "tools": carregar_tools_conversa(),
        "audio": {
            "input": {
                "format": {
                    "type": "pcm",
                    "sample_rate": INPUT_RATE,
                    "sample_format": "s16le",
                    "channels": 1,
                    "packing": "interleaved",
                    "channel_layout": "mono",
                }
            },
            "output": {
                "voice": realtime_voice(),
                "format": {"type": "pcm", "sample_rate": OUTPUT_RATE},
            },
        },
    }


def resample_pcm16(pcm: bytes, src_rate: int, dst_rate: int) -> bytes:
    """Reamostra PCM s16le mono por interpolacao linear (voz: qualidade suficiente)."""
    if not pcm or src_rate == dst_rate:
        return pcm
    if len(pcm) % 2:
        pcm = pcm[:-1]
    x = np.frombuffer(pcm, dtype="<i2").astype(np.float32)
    if x.size == 0:
        return b""
    n_dst = max(1, int(round(x.size * dst_rate / src_rate)))
    t_src = np.linspace(0.0, 1.0, num=x.size, endpoint=False)
    t_dst = np.linspace(0.0, 1.0, num=n_dst, endpoint=False)
    y = np.interp(t_dst, t_src, x)
    return np.clip(y, -32768, 32767).astype("<i2").tobytes()


def _run_agent_sync(prompt: str, force_route: Optional[str], allow_tools: bool) -> str:
    """Chama o agente MiMo (core_ai_brain) de forma sincrona; roda em thread."""
    try:
        from core_ai_brain import stream_direct_ai

        partes: List[str] = []
        for delta in stream_direct_ai(
            prompt,
            context="",
            history=None,
            voice=False,
            allow_tools=allow_tools,
            force_route=force_route,
        ):
            if delta:
                partes.append(str(delta))
        texto = "".join(partes).strip()
        if texto:
            return texto
    except Exception as exc:
        print(f"[QWEN/AGENTE] core_ai_brain indisponivel ({type(exc).__name__}): {exc}")
    try:
        from mimo_brain import call_mimo_jarvis

        resultado = call_mimo_jarvis(prompt, timeout=60.0)
        if isinstance(resultado, dict):
            return str(
                resultado.get("speech") or resultado.get("reply") or json.dumps(resultado, ensure_ascii=False)
            )
        return str(resultado)
    except Exception as exc:
        print(f"[QWEN/AGENTE] fallback mimo_brain falhou ({type(exc).__name__}): {exc}")
        return "Nao consegui processar a solicitacao agora, Senhor Werik."


async def _dispatch_tool(name: str, arguments_json: str) -> str:
    """Executa a ferramenta pedida pelo Qwen.

    - Comandos diretos (mimo_tools): executados IMEDIATAMENTE, sem LLM no meio.
    - 'raciocinar': delega raciocinio profundo ao agente MiMo Pro.
    - 'subagente': delega tarefa complexa/sensivel ao agente MiMo completo.
    """
    try:
        args = json.loads(arguments_json) if arguments_json else {}
    except Exception:
        args = {}
    if not isinstance(args, dict):
        args = {}

    # ---- comandos diretos: executa na hora ----
    if name not in ("raciocinar", "subagente"):
        def _executar_direto() -> str:
            try:
                from mimo_tools import execute_tool

                res = execute_tool(name, args)
                if isinstance(res, dict):
                    # Higieniza chaves internas pesadas (_image_b64, _presentation_data,
                    # _screen_data...) - elas sao entregues ao HUD por SSE, nao ao modelo.
                    res = {k: v for k, v in res.items() if not str(k).startswith("_")}
                return json.dumps(res, ensure_ascii=False, default=str)
            except Exception as exc:
                return json.dumps(
                    {"ok": False, "erro": f"{type(exc).__name__}: {exc}"},
                    ensure_ascii=False,
                )

        saida = await asyncio.to_thread(_executar_direto)
        return saida[:MAX_TOOL_RESULT_CHARS]

    # ---- delegacoes ao agente MiMo ----
    if name == "raciocinar":
        pergunta = str(args.get("pergunta", "")).strip()
        prompt = f"[JARVIS | RACIOCINIO PROFUNDO | ORIGEM: VOZ]\n{pergunta}"
        texto = await asyncio.to_thread(_run_agent_sync, prompt, "deep", False)
    else:  # subagente
        tarefa = str(args.get("tarefa", "")).strip()
        prompt = f"[JARVIS | SUBAGENTE COMPLEXO | ORIGEM: VOZ]\n{tarefa}"
        texto = await asyncio.to_thread(_run_agent_sync, prompt, None, True)

    return str(texto)[:MAX_TOOL_RESULT_CHARS]


# --------------------------------------------------------------------------- #
# Saida de audio: fila com pacing e descarte por response_id (interrupt)       #
# --------------------------------------------------------------------------- #


class AudioPipe:
    """Envia PCM 16 kHz para o dispositivo com pacing de ~20 ms por frame.

    - pacing identico ao de sphere_audio_bridge.speak_to_device (640 B / 19 ms):
      enviar mais rapido que o playback enche o buffer TCP/TLS da esfera e o
      socket morre no meio da fala (close 1006).
    - cancel(response_id) descarta frames de uma resposta interrompida.
    """

    def __init__(
        self,
        send_frame: Callable[[bytes], Any],
        on_start: Optional[Callable[[], Any]] = None,
        on_stop: Optional[Callable[[], Any]] = None,
        paced: bool = True,
    ):
        self._send_frame = send_frame
        self._on_start = on_start
        self._on_stop = on_stop
        self._paced = paced
        self._queue: "asyncio.Queue[Tuple[str, Optional[str], bytes]]" = asyncio.Queue()
        self._cancelled: set = set()
        self._task: Optional[asyncio.Task] = None
        self._pending = 0
        self._speaking = False

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    def submit(self, response_id: Optional[str], pcm16k: bytes) -> None:
        if pcm16k:
            self._pending += 1
            self._queue.put_nowait(("pcm", response_id, pcm16k))

    def end_response(self) -> None:
        self._pending += 1
        self._queue.put_nowait(("eof", None, b""))

    def cancel(self, response_id: Optional[str]) -> None:
        if response_id:
            self._cancelled.add(response_id)
        mantidos = []
        try:
            while True:
                item = self._queue.get_nowait()
                if item[0] == "pcm" and item[1] == response_id:
                    self._pending -= 1
                    continue
                mantidos.append(item)
        except asyncio.QueueEmpty:
            pass
        for item in mantidos:
            self._queue.put_nowait(item)

    def clear(self) -> None:
        try:
            while True:
                self._queue.get_nowait()
                self._pending -= 1
        except asyncio.QueueEmpty:
            pass
        self._pending = max(0, self._pending)

    async def drain(self, timeout: float = 30.0) -> None:
        limite = time.monotonic() + timeout
        while self._pending > 0 and time.monotonic() < limite:
            await asyncio.sleep(0.02)

    async def stop(self) -> None:
        self._pending += 1
        self._queue.put_nowait(("stop", None, b""))
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=2.0)
            except Exception:
                self._task.cancel()
            self._task = None

    async def _run(self) -> None:
        while True:
            kind, rid, data = await self._queue.get()
            try:
                if kind == "stop":
                    await self._finalizar_fala()
                    return
                if kind == "eof":
                    if self._pending <= 1:
                        await self._finalizar_fala()
                    continue
                if rid in self._cancelled:
                    continue
                if not self._speaking:
                    self._speaking = True
                    await self._anunciar("start")
                for offset in range(0, len(data), FRAME_BYTES):
                    if rid in self._cancelled:
                        break
                    frame = data[offset:offset + FRAME_BYTES]
                    if len(frame) % 2:
                        frame = frame[:-1]
                    if frame:
                        resultado = self._send_frame(frame)
                        if inspect.isawaitable(resultado):
                            await resultado
                        await asyncio.sleep(FRAME_SLEEP)
            finally:
                self._pending -= 1

    async def _finalizar_fala(self) -> None:
        if self._speaking:
            self._speaking = False
            await self._anunciar("stop")

    async def _anunciar(self, estado: str) -> None:
        if self._on_start is None and self._on_stop is None:
            return
        alvo = self._on_start if estado == "start" else self._on_stop
        try:
            resultado = alvo()
            if inspect.isawaitable(resultado):
                await resultado
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# Sessao realtime                                                              #
# --------------------------------------------------------------------------- #


class QwenRealtimeSession:
    """Uma sessao WebSocket persistente por dispositivo (contexto multi-turno)."""

    def __init__(
        self,
        device_id: str,
        pipe: AudioPipe,
        on_transcript: Optional[Callable[[str, str], Any]] = None,
    ):
        self.device_id = device_id
        self.pipe = pipe
        self._on_transcript = on_transcript
        self._ws = None
        self._recv_task: Optional[asyncio.Task] = None
        self._tools_task: Optional[asyncio.Task] = None
        self._turn_done: Optional[asyncio.Event] = None
        self._turn_ok = False
        self._active_response: Optional[str] = None
        self._response_ativa = False
        self._resposta_livre = asyncio.Event()
        self._resposta_livre.set()
        self._tool_calls: List[Tuple[str, str, str]] = []
        self.created_at = time.time()

    # ----- conexao ----- #

    async def connect(self) -> None:
        self._ws = await _open_ws()
        self._recv_task = asyncio.create_task(self._recv_loop())
        await self._send({"type": "session.update", "session": build_session_config()})
        print(f"[QWEN REALTIME] sessao aberta (device={self.device_id}, model={realtime_model()})")

    def _aberta(self) -> bool:
        if self._ws is None:
            return False
        fechado = getattr(self._ws, "closed", None)
        if fechado is not None:
            return not fechado
        estado = getattr(self._ws, "state", None)
        if estado is not None:
            return str(estado).upper().endswith("OPEN")
        return True

    async def _garantir_conexao(self) -> None:
        if not self._aberta():
            await self.connect()

    async def _send(self, payload: Dict[str, Any]) -> None:
        if self._ws is None:
            raise RuntimeError("sessao realtime fechada")
        await self._ws.send(json.dumps(payload, ensure_ascii=False))

    # ----- turno de conversa ----- #

    async def converse(self, pcm_utterance: bytes, timeout: Optional[float] = None) -> bool:
        """Envia uma uteracao (PCM 16 kHz) e devolve a resposta falada do Qwen.

        Retorna True quando o turno completo (incluindo tools) terminou.
        """
        await self._garantir_conexao()
        self.pipe.start()
        self._turn_done = asyncio.Event()
        self._turn_ok = False
        self._tool_calls = []

        for offset in range(0, len(pcm_utterance), APPEND_CHUNK):
            trecho = pcm_utterance[offset:offset + APPEND_CHUNK]
            await self._send(
                {
                    "type": "input_audio_buffer.append",
                    "audio": base64.b64encode(trecho).decode("ascii"),
                }
            )
        await self._send({"type": "input_audio_buffer.commit"})
        await self._send({"type": "response.create"})

        await asyncio.wait_for(self._turn_done.wait(), timeout=timeout or turn_timeout())
        # Se uma tool ficou em voo (protocolo real: impossivel - a resposta final
        # so chega depois do function_call_output - mas defensivo contra corte),
        # aguarda o despacho terminar antes de encerrar o turno.
        if self._tools_task is not None and not self._tools_task.done():
            try:
                await asyncio.wait_for(asyncio.shield(self._tools_task), timeout=15)
            except Exception:
                pass
        await self.pipe.drain()
        return self._turn_ok

    async def cancel(self) -> None:
        if self._aberta() and self._active_response:
            try:
                await self._send({"type": "response.cancel"})
            except Exception:
                pass
            self.pipe.cancel(self._active_response)

    async def close(self) -> None:
        if self._tools_task is not None and not self._tools_task.done():
            self._tools_task.cancel()
            self._tools_task = None
        if self._recv_task is not None:
            self._recv_task.cancel()
            self._recv_task = None
        if self._ws is not None and self._aberta():
            try:
                await self._ws.close()
            except Exception:
                pass
        self._ws = None

    # ----- recepcao de eventos ----- #

    async def _recv_loop(self) -> None:
        try:
            async for mensagem in self._ws:
                evento = json.loads(mensagem)
                await self._processar_evento(evento)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[QWEN REALTIME] recv encerrado ({type(exc).__name__}): {exc}")
        finally:
            if self._turn_done is not None and not self._turn_done.is_set():
                self._turn_ok = False
                self._turn_done.set()

    async def _processar_evento(self, evento: Dict[str, Any]) -> None:
        tipo = str(evento.get("type", ""))

        if tipo == "error":
            msg = str(evento.get("error", ""))
            # Erros benignos de corrida VAD x response.create durante execucao
            # de tools: a resposta automatica do servidor ja cobre o caso.
            if "no response was created" in msg or "Cannot create response" in msg:
                print(f"[QWEN REALTIME] corrida VAD/response ignorada: {msg[:110]}")
                return
            print(f"[QWEN REALTIME] erro do servidor: {evento.get('error')}")
            if self._turn_done is not None:
                self._turn_ok = False
                self._turn_done.set()
            return

        if tipo == "response.created":
            resposta = evento.get("response") or {}
            self._active_response = resposta.get("id")
            self._response_ativa = True
            self._resposta_livre.clear()
            return

        if tipo == "conversation.item.input_audio_transcription.completed":
            await self._transcricao("user", str(evento.get("transcript", "")))
            return

        if tipo == "response.audio_transcript.delta":
            await self._transcricao("assistant", str(evento.get("delta", "")))
            return

        if tipo == "response.audio.delta":
            try:
                pcm24 = base64.b64decode(evento.get("delta", ""))
            except Exception:
                return
            pcm16 = resample_pcm16(pcm24, OUTPUT_RATE, INPUT_RATE)
            self.pipe.submit(evento.get("response_id") or self._active_response, pcm16)
            return

        if tipo == "response.function_call_arguments.done":
            self._tool_calls.append(
                (
                    str(evento.get("call_id", "")),
                    str(evento.get("name", "")),
                    str(evento.get("arguments", "")),
                )
            )
            return

        if tipo == "input_audio_buffer.speech_started":
            # Interrupcao do usuario: cancela a resposta em andamento e limpa o buffer.
            if self._active_response:
                try:
                    await self._send({"type": "response.cancel"})
                except Exception:
                    pass
                self.pipe.cancel(self._active_response)
            return

        if tipo == "response.done":
            status = ((evento.get("response") or {}).get("status") or "").lower()
            self._response_ativa = False
            self._resposta_livre.set()
            if self._tool_calls and status != "error":
                chamadas, self._tool_calls = self._tool_calls, []
                self._tools_task = asyncio.create_task(self._executar_tools(chamadas))
                return
            self.pipe.end_response()
            self._turn_ok = status != "error"
            if self._turn_done is not None:
                self._turn_done.set()
            return

    async def _aguardar_slot_resposta(self, timeout: float = 60.0) -> bool:
        """Espera o servidor ficar livre antes de um novo response.create.

        Evita 'Cannot create response while another response is in progress'
        quando o usuario continua falando (server_vad) durante tools lentas.
        """
        try:
            await asyncio.wait_for(self._resposta_livre.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    async def _executar_tools(self, chamadas: List[Tuple[str, str, str]]) -> None:
        try:
            for call_id, name, arguments in chamadas:
                inicio = time.time()
                saida = await _dispatch_tool(name, arguments)
                print(
                    f"[QWEN/AGENTE] tool={name} call_id={call_id} "
                    f"duracao={time.time() - inicio:.2f}s retorno={len(saida)} chars"
                )
                await self._send(
                    {
                        "type": "conversation.item.create",
                        "item": build_function_call_output(call_id, saida),
                    }
                )
            # Espera o servidor liberar (evita erro de response.create em corrida
            # com o VAD quando o usuario continua falando durante tools lentas).
            await self._aguardar_slot_resposta()
            await self._send({"type": "response.create"})
        except Exception as exc:
            print(f"[QWEN/AGENTE] falha ao executar tools ({type(exc).__name__}): {exc}")
            if self._turn_done is not None:
                self._turn_ok = False
                self._turn_done.set()

    async def _transcricao(self, papel: str, texto: str) -> None:
        if self._on_transcript is None or not texto:
            return
        try:
            resultado = self._on_transcript(papel, texto)
            if inspect.isawaitable(resultado):
                await resultado
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# Conversa AO VIVO: streaming continuo com VAD no servidor (fala->fala pt-BR)  #
# --------------------------------------------------------------------------- #


class LiveConversation:
    """Conversa continua com o Qwen realtime - microfone aberto, VAD no servidor.

    Diferente de converse_turn() (turno manual por uteracao), aqui o microfone
    fica aberto e o proprio servidor detecta inicio/fim de fala (smart_turn /
    server_vad): o modelo responde sozinho quando o usuario para de falar.

    Eventos de saida (callbacks):
      - on_audio(pcm24k: bytes)   -> reproduzir (24 kHz s16le mono)
      - on_transcript(role, texto) -> "user" (transcricao do usuario) /
                                      "assistant" (falado pelo Qwen)
      - on_state(estado)          -> "listening" | "thinking" | "speaking" | "idle"
      - on_tool(name, args_json)  -> log/observabilidade das tools MiMo
    """

    def __init__(
        self,
        on_audio: Optional[Callable[[bytes], Any]] = None,
        on_transcript: Optional[Callable[[str, str], Any]] = None,
        on_state: Optional[Callable[[str], Any]] = None,
        on_tool: Optional[Callable[[str, str], Any]] = None,
    ):
        self._on_audio = on_audio
        self._on_transcript = on_transcript
        self._on_state = on_state
        self._on_tool = on_tool
        self._ws = None
        self._recv_task: Optional[asyncio.Task] = None
        self._tools_task: Optional[asyncio.Task] = None
        self._tool_calls: List[Tuple[str, str, str]] = []
        self._active_response: Optional[str] = None
        self._speaking = False
        self._response_ativa = False
        self._resposta_livre: Optional[asyncio.Event] = None

    # ----- conexao ----- #

    async def start(self) -> None:
        self._ws = await _open_ws()
        self._resposta_livre = asyncio.Event()
        self._resposta_livre.set()
        await self._send(
            {
                "type": "session.update",
                "session": build_session_config(
                    turn_detection={"type": os.environ.get("QWEN_LIVE_VAD", "server_vad")}
                ),
            }
        )
        self._recv_task = asyncio.create_task(self._recv_loop())
        await self._state("listening")
        print(f"[QWEN LIVE] conversa ao vivo iniciada (model={realtime_model()})")

    def _aberta(self) -> bool:
        if self._ws is None:
            return False
        fechado = getattr(self._ws, "closed", None)
        if fechado is not None:
            return not fechado
        estado = getattr(self._ws, "state", None)
        if estado is not None:
            return str(estado).upper().endswith("OPEN")
        return True

    async def _send(self, payload: Dict[str, Any]) -> None:
        if self._ws is None:
            raise RuntimeError("sessao realtime fechada")
        await self._ws.send(json.dumps(payload, ensure_ascii=False))

    # ----- fluxo de audio ----- #

    async def send_audio(self, pcm16k: bytes) -> None:
        """Microfone aberto: encaminha PCM 16 kHz continuamente."""
        if not pcm16k or not self._aberta():
            return
        await self._send(
            {
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(pcm16k).decode("ascii"),
            }
        )

    async def cancel(self) -> None:
        """Barge-in: o usuario falou por cima - cancela a resposta em andamento."""
        if self._aberta() and self._active_response:
            try:
                await self._send({"type": "response.cancel"})
            except Exception:
                pass
        self._speaking = False

    async def close(self) -> None:
        if self._tools_task is not None and not self._tools_task.done():
            self._tools_task.cancel()
            self._tools_task = None
        if self._recv_task is not None:
            self._recv_task.cancel()
            self._recv_task = None
        if self._ws is not None and self._aberta():
            try:
                await self._ws.close()
            except Exception:
                pass
        self._ws = None
        await self._state("idle")

    # ----- eventos ----- #

    async def _recv_loop(self) -> None:
        try:
            async for mensagem in self._ws:
                await self._processar_evento(json.loads(mensagem))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[QWEN LIVE] recv encerrado ({type(exc).__name__}): {exc}")

    async def _processar_evento(self, evento: Dict[str, Any]) -> None:
        tipo = str(evento.get("type", ""))

        if tipo == "error":
            msg = str(evento.get("error", ""))
            # Corridas benignas VAD x response.create durante execucao de tools:
            # a resposta automatica do servidor ja cobre o caso - nao interromper.
            if "no response was created" in msg or "Cannot create response" in msg:
                print(f"[QWEN LIVE] corrida VAD/response ignorada: {msg[:110]}")
                return
            print(f"[QWEN LIVE] erro do servidor: {evento.get('error')}")
            return

        if tipo == "response.created":
            resposta = evento.get("response") or {}
            self._active_response = resposta.get("id")
            self._response_ativa = True
            if self._resposta_livre is not None:
                self._resposta_livre.clear()
            return

        if tipo == "input_audio_buffer.speech_started":
            # Barge-in nativo do servidor: usuario comecou a falar durante resposta.
            if self._speaking:
                self._speaking = False
                await self._state("interrupt")  # cliente limpa a fila de playback
                await self._state("listening")
            return

        if tipo == "conversation.item.input_audio_transcription.completed":
            await self._transcricao("user", str(evento.get("transcript", "")))
            return

        if tipo == "response.audio_transcript.delta":
            await self._transcricao("assistant", str(evento.get("delta", "")))
            return

        if tipo == "response.audio.delta":
            try:
                pcm24 = base64.b64decode(evento.get("delta", ""))
            except Exception:
                return
            if not self._speaking:
                self._speaking = True
                await self._state("speaking")
            if self._on_audio is not None:
                resultado = self._on_audio(pcm24)
                if inspect.isawaitable(resultado):
                    await resultado
            return

        if tipo == "response.function_call_arguments.done":
            self._tool_calls.append(
                (
                    str(evento.get("call_id", "")),
                    str(evento.get("name", "")),
                    str(evento.get("arguments", "")),
                )
            )
            return

        if tipo == "response.done":
            status = ((evento.get("response") or {}).get("status") or "").lower()
            self._response_ativa = False
            if self._resposta_livre is not None:
                self._resposta_livre.set()
            if self._tool_calls and status != "error":
                chamadas, self._tool_calls = self._tool_calls, []
                self._tools_task = asyncio.create_task(self._executar_tools(chamadas))
                return
            self._speaking = False
            await self._state("listening")

    async def _executar_tools(self, chamadas: List[Tuple[str, str, str]]) -> None:
        try:
            await self._state("thinking")
            for call_id, name, arguments in chamadas:
                if self._on_tool is not None:
                    try:
                        resultado = self._on_tool(name, arguments)
                        if inspect.isawaitable(resultado):
                            await resultado
                    except Exception:
                        pass
                inicio = time.time()
                saida = await _dispatch_tool(name, arguments)
                print(
                    f"[QWEN LIVE/AGENTE] tool={name} duracao={time.time() - inicio:.2f}s "
                    f"retorno={len(saida)} chars"
                )
                await self._send(
                    {
                        "type": "conversation.item.create",
                        "item": build_function_call_output(call_id, saida),
                    }
                )
            # Espera o servidor liberar antes de pedir a resposta falada.
            if self._resposta_livre is not None:
                try:
                    await asyncio.wait_for(self._resposta_livre.wait(), timeout=60)
                except asyncio.TimeoutError:
                    pass
            await self._send({"type": "response.create"})
        except Exception as exc:
            print(f"[QWEN LIVE/AGENTE] falha ao executar tools ({type(exc).__name__}): {exc}")
            await self._state("listening")

    async def _transcricao(self, papel: str, texto: str) -> None:
        if self._on_transcript is None or not texto:
            return
        try:
            resultado = self._on_transcript(papel, texto)
            if inspect.isawaitable(resultado):
                await resultado
        except Exception:
            pass

    async def _state(self, estado: str) -> None:
        if self._on_state is None:
            return
        try:
            resultado = self._on_state(estado)
            if inspect.isawaitable(resultado):
                await resultado
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# Registro de sessoes + entrada principal usada pelo server.py                 #
# --------------------------------------------------------------------------- #

_SESSOES: Dict[str, QwenRealtimeSession] = {}


def _limpar_sessoes_vencidas() -> None:
    agora = time.time()
    for chave in [k for k, s in _SESSOES.items() if agora - s.created_at > SESSION_TTL_SECONDS]:
        sessao = _SESSOES.pop(chave, None)
        if sessao is not None:
            try:
                asyncio.get_running_loop().create_task(sessao.close())
            except Exception:
                pass


async def _drop_session(device_id: str) -> None:
    sessao = _SESSOES.pop(device_id, None)
    if sessao is not None:
        await sessao.close()


async def converse_turn(
    device_id: str,
    pcm_utterance: bytes,
    send_json: Callable[[Dict[str, Any]], Any],
    send_bin: Callable[[bytes], Awaitable[None]],
    timeout: Optional[float] = None,
) -> bool:
    """Ponto de entrada do server.py: um turno de conversa por voz.

    Retorna False quando o Qwen realtime nao puder atender - o chamador
    deve cair para o pipeline classico STT -> LLM -> TTS.
    """
    if not is_enabled() or not pcm_utterance:
        return False

    _limpar_sessoes_vencidas()
    chave = str(device_id or "default")[:80]
    sessao = _SESSOES.get(chave)

    async def _frame(frame: bytes) -> None:
        await send_bin(frame)

    async def _json(payload: Dict[str, Any]) -> None:
        resultado = send_json(payload)
        if inspect.isawaitable(resultado):
            await resultado

    if sessao is None:
        pipe = AudioPipe(
            _frame,
            on_start=lambda: _json({"type": "tts", "state": "start"}),
            on_stop=lambda: _json({"type": "tts", "state": "stop"}),
        )
        sessao = QwenRealtimeSession(
            chave,
            pipe,
            on_transcript=lambda papel, texto: _json(
                {"type": "jarvis.transcript", "role": papel, "text": texto}
            ),
        )
        _SESSOES[chave] = sessao

    try:
        return await sessao.converse(pcm_utterance, timeout=timeout)
    except Exception as exc:
        print(f"[QWEN REALTIME] turno falhou ({type(exc).__name__}): {exc}")
        await _drop_session(chave)
        return False
