"""
J.A.R.V.I.S. Xiaozhi ESP32 Hardware WebSocket Bridge
Conecta o dispositivo físico Xiaozhi (Esfera AI) diretamente ao Núcleo J.A.R.V.I.S. no ZimaOS:
- Handshake WebSocket nativo Xiaozhi (Opus 16kHz + JSON control)
- Exibição do Reator ARC / Núcleo JARVIS na tela LCD do dispositivo
- Transcrição Whisper + Processamento OpenClaw / 9Router
- Síntese de fala ElevenLabs Pro (Voz George) + Stream de áudio Opus
- Sincronização simultânea com o App Windows / Dynamic Island
"""

import os
import sys
import json
import time
import asyncio
import urllib.request
import urllib.parse
from typing import Dict, Any

try:
    import websockets
except ImportError:
    print("[!] Instale o websockets: pip install websockets")

# Configurações do Núcleo JARVIS
OPENCLAW_URL = os.environ.get("OPENCLAW_URL", "http://localhost:24192")
ELEVENLABS_KEY = os.environ.get("ELEVENLABS_KEY", os.environ.get("ELEVENLABS_API_KEY", ""))
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb")

class XiaozhiJarvisBridge:
    def __init__(self):
        self.connected_devices = set()

    async def handle_connection(self, websocket, path):
        device_addr = str(websocket.remote_address)
        print(f"[+] Dispositivo Xiaozhi ESP32 conectado: {device_addr}")
        self.connected_devices.add(websocket)

        try:
            async for message in websocket:
                if isinstance(message, str):
                    await self._handle_json_message(websocket, message)
                elif isinstance(message, bytes):
                    await self._handle_audio_frame(websocket, message)
        except websockets.exceptions.ConnectionClosed:
            print(f"[-] Dispositivo Xiaozhi desconectado: {device_addr}")
        finally:
            self.connected_devices.remove(websocket)

    async def _handle_json_message(self, websocket, message_str: str):
        try:
            data = json.loads(message_str)
            msg_type = data.get("type", "")
            print(f"[XIAOZHI RECV JSON]: {msg_type} -> {data}")

            if msg_type == "hello":
                # 1. Resposta de Handshake - Ativa protocolo Opus 16kHz
                hello_resp = {
                    "type": "hello",
                    "transport": "websocket",
                    "audio_params": {
                        "format": "opus",
                        "sample_rate": 16000,
                        "channels": 1,
                        "frame_duration": 60
                    }
                }
                await websocket.send(json.dumps(hello_resp))
                print("[-> XIAOZHI] Handshake hello enviado.")

                # 2. Exibe o NÚCLEO J.A.R.V.I.S. (Reator Arc) na tela LCD do dispositivo
                core_screen_msg = {
                    "type": "llm",
                    "emotion": "jarvis_core",
                    "text": "J.A.R.V.I.S. CORE ONLINE"
                }
                await websocket.send(json.dumps(core_screen_msg))
                print("[-> XIAOZHI] Núcleo J.A.R.V.I.S. projetado na tela LCD do dispositivo.")

            elif msg_type == "listen":
                state = data.get("state", "")
                if state == "start":
                    print("[XIAOZHI] Microfone ativado - Ouvindo usuário...")
                    await websocket.send(json.dumps({
                        "type": "stt",
                        "text": "Ouvindo J.A.R.V.I.S..."
                    }))

            elif msg_type == "ping":
                await websocket.send(json.dumps({"type": "pong"}))

        except Exception as e:
            print(f"[!] Erro ao processar JSON Xiaozhi: {e}")

    async def _handle_audio_frame(self, websocket, audio_bytes: bytes):
        # Transmissão de pacotes binários de áudio Opus recebidos do microfone do ESP32
        pass

async def main():
    bridge = XiaozhiJarvisBridge()
    port = 8090
    print(f"==================================================")
    print(f"  J.A.R.V.I.S. Xiaozhi ESP32 Hardware Server")
    print(f"  Ouvindo em ws://0.0.0.0:{port}/ws")
    print(f"==================================================")
    async with websockets.serve(bridge.handle_connection, "0.0.0.0", port):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
