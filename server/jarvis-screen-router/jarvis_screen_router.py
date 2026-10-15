"""

J.A.R.V.I.S. Screen Router + Voice Bridge (porta 8095)

Responsabilidades:

1. WebSocket /ws para a Esfera ESP32-S3 (tela, emoção, toque, OTA).

2. VOZ (novo): recebe PCM 16 kHz mono do microfone (frames binários), faz VAD,

   transcreve (Whisper no Core), consulta o cérebro (/api/chat) e devolve o áudio

   TTS em PCM 16 kHz (frames binários) + eventos de emoção para a esfera falar.

"""



import os

import io

import time

import json

import math

import wave

import asyncio

import logging

import audioop

from typing import Dict, Any

from aiohttp import web, ClientSession



logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")



FIRMWARE_PATH = os.environ.get("FIRMWARE_PATH", "/app/firmware.bin")

JARVIS_HUD_URL = os.environ.get("JARVIS_HUD_URL", "http://172.17.0.1:8085").rstrip("/")



SAMPLE_RATE = 16000

BYTES_PER_SEC = SAMPLE_RATE * 2  # s16le mono

VAD_RMS = int(os.environ.get("VAD_RMS", "1800"))

SILENCE_SEC = float(os.environ.get("VAD_SILENCE_SEC", "1.5"))

MIN_UTTERANCE_SEC = 0.5

MAX_UTTERANCE_SEC = 15.0

PREROLL_SEC = 0.3



# Wake word "Jarvis" + janela de follow-up (permite turnos seguidos sem repetir "Jarvis")

WAKE_WORDS = ("jarvis", "jervis", "javis", "jarves", "jarviz")

FOLLOWUP_SEC = float(os.environ.get("WAKE_FOLLOWUP_SEC", "20.0"))

wake_state: Dict[str, float] = {}

processing_state: Dict[str, bool] = {}
followup_tasks: Dict[str, asyncio.Task] = {}

recording_state: Dict[str, Dict[str, Any]] = {}



# ---------------- WAKE WORD LOCAL (openWakeWord "hey_jarvis") ----------------

# Limiar mais conservador para reduzir ativações acidentais do wake-word.
OWW_THRESHOLD = float(os.environ.get("OWW_THRESHOLD", "0.50"))

_oww = None

_np = None

_oww_buf: Dict[str, Any] = {}

_oww_dbg: Dict[str, Any] = {}

try:

    import numpy as _np  # noqa

    from openwakeword.model import Model as _OWWModel  # noqa

    _oww = _OWWModel(wakeword_models=["hey_jarvis"], inference_framework="onnx")

    logging.info("[WW] openWakeWord carregado (modelo hey_jarvis)")

except Exception as _e:

    _oww = None

    logging.warning(f"[WW] openWakeWord indisponivel: {_e}")





async def _ww_wake(ws: web.WebSocketResponse, device_id: str):
    """Ao detectar 'Jarvis', mantém o visor no estado de escuta."""
    try:
        await ws.send_str(json.dumps({"type": "wakeup"}))
        _start_followup_timeout(ws, device_id)
    except Exception:
        pass


async def _return_to_standby_when_idle(ws: web.WebSocketResponse, device_id: str):
    """Mantém a tela aberta enquanto há atividade e retorna ao relógio após 20s."""
    try:
        while not ws.closed:
            if processing_state.get(device_id):
                await asyncio.sleep(0.5)
                continue

            remaining = FOLLOWUP_SEC - (time.time() - wake_state.get(device_id, 0.0))
            if remaining > 0:
                await asyncio.sleep(remaining)
                continue

            await ws.send_str(json.dumps({"type": "emotion", "emotion": "standby"}))
            return
    except Exception as e:
        logging.debug(f"[WW] Fim da janela de escuta ({device_id}): {e}")


def _start_followup_timeout(ws: web.WebSocketResponse, device_id: str):
    task = followup_tasks.get(device_id)
    if task and not task.done():
        task.cancel()
    followup_tasks[device_id] = asyncio.create_task(
        _return_to_standby_when_idle(ws, device_id)
    )


def _oww_feed(device_id: str, data: bytes, ws: web.WebSocketResponse):

    """Alimenta o openWakeWord (chunks de 1280 amostras @16kHz) e detecta a wake word."""

    if _oww is None or _np is None:

        return

    try:

        buf = _oww_buf.get(device_id)

        if buf is None:

            buf = _np.zeros(0, dtype=_np.int16)

        buf = _np.concatenate([buf, _np.frombuffer(data, dtype=_np.int16)])

        fired = False

        peak = 0.0

        while len(buf) >= 1280:

            chunk = buf[:1280]

            buf = buf[1280:]

            try:

                pred = _oww.predict(chunk)

            except Exception:

                pred = {}

            for _name, _score in (pred or {}).items():

                if _score > peak:

                    peak = _score

                if _score >= OWW_THRESHOLD and not fired:

                    fired = True

                    wake_state[device_id] = time.time()

                    logging.info(f"[WW] 'Jarvis' detectado (score {_score:.2f}) em {device_id}")

        # debug: pico de score a cada ~3s

        dbg = _oww_dbg.setdefault(device_id, {"peak": 0.0, "rms": 0.0, "n": 0, "t": time.time()})

        if peak > dbg["peak"]:

            dbg["peak"] = peak

        dbg["n"] += 1

        try:

            _r = float(_np.sqrt(_np.mean(_np.frombuffer(data, dtype=_np.int16).astype(_np.float64) ** 2)))

        except Exception:

            _r = 0.0

        if _r > dbg["rms"]:

            dbg["rms"] = _r

        if time.time() - dbg["t"] >= 3.0:

            logging.info(f"[WW-DBG] score_pico={dbg['peak']:.3f} rms_pico={dbg['rms']:.0f} chunks={dbg['n']} (limiar={OWW_THRESHOLD})")

            dbg["peak"] = 0.0

            dbg["rms"] = 0.0

            dbg["n"] = 0

            dbg["t"] = time.time()

        if fired:

            try:

                asyncio.get_running_loop().create_task(_ww_wake(ws, device_id))

            except Exception:

                pass

        _oww_buf[device_id] = buf

    except Exception as _e:

        logging.warning(f"[WW] erro: {_e}")



active_sessions: Dict[str, web.WebSocketResponse] = {}

pending_requests: Dict[str, Dict[str, Any]] = {}

audio_state: Dict[str, Dict[str, Any]] = {}





# ----------------------------- VOZ -----------------------------

def _pcm_to_wav(pcm: bytes) -> bytes:

    buf = io.BytesIO()

    with wave.open(buf, "wb") as w:

        w.setnchannels(1)

        w.setsampwidth(2)

        w.setframerate(SAMPLE_RATE)

        w.writeframes(pcm)

    return buf.getvalue()





def _highpass_pcm(pcm: bytes, cutoff: float = 200.0, sr: int = SAMPLE_RATE) -> bytes:

    """Biquad high-pass: remove hum de rede (60/120/180Hz) e rumble antes do STT."""

    try:

        import array

        a = array.array("h")

        a.frombytes(pcm)

        w0 = 2.0 * math.pi * cutoff / sr

        cw = math.cos(w0)

        sw = math.sin(w0)

        alpha = sw / (2.0 * 0.707)

        b0 = (1.0 + cw) / 2.0

        b1 = -(1.0 + cw)

        b2 = (1.0 + cw) / 2.0

        a0 = 1.0 + alpha

        a1 = -2.0 * cw

        a2 = 1.0 - alpha

        x1 = x2 = y1 = y2 = 0.0

        out = array.array("h", bytes(len(a) * 2))

        for i in range(len(a)):

            xi = float(a[i])

            yi = (b0 * xi + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2) / a0

            x2 = x1; x1 = xi; y2 = y1; y1 = yi

            v = int(yi)

            out[i] = 32767 if v > 32767 else (-32768 if v < -32768 else v)

        return out.tobytes()

    except Exception:

        return pcm





async def _transcribe(session: ClientSession, wav_bytes: bytes) -> str:

    async with session.post(f"{JARVIS_HUD_URL}/api/transcribe", data=wav_bytes,

                            headers={"Content-Type": "audio/wav"}, timeout=75) as r:

        j = await r.json(content_type=None)

        return (j.get("text") or "").strip()





MODEL_FAILURE_SENTINEL = "__JARVIS_OPENCLAW_MODEL_FAILURE__"

async def _chat(session: ClientSession, text: str, device_id: str = "") -> str:

    async with session.post(f"{JARVIS_HUD_URL}/api/chat",

                            json={"message": text, "device_id": device_id, "source": "esfera"}, timeout=130) as r:

        j = await r.json(content_type=None)
        if r.status >= 500 or j.get("model_failed") is True:
            return MODEL_FAILURE_SENTINEL

        return (j.get("reply") or "").strip()





async def _tts_pcm(session: ClientSession, text: str) -> bytes:

    async with session.post(f"{JARVIS_HUD_URL}/api/tts_pcm", json={"text": text}, timeout=45) as r:

        if r.status == 200:

            return await r.read()

    return b""





def _has_wake_word(text: str) -> bool:

    t = text.lower()

    # Só reconhece o nome como palavra inteira; evita disparar por fragmentos como "vis".
    words = "".join(ch if ch.isalnum() else " " for ch in t).split()
    return any(w in words for w in WAKE_WORDS)





def _strip_wake_word(text: str) -> str:

    t = text

    low = t.lower()

    for w in WAKE_WORDS:

        idx = low.find(w)

        if idx >= 0:

            t = t[:idx] + t[idx + len(w):]

            low = t.lower()

    return t.strip(" ,.!?;:-—\t\n")





async def process_utterance(ws: web.WebSocketResponse, device_id: str, pcm: bytes):

    if not pcm or len(pcm) < int(MIN_UTTERANCE_SEC * BYTES_PER_SEC):

        processing_state[device_id] = False

        return

    logging.info(f"[VOZ] Utterance {len(pcm)} bytes ({len(pcm)/BYTES_PER_SEC:.1f}s) de {device_id} -> transcrevendo...")

    pcm_f = pcm  # sem filtro: o high-pass estava atrapalhando o Whisper

    # DEBUG: salva a última utterance p/ inspeção de qualidade de áudio

    try:

        with open("/tmp/utt_last.wav", "wb") as _f:

            _f.write(_pcm_to_wav(pcm_f))

    except Exception:

        pass

    try:

        async with ClientSession() as session:

            await ws.send_str(json.dumps({"type": "emotion", "emotion": "transcribing"}))
            logging.info(f"[VOZ] {device_id}: chamando STT ({len(pcm)/BYTES_PER_SEC:.1f}s)...")

            text = await _transcribe(session, _pcm_to_wav(pcm_f))

            logging.info(f"[VOZ] {device_id}: STT retornou: {text!r}")

            if not text:

                logging.info("[VOZ] Transcrição vazia (ignorado).")

                return



            now = time.time()

            has_wake = _has_wake_word(text)

            within_followup = (now - wake_state.get(device_id, 0.0)) <= (FOLLOWUP_SEC + 30.0)

            if not has_wake and not within_followup:

                logging.info(f"[VOZ] Sem wake word ('Jarvis'), ignorado: '{text}'")

                return



            # Wake word detectada (ou turno de follow-up): atualiza a janela

            wake_state[device_id] = now

            if has_wake:

                text = _strip_wake_word(text)

                if not text:

                    text = "Pois não?"

            logging.info(f"[VOZ] STT: '{text}'")

            # Evento 'stt' faz a esfera mudar para a tela do rosto (SetDisplayMode kHappy)

            await ws.send_str(json.dumps({"type": "stt", "text": text}))



            try:
                reply = await _chat(session, text, device_id)
            except Exception as chat_error:
                logging.warning(f"[VOZ] OpenClaw request failed ({type(chat_error).__name__}).")
                reply = MODEL_FAILURE_SENTINEL

            model_failed = reply == MODEL_FAILURE_SENTINEL
            if model_failed:
                reply = "Modelo falhou."

            logging.info(f"[VOZ] Resposta: '{reply[:100]}'")

            await ws.send_str(json.dumps({"type": "emotion", "emotion": "speaking"}))

            pcm_out = await _tts_pcm(session, reply)

            if pcm_out:

                for i in range(0, len(pcm_out), 4096):

                    await ws.send_bytes(pcm_out[i:i + 4096])

                logging.info(f"[VOZ] TTS enviado para a esfera ({len(pcm_out)} bytes).")

            else:

                logging.warning("[VOZ] Sem áudio TTS (endpoint /api/tts_pcm falhou).")

            await ws.send_str(json.dumps({"type": "tts", "state": "end"}))

            if model_failed:
                wake_state.pop(device_id, None)
                followup_task = followup_tasks.pop(device_id, None)
                if followup_task and followup_task is not asyncio.current_task():
                    followup_task.cancel()
                await ws.send_str(json.dumps({"type": "emotion", "emotion": "standby"}))
                logging.info(f"[VOZ] {device_id}: modelo falhou; aviso falado e retorno ao standby.")
                return

            wake_state[device_id] = time.time()
            await ws.send_str(json.dumps({"type": "emotion", "emotion": "listening"}))
            _start_followup_timeout(ws, device_id)

    except Exception as e:

        logging.error(f"[VOZ] Erro no pipeline: {type(e).__name__}: {repr(e)}")

    finally:

        processing_state[device_id] = False





def handle_binary(ws: web.WebSocketResponse, device_id: str, data: bytes):

    # Modo gravação manual (contagem regressiva na tela): acumula TODO o PCM, ignora o VAD

    rec = recording_state.get(device_id)

    if rec and time.time() < rec["until"]:

        rec["buf"].extend(data)

        return

    _oww_feed(device_id, data, ws)

    st = audio_state.setdefault(device_id, {"buf": bytearray(), "speaking": False, "silence_start": 0.0})

    try:

        rms = audioop.rms(data, 2)

    except Exception:

        rms = 0

    now = time.time()



    # DEBUG: rastrear nível do microfone (pico de RMS a cada 2s)

    dbg = st.setdefault("dbg", {"n": 0, "peak": 0, "t": now, "bytes": 0})

    dbg["n"] += 1

    dbg["bytes"] += len(data)

    if rms > dbg["peak"]:

        dbg["peak"] = rms

    if now - dbg["t"] >= 2.0:

        logging.info(f"[MIC-DBG] {device_id}: frames={dbg['n']} bytes={dbg['bytes']} peakRMS={dbg['peak']} (VAD={VAD_RMS})")

        dbg["n"] = 0

        dbg["peak"] = 0

        dbg["bytes"] = 0

        dbg["t"] = now



    if rms >= VAD_RMS:

        if time.time() - wake_state.get(device_id, 0.0) <= FOLLOWUP_SEC:

            wake_state[device_id] = now

        st["speaking"] = True

        st["silence_start"] = 0.0

        st["buf"].extend(data)

    elif st["speaking"]:

        st["buf"].extend(data)

        if st["silence_start"] == 0.0:

            st["silence_start"] = now

        elif (now - st["silence_start"]) >= SILENCE_SEC:

            pcm = bytes(st["buf"])

            st["buf"] = bytearray()

            st["speaking"] = False

            st["silence_start"] = 0.0

            within_wake = (time.time() - wake_state.get(device_id, 0.0)) <= FOLLOWUP_SEC

            if not within_wake:

                logging.info(f"[VOZ] {device_id}: sem 'Jarvis' ativo — utterance ignorada (sem STT).")

            elif processing_state.get(device_id):

                logging.info(f"[VOZ] {device_id} ocupado processando — utterance descartada.")

            else:

                processing_state[device_id] = True

                wake_state[device_id] = time.time()

                asyncio.create_task(process_utterance(ws, device_id, pcm))

    else:

        keep = int(PREROLL_SEC * BYTES_PER_SEC)

        if len(st["buf"]) > keep:

            st["buf"] = st["buf"][-keep:]



    if len(st["buf"]) > int(MAX_UTTERANCE_SEC * BYTES_PER_SEC):

        st["buf"] = st["buf"][-int(MAX_UTTERANCE_SEC * BYTES_PER_SEC):]





# ----------------------------- WEBSOCKET -----------------------------

async def handle_websocket(request: web.Request) -> web.WebSocketResponse:

    ws = web.WebSocketResponse(max_msg_size=0)

    await ws.prepare(request)



    device_id = "jarvis_sphere_esp32s3"

    active_sessions[device_id] = ws

    logging.info(f"[WS] Conexão WebSocket estabelecida: {device_id}")



    try:

        async for msg in ws:

            if msg.type == web.WSMsgType.TEXT:

                try:

                    data = json.loads(msg.data)

                except Exception:

                    continue

                msg_type = data.get("type")



                if msg_type == "hello":

                    device_id = data.get("device", device_id)

                    active_sessions[device_id] = ws

                    ap = data.get("audio_params", {})

                    logging.info(f"[WS] hello de {device_id} | audio_params={ap}")



                elif msg_type == "custom":

                    payload = data.get("payload", {})

                    event = payload.get("event")

                    if event == "jarvis.button_clicked":

                        req_id = payload.get("request_id")

                        button_id = payload.get("button_id")

                        logging.info(f"[WS] Toque: req={req_id} btn={button_id}")

                        if req_id in pending_requests:

                            fut = pending_requests[req_id].get("future")

                            if fut and not fut.done():

                                fut.set_result({"status": "success", "button_id": button_id, "request_id": req_id})

                    elif event == "spotify_action":
                        action = str(payload.get("action", "")).strip()
                        device = str(payload.get("device", "") or "").strip()
                        if action:
                            try:
                                async with ClientSession() as _spot_session:
                                    async with _spot_session.post(
                                        f"{JARVIS_HUD_URL}/api/spotify/control",
                                        json={"action": action, "device": device or None}, timeout=15,
                                    ) as _r:
                                        _ok = _r.status in (200, 204)
                                logging.info(f"[SPOTIFY] {device_id}: {action} -> {'ok' if _ok else 'falha'}")
                            except Exception as _e:
                                logging.warning(f"[SPOTIFY] {device_id}: {action} falhou ({type(_e).__name__})")



            elif msg.type == web.WSMsgType.BINARY:

                handle_binary(ws, device_id, msg.data)



            elif msg.type == web.WSMsgType.ERROR:

                logging.error(f"[WS] Erro: {ws.exception()}")



    finally:

        if active_sessions.get(device_id) == ws:

            del active_sessions[device_id]

        audio_state.pop(device_id, None)

        logging.info(f"[WS] Sessão encerrada: {device_id}")



    return ws





# ----------------------------- TELA / OTA -----------------------------

async def handle_show_screen(request: web.Request) -> web.Response:

    try:

        body = await request.json()

        device_id = body.get("device_id", "jarvis_sphere_esp32s3")

        screen = body.get("screen", {})

        timeout_sec = body.get("timeout", 30)



        if device_id not in active_sessions:

            return web.json_response({

                "status": "error",

                "message": f"Dispositivo '{device_id}' sem sessão WebSocket ativa."

            }, status=404)



        ws = active_sessions[device_id]

        req_id = f"req_{int(time.time() * 1000)}"

        loop = asyncio.get_event_loop()

        future = loop.create_future()

        pending_requests[req_id] = {"future": future, "device_id": device_id, "expiry": time.time() + timeout_sec}



        message_json = {

            "type": "custom",

            "payload": {"event": "jarvis.show_screen", "request_id": req_id, "screen": screen}

        }

        await ws.send_str(json.dumps(message_json))

        logging.info(f"[TELA] show_screen -> {device_id} (req {req_id})")



        if timeout_sec and timeout_sec > 0:

            try:

                result = await asyncio.wait_for(future, timeout=timeout_sec)

                return web.json_response(result)

            except asyncio.TimeoutError:

                return web.json_response({"status": "timeout", "request_id": req_id}, status=408)

            finally:

                pending_requests.pop(req_id, None)

        else:

            return web.json_response({"status": "sent", "request_id": req_id})

    except Exception as e:

        logging.error(f"[ERRO API] {e}")

        return web.json_response({"status": "error", "message": str(e)}, status=500)





async def handle_record(request: web.Request) -> web.Response:

    """Grava N segundos do mic da esfera com contagem regressiva NA TELA dela.

    Acumula todo o PCM (ignora o VAD) e salva em /tmp/utt_last.wav."""

    try:

        body = {}

        if request.can_read_body:

            try:

                body = await request.json()

            except Exception:

                body = {}

        sec = int(body.get("sec", 10))

        device_id = body.get("device_id", "jarvis_sphere_esp32s3")

        ws = active_sessions.get(device_id)

        if ws is None:

            return web.json_response({"status": "error", "message": "dispositivo sem sessão WS"}, status=404)



        rec = {"until": time.time() + sec, "buf": bytearray()}

        recording_state[device_id] = rec

        logging.info(f"[REC] iniciando gravação de {sec}s em {device_id}")

        for i in range(sec, 0, -1):

            card = {"type": "custom", "payload": {"event": "jarvis.show_screen",

                    "request_id": f"rec_{int(time.time()*1000)}",

                    "screen": {"title": "● GRAVANDO", "message": f"FALE AGORA... {i}",

                               "button1_id": "", "button1_label": "", "button2_id": "", "button2_label": ""}}}

            try:

                await ws.send_str(json.dumps(card))

            except Exception:

                pass

            await asyncio.sleep(1)



        recording_state.pop(device_id, None)

        pcm = bytes(rec["buf"])

        try:

            with open("/tmp/rec_last.wav", "wb") as f:

                f.write(_pcm_to_wav(pcm))

        except Exception:

            pass

        try:

            await ws.send_str(json.dumps({"type": "emotion", "emotion": "standby"}))

        except Exception:

            pass

        logging.info(f"[REC] fim: {len(pcm)} bytes ({len(pcm)/BYTES_PER_SEC:.1f}s)")

        return web.json_response({"status": "ok", "bytes": len(pcm), "seconds": round(len(pcm)/BYTES_PER_SEC, 2)})

    except Exception as e:

        logging.error(f"[REC] erro: {e}")

        return web.json_response({"status": "error", "message": str(e)}, status=500)





async def handle_emotion(request: web.Request) -> web.Response:

    """Muda a expressão/rosto da esfera (happy, sad, angry, spotify, standby)."""

    try:

        body = {}

        if request.can_read_body:

            try:

                body = await request.json()

            except Exception:

                body = {}

        device_id = body.get("device_id", "jarvis_sphere_esp32s3")

        emotion = body.get("emotion", "happy")

        ws = active_sessions.get(device_id)

        if ws is None:

            return web.json_response({"status": "error", "message": "dispositivo sem sessão WS"}, status=404)

        await ws.send_str(json.dumps({"type": "emotion", "emotion": emotion}))

        return web.json_response({"status": "success", "emotion": emotion})

    except Exception as e:

        return web.json_response({"status": "error", "message": str(e)}, status=500)





async def handle_get_firmware(request: web.Request) -> web.StreamResponse:

    if os.path.exists(FIRMWARE_PATH):

        return web.FileResponse(FIRMWARE_PATH)

    return web.json_response({"status": "error", "message": "Firmware binary not found"}, status=404)





async def handle_upload_firmware(request: web.Request) -> web.Response:

    try:

        os.makedirs(os.path.dirname(FIRMWARE_PATH), exist_ok=True)

        data = await request.read()

        if not data:

            return web.json_response({"status": "error", "message": "Empty file data"}, status=400)

        with open(FIRMWARE_PATH, "wb") as f:

            f.write(data)

        return web.json_response({"status": "success", "message": "Firmware uploaded", "bytes": len(data)})

    except Exception as e:

        return web.json_response({"status": "error", "message": str(e)}, status=500)





async def handle_ota_trigger(request: web.Request) -> web.Response:

    try:

        url = f"${ZIMA_ROUTER_URL:-http://127.0.0.1:8095}/firmware.bin"

        if request.can_read_body:

            try:

                body = await request.json()

                url = body.get("url", url)

            except Exception:

                pass

        message_json = {"type": "custom", "payload": {"event": "jarvis.ota_update", "url": url}}

        n = 0

        for device_id, ws in list(active_sessions.items()):

            try:

                await ws.send_str(json.dumps(message_json))

                n += 1

            except Exception as e:

                logging.error(f"[OTA] erro para {device_id}: {e}")

        return web.json_response({"status": "success", "notified": n, "url": url})

    except Exception as e:

        return web.json_response({"status": "error", "message": str(e)}, status=500)






async def handle_timer(request: web.Request) -> web.Response:
    try:
        body = await request.json()
        device_id = body.get("device_id", "jarvis_sphere_esp32s3")
        seconds = int(body.get("seconds", 0))
        label = body.get("label", "TIMER")
        ws = active_sessions.get(device_id)
        if ws is None:
            return web.json_response({"status": "error", "message": "Dispositivo sem sessão WS"}, status=404)
        msg = {"type": "custom", "payload": {"event": "jarvis.timer", "seconds": seconds, "label": label}}
        await ws.send_str(json.dumps(msg))
        return web.json_response({"status": "success", "seconds": seconds, "label": label})
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=500)


async def handle_alarm(request: web.Request) -> web.Response:
    try:
        body = await request.json()
        device_id = body.get("device_id", "jarvis_sphere_esp32s3")
        hour = int(body.get("hour", -1))
        minute = int(body.get("minute", -1))
        label = body.get("label", "ALARME")
        ws = active_sessions.get(device_id)
        if ws is None:
            return web.json_response({"status": "error", "message": "Dispositivo sem sessão WS"}, status=404)
        msg = {"type": "custom", "payload": {"event": "jarvis.alarm", "hour": hour, "minute": minute, "label": label}}
        await ws.send_str(json.dumps(msg))
        return web.json_response({"status": "success", "hour": hour, "minute": minute, "label": label})
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=500)


def create_app() -> web.Application:

    app = web.Application()

    app.router.add_get("/ws", handle_websocket)

    app.router.add_post("/api/jarvis/show_screen", handle_show_screen)

    app.router.add_post("/api/jarvis/emotion", handle_emotion)

    app.router.add_post("/api/jarvis/record", handle_record)

    app.router.add_get("/firmware.bin", handle_get_firmware)

    app.router.add_post("/api/jarvis/firmware/upload", handle_upload_firmware)

    app.router.add_post("/api/jarvis/ota/trigger", handle_ota_trigger)
    app.router.add_post("/api/jarvis/timer", handle_timer)
    app.router.add_post("/api/jarvis/alarm", handle_alarm)

    return app





if __name__ == "__main__":

    logging.info(f"[+] Screen Router + Voice Bridge na porta 8095 | Core={JARVIS_HUD_URL}")

    web.run_app(create_app(), host="0.0.0.0", port=8095)
