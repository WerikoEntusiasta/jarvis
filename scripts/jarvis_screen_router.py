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
import base64

import time

import json

import math

import wave

import asyncio

import logging

import audioop
import secrets

from typing import Dict, Any

from aiohttp import web, ClientSession

MIC_MONITOR_HTML = '<!DOCTYPE html>\n<html lang="pt-BR">\n<head>\n    <meta charset="UTF-8">\n    <meta name="viewport" content="width=device-width, initial-scale=1.0">\n    <title>J.A.R.V.I.S. - Monitor de Áudio & Wake Word</title>\n    <style>\n        * { box-sizing: border-box; margin: 0; padding: 0; font-family: \'Segoe UI\', -apple-system, sans-serif; }\n        body { background: #07090e; color: #e2e8f0; min-height: 100vh; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 20px; overflow-x: hidden; }\n        .container { width: 100%; max-width: 850px; background: #0d121d; border: 1px solid #1a2333; border-radius: 16px; padding: 28px; box-shadow: 0 10px 40px rgba(0,240,255,0.06); }\n        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; border-bottom: 1px solid #1a2436; padding-bottom: 16px; }\n        .title { display: flex; align-items: center; gap: 12px; font-size: 22px; font-weight: 700; color: #00f0ff; letter-spacing: 1px; text-shadow: 0 0 12px rgba(0,240,255,0.4); }\n        .status-badge { display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 600; padding: 6px 14px; border-radius: 20px; background: rgba(0,255,136,0.1); border: 1px solid rgba(0,255,136,0.3); color: #00ff88; }\n        .status-badge.disconnected { background: rgba(255,75,75,0.1); border-color: rgba(255,75,75,0.3); color: #ff4b4b; }\n        .status-dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; box-shadow: 0 0 8px currentColor; }\n        \n        .scope-card { background: #06080d; border: 1px solid #161f30; border-radius: 12px; padding: 16px; margin-bottom: 24px; position: relative; }\n        canvas { width: 100%; height: 180px; display: block; border-radius: 8px; background: #030508; }\n        .scope-overlay { position: absolute; top: 24px; right: 28px; font-family: monospace; font-size: 12px; color: #00f0ff; opacity: 0.8; }\n        \n        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 18px; margin-bottom: 24px; }\n        .card { background: #090e17; border: 1px solid #182235; border-radius: 12px; padding: 18px; display: flex; flex-direction: column; gap: 8px; }\n        .card-label { font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; color: #7e8b9e; }\n        .card-val { font-size: 28px; font-weight: 800; color: #fff; font-family: monospace; }\n        \n        .meter-bar { width: 100%; height: 10px; background: #131b2a; border-radius: 5px; overflow: hidden; margin-top: 6px; position: relative; }\n        .meter-fill { height: 100%; width: 0%; transition: width 0.08s ease; border-radius: 5px; }\n        .meter-fill.rms { background: linear-gradient(90deg, #00f0ff, #00ff88, #ffcc00, #ff3366); }\n        .meter-fill.score { background: linear-gradient(90deg, #3b82f6, #00f0ff, #00ff88); }\n        .threshold-marker { position: absolute; top: 0; bottom: 0; width: 2px; background: #ff3366; box-shadow: 0 0 6px #ff3366; }\n        \n        .wake-banner { display: none; margin-top: 10px; padding: 14px; border-radius: 10px; background: rgba(0,255,136,0.15); border: 1px solid #00ff88; color: #00ff88; text-align: center; font-weight: 700; font-size: 18px; letter-spacing: 1px; animation: pulse 0.5s infinite alternate; }\n        @keyframes pulse { from { box-shadow: 0 0 10px rgba(0,255,136,0.2); } to { box-shadow: 0 0 25px rgba(0,255,136,0.6); } }\n        \n        .instructions { background: rgba(0,240,255,0.04); border: 1px dashed rgba(0,240,255,0.2); border-radius: 10px; padding: 14px 18px; font-size: 13px; line-height: 1.6; color: #94a3b8; }\n        .instructions strong { color: #00f0ff; }\n    </style>\n</head>\n<body>\n    <div class="container">\n        <div class="header">\n            <div class="title">\n                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" x2="12" y1="19" y2="22"/></svg>\n                J.A.R.V.I.S. AUDIO OSCILLOSCOPE\n            </div>\n            <div class="status-badge disconnected" id="connStatus">\n                <span class="status-dot"></span>\n                <span id="connText">Desconectado</span>\n            </div>\n        </div>\n\n        <div class="scope-card">\n            <div class="scope-overlay" id="fpsText">60 FPS | 16 kHz OPUS</div>\n            <canvas id="scopeCanvas" width="800" height="180"></canvas>\n        </div>\n\n        <div class="grid">\n            <div class="card">\n                <div class="card-label">Volume do Microfone (RMS)</div>\n                <div class="card-val" id="rmsVal">0</div>\n                <div class="meter-bar">\n                    <div class="meter-fill rms" id="rmsBar"></div>\n                </div>\n            </div>\n\n            <div class="card">\n                <div class="card-label">Confiança Wake Word ("Hey Jarvis")</div>\n                <div class="card-val" id="scoreVal">0.00 <span style="font-size:14px;color:#7e8b9e;">/ limiar 0.25</span></div>\n                <div class="meter-bar">\n                    <div class="threshold-marker" style="left: 25%;"></div>\n                    <div class="meter-fill score" id="scoreBar"></div>\n                </div>\n            </div>\n        </div>\n\n        <div class="wake-banner" id="wakeBanner">\n            ⚡ PALAVRA-CHAVE DETECTADA! JARVIS ACORDADO ⚡\n        </div>\n\n        <div class="instructions" style="margin-top: 18px;">\n            💡 <strong>Guia de Calibração:</strong> Fale próximo à esfera. Quando estiver em silêncio, a linha ficará <strong>reta</strong> (RMS ~100-200). Ao falar, a onda <strong>oscilará intensamente</strong> (RMS > 500). Se a barra de confiança passar da linha vermelha (0.25), o Jarvis acordará imediatamente!\n        </div>\n    </div>\n\n    <script>\n        const canvas = document.getElementById(\'scopeCanvas\');\n        const ctx = canvas.getContext(\'2d\');\n        const connStatus = document.getElementById(\'connStatus\');\n        const connText = document.getElementById(\'connText\');\n        const rmsVal = document.getElementById(\'rmsVal\');\n        const rmsBar = document.getElementById(\'rmsBar\');\n        const scoreVal = document.getElementById(\'scoreVal\');\n        const scoreBar = document.getElementById(\'scoreBar\');\n        const wakeBanner = document.getElementById(\'wakeBanner\');\n\n        let waveHistory = new Array(80).fill(0);\n        let targetWave = new Array(80).fill(0);\n        let lastRms = 0;\n        let lastScore = 0;\n        let wakeTimer = null;\n\n        function connect() {\n            const wsProtocol = location.protocol === \'https:\' ? \'wss:\' : \'ws:\';\n            const wsUrl = `${wsProtocol}//${location.host}/ws/mic_monitor`;\n            const ws = new WebSocket(wsUrl);\n\n            ws.onopen = () => {\n                connStatus.className = \'status-badge\';\n                connText.innerText = \'Esfera Conectada (Ao Vivo)\';\n            };\n\n            ws.onclose = () => {\n                connStatus.className = \'status-badge disconnected\';\n                connText.innerText = \'Desconectado - Reconectando...\';\n                setTimeout(connect, 2000);\n            };\n\n            ws.onerror = () => ws.close();\n\n            ws.onmessage = (event) => {\n                try {\n                    const data = JSON.parse(event.data);\n                    if (data.type === \'audio_frame\') {\n                        lastRms = data.rms;\n                        lastScore = data.score;\n                        if (data.wave && data.wave.length > 0) {\n                            targetWave = data.wave;\n                        }\n                    } else if (data.type === \'wake_detected\') {\n                        triggerWakeUI();\n                    }\n                } catch(e) {}\n            };\n        }\n\n        function triggerWakeUI() {\n            wakeBanner.style.display = \'block\';\n            clearTimeout(wakeTimer);\n            wakeTimer = setTimeout(() => {\n                wakeBanner.style.display = \'none\';\n            }, 3500);\n        }\n\n        function render() {\n            // Lerp wave\n            for (let i = 0; i < waveHistory.length; i++) {\n                waveHistory[i] += ((targetWave[i] || 0) - waveHistory[i]) * 0.35;\n            }\n\n            // Decay target towards zero if silent\n            for (let i = 0; i < targetWave.length; i++) {\n                targetWave[i] *= 0.92;\n            }\n\n            // Draw scope\n            ctx.fillStyle = \'#030508\';\n            ctx.fillRect(0, 0, canvas.width, canvas.height);\n\n            // Grid lines\n            ctx.strokeStyle = \'#0e1726\';\n            ctx.lineWidth = 1;\n            ctx.beginPath();\n            ctx.moveTo(0, canvas.height / 2);\n            ctx.lineTo(canvas.width, canvas.height / 2);\n            ctx.stroke();\n\n            // Glow line\n            ctx.strokeStyle = \'#00f0ff\';\n            ctx.lineWidth = 2.5;\n            ctx.shadowBlur = 12;\n            ctx.shadowColor = \'#00f0ff\';\n\n            ctx.beginPath();\n            const step = canvas.width / (waveHistory.length - 1);\n            const midY = canvas.height / 2;\n\n            for (let i = 0; i < waveHistory.length; i++) {\n                const x = i * step;\n                const amp = waveHistory[i] * (canvas.height * 0.44);\n                const y = midY + amp;\n                if (i === 0) ctx.moveTo(x, y);\n                else ctx.lineTo(x, y);\n            }\n            ctx.stroke();\n            ctx.shadowBlur = 0;\n\n            // Update Meters\n            rmsVal.innerText = Math.round(lastRms);\n            const rmsPct = Math.min(100, (lastRms / 3000) * 100);\n            rmsBar.style.width = `${rmsPct}%`;\n\n            scoreVal.innerHTML = `${lastScore.toFixed(3)} <span style="font-size:14px;color:#7e8b9e;">/ limiar 0.25</span>`;\n            const scorePct = Math.min(100, (lastScore / 1.0) * 100);\n            scoreBar.style.width = `${scorePct}%`;\n\n            if (lastScore >= 0.25) {\n                triggerWakeUI();\n            }\n\n            requestAnimationFrame(render);\n        }\n\n        connect();\n        requestAnimationFrame(render);\n    </script>\n</body>\n</html>\n'

_monitor_websockets = set()
_last_peak_score = 0.0

async def handle_mic_monitor_page(request: web.Request) -> web.Response:
    return web.Response(text=MIC_MONITOR_HTML, content_type="text/html")

async def handle_mic_monitor_ws(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    _monitor_websockets.add(ws)
    logging.info("[MONITOR] Novo cliente Web conectado ao osciloscópio")
    try:
        async for msg in ws:
            pass
    finally:
        _monitor_websockets.discard(ws)
    return ws

def _broadcast_mic_wave(rms: float, score: float, pcm_data: bytes, device_id: str):
    if not _monitor_websockets:
        return
    # Downsample pcm_data (16-bit mono 16kHz) to 80 points normalized -1.0 to 1.0
    wave = []
    if len(pcm_data) >= 160:
        step = len(pcm_data) // 160 # 80 samples
        for i in range(0, 80):
            idx = (i * step * 2)
            if idx + 1 < len(pcm_data):
                val = int.from_bytes(pcm_data[idx:idx+2], byteorder='little', signed=True)
                wave.append(round(val / 32768.0, 3))
    payload = json.dumps({
        "type": "audio_frame",
        "rms": round(rms, 1),
        "score": round(score, 3),
        "wave": wave,
        "device_id": device_id
    })
    for client in list(_monitor_websockets):
        try:
            asyncio.create_task(client.send_str(payload))
        except Exception:
            _monitor_websockets.discard(client)


try:
    import opuslib
except ImportError:
    opuslib = None

_router_opus_decoders: Dict[str, Any] = {}

def _router_decode_opus(device_id: str, data: bytes) -> bytes:
    if not opuslib:
        return data
    try:
        dec = _router_opus_decoders.setdefault(device_id, opuslib.Decoder(SAMPLE_RATE, 1))
        if data.startswith(b"OPUS"):
            raw_opus = data[4:]
            try:
                samples = opuslib.api.decoder.get_nb_samples(dec.decoder_state, raw_opus, len(raw_opus))
                if samples <= 0:
                    samples = 960
            except Exception:
                samples = 960
            pcm = dec.decode(raw_opus, samples)
            return pcm
        elif len(data) < 250 and len(data) > 0:
            try:
                samples = opuslib.api.decoder.get_nb_samples(dec.decoder_state, data, len(data))
                if samples <= 0:
                    samples = 960
                pcm = dec.decode(data, samples)
                return pcm
            except Exception:
                return data
    except Exception as e:
        logging.error(f"[OPUS-DEC] Erro decodificando frame Opus ({len(data)}b): {e}")
        return b""
    return data

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")



FIRMWARE_PATH = os.environ.get("FIRMWARE_PATH", "/app/firmware.bin")

OPENCLAW_A2A_URL = os.environ.get('OPENCLAW_A2A_URL', 'https://172.17.0.3:18789/a2a/v1')
OPENCLAW_A2A_TOKEN = os.environ.get('OPENCLAW_A2A_TOKEN', 'esfera_sec_jarvis_991823')
MODEL_FAILURE_SENTINEL = '__MODEL_FAILURE__'

JARVIS_HUD_URL = os.environ.get("JARVIS_HUD_URL", "http://172.17.0.1:8085").rstrip("/")



SAMPLE_RATE = 16000

BYTES_PER_SEC = SAMPLE_RATE * 2  # s16le mono

VAD_RMS = int(os.environ.get("VAD_RMS", "400"))

SILENCE_SEC = float(os.environ.get("VAD_SILENCE_SEC", "2.0"))

MIN_UTTERANCE_SEC = 0.1

MAX_UTTERANCE_SEC = 15.0

PREROLL_SEC = 0.3



# Wake word "Jarvis" + janela de follow-up (permite turnos seguidos sem repetir "Jarvis")

WAKE_WORDS = ("jarvis", "jervis", "javis", "jarves", "jarviz", "jardim", "jardis")

FOLLOWUP_SEC = float(os.environ.get("WAKE_FOLLOWUP_SEC", "20.0"))

wake_state: Dict[str, float] = {}

processing_state: Dict[str, bool] = {}
followup_tasks: Dict[str, asyncio.Task] = {}

recording_state: Dict[str, Dict[str, Any]] = {}



# ---------------- WAKE WORD LOCAL (openWakeWord "hey_jarvis") ----------------

# Limiar balanceado (0.55) para reconhecimento fluido e sem falsos positivos.
OWW_THRESHOLD = float(os.environ.get("OWW_THRESHOLD", "0.25"))

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





_last_ww_time: Dict[str, float] = {}

async def _ww_wake(ws: web.WebSocketResponse, device_id: str):
    """Ao detectar 'Jarvis', mantém o visor no estado de escuta com debounce estrito."""
    now = time.time()
    if now - _last_ww_time.get(device_id, 0.0) < 3.5:
        return
    _last_ww_time[device_id] = now
    wake_state[device_id] = now
    logging.info(f"[WW] Wake acionado com debounce para {device_id}")

# st["buf"] mantido para não truncar comando contínuo

    try:
        await ws.send_str(json.dumps({"type": "wakeup"}))
        _start_followup_timeout(ws, device_id)
    except Exception as e:
        logging.warning(f"[WW] Erro ao enviar wakeup: {e}")


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

        if len(data) % 2 != 0:
            data = data[:len(data) - 1]
        if len(data) > 0:
            buf = _np.concatenate([buf, _np.frombuffer(data, dtype=_np.int16)])

        fired = False

        peak = 0.0
        global _last_peak_score
        global _last_peak_score

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
            _r = float(audioop.rms(data, 2))
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






def _clean_hallucinations(txt: str) -> str:
    txt = txt.strip()
    if not txt:
        return ""
    lower = txt.lower()
    for bad in ["o que é", "o que e", "que é", "que e", "subtitles", "legenda", "obrigado por assistir"]:
        if lower.count(bad) >= 3:
            logging.warning(f"[STT] Alucinacao repetitiva descartada: {txt[:50]}...")
            return ""
    words = txt.split()
    if len(words) >= 4:
        for n in [1, 2, 3, 4]:
            pat = " ".join(words[:n])
            count = lower.count(pat.lower())
            if count >= 3 and len(words) <= (n * count) + 4:
                logging.warning(f"[STT] Loop de repeticao descartado ({pat}): {txt[:50]}...")
                return ""
    return txt

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "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")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyB6LnHIEGJrHmLAey7vXnIZ0XZ7NDkrvpI")
STT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

async def _transcribe_groq(session: ClientSession, wav_bytes: bytes) -> str:
    """Tier 1: Cloud Groq Whisper-large-v3-turbo (ultrarrápido, ~250ms, altíssima precisão em PT-BR)"""
    try:
        boundary = f"----groq{int(time.time()*1000)}"
        nl = b"\r\n"
        parts = [
            b"--" + boundary.encode() + nl + b'Content-Disposition: form-data; name="model"' + nl + nl + b"whisper-large-v3-turbo" + nl,
            b"--" + boundary.encode() + nl + b'Content-Disposition: form-data; name="language"' + nl + nl + b"pt" + nl,
            b"--" + boundary.encode() + nl + b'Content-Disposition: form-data; name="temperature"' + nl + nl + b"0.0" + nl,
            b"--" + boundary.encode() + nl + b'Content-Disposition: form-data; name="prompt"' + nl + nl + b"J.A.R.V.I.S., assistente Jarvis, clima, horas, previsao do tempo, Catanduva, Spotify." + nl,
            b"--" + boundary.encode() + nl + b'Content-Disposition: form-data; name="file"; filename="audio.wav"' + nl + b"Content-Type: audio/wav" + nl + nl,
            wav_bytes,
            nl + b"--" + boundary.encode() + b"--" + nl
        ]
        body = b"".join(parts)
        headers = {
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "User-Agent": STT_USER_AGENT
        }
        t0 = time.time()
        async with session.post("https://api.groq.com/openai/v1/audio/transcriptions",
                                data=body, headers=headers, timeout=8) as r:
            if r.status == 200:
                j = await r.json(content_type=None)
                txt = (j.get("text") or "").strip()
                txt = _clean_hallucinations(txt)
                if txt:
                    logging.info(f"[STT-Tier1:Groq] ({time.time()-t0:.2f}s) Transcrito com sucesso: {txt!r}")
                    return txt
            else:
                err = await r.text()
                logging.warning(f"[STT-Tier1:Groq] HTTP {r.status}: {err[:150]}")
    except Exception as e:
        logging.warning(f"[STT-Tier1:Groq] Falha ou timeout: {e}")
    return ""

async def _transcribe_gemini(session: ClientSession, wav_bytes: bytes) -> str:
    """Tier 2: Google Gemini 2.5 Flash Audio (compreensão contextual fonética em PT-BR)"""
    try:
        t0 = time.time()
        audio_b64 = base64.b64encode(wav_bytes).decode("utf-8")
        data = {
            "contents": [{
                "parts": [
                    {"text": "Transcreva este áudio em português brasileiro com precisão máxima. Retorne estritamente o texto falado, sem introdução ou explicações adicionais. Se for apenas ruído ou silêncio, retorne vazio."},
                    {"inline_data": {"mime_type": "audio/wav", "data": audio_b64}}
                ]
            }],
            "generationConfig": {"temperature": 0.0}
        }
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
        headers = {
            "Content-Type": "application/json",
            "User-Agent": STT_USER_AGENT
        }
        async with session.post(url, json=data, headers=headers, timeout=10) as r:
            if r.status == 200:
                j = await r.json(content_type=None)
                candidates = j.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        txt = parts[0].get("text", "").strip()
                        txt = _clean_hallucinations(txt)
                        if txt:
                            logging.info(f"[STT-Tier2:Gemini] ({time.time()-t0:.2f}s) Transcrito com sucesso: {txt!r}")
                            return txt
            else:
                err = await r.text()
                logging.warning(f"[STT-Tier2:Gemini] HTTP {r.status}: {err[:150]}")
    except Exception as e:
        logging.warning(f"[STT-Tier2:Gemini] Falha ou timeout: {e}")
    return ""

async def _transcribe_local_whisper(session: ClientSession, wav_bytes: bytes) -> str:
    """Tier 3: Whisper Local no ZimaOS (fallback de contingência se a internet cair)"""
    try:
        t0 = time.time()
        boundary = f"----localwhisper{int(time.time()*1000)}"
        nl = bytes([13, 10])
        parts = [
            b"--" + boundary.encode() + nl + b'Content-Disposition: form-data; name="model"' + nl + nl + b"Systran/faster-whisper-tiny" + nl,
            b"--" + boundary.encode() + nl + b'Content-Disposition: form-data; name="language"' + nl + nl + b"pt" + nl,
            b"--" + boundary.encode() + nl + b'Content-Disposition: form-data; name="file"; filename="audio.wav"' + nl + b"Content-Type: audio/wav" + nl + nl,
            wav_bytes,
            nl + b"--" + boundary.encode() + b"--" + nl
        ]
        body = b"".join(parts)
        headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
        async with session.post("http://172.17.0.2:8000/v1/audio/transcriptions", data=body, headers=headers, timeout=25) as r:
            if r.status == 200:
                j = await r.json(content_type=None)
                txt = (j.get("text") or "").strip()
                txt = _clean_hallucinations(txt)
                logging.info(f"[STT-Tier3:LocalWhisper] ({time.time()-t0:.2f}s) Transcrito pelo Whisper local: {txt!r}")
                return txt
            else:
                logging.warning(f"[STT-Tier3:LocalWhisper] status={r.status}")
    except Exception as e:
        logging.warning(f"[STT-Tier3:LocalWhisper] Falha no Whisper local: {e}")

    try:
        async with session.post(f"{JARVIS_HUD_URL}/api/transcribe", data=wav_bytes,
                                headers={"Content-Type": "audio/wav"}, timeout=25) as r:
            j = await r.json(content_type=None)
            return (j.get("text") or "").strip()
    except Exception:
        return ""

async def _transcribe(session: ClientSession, wav_bytes: bytes) -> str:
    """Cascata Multi-Tier STT: Tier 1 (Groq) -> Tier 2 (Gemini) -> Tier 3 (Whisper Local)"""
    # Tier 1: Groq Whisper-large-v3-turbo
    res = await _transcribe_groq(session, wav_bytes)
    if res:
        return res

    # Tier 2: Google Gemini 2.5 Flash Audio
    logging.info("[STT] Groq indisponivel, acionando Tier 2: Gemini Audio...")
    res = await _transcribe_gemini(session, wav_bytes)
    if res:
        return res

    # Tier 3: Local Whisper Fallback
    logging.warning("[STT] APIs externas indisponiveis, acionando Tier 3: Whisper Local de Contingencia...")
    return await _transcribe_local_whisper(session, wav_bytes)

async def _fetch_ze_delivery_order(session: ClientSession):
    url = "https://api.ze.delivery/public-api"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/json",
        "Origin": "https://www.ze.delivery",
        "Referer": "https://www.ze.delivery/",
        "x-accesstoken": ZE_TOKEN,
        "Authorization": f"Bearer {ZE_TOKEN}",
        "x-visitorid": ZE_VISITOR_ID,
        "Cookie": ZE_COOKIE
    }
    payload = {"query": "query ListOrders { listOrders { id number createdDate totalPrice statusesHistory { status createdDate } lineItems { id displayName } } }"}
    try:
        async with session.post(url, headers=headers, json=payload, timeout=12) as r:
            if r.status == 200:
                data = await r.json(content_type=None)
                orders = data.get("data", {}).get("listOrders", [])
                if orders:
                    return orders[0]
    except Exception as e:
        logging.warning(f"[ZE] Erro ao consultar API: {e}")
    return None

async def _refresh_ze_delivery(ws: web.WebSocketResponse):
    try:
        async with ClientSession() as session:
            order = await _fetch_ze_delivery_order(session)
            if order:
                history = order.get("statusesHistory", [])
                raw_status = history[-1]["status"] if history else "UNKNOWN"
                label, sub = STATUS_MAP.get(raw_status, (raw_status, ""))
                order_num = str(order.get("number", "---"))
                total = float(order.get("totalPrice", 0.0))
                items = order.get("lineItems", [])
                item_names = [it.get("displayName", "") for it in items[:2]]
                items_str = ", ".join(item_names)
                if len(items_str) > 28:
                    items_str = items_str[:25] + "..."
                
                payload = {
                    "type": "custom",
                    "event": "jarvis.ze_update",
                    "number": order_num,
                    "status": label,
                    "items": items_str,
                    "total": total,
                    "updated_at": time.strftime("%H:%M"),
                    "show": True
                }
                await ws.send_str(json.dumps(payload))
                logging.info(f"[ZE] Pedido #{order_num} ({label}) enviado para a Esfera.")
    except Exception as e:
        logging.error(f"[ZE] Falha ao atualizar Ze Delivery: {e}")


async def _chat(session: ClientSession, text: str, device_id: str = "") -> str:
    """Envia a mensagem de voz diretamente para o agente J.A.R.V.I.S. no OpenClaw via A2A."""
    headers = {
        "Authorization": f"Bearer {OPENCLAW_A2A_TOKEN}",
        "Content-Type": "application/json",
        "X-Forwarded-For": "127.0.0.1"
    }
    payload = {
        "jsonrpc": "2.0",
        "id": f"esfera-turn-{int(time.time()*1000)}",
        "method": "SendMessage",
        "params": {
            "to": "jarvis",
            "contextId": "esfera-main",
            "threadId": "esfera-main",
            "sessionKey": "agent:jarvis:a2a:default:direct:esfera:ctx-esfera-main",
            "message": {
                "contextId": "esfera-main",
                "messageId": f"msg-{int(time.time()*1000)}",
                "role": "ROLE_USER",
                "parts": [{"text": text}]
            }
        }
    }
    try:
        logging.info(f"[A2A] Despachando turno de voz para OpenClaw (Jarvis): '{text[:60]}'...")
        async with session.post(OPENCLAW_A2A_URL, headers=headers, json=payload, ssl=False, timeout=120) as r:
            if r.status != 200:
                logging.error(f"[A2A] Erro HTTP {r.status} do OpenClaw")
                return MODEL_FAILURE_SENTINEL
            data = await r.json(content_type=None)
            res = data.get("result", {})
            task = res.get("task", {})
            artifacts = task.get("artifacts", [])
            if artifacts:
                parts = artifacts[0].get("parts", [])
                if parts:
                    txt = (parts[0].get("text") or "").strip()
                    if txt:
                        return txt
            for h in reversed(task.get("history", [])):
                if str(h.get("role", "")).lower() in ("model", "assistant", "role_assistant"):
                    parts = h.get("parts", [])
                    if parts:
                        txt = (parts[0].get("text") or "").strip()
                        if txt:
                            return txt
            return MODEL_FAILURE_SENTINEL
    except Exception as e:
        logging.error(f"[A2A] Falha na comunicacao com OpenClaw: {e}")
        return MODEL_FAILURE_SENTINEL





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
    if not pcm or len(pcm) < 3200:
        processing_state[device_id] = False
        return
    try:
        await ws.send_str(json.dumps({"type": "emotion", "emotion": "thinking"}))
    except Exception:
        pass

    logging.info(f"[VOZ] Utterance {len(pcm)} bytes ({len(pcm)/BYTES_PER_SEC:.1f}s) de {device_id} -> transcrevendo...")

    pcm_f = _highpass_pcm(pcm, cutoff=120.0)  # Filtro passa-altas 120Hz: remove hum elétrico de 60Hz e ruído de coolers

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
            text = _clean_hallucinations(text)
            if not text or len(text) < 2:
                logging.info(f"[VOZ] {device_id}: Transcricao vazia ou alucinada ignorada.")
                await ws.send_str(json.dumps({"type": "emotion", "emotion": "standby"}))
                return

            is_awake = (now - wake_state.get(device_id, 0.0) <= FOLLOWUP_SEC)
            has_wake = _has_wake_word(text)

            # Gate de Wake Word: se a esfera esta em repouso e nao falou "Jarvis", descarta silenciosamente!
            if not has_wake and not is_awake:
                logging.info(f"[VOZ] {device_id}: Ignorado (repouso sem 'Jarvis': {text!r}).")
                await ws.send_str(json.dumps({"type": "emotion", "emotion": "standby"}))
                return

            if has_wake:
                wake_state[device_id] = now
                text = _strip_wake_word(text)
                if not text:
                    logging.info(f"[VOZ] {device_id}: Chamou apenas 'Jarvis'. Ativando modo escuta.")
                    await ws.send_str(json.dumps({"type": "wakeup"}))
                    await ws.send_str(json.dumps({"type": "emotion", "emotion": "listening"}))
                    _start_followup_timeout(ws, device_id)
                    return
            else:
                wake_state[device_id] = now

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

                chunk_size = 2048
                for i in range(0, len(pcm_out), chunk_size):
                    await ws.send_bytes(pcm_out[i:i + chunk_size])
                    await asyncio.sleep(0.025)

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

            # Retorno imediato ao Standby (sem loop fantasma de escuta)
            wake_state.pop(device_id, None)
            followup_task = followup_tasks.pop(device_id, None)
            if followup_task and followup_task is not asyncio.current_task():
                followup_task.cancel()
            await ws.send_str(json.dumps({"type": "emotion", "emotion": "standby"}))
            logging.info(f"[VOZ] {device_id}: Resposta concluida -> Esfera em Standby.")

    except Exception as e:

        logging.error(f"[VOZ] Erro no pipeline: {type(e).__name__}: {repr(e)}")

    finally:

        processing_state[device_id] = False





def handle_binary(ws: web.WebSocketResponse, device_id: str, data: bytes):
    data = _router_decode_opus(device_id, data)
    if not data:
        return
    if len(data) % 2 != 0:
        data = data[:len(data) - 1]
    if len(data) == 0:
        return
    # Modo gravação manual (contagem regressiva na tela): acumula TODO o PCM, ignora o VAD

    rec = recording_state.get(device_id)

    if rec and time.time() < rec["until"]:

        rec["buf"].extend(data)

        return

    _oww_feed(device_id, data, ws)

    st = audio_state.setdefault(device_id, {"buf": bytearray(), "speaking": False, "silence_start": 0.0})

    try:

        rms = audioop.rms(data, 2)
        _broadcast_mic_wave(rms, _last_peak_score, data, device_id)
        _broadcast_mic_wave(rms, _last_peak_score, data, device_id)

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



    active_vad = 350 if (time.time() - wake_state.get(device_id, 0.0) <= FOLLOWUP_SEC) else VAD_RMS
    if rms >= active_vad:
        if time.time() - wake_state.get(device_id, 0.0) <= FOLLOWUP_SEC:
            wake_state[device_id] = now
        st["speaking"] = True
        st["silence_start"] = 0.0
        st["buf"].extend(data)
    elif st["speaking"]:
        st["buf"].extend(data)
        if st["silence_start"] == 0.0:
            st["silence_start"] = now
    else:
        st["buf"].extend(data)
        keep = int(0.8 * BYTES_PER_SEC)
        if len(st["buf"]) > keep:
            st["buf"] = st["buf"][-keep:]

    is_silence_cut = st["speaking"] and st["silence_start"] > 0 and (now - st["silence_start"]) >= SILENCE_SEC
    is_max_cut = st["speaking"] and len(st["buf"]) >= int(MAX_UTTERANCE_SEC * BYTES_PER_SEC)

    if is_silence_cut or is_max_cut:
        pcm = bytes(st["buf"])
        st["buf"] = bytearray()
        st["speaking"] = False
        st["silence_start"] = 0.0
        if is_max_cut:
            logging.info(f"[VOZ] {device_id}: Corte forcado por tempo maximo ({MAX_UTTERANCE_SEC}s).")
        if not processing_state.get(device_id) and len(pcm) >= 3200:
            logging.info(f"[VOZ] {device_id}: Fala finalizada por silencio ({len(pcm)}b) -> Whisper STT!")
            processing_state[device_id] = True
            asyncio.create_task(process_utterance(ws, device_id, pcm))
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
                    await ws.send_str(json.dumps({
                        "type": "hello",
                        "transport": "websocket",
                        "audio_params": {"format": "opus", "sample_rate": SAMPLE_RATE, "channels": 1, "frame_duration": 60}
                    }))

                elif msg_type == "voice_start":
                    now = time.time()
                    wake_state[device_id] = now
                    st = audio_state.get(device_id)
                    if st:
                        st["speaking"] = True
                        st["silence_start"] = 0.0
                        st["buf"] = bytearray()
                    logging.info(f"[VOZ] {device_id}: voice_start recebido (Wake Word detectada localmente no ESP32).")

                elif msg_type == "voice_end":
                    now = time.time()
                    wake_state[device_id] = now
                    st = audio_state.get(device_id)
                    buf_len = len(st.get("buf", [])) if st else 0
                    logging.info(f"[VOZ] {device_id}: voice_end recebido! buf={buf_len}b")
                    if st and buf_len >= 3200:
                        pcm = bytes(st["buf"])
                        st["buf"] = bytearray()
                        st["speaking"] = False
                        st["silence_start"] = 0.0
                        if not processing_state.get(device_id):
                            logging.info(f"[VOZ] {device_id}: Fim de fala imediato da esfera ({len(pcm)}b) -> enviando direto para STT Cascata!")
                            processing_state[device_id] = True
                            asyncio.create_task(process_utterance(ws, device_id, pcm))
                        else:
                            logging.info(f"[VOZ] {device_id}: voice_end ignorado (ocupado processando).")





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

                    elif event == "ze_refresh":
                        logging.info(f"[WS] Pedido de atualizacao Ze Delivery recebido da esfera ({device_id}).")
                        asyncio.create_task(_refresh_ze_delivery(ws))
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
        host = request.headers.get('Host', '45.167.187.80:8095')
        if 'localhost' in host or '127.0.0.1' in host:
            host = '45.167.187.80:8095'
        url = os.environ.get('ZIMA_ROUTER_URL', f'http://{host}/firmware.bin')
        try:
            body = await request.json()
            if 'url' in body and body['url']:
                url = body['url']
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
    app.router.add_get("/mic_monitor", handle_mic_monitor_page)
    app.router.add_get("/ws/mic_monitor", handle_mic_monitor_ws)

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