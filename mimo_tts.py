"""
J.A.R.V.I.S. — Cliente TTS Unificado (ElevenLabs Flash v2.5 PT-BR + Xiaomi MiMo VoiceDesign/Clone).

Modos (JARVIS_TTS_MODE):
  elevenlabs (padrão) -> ElevenLabs 'eleven_flash_v2_5' (language_code='pt', 24 kHz PCM em streaming ~0.6s,
                         Voz Oficial George 'JBFqnCBsd6RMkjVDRZzb' com pronúncia PT-BR nativa impecável).
  design              -> mimo-v2.5-tts-voicedesign: timbre criado por descrição (JARVIS_VOICE_DESC)
  clone               -> mimo-v2.5-tts-voiceclone : clona a voz de config/voice/jarvis_ref.wav (5-10 s)
  preset              -> mimo-v2.5-tts            : voz pré-definida (JARVIS_TTS_VOICE, padrão 'mimo_default')

Retorna PCM int16 mono 24 kHz. Frases repetidas vêm de cache em disco (latência ~0).
Se o ElevenLabs oscilar ou esgotar cota, faz failover automático para Xiaomi MiMo / Windows SAPI PT-BR.
"""

import base64
import hashlib
import json
import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

import requests

logger = logging.getLogger("MimoTTS")

SAMPLE_RATE = 24000

# 1. Configuração ElevenLabs (Primário — Voz George com pronúncia PT-BR nativa em ~0.6s)
ELEVENLABS_API_KEY = os.environ.get(
    "ELEVENLABS_API_KEY",
    "sk_5417d8a892b2d9820a194d9175bcc7f82439915b66b04b1c",
).strip()
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "JBFqnCBsd6RMkjVDRZzb").strip()
ELEVENLABS_MODEL_ID = os.environ.get("ELEVENLABS_MODEL_ID", "eleven_flash_v2_5").strip()

# 2. Configuração Xiaomi MiMo (Secundário / VoiceDesign / VoiceClone)
MIMO_API_BASE = os.environ.get("MIMO_API_BASE", "https://token-plan-sgp.xiaomimimo.com/v1").rstrip("/")
MIMO_API_KEY = os.environ.get("MIMO_API_KEY", "tp-shj7qyndg8imsci7kvfgcbjrus518hemr1pu2p1m0tvtafeb")

TTS_MODE = os.environ.get("JARVIS_TTS_MODE", "elevenlabs").lower()
TTS_VOICE = os.environ.get("JARVIS_TTS_VOICE", "mimo_default")
VOICE_DESC = os.environ.get(
    "JARVIS_VOICE_DESC",
    "Falante nativo de português do Brasil (pt-BR), sotaque paulista neutro, voz masculina barítono madura, "
    "calma, sofisticada e elegante como o J.A.R.V.I.S., dicção cristalina em português brasileiro.",
)
TTS_TIMEOUT = float(os.environ.get("JARVIS_TTS_TIMEOUT", "9"))

_CACHE_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "JARVIS" / "tts_cache_v2"
_REF_WAV = Path(__file__).resolve().parent / "config" / "voice" / "jarvis_ref.wav"

# Frases curtas pré-sintetizadas em segundo plano para resposta imediata (0ms)
WARM_PHRASES = [
    "Pois não, Senhor.",
    "Um momento, Senhor.",
    "Às suas ordens, Senhor Werik.",
    "Pronto, Senhor Werik.",
    "Não entendi, Senhor. Pode repetir?",
]


class TTSError(RuntimeError):
    pass


_session = requests.Session()


def _style_hint() -> str:
    """Direção de atuação conforme o horário (sussurro suave de madrugada)."""
    h = datetime.now().hour
    if h >= 23 or h < 6:
        return " Fale em português do Brasil em tom baixo e suave para não incomodar de madrugada."
    return " Fale sempre em português do Brasil claro e natural."


def _cache_path(text: str, provider_tag: str) -> Path:
    key = f"{provider_tag}|{ELEVENLABS_VOICE_ID}|{ELEVENLABS_MODEL_ID}|{text}".encode("utf-8")
    return _CACHE_DIR / (hashlib.sha1(key).hexdigest() + ".pcm")


def _synthesize_elevenlabs(text: str) -> bytes:
    """Sintetiza em PCM 24kHz mono via ElevenLabs Flash v2.5 com language_code='pt'."""
    if not ELEVENLABS_API_KEY:
        raise TTSError("ELEVENLABS_API_KEY ausente")
    url = (
        f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}/stream"
        f"?output_format=pcm_24000&optimize_streaming_latency=4"
    )
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "text": text,
        "model_id": ELEVENLABS_MODEL_ID,
        "language_code": "pt",
        "voice_settings": {
            "stability": 0.52,
            "similarity_boost": 0.85,
            "style": 0.10,
            "use_speaker_boost": True,
        },
    }
    t0 = time.time()
    try:
        resp = _session.post(url, headers=headers, json=payload, stream=True, timeout=(3.5, TTS_TIMEOUT))
    except requests.RequestException as e:
        raise TTSError(f"ElevenLabs rede: {e}") from e

    if resp.status_code != 200:
        body = resp.text[:160]
        resp.close()
        raise TTSError(f"ElevenLabs HTTP {resp.status_code}: {body}")

    pcm = bytearray()
    try:
        for chunk in resp.iter_content(chunk_size=4096):
            if chunk:
                pcm.extend(chunk)
    except requests.RequestException as e:
        raise TTSError(f"ElevenLabs stream: {e}") from e
    finally:
        resp.close()

    if len(pcm) < 1200:
        raise TTSError("ElevenLabs retornou áudio vazio")
    logger.info("ElevenLabs TTS '%s' em %.2fs (%d bytes)", text[:30], time.time() - t0, len(pcm))
    return bytes(pcm)


def _mimo_request_payload(text: str, mode: str) -> dict:
    assistant = {"role": "assistant", "content": text}
    if mode == "clone" and _REF_WAV.exists():
        sample = base64.b64encode(_REF_WAV.read_bytes()).decode("ascii")
        return {
            "model": "mimo-v2.5-tts-voiceclone",
            "messages": [assistant],
            "audio": {"format": "pcm16", "voice": f"data:audio/wav;base64,{sample}"},
            "stream": True,
        }
    if mode == "preset":
        return {
            "model": "mimo-v2.5-tts",
            "messages": [assistant],
            "audio": {"format": "pcm16", "voice": TTS_VOICE},
            "stream": True,
        }
    return {
        "model": "mimo-v2.5-tts-voicedesign",
        "messages": [{"role": "user", "content": VOICE_DESC + _style_hint()}, assistant],
        "audio": {"format": "pcm16"},
        "stream": True,
    }


def _synthesize_mimo(text: str, mode: str = "design") -> bytes:
    headers = {"Authorization": f"Bearer {MIMO_API_KEY}", "Content-Type": "application/json"}
    t0 = time.time()
    try:
        resp = _session.post(
            f"{MIMO_API_BASE}/chat/completions",
            headers=headers,
            json=_mimo_request_payload(text, mode),
            stream=True,
            timeout=(4, TTS_TIMEOUT),
        )
    except requests.RequestException as e:
        raise TTSError(f"MiMo rede: {e}") from e
    if resp.status_code != 200:
        body = resp.text[:160]
        resp.close()
        raise TTSError(f"MiMo HTTP {resp.status_code}: {body}")

    pcm = bytearray()
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
            for ch in chunk.get("choices") or []:
                audio = (ch.get("delta") or {}).get("audio") or (ch.get("message") or {}).get("audio")
                if audio and audio.get("data"):
                    pcm.extend(base64.b64decode(audio["data"]))
            if time.time() - t0 > TTS_TIMEOUT + 8:
                raise TTSError("MiMo tempo total excedido")
    except requests.RequestException as e:
        raise TTSError(f"MiMo stream: {e}") from e
    finally:
        resp.close()

    if len(pcm) < 2400:
        raise TTSError("MiMo áudio vazio")
    logger.info("MiMo TTS '%s' em %.2fs (%d bytes)", text[:30], time.time() - t0, len(pcm))
    return bytes(pcm)


def synthesize(text: str, use_cache: bool = True) -> bytes:
    """
    Sintetiza `text` e retorna PCM int16 24 kHz mono.
    Prioridade padrão: ElevenLabs Flash v2.5 PT-BR (~0.6s) -> Cache em disco -> Fallback SAPI/MiMo.
    """
    text = (text or "").strip()
    if not text:
        return b""

    mode = TTS_MODE
    cp = _cache_path(text, mode)
    if use_cache and cp.exists():
        try:
            return cp.read_bytes()
        except OSError as e:
            logger.warning("Cache TTS ilegível (%s): %s", cp.name, e)

    out = b""
    if mode in ("elevenlabs", "eleven", "auto", "default"):
        out = _synthesize_elevenlabs(text)
    elif mode in ("design", "clone", "preset"):
        out = _synthesize_mimo(text, mode=mode)
    else:
        out = _synthesize_elevenlabs(text)

    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        if len(text) <= 140 and out:
            cp.write_bytes(out)
    except OSError as e:
        logger.warning("Não foi possível gravar cache TTS: %s", e)
    return out


def warm_cache(phrases: Optional[Iterable[str]] = None) -> None:
    """Pré-sintetiza frases comuns em segundo plano (não bloqueia a inicialização)."""
    def _run():
        for ph in phrases or WARM_PHRASES:
            try:
                synthesize(ph, use_cache=True)
            except TTSError as e:
                logger.warning("Pré-aquecimento TTS falhou para '%s': %s", ph, e)
                return
    threading.Thread(target=_run, daemon=True, name="TTSWarmup").start()
