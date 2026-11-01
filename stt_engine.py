"""J.A.R.V.I.S. Speech-to-Text (STT) Engine.

Primary: Groq Cloud Whisper (whisper-large-v3-turbo) - Ultra-fast (~300ms) and high accuracy.
Fallback: Local Faster-Whisper (Docker container or local endpoint) - 100% offline contingency.
"""

import base64
import io
import json
import logging
import os
import re
import socket
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

# Load environment if not already loaded
def _load_env_fallback():
    env_file = Path(__file__).resolve().parent / ".env"
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    if k.strip() not in os.environ:
                        os.environ[k.strip()] = v.strip()

_load_env_fallback()

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "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").strip()
GROQ_WHISPER_MODEL = os.environ.get("GROQ_WHISPER_MODEL", "whisper-large-v3-turbo").strip()
LOCAL_WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "Systran/faster-whisper-tiny").strip()

HALLUCINATIONS = [
    r"subtitles by",
    r"legendas pela comunidade",
    r"obrigado por assistir",
    r"inscreva-se no canal",
    r"curta e compartilhe",
    r"deixe seu like",
    r"amara\.org",
    r"^[\s\.\,\-\?!]+$",
    r"transcricao por",
    r"tchau tchau",
    r"ate a proxima",
    r"^legenda.*",
]

def clean_hallucinations(text: str) -> str:
    if not text:
        return ""
    t = text.strip()
    if re.search(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]", t):
        return ""
    for pat in HALLUCINATIONS:
        if re.search(pat, t, re.IGNORECASE):
            return ""
    if len(t) < 2:
        return ""
    return t

def detect_audio_format(data: bytes) -> tuple[str, str]:
    """Returns (filename, content_type) based on magic bytes."""
    if data.startswith(b"RIFF"):
        return "audio.wav", "audio/wav"
    elif data.startswith(b"ID3") or (len(data) >= 2 and data[:2] in [b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"]):
        return "audio.mp3", "audio/mp3"
    elif data.startswith(b"OggS"):
        return "audio.ogg", "audio/ogg"
    elif data.startswith(b"\x1a\x45\xdf\xa3"):
        return "audio.webm", "audio/webm"
    return "audio.wav", "audio/wav"

def pcm_to_wav(pcm_bytes: bytes, sample_rate: int = 16000, channels: int = 1, sampwidth: int = 2) -> bytes:
    """Encapsulates raw PCM into standard WAV format buffer."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()

def transcribe_groq(audio_bytes: bytes, language: str = "pt", prompt: str = "J.A.R.V.I.S., assistente Jarvis, clima, horas, previsao do tempo, Catanduva, Spotify.") -> str:
    """Tier 1: Groq Cloud Whisper STT."""
    if not GROQ_API_KEY:
        return ""

    filename, content_type = detect_audio_format(audio_bytes)
    boundary = f"----groqstt{int(time.time() * 1000)}"
    nl = b"\r\n"
    parts = [
        b"--" + boundary.encode() + nl + b'Content-Disposition: form-data; name="model"' + nl + nl + GROQ_WHISPER_MODEL.encode() + nl,
        b"--" + boundary.encode() + nl + b'Content-Disposition: form-data; name="language"' + nl + nl + language.encode() + nl,
        b"--" + boundary.encode() + nl + b'Content-Disposition: form-data; name="temperature"' + nl + nl + b"0.0" + nl,
    ]
    if prompt:
        parts.append(b"--" + boundary.encode() + nl + b'Content-Disposition: form-data; name="prompt"' + nl + nl + prompt.encode("utf-8") + nl)
    parts.extend([
        b"--" + boundary.encode() + nl + f'Content-Disposition: form-data; name="file"; filename="{filename}"'.encode() + nl + f'Content-Type: {content_type}'.encode() + nl + nl,
        audio_bytes,
        nl + b"--" + boundary.encode() + b"--" + nl
    ])
    body = b"".join(parts)

    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "User-Agent": "JARVIS-Core/1.0"
    }

    req = urllib.request.Request("https://api.groq.com/openai/v1/audio/transcriptions", data=body, headers=headers)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                text = (data.get("text") or "").strip()
                cleaned = clean_hallucinations(text)
                if cleaned:
                    logging.info(f"[STT-Groq] Transcrito em {time.time()-t0:.2f}s: {cleaned!r}")
                    return cleaned
    except Exception as e:
        logging.warning(f"[STT-Groq] Falha ou timeout ({time.time()-t0:.2f}s): {e}")

    return ""

def _is_port_open(host: str, port: int, timeout: float = 0.8) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False

def get_active_local_whisper_endpoint() -> str:
    """Discovers reachable local whisper endpoint quickly without hanging."""
    custom_url = os.environ.get("WHISPER_URL")
    if custom_url:
        return f"{custom_url.rstrip('/')}/v1/audio/transcriptions"

    candidates = [
        ("172.17.0.2", 8000, "http://172.17.0.2:8000/v1/audio/transcriptions"),
        ("127.0.0.1", 8000, "http://127.0.0.1:8000/v1/audio/transcriptions"),
        ("45.167.187.80", 8000, "http://45.167.187.80:8000/v1/audio/transcriptions"),
    ]
    for host, port, url in candidates:
        if _is_port_open(host, port, timeout=0.8):
            return url
    return ""

def transcribe_local(audio_bytes: bytes, language: str = "pt") -> str:
    """Tier 2: Local Faster-Whisper Fallback."""
    ep = get_active_local_whisper_endpoint()
    if not ep:
        logging.warning("[STT-LocalWhisper] Nenhum endpoint Whisper local acessivel no momento.")
        return ""

    filename, content_type = detect_audio_format(audio_bytes)
    boundary = f"----localwhisper{int(time.time() * 1000)}"
    nl = b"\r\n"
    parts = [
        b"--" + boundary.encode() + nl + b'Content-Disposition: form-data; name="model"' + nl + nl + LOCAL_WHISPER_MODEL.encode() + nl,
        b"--" + boundary.encode() + nl + b'Content-Disposition: form-data; name="language"' + nl + nl + language.encode() + nl,
        b"--" + boundary.encode() + nl + f'Content-Disposition: form-data; name="file"; filename="{filename}"'.encode() + nl + f'Content-Type: {content_type}'.encode() + nl + nl,
        audio_bytes,
        nl + b"--" + boundary.encode() + b"--" + nl
    ]
    body = b"".join(parts)
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}

    t0 = time.time()
    try:
        req = urllib.request.Request(ep, data=body, headers=headers)
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                text = (data.get("text") or "").strip()
                cleaned = clean_hallucinations(text)
                if cleaned:
                    logging.info(f"[STT-LocalWhisper] Transcrito em {time.time()-t0:.2f}s via {ep}: {cleaned!r}")
                    return cleaned
    except Exception as e:
        logging.warning(f"[STT-LocalWhisper] Falha ao transcrever via {ep}: {e}")

    return ""

def transcribe_audio(audio_data, language: str = "pt", is_pcm: bool = False) -> str:
    """Transcribes audio using Groq Whisper with automatic fallback to Xiaomi MiMo ASR and Local Whisper."""
    if isinstance(audio_data, (str, Path)):
        with open(audio_data, "rb") as f:
            audio_bytes = f.read()
    elif is_pcm or (isinstance(audio_data, (bytes, bytearray)) and not (audio_data.startswith(b"RIFF") or audio_data.startswith(b"ID3"))):
        audio_bytes = pcm_to_wav(bytes(audio_data))
    else:
        audio_bytes = bytes(audio_data)

    # 1. Primary: Groq Whisper Cloud
    res = transcribe_groq(audio_bytes, language=language)
    if res:
        return res

    # 2. Redundant Cloud Fallback: Xiaomi MiMo ASR (mimo-v2.5-asr)
    logging.info("[STT] Acionando contingencia Tier 2: Xiaomi MiMo ASR (TokenPlan)...")
    try:
        from mimo_brain import transcribe_mimo_asr
        mimo_res = transcribe_mimo_asr(audio_bytes)
        cleaned = clean_hallucinations(mimo_res)
        if cleaned:
            logging.info(f"[STT-MiMo] Transcrito com sucesso: {cleaned!r}")
            return cleaned
    except Exception as e:
        logging.warning(f"[STT-MiMo] Falha: {e}")

    # 3. Fallback Tier 3: Local Whisper
    logging.info("[STT] Acionando contingencia Tier 3: Whisper Local...")
    res = transcribe_local(audio_bytes, language=language)
    return res or ""

async def transcribe_async(session, audio_bytes: bytes, language: str = "pt") -> str:
    """Asynchronous pipeline: Groq Whisper Cloud -> Xiaomi MiMo ASR -> Local Whisper."""
    filename, content_type = detect_audio_format(audio_bytes)

    # 1. Groq Whisper
    try:
        boundary = f"----groq{int(time.time()*1000)}"
        nl = b"\r\n"
        parts = [
            b"--" + boundary.encode() + nl + b'Content-Disposition: form-data; name="model"' + nl + nl + GROQ_WHISPER_MODEL.encode() + nl,
            b"--" + boundary.encode() + nl + b'Content-Disposition: form-data; name="language"' + nl + nl + language.encode() + nl,
            b"--" + boundary.encode() + nl + b'Content-Disposition: form-data; name="temperature"' + nl + nl + b"0.0" + nl,
            b"--" + boundary.encode() + nl + b'Content-Disposition: form-data; name="prompt"' + nl + nl + b"J.A.R.V.I.S., assistente Jarvis, clima, horas, previsao do tempo, Catanduva, Spotify." + nl,
            b"--" + boundary.encode() + nl + f'Content-Disposition: form-data; name="file"; filename="{filename}"'.encode() + nl + f'Content-Type: {content_type}'.encode() + nl + nl,
            audio_bytes,
            nl + b"--" + boundary.encode() + b"--" + nl
        ]
        body = b"".join(parts)
        headers = {
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "User-Agent": "JARVIS-Core/1.0"
        }
        t0 = time.time()
        async with session.post("https://api.groq.com/openai/v1/audio/transcriptions",
                                data=body, headers=headers, timeout=5.0) as r:
            if r.status == 200:
                j = await r.json(content_type=None)
                txt = clean_hallucinations((j.get("text") or "").strip())
                if txt:
                    logging.info(f"[STT-Async:Groq] ({time.time()-t0:.2f}s) Transcrito: {txt!r}")
                    return txt
            else:
                err = await r.text()
                logging.warning(f"[STT-Async:Groq] HTTP {r.status}: {err[:150]}")
    except Exception as e:
        logging.warning(f"[STT-Async:Groq] Falha ou timeout: {e}")

    # 2. Redundant Cloud Fallback: Xiaomi MiMo ASR (mimo-v2.5-asr)
    try:
        from mimo_brain import MIMO_API_BASE, MIMO_API_KEY
        if MIMO_API_KEY:
            t0 = time.time()
            wav_data = audio_bytes
            if not wav_data.startswith(b"RIFF"):
                wav_data = pcm_to_wav(audio_bytes)
            b64_data = base64.b64encode(wav_data).decode("utf-8")
            mimo_payload = {
                "model": "mimo-v2.5-asr",
                "messages": [{
                    "role": "user",
                    "content": [{"type": "input_audio", "input_audio": {"data": b64_data, "format": "wav"}}]
                }]
            }
            mimo_headers = {
                "Authorization": f"Bearer {MIMO_API_KEY}",
                "Content-Type": "application/json"
            }
            async with session.post(f"{MIMO_API_BASE}/chat/completions", json=mimo_payload, headers=mimo_headers, timeout=8.0) as r:
                if r.status == 200:
                    j = await r.json(content_type=None)
                    choice = j.get("choices", [{}])[0]
                    txt = clean_hallucinations((choice.get("message", {}).get("content") or "").strip())
                    if txt and not txt.startswith(("。", "...", "silence")):
                        logging.info(f"[STT-Async:MiMo] ({time.time()-t0:.2f}s) Transcrito: {txt!r}")
                        return txt
    except Exception as e:
        logging.warning(f"[STT-Async:MiMo] Falha: {e}")

    # 3. Fallback Tier 3: Local Whisper
    logging.info("[STT-Async] Groq e MiMo indisponiveis, acionando fallback Tier 3: Whisper Local...")
    ep = get_active_local_whisper_endpoint() or "http://172.17.0.2:8000/v1/audio/transcriptions"
    try:
        t0 = time.time()
        boundary = f"----localwhisper{int(time.time()*1000)}"
        nl = bytes([13, 10])
        parts = [
            b"--" + boundary.encode() + nl + b'Content-Disposition: form-data; name="model"' + nl + nl + LOCAL_WHISPER_MODEL.encode() + nl,
            b"--" + boundary.encode() + nl + b'Content-Disposition: form-data; name="language"' + nl + nl + language.encode() + nl,
            b"--" + boundary.encode() + nl + f'Content-Disposition: form-data; name="file"; filename="{filename}"'.encode() + nl + f'Content-Type: {content_type}'.encode() + nl + nl,
            audio_bytes,
            nl + b"--" + boundary.encode() + b"--" + nl
        ]
        body = b"".join(parts)
        headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
        
        async with session.post(ep, data=body, headers=headers, timeout=15.0) as r:
            if r.status == 200:
                j = await r.json(content_type=None)
                txt = clean_hallucinations((j.get("text") or "").strip())
                if txt:
                    logging.info(f"[STT-Async:LocalWhisper] ({time.time()-t0:.2f}s) Transcrito: {txt!r}")
                    return txt
    except Exception as e:
        logging.warning(f"[STT-Async:LocalWhisper] Falha: {e}")

    return ""
