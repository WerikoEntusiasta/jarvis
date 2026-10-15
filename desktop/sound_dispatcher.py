"""
J.A.R.V.I.S. Desktop Sound Dispatcher
Dispara reprodução simultânea de áudio TTS PCM nas caixas de som do Windows PC.
"""
import os
import sys
import time
import json
import io
import wave
import urllib.request
import threading

def play_pcm_on_pc(pcm_bytes: bytes, sample_rate: int = 16000):
    """Reproduz áudio PCM 16kHz mono nas caixas de som do Windows PC."""
    if not pcm_bytes or len(pcm_bytes) < 10:
        return
    try:
        import sounddevice as sd
        import numpy as np
        audio_int16 = np.frombuffer(pcm_bytes, dtype=np.int16)
        audio_float32 = audio_int16.astype(np.float32) / 32768.0
        sd.play(audio_float32, samplerate=sample_rate)
        sd.wait()
        return
    except Exception as e:
        print("[SOUND DISPATCHER] sounddevice error:", e)

    try:
        import winsound
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_bytes)
        winsound.PlaySound(buf.getvalue(), winsound.SND_MEMORY)
    except Exception as e:
        print("[SOUND DISPATCHER] winsound error:", e)

def fetch_and_play_tts(text: str):
    """Obtém áudio PCM do endpoint /api/tts_pcm e reproduz no PC."""
    if not text:
        return
    hosts = ["http://localhost:8080", "https://jarvis.werikspace.xyz", "http://${ZIMA_IP:-127.0.0.1}:8085", "http://127.0.0.1:8085", "http://127.0.0.1:8080"]
    for host in hosts:
        try:
            url = f"{host}/api/tts_pcm"
            payload = json.dumps({"text": text}).encode("utf-8")
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                if resp.status == 200:
                    pcm = resp.read()
                    if pcm and len(pcm) > 100:
                        play_pcm_on_pc(pcm)
                        return
        except Exception:
            pass

def play_tts_async(text: str):
    """Inicia reprodução assíncrona sem bloquear."""
    threading.Thread(target=fetch_and_play_tts, args=(text,), daemon=True, name="JarvisDualAudioPlay").start()
