
_LATEST_ELECTION_DATA = {
    "apurado": "0,25%",
    "hora": "17:06:27",
    "c1": {"num": "13", "nome": "LULA", "pct": "57,66%", "votos": "193.574"},
    "c2": {"num": "22", "nome": "FLAVIO BOLSONARO", "pct": "42,34%", "votos": "142.169"},
    "timestamp": 0
}

async def fetch_tse_election_data():
    global _LATEST_ELECTION_DATA
    url = "https://resultados.tse.jus.br/oficial/ele2026/6258/dados/br/br-c0001-e006258-u.json"
    try:
        async with ClientSession() as session:
            async with session.get(url, timeout=7, ssl=False, headers={"User-Agent": "Mozilla/5.0"}) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    secoes_pct = str(data.get("s", {}).get("pst", "0")) + "%"
                    hora_tse = str(data.get("ht", ""))
                    cands = []
                    for agr in data.get("carg", [{}])[0].get("agr", []):
                        for par in agr.get("par", []):
                            for c in par.get("cand", []):
                                cands.append({
                                    "num": str(c.get("n", "")),
                                    "nome": str(c.get("nmu") or c.get("nm") or ""),
                                    "pct": str(c.get("pvap", "0")) + "%",
                                    "votos": f"{int(c.get('vap', 0)):,}".replace(",", ".")
                                })
                    cands.sort(key=lambda x: float(x["pct"].replace("%", "").replace(",", ".")), reverse=True)
                    c1 = cands[0] if len(cands) > 0 else {"num": "13", "nome": "LULA", "pct": "0%", "votos": "0"}
                    c2 = cands[1] if len(cands) > 1 else {"num": "22", "nome": "FLAVIO BOLSONARO", "pct": "0%", "votos": "0"}
                    _LATEST_ELECTION_DATA = {
                        "apurado": secoes_pct,
                        "hora": hora_tse,
                        "c1": c1,
                        "c2": c2,
                        "timestamp": time.time()
                    }
                    logging.info(f"[ELECTION-TSE] Apurado={secoes_pct} | 1o: {c1['nome']} ({c1['pct']}) | 2o: {c2['nome']} ({c2['pct']})")
                    return _LATEST_ELECTION_DATA
    except Exception as e:
        logging.warning(f"[ELECTION-TSE] Falha ao consultar TSE: {e}")
    return _LATEST_ELECTION_DATA

async def _election_poller_loop(app):
    async def _poller():
        logging.info("[ELECTION-POLLER] Background poller da Apuracao TSE 2026 ATIVO (20s)!")
        while True:
            try:
                data = await fetch_tse_election_data()
                if data and active_sessions:
                    msg = {
                        "type": "custom",
                        "payload": {
                            "event": "jarvis.election",
                            "apurado": data["apurado"],
                            "hora": data["hora"],
                            "c1": data["c1"],
                            "c2": data["c2"],
                            "show": False
                        }
                    }
                    msg_str = json.dumps(msg)
                    for ws in list(active_sessions.values()):
                        if not ws.closed:
                            try:
                                await ws.send_str(msg_str)
                            except Exception:
                                pass
            except Exception as e:
                logging.warning(f"[ELECTION-POLLER] Erro: {e}")
            await asyncio.sleep(20)
    asyncio.create_task(_poller())

"""

J.A.R.V.I.S. Screen Router + Voice Bridge (porta 8095)

Responsabilidades:

1. WebSocket /ws para a Esfera ESP32-S3 (tela, emoção, toque, OTA).

2. VOZ (novo): recebe PCM 16 kHz mono do microfone (frames binários), faz VAD,

   transcreve (Whisper no Core), consulta o cérebro (/api/chat) e devolve o áudio

   TTS em PCM 16 kHz (frames binários) + eventos de emoção para a esfera falar.

"""



import os
import re

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
    import ctypes
    import ctypes.util
    if not ctypes.util.find_library('opus'):
        # Fallback explicito para Debian slim onde ldconfig nao esta no PATH
        _orig_find_lib = ctypes.util.find_library
        def _patched_find_lib(name):
            if name == 'opus':
                for p in ('/usr/lib/x86_64-linux-gnu/libopus.so.0', '/usr/lib/x86_64-linux-gnu/libopus.so', 'libopus.so.0'):
                    if os.path.exists(p):
                        return p
            return _orig_find_lib(name)
        ctypes.util.find_library = _patched_find_lib
    import opuslib
except Exception as _e_opus:
    logging.error(f"[OPUS-INIT] Falha ao carregar opuslib: {_e_opus}")
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

import sys
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", stream=sys.stdout, force=True)



FIRMWARE_PATH = os.environ.get("FIRMWARE_PATH", "/app/firmware.bin")

OPENCLAW_A2A_URL = os.environ.get('OPENCLAW_A2A_URL', 'https://172.17.0.3:18789/a2a/v1')
OPENCLAW_A2A_TOKEN = os.environ.get('OPENCLAW_A2A_TOKEN', 'esfera_sec_jarvis_991823')
MODEL_FAILURE_SENTINEL = '__MODEL_FAILURE__'

JARVIS_HUD_URL = os.environ.get("JARVIS_HUD_URL", "http://127.0.0.1:8085").rstrip("/")



SAMPLE_RATE = 16000

BYTES_PER_SEC = SAMPLE_RATE * 2  # s16le mono

VAD_RMS = int(os.environ.get("VAD_RMS", "2200"))

SILENCE_SEC = float(os.environ.get("VAD_SILENCE_SEC", "1.4"))

MIN_UTTERANCE_SEC = 0.1

MAX_UTTERANCE_SEC = 15.0

PREROLL_SEC = 0.3



# Wake word "Jarvis" + janela de follow-up (permite turnos seguidos sem repetir "Jarvis")

WAKE_WORDS = ("jarvis", "jervis", "javis", "jarves", "jarviz", "jardis", "joves", "javes", "jovis", "jairz", "charvis", "iarvis", "yarvis", "darvis", "jarvi", "jarve", "hey jarvis", "ei jarvis", "oi jarvis", "j.a.r.v.i.s.")

FOLLOWUP_SEC = float(os.environ.get("WAKE_FOLLOWUP_SEC", "25.0"))

wake_state: Dict[str, float] = {}

processing_state: Dict[str, bool] = {}
stop_tts_requested: Dict[str, bool] = {}
followup_tasks: Dict[str, asyncio.Task] = {}
active_utterance_tasks: Dict[str, asyncio.Task] = {}

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
        await ws.send_str(json.dumps({"type": "emotion", "emotion": "listening"}))
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

        # Normalizacao dinamica de pico (AGC suave ate 8x para fala distante na esfera)
        peak = max((abs(x) for x in out), default=0)
        if 120 < peak < 18000:
            gain = min(8.0, 18000.0 / float(peak))
            for i in range(len(out)):
                v = int(out[i] * gain)
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
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "sk_5417d8a892b2d9820a194d9175bcc7f82439915b66b04b1c")
ELEVENLABS_FALLBACK_KEY = os.environ.get("ELEVENLABS_FALLBACK_KEY", "sk_a80d73f6ae00f6cf4c2305047c9e0b50935cdaca1e5ae187")

async def _transcribe_elevenlabs_scribe(session: ClientSession, wav_bytes: bytes) -> str:
    """Tier 1: ElevenLabs Scribe STT (scribe_v1) - Alta precisao e compreensao contextual em PT-BR"""
    keys_to_try = [k for k in [ELEVENLABS_API_KEY, ELEVENLABS_FALLBACK_KEY] if k]
    boundary = f"----elevenstt{int(time.time()*1000)}"
    nl = b"\r\n"
    parts = [
        b"--" + boundary.encode() + nl + b'Content-Disposition: form-data; name="model_id"' + nl + nl + b"scribe_v1" + nl,
        b"--" + boundary.encode() + nl + b'Content-Disposition: form-data; name="language_code"' + nl + nl + b"por" + nl,
        b"--" + boundary.encode() + nl + b'Content-Disposition: form-data; name="tag_audio_events"' + nl + nl + b"false" + nl,
        b"--" + boundary.encode() + nl + b'Content-Disposition: form-data; name="file"; filename="audio.wav"' + nl + b"Content-Type: audio/wav" + nl + nl,
        wav_bytes,
        nl + b"--" + boundary.encode() + b"--" + nl
    ]
    body = b"".join(parts)

    for idx, key in enumerate(keys_to_try):
        try:
            t0 = time.time()
            headers = {
                "xi-api-key": key,
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": STT_USER_AGENT
            }
            async with session.post("https://api.elevenlabs.io/v1/speech-to-text",
                                    data=body, headers=headers, timeout=10) as r:
                if r.status == 200:
                    j = await r.json(content_type=None)
                    txt = (j.get("text") or "").strip()
                    txt = re.sub(r'\[.*?\]|\(.*?\)', '', txt).strip()
                    txt = _clean_hallucinations(txt)
                    if txt:
                        logging.info(f"[STT-Tier1:ElevenLabsScribe] ({time.time()-t0:.2f}s) Transcrito com sucesso: {txt!r}")
                        return txt
                    else:
                        logging.info(f"[STT-Tier1:ElevenLabsScribe] Transcricao vazia ou apenas ruido descartada.")
                else:
                    err = await r.text()
                    logging.warning(f"[STT-Tier1:ElevenLabsScribe] HTTP {r.status} (key {idx+1}): {err[:150]}")
        except Exception as e:
            logging.warning(f"[STT-Tier1:ElevenLabsScribe] Falha ou timeout (key {idx+1}): {e}")
    return ""
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
    """Cascata Multi-Tier STT: Tier 1 (Groq Whisper-large-v3-turbo) -> Tier 2 (Gemini) -> Tier 3 (Whisper Local)"""
    # Tier 1: Groq Whisper-large-v3-turbo (~0.35s)
    res = await _transcribe_groq(session, wav_bytes)
    if res:
        return res

    # Tier 3: Google Gemini 2.5 Flash Audio
    logging.info("[STT] Groq indisponivel, acionando Tier 3: Gemini Audio...")
    res = await _transcribe_gemini(session, wav_bytes)
    if res:
        return res

    # Tier 4: Local Whisper Fallback
    logging.warning("[STT] APIs externas indisponiveis, acionando Tier 4: Whisper Local de Contingencia...")
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
    """Envia a mensagem de voz diretamente para o Núcleo J.A.R.V.I.S. (core_ai_brain com SOUL.md)."""
    try:
        payload = {
            "message": text,
            "device_id": device_id,
            "source": "esfera"
        }
        logging.info(f"[Chat] Despachando turno de voz para Núcleo JARVIS ({JARVIS_HUD_URL}): '{text[:60]}'...")
        async with session.post(f"{JARVIS_HUD_URL}/api/chat", json=payload, timeout=45) as r:
            if r.status == 200:
                data = await r.json(content_type=None)
                reply = data.get("reply") or data.get("response") or ""
                if reply:
                    return reply.strip()
            else:
                err_txt = await r.text()
                logging.error(f"[Chat] Erro HTTP {r.status} do Núcleo: {err_txt[:120]}")
    except Exception as e:
        logging.error(f"[Chat] Falha na comunicação com Núcleo JARVIS: {e}")
    return MODEL_FAILURE_SENTINEL





async def _tts_pcm(session: ClientSession, text: str) -> bytes:

    async with session.post(f"{JARVIS_HUD_URL}/api/tts_pcm", json={"text": text}, timeout=45) as r:

        if r.status == 200:

            return await r.read()

    return b""





def _has_wake_word(text: str) -> bool:
    if not text:
        return False
    t = text.lower()
    t_clean = re.sub(r'[\.\-\_]', '', t)
    words = "".join(ch if ch.isalnum() else " " for ch in t_clean).split()
    return any(w in words or w in t_clean or w in t for w in WAKE_WORDS)





def clean_utterance(text: str) -> str:
    """Normaliza variantes fonéticas de JARVIS e remove repetições de frases causadas por eco de microfone."""
    if not text:
        return ""
    # 1. Normaliza qualquer variação de JARVIS com ou sem pontos (ex: J.A.R.V., J.A.R.V.I.S., JARVIS)
    t = re.sub(r'(?i)\b(?:hey\s+|ei\s+|oi\s+)?j\s*\.?\s*a\s*\.?\s*r\s*\.?\s*v\s*\.?(?:\s*i\s*\.?\s*s\s*\.?)?\b', 'Jarvis', text)
    # 2. Se a frase inteira foi repetida pelo STT (ex: 'Jarvis, abra... Jarvis, abra...')
    m = re.match(r'^(.+?)[.!?\s,]+\1[.!?\s,]*$', t, re.IGNORECASE)
    if m:
        t = m.group(1)
    else:
        chunks = re.split(r'(?i)(?:\.\s*|\b)Jarvis\b[,:\s]*', t)
        chunks = [c.strip(' ,.!') for c in chunks if c.strip(' ,.!')]
        if chunks and len(chunks) >= 2 and chunks[0].lower() == chunks[1].lower():
            t = chunks[0]
    # 3. Remove Jarvis do início
    t = re.sub(r'(?i)^\s*(?:hey[\s,.:]+|ei[\s,.:]+|oi[\s,.:]+|o[\s,.:]+|ô[\s,.:]+|p\.?[\s,.:]+)?(?:jarvis|jervis|javis|jarves|jarviz|jardis|jarve|jarvi|joves|javes|jovis|jairz|charvis|iarvis|yarvis|darvis)\b[,.:;!?-]*\s*', '', t)
    return t.strip(' ,.!?;:-—\t\n')


def _strip_wake_word(text: str) -> str:
    if not text:
        return ""
    # Corta qualquer fala/ruido de fundo que tenha ocorrido ANTES de chamar "Jarvis"
    m = re.search(r'(?i)\b(?:hey[\s,.:]+|ei[\s,.:]+|oi[\s,.:]+|o[\s,.:]+|ô[\s,.:]+|p\.?[\s,.:]+)?(?:j\s*\.?\s*a\s*\.?\s*r\s*\.?\s*v(?:\s*\.?\s*i\s*\.?\s*s)?|jarvis|jervis|javis|jarves|jarviz|jardim|jardis|jarve|jarvi|joves|javes|jovis|chaves|charvis|iarvis|yarvis|darvis)\b[,.:;!?-]*\s*(.*)$', text)
    if m:
        after_wake = m.group(1).strip(' ,.!?;:-—\t\n')
        return clean_utterance(after_wake) if after_wake else ""
    return clean_utterance(text)





def parse_timer_alarm_intent(text: str):
    if not text:
        return None
    text_lower = text.lower().strip()

    # Intencao Apuracao Eleicoes Presidenciais 2026
    if any(k in text_lower for k in ['eleicao', 'eleição', 'apuracao', 'apuração', 'votos', 'quem esta na frente', 'quem ta na frente', 'resultado da eleicao', 'resultado da eleição', 'apuracao presidente']):
        data = _LATEST_ELECTION_DATA
        c1 = data.get("c1", {})
        c2 = data.get("c2", {})
        apurado = data.get("apurado", "0%")
        hora = data.get("hora", "")
        reply = f"Senhor Werik, segundo a apuração oficial do TSE das {hora}, com {apurado} das seções totalizadas: {c1.get('nome', 'Lula')} lidera com {c1.get('pct', '')} dos votos válidos, contra {c2.get('pct', '')} de {c2.get('nome', 'Flávio Bolsonaro')}."
        return {
            'type': 'election',
            'reply': reply
        }
    if not text:
        return None
    text_lower = text.lower().strip()
    words_to_num = {
        'um': 1, 'uma': 1, 'dois': 2, 'duas': 2, 'tres': 3, 'três': 3,
        'quatro': 4, 'cinco': 5, 'seis': 6, 'sete': 7, 'oito': 8, 'nove': 9, 'dez': 10,
        'quinze': 15, 'vinte': 20, 'trinta': 30, 'quarenta': 40, 'cinquenta': 50
    }
    for w, n in words_to_num.items():
        text_lower = re.sub(rf'\b{w}\b', str(n), text_lower)
    
    # 1. Ações de Timer
    if any(k in text_lower for k in ['pausar timer', 'pausa o timer', 'pausar o timer', 'pausa timer']):
        return {'type': 'timer_action', 'action': 'pause', 'reply': 'Timer pausado, senhor.'}
    if any(k in text_lower for k in ['retomar timer', 'retoma o timer', 'continuar timer', 'continua o timer', 'retoma timer']):
        return {'type': 'timer_action', 'action': 'resume', 'reply': 'Timer retomado, senhor.'}
    if any(k in text_lower for k in ['cancelar timer', 'cancela o timer', 'para o timer', 'parar timer', 'desliga o timer', 'cancela timer']):
        return {'type': 'timer_action', 'action': 'cancel', 'reply': 'Timer cancelado, senhor.'}

    # 2. Ações de Alarme
    if any(k in text_lower for k in ['desligar alarme', 'desliga o alarme', 'cancelar alarme', 'cancela o alarme', 'para o alarme', 'parar alarme', 'desliga alarme', 'cancela alarme']):
        return {'type': 'alarm_action', 'action': 'cancel', 'reply': 'Alarme desligado, senhor.'}

    # 3. Definir Timer
    m_timer = re.search(r'(?:timer|cronometro|cronômetro|marca|cronometra|temporizador)\s+(?:de\s+)?(?:para\s+)?(\d+)\s*(minuto|minutos|min|segundo|segundos|seg|hora|horas|h)\b', text_lower)
    if m_timer:
        val = int(m_timer.group(1))
        unit = m_timer.group(2)
        if 'min' in unit:
            sec = val * 60
            unit_str = f'{val} minuto' if val == 1 else f'{val} minutos'
            label = f'TIMER {val}M'
        elif 'seg' in unit:
            sec = val
            unit_str = f'{val} segundo' if val == 1 else f'{val} segundos'
            label = f'TIMER {val}S'
        elif 'h' in unit:
            sec = val * 3600
            unit_str = f'{val} hora' if val == 1 else f'{val} horas'
            label = f'TIMER {val}H'
        else:
            sec = val * 60
            unit_str = f'{val} minutos'
            label = f'TIMER {val}M'
        return {
            'type': 'timer',
            'seconds': sec,
            'label': label,
            'reply': f'Timer de {unit_str} iniciado na esfera, senhor.'
        }

    # 4. Definir Alarme
    m_alarm = re.search(r'(?:alarme|despertador|despertar|acordar)\s+(?:para\s+)?(?:as\s+|às\s+)?(\d{1,2})(?::(\d{1,2})|\s*h(?:oras?)?\s*(\d{1,2})?|\s*e\s*meia|\s*e\s*(\d{1,2}))?', text_lower)
    if m_alarm:
        hr = int(m_alarm.group(1))
        mn = 0
        if 'meia' in text_lower:
            mn = 30
        elif m_alarm.group(2):
            mn = int(m_alarm.group(2))
        elif m_alarm.group(3):
            mn = int(m_alarm.group(3))
        elif m_alarm.group(4):
            mn = int(m_alarm.group(4))
        if 0 <= hr <= 23 and 0 <= mn <= 59:
            time_str = f'{hr:02d}:{mn:02d}'
            return {
                'type': 'alarm',
                'hour': hr,
                'minute': mn,
                'label': f'ALARME {time_str}',
                'reply': f'Alarme programado para as {time_str} na esfera, senhor.'
            }

def is_stop_command(text: str) -> bool:
    if not text:
        return False
    t = text.lower().strip()
    t = re.sub(r'[^\w\s]', ' ', t)
    t = " ".join(t.split())

    stop_phrases = [
        "cale a boca", "cala a boca", "cala boca", "cale boca",
        "fique quieto", "fica quieto", "fique quieta", "fica quieta",
        "fique calado", "fica calado", "fiquem quietos",
        "pare de falar", "para de falar", "pare de fala", "para de fala",
        "pare com isso", "para com isso",
        "ja entendi", "já entendi", "ta ja entendi", "tá já entendi",
        "ta bom ja entendi", "tá bom já entendi", "bom ja entendi",
        "ja deu", "já deu", "chega", "silencio", "silêncio",
        "cancela", "cancelar", "basta", "shh", "shhh", "psiu"
    ]
    for phrase in stop_phrases:
        if phrase in t:
            return True

    words = t.split()
    if len(words) <= 3:
        stop_words = {"para", "pare", "parou", "quieto", "quieta", "chega", "silencio", "silêncio", "cancela", "cancelar", "basta"}
        if any(w in stop_words for w in words):
            return True

    return False




def parse_windows_intent(text: str):
    if not text:
        return None
    tl = text.lower().strip()
    tl_clean = re.sub(r'[,.:;!?-]', ' ', tl).strip()
    tl_clean = re.sub(r'\s+', ' ', tl_clean)

    # 0. Controles de Energia do PC (Desligar, Reiniciar, Bloquear, Suspender)
    if re.search(r'\b(?:desligar|desliga|desligue|apagar|apaga|apague)\s+(?:o\s+)?(?:pc|computador|desktop|windows)\b', tl_clean):
        return {
            'action': 'system_power',
            'params': {'action': 'shutdown'},
            'reply': 'Desligando o computador, senhor.'
        }
    if re.search(r'\b(?:reiniciar|reinicia|reinicie|rebootar|reboota)\s+(?:o\s+)?(?:pc|computador|desktop|windows)\b', tl_clean):
        return {
            'action': 'system_power',
            'params': {'action': 'restart'},
            'reply': 'Reiniciando o computador, senhor.'
        }
    if re.search(r'\b(?:bloquear|bloqueia|bloqueie|travar|trava|trave)\s+(?:o\s+)?(?:pc|computador|desktop|windows|tela)\b', tl_clean):
        return {
            'action': 'system_power',
            'params': {'action': 'lock'},
            'reply': 'Computador bloqueado por segurança, senhor.'
        }
    if re.search(r'\b(?:suspender|suspende|suspenda|dormir)\s+(?:o\s+)?(?:pc|computador|desktop)\b', tl_clean):
        return {
            'action': 'system_power',
            'params': {'action': 'sleep'},
            'reply': 'Suspendendo o computador, senhor.'
        }

    # 0.5 Pesquisa no Google / Web (Google Search)
    # Exemplos: "abra o google e pesquise por manoel gomes", "pesquise no google por manoel gomes", "pesquisar manoel gomes"
    m_search = re.search(
        r'(?:(?:abrir|abre|abra|iniciar|inicia|inicie)?\s*(?:o\s+)?(?:google|navegador|chrome)\s*(?:e\s+)?)?'
        r'(?:pesquisar|pesquisa|pesquise|buscar|busca|busque|procurar|procura|procure)\s+'
        r'(?:no\s+google\s+|no\s+navegador\s+|na\s+internet\s+|na\s+web\s+)?'
        r'(?:por\s+|sobre\s+|o\s+|a\s+|os\s+|as\s+)?(.+)',
        tl_clean,
        re.IGNORECASE
    )
    if m_search and m_search.group(1).strip():
        q_raw = m_search.group(1).strip()
        q_raw = re.sub(r'\s+(?:no\s+google|no\s+navegador|na\s+web|no\s+pc|no\s+computador)$', '', q_raw).strip()
        if q_raw and q_raw not in ['algo', 'nada', 'coisa']:
            return {
                'action': 'google_search',
                'params': {'query': q_raw},
                'reply': f'Abrindo o Google e pesquisando por {q_raw} no seu computador, senhor.'
            }

    # 1. Aplicativos e Programas
    verb_open = r'(?:abrir|abre|abra|iniciar|inicia|inicie|executar|executa|execute|rodar|roda|rode|lancar|lanca|lançar|lança|bota|bote|coloca|coloque)'
    verb_close = r'(?:fechar|fecha|feche|encerrar|encerra|encerre|desligar|desliga|desligue|matar|mata|mate)'
    pc_suffix = r'(?:\s+(?:no|do)\s+(?:meu\s+)?(?:pc|computador|desktop))?'

    app_patterns = [
        # Calculadora
        (rf'{verb_open}\s+(?:a\s+)?(?:calculadora|calc){pc_suffix}', 'open_app', {'target': 'calc'}, 'Abrindo a Calculadora no seu computador, senhor.'),
        (rf'{verb_close}\s+(?:a\s+)?(?:calculadora|calc){pc_suffix}', 'close_app', {'processo': 'CalculatorApp.exe'}, 'Fechando a Calculadora, senhor.'),

        # Chrome / Navegador
        (rf'{verb_open}\s+(?:o\s+|a\s+)?(?:chrome|google chrome|google|navegador|browser){pc_suffix}', 'open_app', {'target': 'https://www.google.com'}, 'Abrindo o Google Chrome no seu computador, senhor.'),
        (rf'{verb_close}\s+(?:o\s+|a\s+)?(?:chrome|google chrome|navegador|browser){pc_suffix}', 'close_app', {'processo': 'chrome.exe'}, 'Fechando o Google Chrome, senhor.'),

        # Spotify / Música
        (rf'(?:{verb_open}|tocar|toca|toque)\s+(?:o\s+)?(?:spotify|musica|música){pc_suffix}', 'open_app', {'target': 'spotify'}, 'Abrindo o Spotify no PC, senhor.'),
        (rf'{verb_close}\s+(?:o\s+)?(?:spotify){pc_suffix}', 'close_app', {'processo': 'Spotify.exe'}, 'Fechando o Spotify, senhor.'),

        # VSCode / Código
        (rf'{verb_open}\s+(?:o\s+)?(?:vscode|vs code|codigo|código|code){pc_suffix}', 'open_app', {'target': 'code'}, 'Abrindo o Visual Studio Code, senhor.'),
        (rf'{verb_close}\s+(?:o\s+)?(?:vscode|vs code|codigo|código|code){pc_suffix}', 'close_app', {'processo': 'Code.exe'}, 'Fechando o Visual Studio Code, senhor.'),

        # Terminal / CMD / PowerShell
        (rf'{verb_open}\s+(?:o\s+)?(?:terminal|powershell|cmd|prompt){pc_suffix}', 'open_app', {'target': 'wt'}, 'Abrindo o Terminal no Windows, senhor.'),

        # Bloco de Notas / Notepad
        (rf'{verb_open}\s+(?:o\s+)?(?:bloco de notas|notepad){pc_suffix}', 'open_app', {'target': 'notepad'}, 'Abrindo o Bloco de Notas, senhor.'),
        (rf'{verb_close}\s+(?:o\s+)?(?:bloco de notas|notepad){pc_suffix}', 'close_app', {'processo': 'notepad.exe'}, 'Fechando o Bloco de Notas, senhor.'),

        # Discord
        (rf'{verb_open}\s+(?:o\s+)?(?:discord){pc_suffix}', 'open_app', {'target': 'discord'}, 'Abrindo o Discord no PC, senhor.'),
        (rf'{verb_close}\s+(?:o\s+)?(?:discord){pc_suffix}', 'close_app', {'processo': 'Discord.exe'}, 'Fechando o Discord, senhor.'),

        # Steam
        (rf'{verb_open}\s+(?:o\s+)?(?:steam){pc_suffix}', 'open_app', {'target': 'steam'}, 'Abrindo a Steam, senhor.'),
        (rf'{verb_close}\s+(?:o\s+)?(?:steam){pc_suffix}', 'close_app', {'processo': 'steam.exe'}, 'Fechando a Steam, senhor.'),

        # Explorador de Arquivos
        (rf'{verb_open}\s+(?:o\s+)?(?:explorador|arquivos|pastas){pc_suffix}', 'open_app', {'target': 'explorer'}, 'Abrindo o Explorador de Arquivos, senhor.'),

        # YouTube
        (rf'{verb_open}\s+(?:o\s+)?(?:youtube){pc_suffix}', 'open_app', {'target': 'https://youtube.com'}, 'Abrindo o YouTube no navegador, senhor.'),
    ]

    for pattern, action, params, reply in app_patterns:
        if re.search(pattern, tl_clean, re.IGNORECASE):
            return {'action': action, 'params': params, 'reply': reply}

    # 2. Volume do Windows
    if any(k in tl_clean for k in ['aumenta o volume', 'aumentar o volume', 'aumenta volume', 'mais alto', 'volume mais alto', 'aumente o volume']):
        return {'action': 'volume', 'params': {'acao': 'up', 'passos': 4}, 'reply': 'Volume do computador aumentado, senhor.'}
    if any(k in tl_clean for k in ['abaixa o volume', 'abaixar o volume', 'diminui o volume', 'diminuir volume', 'mais baixo', 'abaixe o volume', 'diminua o volume']):
        return {'action': 'volume', 'params': {'acao': 'down', 'passos': 4}, 'reply': 'Volume do computador diminuído, senhor.'}
    if any(k in tl_clean for k in ['muta o pc', 'mutar o pc', 'silencia o pc', 'silenciar o pc', 'mudo no pc', 'mutar audio', 'silenciar audio']):
        return {'action': 'volume', 'params': {'acao': 'mute'}, 'reply': 'Áudio do computador silenciado, senhor.'}

    # 3. Mídia (Play/Pause/Next/Prev)
    if any(k in tl_clean for k in ['pausar musica', 'pausa a musica', 'para a musica', 'pausar o video', 'pausa o video', 'pause a musica']):
        return {'action': 'media', 'params': {'acao': 'play_pause'}, 'reply': 'Mídia pausada no PC, senhor.'}
    if any(k in tl_clean for k in ['continuar musica', 'despausar', 'tocar musica', 'play na musica', 'solta o som', 'continua a musica']):
        return {'action': 'media', 'params': {'acao': 'play_pause'}, 'reply': 'Reproduzindo mídia no PC, senhor.'}
    if any(k in tl_clean for k in ['proxima musica', 'proxima faixa', 'avancar musica', 'pula a musica', 'pular musica', 'próxima música', 'avançar música']):
        return {'action': 'media', 'params': {'acao': 'next'}, 'reply': 'Avançando faixa no PC, senhor.'}
    if any(k in tl_clean for k in ['musica anterior', 'faixa anterior', 'volta a musica', 'voltar musica', 'música anterior']):
        return {'action': 'media', 'params': {'acao': 'prev'}, 'reply': 'Voltando à faixa anterior no PC, senhor.'}

    # 4. Sistema (Minimizar)
    if any(k in tl_clean for k in ['minimizar tudo', 'minimiza tudo', 'minimize tudo', 'mostra a area de trabalho', 'mostrar desktop', 'minimizar janelas', 'minimiza janelas', 'minimize janelas', 'minimize as janelas', 'minimizar todas as janelas', 'minimiza todas as janelas', 'minimize todas as janelas']):
        return {'action': 'minimize', 'params': {}, 'reply': 'Minimizando todas as janelas no Windows, senhor.'}

    # 5. Comandos livres PowerShell
    m_cmd = re.search(r'(?:executa(?:r)?\s+(?:no\s+pc\s+|no\s+windows\s+|comando\s+))(.*)', tl)
    if m_cmd:
        cmd_str = m_cmd.group(1).strip()
        if cmd_str:
            return {'action': 'powershell', 'params': {'comando': cmd_str}, 'reply': 'Executando comando no PowerShell do PC, senhor.'}

    # 6. Mouse (Rolagem / Scroll)
    if any(k in tl_clean for k in ['rola para baixo', 'rola pra baixo', 'desce a pagina', 'desce a página', 'desce a tela', 'scroll down', 'rolar para baixo', 'rolar pra baixo']):
        return {'action': 'mouse_scroll', 'params': {'direction': 'down', 'clicks': 6}, 'reply': 'Rolando a tela para baixo, senhor.'}
    if any(k in tl_clean for k in ['rola para cima', 'rola pra cima', 'sobe a pagina', 'sobe a página', 'sobe a tela', 'scroll up', 'rolar para cima', 'rolar pra cima']):
        return {'action': 'mouse_scroll', 'params': {'direction': 'up', 'clicks': 6}, 'reply': 'Rolando a tela para cima, senhor.'}

    # 7. Mouse (Cliques)
    if any(k in tl_clean for k in ['duplo clique', 'dois cliques', 'clique duplo']):
        return {'action': 'mouse_double_click', 'params': {}, 'reply': 'Duplo clique executado, senhor.'}
    if any(k in tl_clean for k in ['clique direito', 'botao direito', 'botão direito']):
        return {'action': 'mouse_right_click', 'params': {}, 'reply': 'Clique com o botão direito executado, senhor.'}
    if any(k in tl_clean for k in ['clica com o mouse', 'dar um clique', 'da um clique', 'clique do mouse', 'clica aqui', 'clica na tela']):
        return {'action': 'mouse_click', 'params': {'button': 'left'}, 'reply': 'Clique executado, senhor.'}

    # 8. Teclado (Digitação de Texto)
    m_type = re.search(r'(?:digita(?:r)?|escreve(?:r)?)\s+(?:o\s+texto\s+|a\s+frase\s+|no\s+pc\s+)?(.*)', tl)
    if m_type:
        text_to_type = m_type.group(1).strip()
        if text_to_type and not any(k in text_to_type for k in ['comando', 'powershell']):
            return {'action': 'keyboard_type', 'params': {'text': text_to_type}, 'reply': 'Digitando no seu computador, senhor.'}

    # 9. Teclado (Teclas Especiais e Atalhos)
    if any(k in tl_clean for k in ['dar enter', 'da enter', 'dá enter', 'aperta enter', 'pressiona enter', 'pressione enter', 'aperta o enter']):
        return {'action': 'keyboard_press', 'params': {'key': 'enter'}, 'reply': 'Enter pressionado, senhor.'}
    if any(k in tl_clean for k in ['aperta esc', 'pressiona esc', 'aperta o esc', 'cancelar janela']):
        return {'action': 'keyboard_press', 'params': {'key': 'esc'}, 'reply': 'Escape pressionado, senhor.'}
    if any(k in tl_clean for k in ['copiar isso', 'copia isso', 'copiar texto', 'copia o texto']):
        return {'action': 'keyboard_hotkey', 'params': {'keys': ['ctrl', 'c']}, 'reply': 'Copiado para a área de transferência, senhor.'}
    if any(k in tl_clean for k in ['colar isso', 'cola isso', 'colar texto', 'cola o texto']):
        return {'action': 'keyboard_hotkey', 'params': {'keys': ['ctrl', 'v']}, 'reply': 'Conteúdo colado, senhor.'}
    if any(k in tl_clean for k in ['selecionar tudo', 'seleciona tudo']):
        return {'action': 'keyboard_hotkey', 'params': {'keys': ['ctrl', 'a']}, 'reply': 'Tudo selecionado, senhor.'}

    # 10. Captura de Tela (Print / Screenshot)
    if any(k in tl_clean for k in ['tira um print', 'tira print', 'captura a tela', 'capturar a tela', 'print da tela', 'foto da tela', 'screenshot']):
        return {'action': 'screenshot', 'params': {}, 'reply': 'Captura de tela realizada no PC, senhor.'}

    return None

LOCAL_SERVER_ENDPOINTS = [
    "http://10.147.20.34:8085",  # ZeroTier direto ao PC (validado em tempo real)
    "http://192.168.10.8:8085",  # LAN fallback
    "http://172.17.0.1:8085",    # Docker host fallback
]



_TUYA_CLIENT_ID = "ckavrpcrr8qhwfy3ku4s"
_TUYA_SECRET = b"8478c589465643f7bf2ea5a6a825e886"
_TUYA_BASE = "https://openapi.tuyaus.com"
_TUYA_DEVICE_IDS = ["eb36293864e8ca3484qifm", "eb8b0726824352aae25fgl"]
_tuya_cached_token = ""
_tuya_token_exp = 0.0
_tuya_last_state = False


def _tuya_sign_headers(method: str, path: str, body_bytes: bytes, token: str = "") -> dict:
    import uuid as _uuid, hashlib, hmac
    t = str(int(time.time() * 1000))
    nonce = _uuid.uuid4().hex
    content_sha = hashlib.sha256(body_bytes).hexdigest()
    s2s = f"{method.upper()}\n{content_sha}\n\n{path}"
    raw = _TUYA_CLIENT_ID + token + t + nonce + s2s
    sig = hmac.new(_TUYA_SECRET, raw.encode("utf-8"), hashlib.sha256).hexdigest().upper()
    h = {
        "client_id": _TUYA_CLIENT_ID,
        "sign": sig,
        "t": t,
        "sign_method": "HMAC-SHA256",
        "nonce": nonce,
        "Content-Type": "application/json",
    }
    if token:
        h["access_token"] = token
    return h


async def _tuya_get_token(session: ClientSession, force: bool = False) -> str:
    global _tuya_cached_token, _tuya_token_exp
    now = time.time()
    if not force and _tuya_cached_token and now < _tuya_token_exp:
        return _tuya_cached_token
    path = "/v1.0/token?grant_type=1"
    headers = _tuya_sign_headers("GET", path, b"")
    async with session.get(_TUYA_BASE + path, headers=headers, timeout=4) as resp:
        data = await resp.json()
        if data.get("success") and data.get("result"):
            _tuya_cached_token = data["result"]["access_token"]
            _tuya_token_exp = now + float(data["result"].get("expire_time", 7200)) - 120.0
            return _tuya_cached_token
    return ""


async def _tuya_openapi_set_devices(device_ids: list, state: bool) -> bool:
    global _tuya_last_state
    _tuya_last_state = bool(state)
    body_bytes = json.dumps(
        {"commands": [{"code": "switch_1", "value": bool(state)}]},
        separators=(",", ":"),
    ).encode("utf-8")
    any_ok = False
    try:
        async with ClientSession() as session:
            tok = await _tuya_get_token(session, force=False)
            if not tok:
                tok = await _tuya_get_token(session, force=True)
            if not tok:
                return False

            async def _send_one(dev_id: str) -> bool:
                path = f"/v1.0/iot-03/devices/{dev_id}/commands"
                headers = _tuya_sign_headers("POST", path, body_bytes, token=tok)
                async with session.post(_TUYA_BASE + path, data=body_bytes, headers=headers, timeout=4) as r:
                    d = await r.json()
                    return bool(d.get("success"))

            results = await asyncio.gather(*[_send_one(did) for did in device_ids], return_exceptions=True)
            any_ok = any(r is True for r in results)
            logging.info(f"[TUYA-ZIMA-OPENAPI] targets={device_ids} state={state} results={results}")
    except Exception as e:
        logging.warning(f"[TUYA-ZIMA-OPENAPI] Erro: {e}")
    return any_ok

async def _tuya_openapi_set_both(state: bool) -> bool:
    return await _tuya_openapi_set_devices(_TUYA_DEVICE_IDS, state)


async def handle_devices_registry(request: web.Request) -> web.Response:
    """Proxy somente-leitura do registro de nomes/grupos de dispositivos (sincronizacao do Windows)."""
    try:
        async with ClientSession() as session:
            async with session.get(
                f"{JARVIS_HUD_URL}/api/devices/registry",
                headers={"X-Jarvis-Client": "desktop_windows"},
                timeout=5,
            ) as r:
                body = await r.text()
                return web.Response(text=body, status=r.status, content_type="application/json")
    except Exception as e:
        return web.json_response({"success": False, "error": f"Registro indisponivel: {e}"}, status=502)


async def handle_tuya_http(request: web.Request) -> web.Response:
    try:
        data = await request.json()
    except Exception:
        data = {}
    raw_act = str(data.get("action", "toggle")).strip().lower()
    if raw_act in ("on", "turn_on", "true", "1"):
        act = "on"
        st = True
    elif raw_act in ("off", "turn_off", "false", "0"):
        act = "off"
        st = False
    else:
        act = "toggle"
        st = not _tuya_last_state
    ok = await _dispatch_tuya_action(act, st)
    return web.json_response({"success": ok, "action": act, "is_on": st})


async def _dispatch_tuya_action(action: str, state: bool = None, target: str = "todas") -> bool:
    """Dispara comando Tuya diretamente pelo ZimaOS (OpenAPI) + Esfera (LAN 3.4), 100% independente do Windows PC."""
    if state is None:
        state = (action == "on") if action in ("on", "off") else (not _tuya_last_state)
    dev_map = {
        "setup": ["eb36293864e8ca3484qifm"],
        "quarto": ["eb8b0726824352aae25fgl"],
        "todas": ["eb36293864e8ca3484qifm", "eb8b0726824352aae25fgl"]
    }
    target_ids = dev_map.get(target, _TUYA_DEVICE_IDS)
    cloud_ok = await _tuya_openapi_set_devices(target_ids, bool(state))
    sync_msg = json.dumps({
        "type": "custom",
        "payload": {
            "event": "tuya_command",
            "action": "on" if state else "off",
            "state": bool(state)
        }
    })
    ws_sphere = active_sessions.get("jarvis_sphere_esp32s3")
    sphere_ok = False
    if ws_sphere and not ws_sphere.closed:
        try:
            await ws_sphere.send_str(sync_msg)
            sphere_ok = True
        except Exception as e:
            logging.warning(f"[TUYA-DISPATCH] Falha envio p/ Esfera: {e}")
    return cloud_ok or sphere_ok


async def _dispatch_pc_action(action: str, params: dict = None) -> dict:
    """Dispara ação de controle no PC (Mouse, Teclado, Apps, Mídia, Macros, PowerShell) com sincronização em tempo real."""
    if params is None:
        params = {}
    payload = {"action": action, "params": params}
    
    # 1. Envia via HTTP para o local_server do Windows (ZeroTier / LAN)
    res = None
    for base in LOCAL_SERVER_ENDPOINTS:
        try:
            async with ClientSession() as s:
                async with s.post(f"{base}/api/system/control", json=payload, timeout=4.0) as r:
                    if r.status == 200:
                        res = await r.json(content_type=None)
                        logging.info(f"[PC-ACTION] Sucesso via {base}: action='{action}' res={res}")
                        break
        except Exception as e:
            logging.debug(f"[PC-ACTION] Falha via {base}: {e}")

    # 2. Sincroniza via WebSocket se o PC estiver conectado
    win_ws = active_sessions.get("jarvis_windows_pc")
    if win_ws and not win_ws.closed:
        try:
            asyncio.create_task(win_ws.send_str(json.dumps({
                "type": "windows_command",
                "action": action,
                "params": params
            })))
        except Exception as e:
            logging.debug(f"[PC-ACTION] Falha sync win_ws: {e}")

    return res or {"success": True, "action": action}

def parse_lighting_intent(text: str):
    if not text:
        return None
    tl = text.lower().strip()
    tl_clean = re.sub(r'[.,!?;:]', '', tl)

    # Remove saudações e prefixos comuns
    for prefix in ["jarvis", "ei jarvis", "hey jarvis", "por favor", "por gentileza"]:
        if tl_clean.startswith(prefix):
            tl_clean = tl_clean[len(prefix):].strip()

    has_light_word = any(w in tl_clean for w in [
        "luz", "lampada", "lâmpada", "iluminacao", "iluminação", "led", "setup", "mesa", "quarto", "werik", "cama"
    ])

    is_off = any(w in tl_clean for w in [
        "apagar", "apaga", "apague", "desligar", "desliga", "desligue", "apagar tudo", "desligar tudo", "apaga tudo", "desliga tudo"
    ])
    is_on = any(w in tl_clean for w in [
        "acender", "acende", "acenda", "ligar", "liga", "ligue"
    ])

    if not (is_off or is_on):
        return None

    # Se mencionou luz/lampada/led OU se falou 'apaga tudo' / 'desliga tudo'
    if not has_light_word and not any(k in tl_clean for k in ["tudo", "setup", "mesa"]):
        return None

    target_state = is_on if not is_off else False
    action_endpoint = "on" if target_state else "off"

    is_quarto = any(w in tl_clean for w in ["quarto", "cama", "werik", "dormitório", "dormitorio"])
    is_setup = any(w in tl_clean for w in ["setup", "mesa", "computador", "pc", "escritorio", "escritório"])

    if is_quarto and not is_setup:
        target = "quarto"
        reply = "Luz do quarto ligada, senhor." if target_state else "Luz do quarto desligada, senhor."
    elif is_setup and not is_quarto:
        target = "setup"
        reply = "Luz do setup ligada, senhor." if target_state else "Luz do setup desligada, senhor."
    else:
        target = "todas"
        reply = "Lâmpadas ligadas, senhor." if target_state else "Lâmpadas desligadas, senhor."

    return {
        "type": "lighting",
        "action": action_endpoint,
        "target": target,
        "state": target_state,
        "reply": reply
    }

def parse_alexa_intent(text: str):
    if not text:
        return None
    tl = text.lower().strip()
    tl_clean = re.sub(r'[.,!?;:]', '', tl)
    for prefix in ["jarvis", "ei jarvis", "hey jarvis", "por favor", "por gentileza"]:
        if tl_clean.startswith(prefix):
            tl_clean = tl_clean[len(prefix):].strip()

    patterns = [
        r"(?:avisa(?:r)?|fala(?:r)?|diz(?:er)?|mande(?:r)?)\s+(?:na\s+alexa|para\s+a\s+alexa|na\s+echo)\s+(?:que\s+|:)?(.+)",
        r"(?:na\s+alexa|na\s+echo)\s+(?:avisa(?:r)?|fala(?:r)?|diz(?:er)?)\s+(?:que\s+|:)?(.+)",
        r"(?:eco|echo|alexa)\s+(?:fala(?:r)?|diga|avise)\s+(.+)",
    ]
    for pat in patterns:
        m = re.search(pat, tl_clean)
        if m:
            msg = m.group(1).strip()
            if msg:
                return {"action": "speak", "message": msg}
    return None

def parse_and_execute_llm_tool(reply_str: str, active_sessions: dict) -> tuple[str, bool]:
    """
    Analisa se a resposta do LLM é uma chamada de ferramenta/código/JSON.
    Se for, executa no Windows PC ou Hardware Tuya e retorna SEMPRE fala limpa em português para TTS.
    Garante que Piper TTS NUNCA fale siglas ou JSON em inglês!
    """
    if not reply_str:
        return ("Comando processado com sucesso, senhor.", True)

    raw = reply_str.strip()
    if raw.startswith("```json"):
        raw = raw[7:].strip()
    elif raw.startswith("```"):
        raw = raw[3:].strip()
    if raw.endswith("```"):
        raw = raw[:-3].strip()

    is_tool_like = (
        (raw.startswith("{") and any(k in raw for k in ["tool", "action", "command", "name", "arguments"])) or
        '"tool":' in raw or '"arguments":' in raw or '"parameters":' in raw or 'windows-automation' in raw
    )

    if not is_tool_like:
        return (reply_str, False)

    win_ws = active_sessions.get("jarvis_windows_pc")
    import json as _js

    data = None
    try:
        data = _js.loads(raw)
    except Exception:
        pass

    tool_name = ""
    args = {}
    if isinstance(data, dict):
        tool_name = str(data.get("tool") or data.get("name") or data.get("action") or "").lower()
        args = data.get("arguments") or data.get("parameters") or data.get("args") or {}
        if not isinstance(args, dict):
            args = {"raw_args": str(args)}
    else:
        m_tool = re.search(r'["\']tool["\']\s*:\s*["\']([^"\']+)["\']', raw)
        if m_tool:
            tool_name = m_tool.group(1).lower()
        m_cmd = re.search(r'["\']command["\']\s*:\s*["\']([^"\']+)["\']', raw)
        if m_cmd:
            args["command"] = m_cmd.group(1)

    logging.info(f"[TOOL-INTERCEPTOR] Ferramenta interceptada: '{tool_name}' args={args}")

    # 0. Pesquisa no Google (Google Search)
    if any(k in tool_name for k in ["google_search", "google", "web_search", "pesquisa_google", "pesquisar_google", "buscar_google", "search"]):
        qry = args.get("query") or args.get("termo") or args.get("q") or args.get("busca") or args.get("pesquisa") or ""
        asyncio.create_task(_dispatch_pc_action("google_search", {"query": qry}))
        return (f"Pesquisando por {qry} no Google no seu computador, senhor." if qry else "Abrindo o Google no seu computador, senhor.", True)

    # 1. Iluminação / Lâmpada Tuya
    if any(k in tool_name or k in str(args).lower() for k in ["luz", "lampada", "light", "tuya", "iluminacao", "led"]):
        state = True
        act = "on"
        if any(k in tool_name or k in str(args).lower() for k in ["off", "deslig", "apag"]):
            state = False
            act = "off"
        asyncio.create_task(_dispatch_tuya_action(act, state))
        status_txt = "ligada" if state else "desligada"
        return (f"Luz do computador {status_txt}, senhor.", True)

    # 2. Controle do Mouse (Movimento, Cliques, Rolagem, Arrasto)
    if any(k in tool_name for k in ["mouse", "clique", "click", "cursor", "scroll", "rolar", "arrastar"]):
        asyncio.create_task(_dispatch_pc_action(tool_name, args))
        if "scroll" in tool_name or "rol" in tool_name:
            return ("Rolando a tela no seu computador, senhor.", True)
        elif "click" in tool_name or "clic" in tool_name:
            return ("Clique executado no seu computador, senhor.", True)
        elif "move" in tool_name or "mov" in tool_name:
            return ("Cursor posicionado, senhor.", True)
        return ("Ação de mouse executada com sucesso, senhor.", True)

    # 3. Controle do Teclado (Digitação, Teclas, Atalhos)
    if any(k in tool_name for k in ["keyboard", "teclado", "type", "digitar", "escrever", "press", "tecla", "hotkey", "atalho"]):
        asyncio.create_task(_dispatch_pc_action(tool_name, args))
        if "type" in tool_name or "digit" in tool_name or "escrev" in tool_name:
            return ("Texto digitado no seu computador, senhor.", True)
        elif "press" in tool_name or "tecla" in tool_name:
            return ("Tecla pressionada no seu computador, senhor.", True)
        elif "hotkey" in tool_name or "atalho" in tool_name:
            return ("Atalho de teclado executado, senhor.", True)
        return ("Ação de teclado executada, senhor.", True)

    # 4. Captura de Tela (Print / Screenshot)
    if any(k in tool_name for k in ["screenshot", "print", "captura"]):
        asyncio.create_task(_dispatch_pc_action("screenshot", args))
        return ("Captura de tela realizada no seu computador, senhor.", True)

    # 5. Área de Transferência (Clipboard)
    if any(k in tool_name for k in ["clipboard", "copiar", "colar"]):
        asyncio.create_task(_dispatch_pc_action(tool_name, args))
        return ("Ação de área de transferência executada, senhor.", True)

    # 6. Motor de Macros e Sequências
    if any(k in tool_name for k in ["macro", "pc_macro", "sequencia", "workflow"]):
        asyncio.create_task(_dispatch_pc_action("macro", args))
        return ("Sequência de automação executada no seu computador, senhor.", True)

    # 7. Aplicativos (Calculadora, Chrome, Spotify, etc.)
    if any(k in tool_name or k in str(args).lower() for k in ["calc", "calculadora", "chrome", "navegador", "browser", "spotify", "musica", "open_app", "abrir"]):
        target = args.get("target") or args.get("aplicativo") or args.get("nome") or tool_name
        asyncio.create_task(_dispatch_pc_action("open_app", {"target": target}))
        return (f"Abrindo aplicativo no seu computador, senhor.", True)

    # 8. Comandos de terminal / powershell / execute_command
    if any(k in tool_name for k in ["execute", "command", "powershell", "runcommand", "system_command", "windows-automation"]):
        cmd = args.get("command") or args.get("comando") or args.get("action") or ""
        asyncio.create_task(_dispatch_pc_action("powershell", {"comando": cmd}))
        return ("Comando executado no seu computador, senhor.", True)

    # 6. Mensagem amigável inclusa no payload
    if isinstance(data, dict):
        friendly_msg = data.get("reply") or data.get("response") or data.get("message")
        if friendly_msg and isinstance(friendly_msg, str) and not friendly_msg.strip().startswith("{"):
            return (friendly_msg.strip(), True)

    # 7. Fallback seguro: NUNCA ler JSON em voz alta!
    return ("Comando processado com sucesso no seu computador, senhor.", True)

tts_mute_until: Dict[str, float] = {}

async def interrupt_tts_and_listen(ws: web.WebSocketResponse, device_id: str):
    """
    Interrompe imediatamente qualquer reproducao de TTS e retorna para Standby limpo,
    sem abrir microfone no meio do eco do alto-falante.
    """
    logging.info(f"[STOP-TTS] Interrupcao de TTS para {device_id} acionada -> Standby.")
    stop_tts_requested[device_id] = True
    tts_mute_until[device_id] = time.time() + 1.5
    wake_state.pop(device_id, None)

    old_task = active_utterance_tasks.pop(device_id, None)
    if old_task and not old_task.done():
        old_task.cancel()
        try:
            await asyncio.sleep(0.01)
        except Exception:
            pass

    try:
        await ws.send_str(json.dumps({"type": "stop_tts"}))
        await ws.send_str(json.dumps({"type": "emotion", "emotion": "standby"}))
    except Exception:
        pass

    st = audio_state.setdefault(device_id, {"buf": bytearray(), "speaking": False, "silence_start": 0.0})
    st["buf"] = bytearray()
    st["speaking"] = False
    st["silence_start"] = 0.0

    processing_state[device_id] = False
    stop_tts_requested[device_id] = False


async def process_utterance(ws: web.WebSocketResponse, device_id: str, pcm: bytes):
    if not pcm or len(pcm) < 3200:
        processing_state[device_id] = False
        return
    stop_tts_requested[device_id] = False
    active_utterance_tasks[device_id] = asyncio.current_task()
    was_awake_at_start = (time.time() - wake_state.get(device_id, 0.0) <= FOLLOWUP_SEC)
    if was_awake_at_start:
        try:
            await ws.send_str(json.dumps({"type": "emotion", "emotion": "thinking"}))
        except Exception:
            pass

    logging.info(f"[VOZ] Utterance {len(pcm)} bytes ({len(pcm)/BYTES_PER_SEC:.1f}s) de {device_id} (awake={was_awake_at_start}) -> transcrevendo...")

    pcm_f = _highpass_pcm(pcm, cutoff=120.0)

    try:
        with open("/tmp/utt_last.wav", "wb") as _f:
            _f.write(_pcm_to_wav(pcm_f))
    except Exception:
        pass

    try:
        async with ClientSession() as session:
            if was_awake_at_start:
                await ws.send_str(json.dumps({"type": "emotion", "emotion": "transcribing"}))
            logging.info(f"[VOZ] {device_id}: chamando STT ({len(pcm)/BYTES_PER_SEC:.1f}s)...")

            text = await _transcribe(session, _pcm_to_wav(pcm_f))
            logging.info(f"[VOZ] {device_id}: STT retornou: {text!r}")

            if not text:
                logging.info("[VOZ] Transcrição vazia (ignorado).")
                if was_awake_at_start:
                    await ws.send_str(json.dumps({"type": "emotion", "emotion": "standby"}))
                return

            now = time.time()
            text = _clean_hallucinations(text)
            if not text or len(text) < 2:
                logging.info(f"[VOZ] {device_id}: Transcricao vazia ou alucinada ignorada.")
                if was_awake_at_start:
                    await ws.send_str(json.dumps({"type": "emotion", "emotion": "standby"}))
                return

            is_awake = was_awake_at_start or (now - wake_state.get(device_id, 0.0) <= FOLLOWUP_SEC)
            has_wake = _has_wake_word(text)

            # Reconhecimento inteligente de intenção direta: se o usuário falou uma ordem clara (luz, alexa, alarme, timer, etc.),
            # processa diretamente mesmo que não tenha dito a palavra "Jarvis" explicitamente!
            direct_intent = bool(parse_lighting_intent(text) or parse_alexa_intent(text) or parse_timer_alarm_intent(text) or parse_windows_intent(text))

            # Se a esfera está em repouso, não falou "Jarvis", não é comando direto e tem poucas palavras aleatórias:
            if not has_wake and not is_awake and not direct_intent and len(text.strip().split()) <= 2:
                logging.info(f"[VOZ] {device_id}: Ignorado silenciosamente (repouso sem 'Jarvis' e sem comando direto: {text!r}).")
                return

            wake_state[device_id] = now

            if has_wake:
                wake_state[device_id] = now
                text = _strip_wake_word(text)
                if not text or len(text.strip()) < 3:
                    logging.info(f"[VOZ] {device_id}: Chamou 'Jarvis' ({text!r}). Abrindo escuta ativa sem processar comando vazio!")
                    st_reset = audio_state.get(device_id)
                    if st_reset:
                        st_reset["buf"] = bytearray()
                        st_reset["speaking"] = False
                        st_reset["silence_start"] = 0.0
                    await ws.send_str(json.dumps({"type": "wakeup"}))
                    await ws.send_str(json.dumps({"type": "emotion", "emotion": "listening"}))
                    _start_followup_timeout(ws, device_id)
                    return
                else:
                    await ws.send_str(json.dumps({"type": "emotion", "emotion": "thinking"}))
            else:
                wake_state[device_id] = now

            logging.info(f"[VOZ] STT: '{text}'")
            try:
                from unified_memory import memory_mgr
                asyncio.create_task(memory_mgr.add_dialogue(device_id, "esfera", "user", text))
            except Exception as ex_m:
                logging.warning(f"[MEMORY] Falha ao registrar diálogo do usuário: {ex_m}")

            if is_stop_command(text):
                logging.info(f"[VOZ] {device_id}: Comando de interrupção imediata detectado: {text!r}")
                stop_tts_requested[device_id] = True
                wake_state.pop(device_id, None)
                followup_task = followup_tasks.pop(device_id, None)
                if followup_task and followup_task is not asyncio.current_task():
                    followup_task.cancel()
                await ws.send_str(json.dumps({"type": "stop_tts"}))
                await ws.send_str(json.dumps({"type": "emotion", "emotion": "standby"}))
                return

            # Evento 'stt' faz a esfera mudar para a tela do rosto (SetDisplayMode kHappy)
            await ws.send_str(json.dumps({"type": "stt", "text": text}))

            # Interceptador direto de comandos de Timer e Alarme (execução local ultra-rápida na esfera)
            # Interceptador direto de Comandos do Windows PC (Apps, Mídia, Volume, PowerShell)
            light_intent = parse_lighting_intent(text)
            alexa_intent = parse_alexa_intent(text)
            win_intent = None
            intent = None

            if light_intent:
                logging.info(f"[VOZ] {device_id}: Intent de iluminacao Tuya (Prioridade Maxima): {light_intent}")
                action = light_intent["action"]
                asyncio.create_task(_dispatch_tuya_action(action, light_intent["state"], light_intent.get("target", "todas")))
                reply = light_intent["reply"]
            elif alexa_intent:
                msg_to_speak = alexa_intent["message"]
                logging.info(f"[VOZ] {device_id}: Intent Alexa reconhecido: '{msg_to_speak}'")
                if alexa_bridge and alexa_bridge.is_authenticated:
                    asyncio.create_task(alexa_bridge.speak(msg_to_speak))
                    reply = "Avisando na Alexa agora mesmo, senhor."
                else:
                    reply = "Senhor Werik, a Alexa ainda não foi pareada no sistema." 
            elif (win_intent := parse_windows_intent(text)):
                is_win_online = ("jarvis_windows_pc" in active_sessions and not active_sessions["jarvis_windows_pc"].closed)
                if not is_win_online and win_intent.get("action") not in ["wake_on_lan"]:
                    explicit_pc = any(k in text.lower() for k in ["pc", "computador", "windows", "desktop"])
                    if explicit_pc:
                        logging.info(f"[VOZ] {device_id}: PC Windows offline para comando explícito: '{text}'.")
                        reply = "Senhor Werik, seu computador Windows está desligado no momento. Deseja que eu ligue o PC via Wake-on-LAN?"
                    else:
                        logging.info(f"[VOZ] {device_id}: Windows offline e comando genérico '{text}'. Encaminhando ao Núcleo IA.")
                        win_intent = None
                if win_intent and (is_win_online or win_intent.get("action") in ["wake_on_lan"]):
                    logging.info(f"[VOZ] {device_id}: Intent Windows reconhecido: {win_intent}")
                    asyncio.create_task(_dispatch_pc_action(win_intent["action"], win_intent["params"]))
                    reply = win_intent["reply"]
            elif (intent := parse_timer_alarm_intent(text)):
                logging.info(f"[VOZ] {device_id}: Intent timer/alarme reconhecido: {intent}")
                if intent["type"] == "timer":
                    msg = {"type": "custom", "payload": {"event": "jarvis.timer", "seconds": intent["seconds"], "label": intent["label"]}}
                    await ws.send_str(json.dumps(msg))
                elif intent["type"] == "alarm":
                    msg = {"type": "custom", "payload": {"event": "jarvis.alarm", "hour": intent["hour"], "minute": intent["minute"], "label": intent["label"]}}
                    await ws.send_str(json.dumps(msg))
                elif intent["type"] == "timer_action":
                    msg = {"type": "custom", "payload": {"event": "jarvis.timer_action", "action": intent["action"]}}
                    await ws.send_str(json.dumps(msg))
                elif intent["type"] == "alarm_action":
                    msg = {"type": "custom", "payload": {"event": "jarvis.alarm_action", "action": intent["action"]}}
                    await ws.send_str(json.dumps(msg))
                reply = intent["reply"]
            else:
                try:
                    reply = await _chat(session, text, device_id)
                except Exception as chat_error:
                    logging.warning(f"[VOZ] OpenClaw request failed ({type(chat_error).__name__}).")
                    reply = MODEL_FAILURE_SENTINEL

                model_failed = (reply == MODEL_FAILURE_SENTINEL)
                if model_failed:
                    reply = "Desculpe, senhor, estou com instabilidade temporária na minha inteligência central."
                else:
                    clean_reply, was_tool = parse_and_execute_llm_tool(reply, active_sessions)
                    reply = clean_reply

            if stop_tts_requested.get(device_id, False):
                logging.info(f"[VOZ] {device_id}: Resposta cancelada antes do TTS devido a stop_tts.")
                return

            logging.info(f"[VOZ] Resposta: '{reply[:100]}'")
            try:
                from unified_memory import memory_mgr
                asyncio.create_task(memory_mgr.add_dialogue(device_id, "esfera", "assistant", reply))
            except Exception as ex_m:
                logging.warning(f"[MEMORY] Falha ao registrar resposta do assistente: {ex_m}")

            await ws.send_str(json.dumps({"type": "emotion", "emotion": "speaking"}))

            pcm_out = await _tts_pcm(session, reply)

            if pcm_out:
                tts_mute_until[device_id] = time.time() + (len(pcm_out) / 32000.0) + 1.8
                chunk_size = 2048
                t_send_start = time.time()
                for i in range(0, len(pcm_out), chunk_size):
                    if stop_tts_requested.get(device_id, False):
                        logging.info(f"[VOZ] {device_id}: TTS interrompido no envio por stop_tts.")
                        break
                    await ws.send_bytes(pcm_out[i:i + chunk_size])
                    await asyncio.sleep(0.025)

                t_send_elapsed = time.time() - t_send_start
                # 16000 Hz mono 16-bit = 32000 bytes/sec
                audio_duration = len(pcm_out) / 32000.0
                remaining_play = max(0.0, audio_duration - t_send_elapsed)

                if not stop_tts_requested.get(device_id, False):
                    logging.info(f"[VOZ] TTS enviado ({len(pcm_out)}b / {audio_duration:.1f}s). Aguardando reproducao ({remaining_play:.1f}s)...")
                    while remaining_play > 0 and not stop_tts_requested.get(device_id, False):
                        step = min(0.2, remaining_play)
                        await asyncio.sleep(step)
                        remaining_play -= step

            else:
                logging.warning("[VOZ] Sem audio TTS (endpoint /api/tts_pcm falhou).")

            if not stop_tts_requested.get(device_id, False):
                await ws.send_str(json.dumps({"type": "tts", "state": "end"}))
                await asyncio.sleep(0.4)

            tts_mute_until[device_id] = time.time() + 1.5
            st_clean = audio_state.get(device_id)
            if st_clean:
                st_clean["buf"] = bytearray()
                st_clean["speaking"] = False
                st_clean["silence_start"] = 0.0
            wake_state.pop(device_id, None)
            followup_task = followup_tasks.pop(device_id, None)
            if followup_task and followup_task is not asyncio.current_task():
                followup_task.cancel()

            if not stop_tts_requested.get(device_id, False):
                await ws.send_str(json.dumps({"type": "emotion", "emotion": "standby"}))
                logging.info(f"[VOZ] {device_id}: Resposta reproduzida integralmente -> Esfera em Standby.")

    except asyncio.CancelledError:
        logging.info(f"[VOZ] {device_id}: process_utterance cancelado com sucesso por Barge-In.")
        raise
    except Exception as e:
        logging.error(f"[VOZ] Erro no pipeline: {type(e).__name__}: {repr(e)}")
    finally:
        processing_state[device_id] = False
        if active_utterance_tasks.get(device_id) is asyncio.current_task():
            active_utterance_tasks.pop(device_id, None)





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

    if processing_state.get(device_id) or time.time() < tts_mute_until.get(device_id, 0.0):
        st_m = audio_state.get(device_id)
        if st_m:
            st_m["buf"] = bytearray()
            st_m["speaking"] = False
            st_m["silence_start"] = 0.0
        return

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



    active_vad = 1200 if (time.time() - wake_state.get(device_id, 0.0) <= FOLLOWUP_SEC) else VAD_RMS
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
    eff_max_sec = MAX_UTTERANCE_SEC if (time.time() - wake_state.get(device_id, 0.0) <= FOLLOWUP_SEC) else 5.5
    is_max_cut = st["speaking"] and len(st["buf"]) >= int(eff_max_sec * BYTES_PER_SEC)

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



    ua = request.headers.get("User-Agent", "").lower()
    if "python" in ua:
        device_id = "jarvis_windows_pc"
    else:
        device_id = "jarvis_sphere_esp32s3"
    active_sessions[device_id] = ws
    logging.info(f"[WS] Conexão WebSocket estabelecida: {device_id} (UA={ua})")



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
                    if device_id in ("pc-werik-workstation", "jarvis_windows_pc"):
                        active_sessions["pc-werik-workstation"] = ws
                        active_sessions["jarvis_windows_pc"] = ws
                    ap = data.get("audio_params", {})
                    logging.info(f"[WS] hello de {device_id} | audio_params={ap}")
                    await ws.send_str(json.dumps({
                        "type": "hello",
                        "transport": "websocket",
                        "audio_params": {"format": "opus", "sample_rate": SAMPLE_RATE, "channels": 1, "frame_duration": 60}
                    }))

                elif msg_type == "voice_start":
                    logging.info(f"[VOZ] {device_id}: voice_start recebido (TAP-TO-TALK / Fala iniciada).")
                    st = audio_state.setdefault(device_id, {"buf": bytearray(), "speaking": False, "silence_start": 0.0})
                    st["speaking"] = True
                    st["silence_start"] = 0.0
                    st["buf"] = bytearray()
                    wake_state[device_id] = time.time()
                    try:
                        await ws.send_str(json.dumps({"type": "wakeup"}))
                        await ws.send_str(json.dumps({"type": "emotion", "emotion": "listening"}))
                    except Exception:
                        pass

                elif msg_type == "stop_tts":
                    logging.info(f"[WS] {device_id}: stop_tts recebido da esfera.")
                    await interrupt_tts_and_listen(ws, device_id)

                elif msg_type == "voice_end":
                    if processing_state.get(device_id) or time.time() < tts_mute_until.get(device_id, 0.0):
                        logging.info(f"[VOZ] {device_id}: voice_end ignorado (TTS em andamento/cooldown).")
                        continue
                    st = audio_state.get(device_id)
                    buf_len = len(st.get("buf", [])) if st else 0
                    logging.info(f"[VOZ] {device_id}: voice_end recebido! buf={buf_len}b")
                    if st and st.get("speaking") and buf_len >= 3200:
                        pcm = bytes(st["buf"])
                        st["buf"] = bytearray()
                        st["speaking"] = False
                        st["silence_start"] = 0.0

                        logging.info(f"[VOZ] {device_id}: Despachando nova fala ({len(pcm)}b) para STT Cascata!")
                        processing_state[device_id] = True
                        stop_tts_requested[device_id] = False
                        task = asyncio.create_task(process_utterance(ws, device_id, pcm))
                        active_utterance_tasks[device_id] = task

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

                    elif event == "tuya_toggle":
                        target_state = bool(payload.get("state", not _tuya_last_state))
                        logging.info(f"[WS] {device_id}: tuya_toggle recebido da Esfera -> acionando Tuya state={target_state}")
                        asyncio.create_task(_tuya_openapi_set_both(target_state))
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


async def handle_whatsapp(request: web.Request) -> web.Response:
    try:
        body = await request.json()
        device_id = body.get("device_id", "jarvis_sphere_esp32s3")
        sender = str(body.get("sender", "WhatsApp"))
        message = str(body.get("message", ""))
        time_str = str(body.get("time", ""))
        
        msg = {
            "type": "custom",
            "payload": {
                "event": "jarvis.whatsapp",
                "sender": sender,
                "message": message,
                "time": time_str
            }
        }
        sent_count = 0
        if device_id in active_sessions:
            ws = active_sessions[device_id]
            await ws.send_str(json.dumps(msg))
            sent_count += 1
        else:
            for dev, ws in list(active_sessions.items()):
                try:
                    await ws.send_str(json.dumps(msg))
                    sent_count += 1
                except Exception:
                    pass
        logging.info(f"[WHATSAPP] Mensagem enviada para {sent_count} esfera(s): {sender}: {message}")
        return web.json_response({"status": "success", "sent_to": sent_count, "sender": sender, "message": message, "time": time_str})
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=500)


async def handle_stop_tts(request: web.Request) -> web.Response:
    try:
        device_id = "jarvis_sphere_esp32s3"
        stop_tts_requested[device_id] = True
        wake_state.pop(device_id, None)
        followup_task = followup_tasks.pop(device_id, None)
        if followup_task and followup_task is not asyncio.current_task():
            followup_task.cancel()
        st = audio_state.get(device_id)
        if st:
            st["buf"] = bytearray()
            st["speaking"] = False
        ws = active_sessions.get(device_id)
        if ws and not ws.closed:
            try:
                await ws.send_str(json.dumps({"type": "stop_tts"}))
                await ws.send_str(json.dumps({"type": "emotion", "emotion": "standby"}))
            except Exception:
                pass
        logging.info(f"[STOP_TTS] Comando de silêncio disparado via HTTP para {device_id}")
        return web.json_response({"status": "success", "message": "TTS stopped and sphere returned to standby"})
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=500)


async def stream_pcm_to_sphere(device_id: str, pcm_bytes: bytes, emotion: str = "speaking") -> Dict[str, Any]:
    """Transmite fluxo binário PCM 16kHz mono para o hardware da Esfera ESP32-S3 via WebSocket."""
    ws = active_sessions.get(device_id)
    if not ws or ws.closed:
        for dev, conn in active_sessions.items():
            if "sphere" in dev and not conn.closed:
                ws = conn
                device_id = dev
                break
    if not ws or ws.closed:
        return {"status": "error", "message": f"Dispositivo '{device_id}' não está conectado no WebSocket."}

    stop_tts_requested[device_id] = False
    try:
        if emotion:
            await ws.send_str(json.dumps({"type": "emotion", "emotion": emotion}))
    except Exception:
        pass

    chunk_size = 2048
    t_send_start = time.time()
    for i in range(0, len(pcm_bytes), chunk_size):
        if stop_tts_requested.get(device_id, False):
            logging.info(f"[AUDIO-STREAM] {device_id}: Stream interrompido por stop_tts.")
            break
        await ws.send_bytes(pcm_bytes[i:i + chunk_size])
        await asyncio.sleep(0.025)

    t_send_elapsed = time.time() - t_send_start
    audio_duration = len(pcm_bytes) / 32000.0
    remaining_play = max(0.0, audio_duration - t_send_elapsed)

    while remaining_play > 0 and not stop_tts_requested.get(device_id, False):
        step = min(0.2, remaining_play)
        await asyncio.sleep(step)
        remaining_play -= step

    if not stop_tts_requested.get(device_id, False):
        try:
            await ws.send_str(json.dumps({"type": "tts", "state": "end"}))
            await asyncio.sleep(0.4)
            await ws.send_str(json.dumps({"type": "emotion", "emotion": "standby"}))
        except Exception:
            pass

    return {
        "status": "success",
        "device_id": device_id,
        "bytes_sent": len(pcm_bytes),
        "duration_seconds": round(audio_duration, 2)
    }


async def convert_audio_to_pcm16(raw_bytes: bytes) -> bytes:
    """Converte qualquer formato de áudio (MP3, WAV, OGG, etc.) para PCM 16kHz Mono 16-bit com ffmpeg."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-i", "pipe:0", "-f", "s16le", "-acodec", "pcm_s16le", "-ac", "1", "-ar", "16000", "pipe:1",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate(input=raw_bytes)
        if proc.returncode == 0 and len(stdout) > 0:
            return stdout
        logging.warning(f"[AUDIO-CONVERT] ffmpeg retornou erro ou vazio: {stderr.decode('utf-8', errors='ignore')[:150]}")
    except Exception as e:
        logging.error(f"[AUDIO-CONVERT] Falha ao invocar ffmpeg: {e}")
    return raw_bytes


async def handle_speak(request: web.Request) -> web.Response:
    """API pública HTTP para outros projetos enviarem texto para a Esfera falar em voz alta."""
    try:
        text = ""
        emotion = "speaking"
        device_id = "jarvis_sphere_esp32s3"

        if request.can_read_body:
            content_type = request.headers.get("Content-Type", "")
            if "application/json" in content_type:
                body = await request.json()
                text = str(body.get("text", "")).strip()
                emotion = str(body.get("emotion", "speaking")).strip()
                device_id = str(body.get("device_id", device_id)).strip()
            else:
                text = (await request.text()).strip()

        if not text and "text" in request.query:
            text = request.query["text"].strip()
            emotion = request.query.get("emotion", emotion)
            device_id = request.query.get("device_id", device_id)

        if not text:
            return web.json_response({"status": "error", "message": "O campo 'text' é obrigatório."}, status=400)

        logging.info(f"[HTTP-SPEAK] Solicitação de fala recebida para {device_id}: '{text[:60]}'...")
        async with ClientSession() as s:
            pcm_out = await _tts_pcm(s, text)

        if not pcm_out:
            return web.json_response({"status": "error", "message": "Falha na síntese TTS via /api/tts_pcm."}, status=500)

        result = await stream_pcm_to_sphere(device_id, pcm_out, emotion=emotion)
        result["text"] = text
        return web.json_response(result)
    except Exception as e:
        logging.error(f"[HTTP-SPEAK] Erro: {e}")
        return web.json_response({"status": "error", "message": str(e)}, status=500)


async def handle_play_audio(request: web.Request) -> web.Response:
    """API pública HTTP para outros projetos enviarem arquivos de áudio (MP3, WAV, PCM) para reprodução na Esfera."""
    try:
        device_id = request.query.get("device_id", "jarvis_sphere_esp32s3")
        emotion = request.query.get("emotion", "speaking")
        content_type = request.headers.get("Content-Type", "")
        raw_audio = b""

        if "application/json" in content_type:
            body = await request.json()
            device_id = str(body.get("device_id", device_id)).strip()
            emotion = str(body.get("emotion", emotion)).strip()
            if "audio_base64" in body:
                raw_audio = base64.b64decode(body["audio_base64"])
            elif "url" in body:
                url = body["url"]
                logging.info(f"[HTTP-PLAY] Baixando áudio da URL: {url}")
                async with ClientSession() as s:
                    async with s.get(url, timeout=30) as r:
                        if r.status == 200:
                            raw_audio = await r.read()
                        else:
                            return web.json_response({"status": "error", "message": f"Falha ao baixar áudio da URL: HTTP {r.status}"}, status=400)
        else:
            raw_audio = await request.read()

        if not raw_audio:
            return web.json_response({"status": "error", "message": "Nenhum dado de áudio recebido."}, status=400)

        logging.info(f"[HTTP-PLAY] Recebidos {len(raw_audio)} bytes de áudio para {device_id}. Convertendo para PCM 16kHz...")
        pcm_bytes = await convert_audio_to_pcm16(raw_audio)
        result = await stream_pcm_to_sphere(device_id, pcm_bytes, emotion=emotion)
        return web.json_response(result)
    except Exception as e:
        logging.error(f"[HTTP-PLAY] Erro: {e}")
        return web.json_response({"status": "error", "message": str(e)}, status=500)


try:
    from alexa_service import alexa_bridge
except ImportError:
    alexa_bridge = None


async def handle_alexa_pair_start(request: web.Request) -> web.Response:
    """Inicia o proxy de pareamento na porta 8092 para o usuário fazer login na Amazon."""
    if not alexa_bridge:
        return web.json_response({"status": "error", "message": "Módulo Alexa não disponível"}, status=500)
    try:
        url = await alexa_bridge.start_pairing_proxy()
        return web.json_response({
            "status": "ready",
            "message": "Abra a URL no seu navegador para fazer login na Amazon com a conta da sua Echo Dot 3.",
            "pairing_url": url,
            "is_authenticated": alexa_bridge.is_authenticated
        })
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=500)


async def handle_alexa_debug(request: web.Request) -> web.Response:
    if not alexa_bridge or not alexa_bridge.login:
        return web.json_response({"error": "No login"})
    l = alexa_bridge.login
    return web.json_response({
        "auth_code": bool(l.authorization_code),
        "auth_code_val": l.authorization_code,
        "access_token": bool(l.access_token),
        "refresh_token": bool(l.refresh_token),
        "code_verifier": bool(l.code_verifier),
        "deviceid": l.deviceid,
        "customer_id": l.customer_id,
        "is_authenticated": alexa_bridge.is_authenticated,
        "devices_count": len(alexa_bridge.devices)
    })


async def handle_alexa_redeem(request: web.Request) -> web.Response:
    if not alexa_bridge:
        return web.json_response({"error": "alexa_bridge não inicializado"}, status=500)
    success = await alexa_bridge.complete_login_flow()
    return web.json_response({
        "success": success,
        "is_authenticated": alexa_bridge.is_authenticated,
        "device_count": len(alexa_bridge.devices),
        "devices": [
            d.get("accountName", d.get("friendlyName", "Dispositivo"))
            for d in alexa_bridge.devices
        ]
    })


async def handle_alexa_pair_status(request: web.Request) -> web.Response:
    """Retorna o status atual da autenticação da Alexa e dispositivos conectados."""
    if not alexa_bridge:
        return web.json_response({"status": "error", "message": "Módulo Alexa não disponível"}, status=500)
    return web.json_response({
        "is_authenticated": alexa_bridge.is_authenticated,
        "device_count": len(alexa_bridge.devices),
        "devices": [
            {"name": d.get("accountName"), "family": d.get("deviceFamily"), "online": d.get("online")}
            for d in alexa_bridge.devices
        ]
    })


async def handle_alexa_devices(request: web.Request) -> web.Response:
    """Lista todos os dispositivos Echo vinculados à conta da Amazon."""
    if not alexa_bridge:
        return web.json_response({"status": "error", "message": "Módulo Alexa não disponível"}, status=500)
    devs = await alexa_bridge.refresh_devices()
    return web.json_response({
        "status": "success",
        "count": len(devs),
        "devices": [
            {"name": d.get("accountName"), "family": d.get("deviceFamily"), "serial": d.get("serialNumber"), "online": d.get("online")}
            for d in devs
        ]
    })


async def handle_alexa_speak(request: web.Request) -> web.Response:
    """Envia texto para a Echo Dot 3 falar em voz alta."""
    if not alexa_bridge:
        return web.json_response({"status": "error", "message": "Módulo Alexa não disponível"}, status=500)
    try:
        text = ""
        device = None
        if request.can_read_body:
            content_type = request.headers.get("Content-Type", "")
            if "application/json" in content_type:
                body = await request.json()
                text = str(body.get("text", "")).strip()
                device = body.get("device")
            else:
                text = (await request.text()).strip()
        if not text and "text" in request.query:
            text = request.query["text"].strip()
            device = request.query.get("device", device)

        if not text:
            return web.json_response({"status": "error", "message": "O campo 'text' é obrigatório."}, status=400)

        res = await alexa_bridge.speak(text, device)
        return web.json_response(res)
    except Exception as e:
        return web.json_response({"status": "error", "message": str(e)}, status=500)



async def handle_skills_page(request):
    try:
        with open("/DATA/AppData/jarvis-hud/web/skills.html", "r", encoding="utf-8") as f:
            return web.Response(text=f.read(), content_type="text/html")
    except Exception:
        return web.Response(text="<h1>Skills Marketplace</h1>", content_type="text/html")



async def handle_skills_api_proxy(request):
    try:
        async with ClientSession() as session:
            url = f"{JARVIS_HUD_URL}{request.path}"
            if request.query_string:
                url += f"?{request.query_string}"
            async with session.request(request.method, url) as resp:
                data = await resp.read()
                return web.Response(body=data, status=resp.status, content_type=resp.content_type)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


def create_app() -> web.Application:

    app = web.Application()

    app.router.add_get("/ws", handle_websocket)
    app.router.add_get("/mic_monitor", handle_mic_monitor_page)
    app.router.add_get("/ws/mic_monitor", handle_mic_monitor_ws)

    app.router.add_post("/api/jarvis/show_screen", handle_show_screen)
    app.router.add_post("/api/jarvis/tuya", handle_tuya_http)
    app.router.add_get("/api/devices/registry", handle_devices_registry)

    async def handle_election_show(request: web.Request) -> web.Response:
        data = await fetch_tse_election_data()
        msg = {
            "type": "custom",
            "payload": {
                "event": "jarvis.election",
                "apurado": data.get("apurado", "0%"),
                "hora": data.get("hora", ""),
                "c1": data.get("c1", {}),
                "c2": data.get("c2", {}),
                "show": True
            }
        }
        for ws in list(active_sessions.values()):
            if not ws.closed:
                await ws.send_str(json.dumps(msg))
        return web.json_response({"status": "success", "data": data})

    app.router.add_post("/api/jarvis/election/show", handle_election_show)
    app.router.add_get("/api/jarvis/election/data", lambda r: web.json_response(_LATEST_ELECTION_DATA))
    app.on_startup.append(_election_poller_loop)

    app.router.add_post("/api/jarvis/emotion", handle_emotion)

    app.router.add_post("/api/jarvis/record", handle_record)

    app.router.add_get("/firmware.bin", handle_get_firmware)
    app.router.add_get("/skills", handle_skills_page)
    app.router.add_get("/skills.html", handle_skills_page)
    app.router.add_get("/marketplace", handle_skills_page)
    app.router.add_get("/api/skills/{tail:.*}", handle_skills_api_proxy)
    app.router.add_post("/api/skills/{tail:.*}", handle_skills_api_proxy)


    app.router.add_post("/api/jarvis/firmware/upload", handle_upload_firmware)

    app.router.add_post("/api/jarvis/ota/trigger", handle_ota_trigger)
    app.router.add_post("/api/jarvis/timer", handle_timer)
    app.router.add_post("/api/jarvis/alarm", handle_alarm)
    app.router.add_post("/api/jarvis/whatsapp", handle_whatsapp)
    app.router.add_post("/api/jarvis/stop_tts", handle_stop_tts)
    app.router.add_post("/api/jarvis/speak", handle_speak)
    app.router.add_get("/api/jarvis/speak", handle_speak)
    app.router.add_post("/api/jarvis/play_audio", handle_play_audio)

    if alexa_bridge:
        async def _init_alexa_startup(a):
            asyncio.create_task(alexa_bridge.initialize())
        app.on_startup.append(_init_alexa_startup)

    app.router.add_post("/api/jarvis/alexa/pair/start", handle_alexa_pair_start)
    app.router.add_get("/api/jarvis/alexa/pair/start", handle_alexa_pair_start)
    app.router.add_get("/api/jarvis/alexa/pair/status", handle_alexa_pair_status)
    app.router.add_post("/api/jarvis/alexa/pair/redeem", handle_alexa_redeem)
    app.router.add_get("/api/jarvis/alexa/pair/redeem", handle_alexa_redeem)
    app.router.add_get("/api/jarvis/alexa/debug", handle_alexa_debug)
    app.router.add_get("/api/jarvis/alexa/devices", handle_alexa_devices)
    app.router.add_post("/api/jarvis/alexa/speak", handle_alexa_speak)
    app.router.add_get("/api/jarvis/alexa/speak", handle_alexa_speak)

    return app





if __name__ == "__main__":

    logging.info(f"[+] Screen Router + Voice Bridge na porta 8095 | Core={JARVIS_HUD_URL}")

    web.run_app(create_app(), host="0.0.0.0", port=8095)