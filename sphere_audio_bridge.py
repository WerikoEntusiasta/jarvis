"""Authenticated WSS transport for the physical J.A.R.V.I.S. sphere.

The listener fails closed: no TLS certificate or per-device token means no
socket is opened. Audio is passed to the caller only after a nonce-based HMAC
challenge succeeds.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import re
import ssl
import secrets
from http import HTTPStatus
from pathlib import Path
from typing import Awaitable, Callable

try:
    import opuslib
except ImportError:
    opuslib = None

_opus_decoders: dict = {}

def _decode_audio_frame(device_id: str, message: bytes) -> bytes:
    if not opuslib:
        return message
    dec = _opus_decoders.setdefault(device_id, opuslib.Decoder(16000, 1))
    if message.startswith(b"OPUS"):
        raw_opus = message[4:]
        try:
            samples = opuslib.api.decoder.get_nb_samples(dec._state, raw_opus, len(raw_opus))
            if samples <= 0:
                samples = 960
        except Exception:
            samples = 960
        return dec.decode(raw_opus, samples)
    elif len(message) < 250:
        try:
            samples = opuslib.api.decoder.get_nb_samples(dec._state, message, len(message))
            if samples <= 0:
                samples = 960
            return dec.decode(message, samples)
        except Exception:
            return message
    return message

# Registro acessível ao Core: device_id -> websocket autenticado.
# Todas as escritas acontecem no loop do serve (run_coroutine_threadsafe
# agenda push_to_device no mesmo thread) — acesso é single-threaded.
ACTIVE_SOCKETS: dict = {}
_LOOP = None


def get_loop():
    return _LOOP


async def push_to_device(device_id: str, payload: dict) -> bool:
    """Envia um JSON ao dispositivo autenticado; False se não estiver conectado."""
    ws = ACTIVE_SOCKETS.get(str(device_id)[:80])
    if ws is None:
        return False
    await ws.send(json.dumps(payload))
    return True


async def speak_to_device(device_id: str, pcm: bytes) -> bool:
    """Fala no dispositivo: tts start + frames PCM 16k (pacing ~tempo real) + stop.
    Pacing de 19ms por 640B (20ms de áudio) — mais rápido que isso enche o buffer
    da esfera e mata o socket (close 1006)."""
    ws = ACTIVE_SOCKETS.get(str(device_id)[:80])
    if ws is None:
        return False
    await ws.send(json.dumps({"type": "tts", "state": "start"}))
    try:
        for offset in range(0, len(pcm), 640):
            frame = pcm[offset:offset + 640]
            if len(frame) % 2:
                frame = frame[:-1]
            if frame:
                await ws.send(frame)
                await asyncio.sleep(0.019)
        await ws.send(json.dumps({"type": "tts", "state": "stop"}))
        return True
    except Exception:
        return False


def _load_device_tokens() -> dict[str, str]:
    raw = os.environ.get("SPHERE_DEVICE_TOKENS", "").strip()
    if not raw:
        return {}
    try:
        values = json.loads(raw)
    except Exception as exc:
        raise RuntimeError("SPHERE_DEVICE_TOKENS precisa ser um objeto JSON.") from exc
    if not isinstance(values, dict):
        raise RuntimeError("SPHERE_DEVICE_TOKENS precisa mapear device_id para segredo.")
    return {
        str(device_id)[:80]: str(token)
        for device_id, token in values.items()
        if str(device_id).strip() and len(str(token)) >= 32
    }


def _proof(secret: str, device_id: str, nonce: str) -> str:
    material = f"jarvis-sphere-v1:{device_id}:{nonce}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), material, hashlib.sha256).hexdigest()


async def serve_sphere_audio(on_audio: AudioCallback, on_disconnect=None) -> None:
    """Serve authenticated PCM over TLS; refuses insecure/missing configuration."""
    host = os.environ.get("SPHERE_WS_HOST", "0.0.0.0")
    # 8095 is reserved for the existing, plaintext screen/control router.
    # Voice must use its own TLS listener so it never falls back to cleartext.
    port = int(os.environ.get("SPHERE_WS_PORT", "8096"))
    cert_file = os.environ.get("SPHERE_WS_CERTFILE", "").strip()
    key_file = os.environ.get("SPHERE_WS_KEYFILE", "").strip()
    device_tokens = _load_device_tokens()
    if not cert_file or not key_file or not device_tokens:
        raise RuntimeError(
            "Ponte da esfera desativada: configure TLS e ao menos um token de dispositivo."
        )

    import websockets
    from websockets.datastructures import Headers
    from websockets.http11 import Response

    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.minimum_version = ssl.TLSVersion.TLSv1_2
    tls.load_cert_chain(certfile=cert_file, keyfile=key_file)
    global _LOOP
    _LOOP = asyncio.get_running_loop()
    connection_slots = asyncio.Semaphore(4)
    active_devices: set[str] = set()

    async def handle_http_request(_connection, request):
        """Expose only the authenticated, TLS-protected device firmware file."""
        if request.path.split("?", 1)[0] != "/firmware.bin":
            return None
        if request.method != "GET":
            return Response(
                HTTPStatus.METHOD_NOT_ALLOWED,
                "Method Not Allowed",
                Headers([("Content-Length", "0"), ("Cache-Control", "no-store")]),
            )

        device_id = str(request.headers.get("X-Jarvis-Device", ""))[:80]
        secret = device_tokens.get(device_id)
        supplied = str(request.headers.get("Authorization", ""))
        expected = f"Bearer {secret}" if secret else ""
        if not secret or not hmac.compare_digest(supplied, expected):
            return Response(
                HTTPStatus.UNAUTHORIZED,
                "Unauthorized",
                Headers([
                    ("Content-Length", "0"),
                    ("Cache-Control", "no-store"),
                    ("WWW-Authenticate", "Bearer"),
                ]),
            )

        firmware_path = Path(os.environ.get("SPHERE_FIRMWARE_PATH", "/app/firmware.bin"))
        try:
            firmware = firmware_path.read_bytes()
        except OSError:
            firmware = b""
        if not firmware or len(firmware) > 4 * 1024 * 1024:
            return Response(
                HTTPStatus.NOT_FOUND,
                "Not Found",
                Headers([("Content-Length", "0"), ("Cache-Control", "no-store")]),
            )
        return Response(
            HTTPStatus.OK,
            "OK",
            Headers([
                ("Content-Type", "application/octet-stream"),
                ("Content-Length", str(len(firmware))),
                ("Cache-Control", "no-store"),
                ("X-Content-Type-Options", "nosniff"),
            ]),
            firmware,
        )

    async def handle_connection(websocket, _path=None):
        device_id = ""
        authenticated = False
        slot_acquired = False
        device_reserved = False
        stage = "hello"
        try:
            await asyncio.wait_for(connection_slots.acquire(), timeout=2)
            slot_acquired = True
            request_path = getattr(websocket, "path", None) or getattr(getattr(websocket, "request", None), "path", "/ws")
            if str(request_path).split("?", 1)[0] != "/ws":
                await websocket.close(code=1008, reason="rota inválida")
                return
            hello_raw = await asyncio.wait_for(websocket.recv(), timeout=8)
            if not isinstance(hello_raw, str):
                print("[ESFERA] Handshake recusado (hello-binario).")
                await websocket.close(code=1008, reason="handshake inválido")
                return
            hello = json.loads(hello_raw)
            if hello.get("type") != "hello":
                print("[ESFERA] Handshake recusado (hello-tipo-inválido).")
                await websocket.close(code=1008, reason="handshake inválido")
                return
            device_id = str(hello.get("device_id") or hello.get("device") or "")[:80]
            secret = device_tokens.get(device_id)
            if not secret:
                print("[ESFERA] Handshake recusado (dispositivo-nao-cadastrado).")
                await websocket.close(code=1008, reason="dispositivo não autorizado")
                return
            if device_id in active_devices:
                print(f"[ESFERA] Sessão anterior assumida por nova conexão ({device_id}).")
                old_ws = ACTIVE_SOCKETS.pop(device_id, None)
                active_devices.discard(device_id)
                if old_ws is not None and old_ws is not websocket:
                    try:
                        await old_ws.close(code=1001, reason="sessão assumida")
                    except Exception:
                        pass
            active_devices.add(device_id)
            ACTIVE_SOCKETS[device_id] = websocket
            device_reserved = True

            nonce = secrets.token_hex(32)
            await websocket.send(json.dumps({"type": "challenge", "nonce": nonce}))
            stage = "auth"
            auth_raw = ""
            try:
                for _ in range(300):
                    msg = await asyncio.wait_for(websocket.recv(), timeout=5)
                    if isinstance(msg, str):
                        auth_raw = msg
                        break
            except asyncio.TimeoutError:
                pass
            print(f"[ESFERA] Prova recebida ({device_id}).")
            if not auth_raw:
                print(f"[ESFERA] Sem prova textual ({device_id}).")
                await websocket.close(code=1008, reason="autenticação inválida")
                return
            auth_message = json.loads(auth_raw)
            supplied = str(auth_message.get("proof", ""))
            expected = _proof(secret, device_id, nonce)
            if auth_message.get("type") != "auth":
                rejection_reason = "message-type"
            elif auth_message.get("device_id") != device_id:
                rejection_reason = "device-id"
            elif not re.fullmatch(r"[0-9a-f]{64}", supplied):
                rejection_reason = "proof-format"
            elif not hmac.compare_digest(supplied, expected):
                rejection_reason = "proof-mismatch"
            else:
                rejection_reason = ""

            if rejection_reason:
                print(f"[ESFERA] Desafio recusado ({rejection_reason}; {device_id}).")
                await websocket.close(code=1008, reason="autenticação inválida")
                return

            authenticated = True
            stage = "authenticated"
            await websocket.send(json.dumps({
                "type": "hello",
                "transport": "websocket",
                "audio_params": {"format": "opus", "sample_rate": 16000, "channels": 1, "frame_duration": 60},
            }))
            print(f"[ESFERA] Dispositivo autenticado; TLS ativo ({device_id}).")
            async for message in websocket:
                if isinstance(message, bytes):
                    pcm = _decode_audio_frame(device_id, message)
                    await on_audio(device_id, pcm, websocket)
                elif isinstance(message, str):
                    try:
                        control = json.loads(message)
                    except Exception:
                        continue
                    if control.get("type") == "ping":
                        await websocket.send(json.dumps({"type": "pong"}))
        except asyncio.TimeoutError:
            print(f"[ESFERA] Tempo esgotado na etapa {stage}.")
            try:
                await websocket.close(code=1008, reason="handshake expirado")
            except Exception:
                pass
        except Exception as exc:
            # Deliberately omit payloads, tokens, audio, and exception text from logs.
            try:
                code = websocket.close_code
                reason = str(websocket.close_reason or "")[:64]
            except Exception:
                code, reason = None, ""
            print(f"[ESFERA] Sessão encerrada ({type(exc).__name__} close={code} reason={reason}).")
        finally:
            if authenticated and on_disconnect:
                try:
                    on_disconnect(device_id, websocket)
                except Exception:
                    pass
            if device_reserved:
                if ACTIVE_SOCKETS.get(device_id) is websocket:
                    ACTIVE_SOCKETS.pop(device_id, None)
                    active_devices.discard(device_id)
            if slot_acquired:
                connection_slots.release()

    async with websockets.serve(
        handle_connection,
        host,
        port,
        ssl=tls,
        max_size=256 * 1024,
        ping_interval=20,
        ping_timeout=20,
        close_timeout=3,
        process_request=handle_http_request,
    ):
        print(f"[+] Ponte WSS da esfera ativa em {host}:{port}; TLS e HMAC obrigatórios.")
        await asyncio.Future()
