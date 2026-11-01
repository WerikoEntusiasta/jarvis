"""
Cliente de Rede WebSocket de Alta Performance com o Núcleo J.A.R.V.I.S. (ZimaOS Core :8095)
Mantém conexão WebSocket bidirecional em tempo real, executa comandos remotos no PC,
transmite telemetria contínua e integra com a Esfera física e o HUD.
"""

import json
import time
import threading
import asyncio
import urllib.request
from typing import Callable, Optional, Dict, Any

try:
    import websockets
except ImportError:
    websockets = None

from config.settings import CORE_URL, BRIDGE_SECRET, NODE_ID
from mcp.windows_mcp import dispatch_mcp_tool
from system.hardware_monitor import get_system_telemetry

ZIMA_WS_URL = "ws://45.167.187.80:8095/ws"

class JarvisNetworkClient(threading.Thread):
    def __init__(self,
                 on_command_received: Optional[Callable[[Dict[str, Any]], None]] = None,
                 on_status_changed: Optional[Callable[[bool, str], None]] = None):
        super().__init__(daemon=True, name="JarvisWebSocketClient")
        self.on_command = on_command_received
        self.on_status = on_status_changed
        self._running = True
        self.is_connected = False
        self._loop = None
        self._ws = None

    def run(self):
        print(f"[JarvisNetwork] Conectando WebSocket ao Núcleo ZimaOS ({ZIMA_WS_URL})...")
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._main_ws_loop())

    async def _main_ws_loop(self):
        while self._running:
            try:
                if websockets is None:
                    print("[JarvisNetwork] Erro: biblioteca 'websockets' não disponível.")
                    await asyncio.sleep(5)
                    continue

                async with websockets.connect(ZIMA_WS_URL, ping_interval=20, ping_timeout=15) as ws:
                    self._ws = ws
                    self.is_connected = True
                    if self.on_status:
                        self.on_status(True, "Conectado ao Núcleo J.A.R.V.I.S.")
                    print("[JarvisNetwork] WebSocket CONECTADO com sucesso ao Núcleo J.A.R.V.I.S.!")

                    # 1. Handshake de Registro do PC Windows
                    hello_msg = {
                        "type": "hello",
                        "device": "jarvis_windows_pc",
                        "version": 1,
                        "transport": "websocket"
                    }
                    await ws.send(json.dumps(hello_msg))

                    # 2. Inicia loop de telemetria em segundo plano
                    telemetry_task = asyncio.create_task(self._telemetry_stream(ws))

                    # 3. Loop de recebimento de mensagens e comandos
                    async for raw_msg in ws:
                        try:
                            if isinstance(raw_msg, str):
                                data = json.loads(raw_msg)
                                await self._handle_incoming_message(ws, data)
                        except Exception as msg_err:
                            print(f"[JarvisNetwork] Erro ao processar mensagem: {msg_err}")

                    telemetry_task.cancel()

            except Exception as e:
                self.is_connected = False
                if self.on_status:
                    self.on_status(False, f"Reconectando ao Núcleo... ({type(e).__name__})")
                print(f"[JarvisNetwork] Conexão perdida ({e}). Reconectando em 3s...")
                await asyncio.sleep(3.0)

    async def _telemetry_stream(self, ws):
        """Transmite telemetria ao vivo da máquina (CPU, RAM, GPU RTX) a cada 3 segundos."""
        while self._running and self.is_connected:
            try:
                telem = get_system_telemetry()
                cpu = telem.get("cpu_percent", 0)
                ram = telem.get("ram_percent", 0)
                gpu = telem.get("gpu", {})
                msg = {
                    "type": "custom",
                    "payload": {
                        "event": "jarvis.telemetry",
                        "cpu": cpu,
                        "ram": ram,
                        "gpu_temp": gpu.get("temp", 0),
                        "gpu_util": gpu.get("utilization", 0),
                        "gpu_vram": gpu.get("vram_used", "0G")
                    }
                }
                await ws.send(json.dumps(msg))
            except Exception:
                pass
            await asyncio.sleep(3.0)

    async def _handle_incoming_message(self, ws, data: Dict[str, Any]):
        msg_type = data.get("type", "")
        payload = data.get("payload", {})
        event = payload.get("event", "") if isinstance(payload, dict) else ""

        # Comandos de iluminação Tuya (Lâmpada / Luz do PC / Setup)
        if msg_type in ("tuya_command", "lighting") or event in ("tuya_command", "jarvis.tuya_command", "tuya_state"):
            act = data.get("action") or payload.get("action", "")
            state = data.get("state", None)
            if state is None:
                state = payload.get("state", None)
            target = data.get("target") or payload.get("target", "setup")
            print(f"[JarvisNetwork] Executando comando de iluminação local: action='{act}' state={state} target='{target}'")
            try:
                from services.tuya_service import tuya_service
                if act == "on" or state is True:
                    tuya_service.turn_on(target)
                elif act == "off" or state is False:
                    tuya_service.turn_off(target)
                else:
                    tuya_service.toggle(target)
            except Exception as e:
                print(f"[JarvisNetwork] Erro ao comutar lâmpada Tuya: {e}")
            return

        # Comandos direcionados ao Windows (por voz, pela Esfera ou por API)
        if msg_type in ("windows_command", "system_command") or event in ("windows_command", "system_command"):
            action = data.get("action") or payload.get("action", "")
            params = data.get("params") or payload.get("params", {})
            cmd_id = data.get("id") or payload.get("id", str(int(time.time())))

            print(f"[JarvisNetwork] Executando comando Windows: action='{action}' params={params}")

            # Dispara callback para alertar o HUD visual
            if self.on_command:
                try:
                    self.on_command({"action": action, "params": params, "id": cmd_id})
                except Exception:
                    pass

            # Executa a ação do Windows em thread separada
            def _exec():
                res = dispatch_mcp_tool(action, params)
                print(f"[JarvisNetwork] Resultado do comando '{action}': {res}")
                # Envia resultado de volta ao ZimaOS
                if self._loop and self._ws:
                    resp_msg = {
                        "type": "custom",
                        "payload": {
                            "event": "windows_command_result",
                            "id": cmd_id,
                            "action": action,
                            "result": res
                        }
                    }
                    asyncio.run_coroutine_threadsafe(self._ws.send(json.dumps(resp_msg)), self._loop)

            threading.Thread(target=_exec, daemon=True).start()

    def send_chat_message(self, message: str) -> Dict[str, Any]:
        """Envia mensagem ao cérebro local/remoto do J.A.R.V.I.S. e aguarda resposta."""
        url = f"{CORE_URL}/api/chat"
        payload = {
            "message": message,
            "source": "windows_native_hud",
            "device_id": NODE_ID
        }
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "X-Bridge-Secret": BRIDGE_SECRET
        }
        try:
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            return {"ok": False, "error": str(e), "response": f"Erro de comunicação: {e}"}

    def stop(self):
        self._running = False
        if self._loop:
            self._loop.stop()
