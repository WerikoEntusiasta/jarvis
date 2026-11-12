"""
qwen_live_bridge.py - Ponte de CONVERSA AO VIVO do J.A.R.V.I.S. (fala->fala pt-BR).

Microfone aberto <-> Qwen-Audio-3.0-Realtime-Plus, com VAD no servidor:
o usuario fala naturalmente e o modelo responde quando ele para de falar.
Raciocinio/execucao sao roteados por function calling para o agente MiMo.

PROCESSO INDEPENDENTE (nao depende do rebuild do JARVIS.exe):
    python qwen_live_bridge.py

PROTOCOLO (ws://127.0.0.1:8087/ws/voice):
  cliente -> servidor : frames BINARIOS = PCM s16le mono 16 kHz (microfone)
  cliente -> servidor : texto JSON {"type":"cancel"|"close"|"ping"}
  servidor -> cliente : frames BINARIOS = PCM s16le mono 24 kHz (resposta falada)
  servidor -> cliente : texto JSON:
      {"type":"hello", "sample_rate_in":16000, "sample_rate_out":24000}
      {"type":"state", "state":"listening"|"thinking"|"speaking"|"idle"}
      {"type":"transcript", "role":"user"|"assistant", "text":"..."}
      {"type":"tool", "name":"...", "arguments":"..."}
      {"type":"error", "message":"..."}

Sem QWEN_REALTIME_API_KEY configurada a ponte responde {"type":"error"} e o
HUD cai automaticamente para o fluxo classico (gravar -> STT -> texto).
"""

import asyncio
import inspect
import json
import os
import sys
import threading
import time
from typing import Any, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import qwen_realtime as qr

try:
    import websockets
except Exception:  # pragma: no cover
    websockets = None

WS_HOST = os.environ.get("QWEN_LIVE_HOST", "127.0.0.1")
WS_PORT = int(os.environ.get("QWEN_LIVE_PORT", "8087"))
WS_PATH = os.environ.get("QWEN_LIVE_PATH", "/ws/voice")

_loop: Optional[asyncio.AbstractEventLoop] = None
_thread: Optional[threading.Thread] = None
_server = None


class _ClientBridge:
    """Uma conexao de HUD <-> uma LiveConversation do Qwen."""

    def __init__(self, ws):
        self.ws = ws
        self.conv: Optional[qr.LiveConversation] = None

    async def _enviar_json(self, payload: Dict[str, Any]) -> None:
        try:
            await self.ws.send(json.dumps(payload, ensure_ascii=False))
        except Exception:
            pass

    async def _enviar_audio(self, pcm24k: bytes) -> None:
        try:
            await self.ws.send(pcm24k)
        except Exception:
            pass

    async def rodar(self) -> None:
        if not qr.is_enabled():
            await self._enviar_json(
                {
                    "type": "error",
                    "message": "QWEN_REALTIME_API_KEY nao configurada no .env",
                }
            )
            return

        self.conv = qr.LiveConversation(
            on_audio=self._enviar_audio,
            on_transcript=lambda papel, texto: self._enviar_json(
                {"type": "transcript", "role": papel, "text": texto}
            ),
            on_state=lambda estado: self._enviar_json({"type": "state", "state": estado}),
            on_tool=lambda name, args: self._enviar_json(
                {"type": "tool", "name": name, "arguments": args}
            ),
        )

        # Saudacao primeiro: o cliente sabe os formatos antes de qualquer audio.
        await self._enviar_json(
            {
                "type": "hello",
                "model": qr.realtime_model(),
                "voice": qr.realtime_voice(),
                "sample_rate_in": qr.INPUT_RATE,
                "sample_rate_out": qr.OUTPUT_RATE,
            }
        )

        try:
            await self.conv.start()
        except Exception as exc:
            await self._enviar_json(
                {"type": "error", "message": f"Falha ao abrir sessao realtime: {type(exc).__name__}: {exc}"}
            )
            return

        try:
            async for mensagem in self.ws:
                if isinstance(mensagem, (bytes, bytearray)):
                    # Microfone: PCM 16 kHz em blocos de ~100 ms (3200 bytes).
                    await self.conv.send_audio(bytes(mensagem))
                else:
                    await self._comando(json.loads(mensagem))
        finally:
            if self.conv is not None:
                await self.conv.close()

    async def _comando(self, dados: Dict[str, Any]) -> None:
        tipo = str(dados.get("type", ""))
        if tipo == "cancel":
            await self.conv.cancel()
        elif tipo == "ping":
            await self._enviar_json({"type": "pong", "t": time.time()})
        elif tipo == "close":
            await self.conv.close()


async def _handler(ws, path: Optional[str] = None) -> None:
    alvo = path or WS_PATH
    if not str(alvo).startswith(WS_PATH):
        try:
            await ws.close(code=1008, reason="path invalido")
        except Exception:
            pass
        return
    print(f"[QWEN LIVE] cliente conectado ({time.strftime('%H:%M:%S')})")
    bridge = _ClientBridge(ws)
    try:
        await bridge.rodar()
    except Exception as exc:
        print(f"[QWEN LIVE] sessao encerrada com erro ({type(exc).__name__}): {exc}")
    print(f"[QWEN LIVE] cliente desconectado ({time.strftime('%H:%M:%S')})")


def start_live_bridge(host: str = WS_HOST, port: int = WS_PORT):
    """Inicia a ponte numa thread daemon com event loop proprio.

    Seguro para chamar de servidores threadados (ex.: local_server do HUD).
    Retorna False quando a ponte nao pode iniciar (sem websockets/chave).
    """
    global _loop, _thread, _server
    if websockets is None:
        print("[QWEN LIVE] websockets indisponivel - ponte desativada.")
        return False
    if _thread is not None and _thread.is_alive():
        return True

    pronto = threading.Event()

    def _rodar():
        global _loop, _server
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)

        async def _start():
            global _server
            _server = await websockets.serve(_handler, host, port)
            pronto.set()

        _loop.run_until_complete(_start())
        _loop.run_forever()

    _thread = threading.Thread(target=_rodar, daemon=True, name="QwenLiveBridge")
    _thread.start()
    if not pronto.wait(timeout=5):
        print("[QWEN LIVE] ponte nao respondeu no boot.")
        return False
    print(f"[QWEN LIVE] ponte ativa em ws://{host}:{port}{WS_PATH}")
    return True


def stop_live_bridge() -> None:
    global _loop, _server
    if _loop is not None and _server is not None:
        try:
            asyncio.run_coroutine_threadsafe(_server.close(), _loop)
        except Exception:
            pass
    _server = None


if __name__ == "__main__":
    if websockets is None:
        print("Instale a dependencia: pip install websockets")
        sys.exit(1)
    if not qr.is_enabled():
        print("ATENCAO: QWEN_REALTIME_API_KEY ausente em C:\\JARVIS\\.env - a ponte")
        print("vai recusar sessoes. Configure a chave e reinicie.")
    print("=" * 64)
    print("  J.A.R.V.I.S. - CONVERSA AO VIVO (Qwen-Audio-3.0-Realtime-Plus)")
    print(f"  ws://{WS_HOST}:{WS_PORT}{WS_PATH}")
    print("=" * 64)
    start_live_bridge()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop_live_bridge()
        print("\n[QWEN LIVE] ponte encerrada.")
