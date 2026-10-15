"""
J.A.R.V.I.S. Native Desktop Audio Listener (Background Voice Engine)
Permite que o JARVIS e a Dynamic Island ouçam o usuário continuamente,
mesmo com TODAS as abas e navegadores fechados!
- Captura de microfone nativa com sounddevice (16kHz mono)
- Voice Activity Detection (VAD) inteligente por energia acústica RMS
- 1.5s de buffer de silêncio pós-fala antes do envio
- Transcrição ultra-rápida via Faster-Whisper Small local na GPU (CUDA)
- Processamento e resposta integrados com o núcleo do JARVIS
"""

import io
import os
import time
import json
import wave
import ctypes
import urllib.request
import threading
import numpy as np
import sounddevice as sd
from typing import Callable, Optional

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ISLAND_SETTINGS_PATH = os.path.join(ROOT_DIR, "config", "island_settings.json")
VOICE_LOG_PATH = os.path.join(ROOT_DIR, "logs", "voice.log")
CORE_BASE_URL = os.environ.get("JARVIS_CORE_URL", "https://jarvis.werikspace.xyz")


def _vlog(msg: str):
    try:
        os.makedirs(os.path.dirname(VOICE_LOG_PATH), exist_ok=True)
        with open(VOICE_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    except Exception:
        pass

def _load_island_settings() -> dict:
    try:
        with open(ISLAND_SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _resolve_mic_device():
    """Resolve o microfone do Jarvis: prefere o salvo (island_settings.mic_device);
    senão busca auto o FIFINE K670; senão o default do sistema."""
    settings = _load_island_settings()
    want = str(settings.get("mic_device", "")).strip().lower()
    try:
        devs = sd.query_devices()
        if want:
            for i, d in enumerate(devs):
                if d.get("max_input_channels", 0) > 0 and want in str(d.get("name", "")).lower():
                    return i, str(d.get("name"))
        for i, d in enumerate(devs):
            name = str(d.get("name", "")).lower()
            if d.get("max_input_channels", 0) > 0 and ("k670" in name or "fifine" in name):
                return i, str(d.get("name"))
    except Exception:
        pass
    return None, "padrão do sistema"

class NativeAudioListener:
    def __init__(self, on_speech_start: Optional[Callable] = None,
                 on_speech_end: Optional[Callable] = None,
                 on_rms_level: Optional[Callable[[float], None]] = None,
                 on_transcript_ready: Optional[Callable[[str, str], None]] = None,
                 on_partial_transcript: Optional[Callable[[str], None]] = None):
        self.sample_rate = 16000
        self.channels = 1
        self.block_size = 800 # 50ms por bloco
        self.is_running = False
        self.stream = None

        self.on_speech_start = on_speech_start
        self.on_speech_end = on_speech_end
        self.on_rms_level = on_rms_level
        self.on_transcript_ready = on_transcript_ready
        self.on_partial_transcript = on_partial_transcript

        # Parâmetros de calibração acústica VAD
        self.ambient_noise_floor = 0.012
        self.calibration_count = 0
        self.is_speaking = False
        self.speech_start_time = 0
        self.last_voice_time = 0
        self.silence_timeout_sec = 0.55 # 0.55s de silêncio contínuo para resposta ultra-rápida (<600ms)
        self.recorded_blocks = []
        self._lock = threading.Lock()

        # Parque: WAKE WORD "Jarvis" + transcrição ao vivo (buffer rolado)
        self.conversation_unlocked_until = 0.0
        self.last_partial_time = 0.0
        self.last_partial_text = ""
        self._partial_busy = False
        self.wake_words = ("jarvis", "jarvez", "jarvi", "javis")

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self.recorded_blocks = []
        self.is_speaking = False
        self._mic_index, self._mic_name = _resolve_mic_device()
        print(f"[NATIVE AUDIO] Microfone fixado: '{self._mic_name}' (índice {self._mic_index})")

        threading.Thread(target=self._audio_capture_thread, daemon=True, name="NativeJarvisAudioVAD").start()
        print("[NATIVE AUDIO] Escuta de voz contínua com wake word 'Jarvis' ativada.")

    def stop(self):
        self.is_running = False
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass

    def _audio_capture_thread(self):
        try:
            with sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="float32",
                blocksize=self.block_size,
                device=getattr(self, "_mic_index", None),
                callback=self._audio_callback
            ):
                while self.is_running:
                    time.sleep(0.05)
                    self._check_silence_timeout()
        except Exception as e:
            print("[NATIVE AUDIO ERROR] Falha no fluxo do microfone:", e)

    def _audio_callback(self, indata, frames, time_info, status):
        if not self.is_running:
            return

        audio_data = indata[:, 0]
        rms = float(np.sqrt(np.mean(audio_data ** 2)))

        if self.on_rms_level:
            try:
                self.on_rms_level(rms)
            except Exception:
                pass

        # Calibração inicial de ruído de sala
        if self.calibration_count < 30:
            self.ambient_noise_floor = (self.ambient_noise_floor * self.calibration_count + rms) / (self.calibration_count + 1)
            self.calibration_count += 1
            return

        dynamic_threshold = max(0.020, self.ambient_noise_floor * 2.2 + 0.012)
        now = time.time()

        with self._lock:
            if rms > dynamic_threshold:
                if not self.is_speaking:
                    self.is_speaking = True
                    self.speech_start_time = now
                    self.recorded_blocks = []
                    # Só sinaliza "falando" (mostra a ilha) se já estivermos numa conversa
                    # desbloqueada — evita a ilha pipocar a cada ruído sem a wake word "Jarvis".
                    if self.on_speech_start and now < self.conversation_unlocked_until:
                        try: self.on_speech_start()
                        except Exception: pass

                self.last_voice_time = now
                self.recorded_blocks.append(audio_data.copy())
                self._maybe_emit_partial_locked(now)
            elif self.is_speaking:
                # Mantém guardando blocos durante o período de tolerância de 1.5s
                self.recorded_blocks.append(audio_data.copy())

    def _maybe_emit_partial_locked(self, now: float):
        """Transcrição AO VIVO: enquanto o usuário fala, atualiza o texto a cada ~1.1s.
        Só durante a janela de conversa (após dizer 'Jarvis'), para privacidade e economia."""
        try:
            if now >= self.conversation_unlocked_until:
                return  # sem wake word "Jarvis": não emite legenda ao vivo (privacidade/economia)
            if now < self.last_partial_time + 1.1:
                return
            if len(self.recorded_blocks) < 14:  # menos de ~0.7s de fala
                return
            self.last_partial_time = now
            rolling = np.concatenate(self.recorded_blocks[-36:])  # ~2.2s a 16kHz/50ms
            self._partial_busy = True
            threading.Thread(target=self._transcribe_partial, args=(rolling,), daemon=True,
                             name="JarvisPartialTranscribe").start()
        except Exception:
            self._partial_busy = False

    def _transcribe_partial(self, audio_data: np.ndarray):
        try:
            wav_io = io.BytesIO()
            with wave.open(wav_io, "wb") as wf:
                wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(self.sample_rate)
                wf.writeframes((np.clip(audio_data, -1.0, 1.0) * 32767).astype(np.int16).tobytes())
            req = urllib.request.Request(
                f"{CORE_BASE_URL}/api/transcribe",
                data=wav_io.getvalue(),
                headers={"Content-Type": "audio/wav"}
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                text = json.loads(resp.read().decode("utf-8")).get("text", "").strip()
            if self.on_partial_transcript and text and text != self.last_partial_text and len(text) > 1:
                self.last_partial_text = text
                try: self.on_partial_transcript(text)
                except Exception: pass
        except Exception:
            pass
        finally:
            self._partial_busy = False

    def _check_silence_timeout(self):
        now = time.time()
        should_process = False
        audio_to_send = None

        with self._lock:
            if self.is_speaking and (now - self.last_voice_time >= self.silence_timeout_sec):
                # Completou 1.5 segundos de silêncio contínuo pós-fala!
                duration = now - self.speech_start_time
                if duration >= 0.7 and len(self.recorded_blocks) > 10:
                    audio_to_send = np.concatenate(self.recorded_blocks)
                    should_process = True

                self.is_speaking = False
                self.recorded_blocks = []
                if self.on_speech_end:
                    try: self.on_speech_end()
                    except Exception: pass

        if should_process and audio_to_send is not None:
            threading.Thread(target=self._process_and_send_audio, args=(audio_to_send,), daemon=True).start()

    def _process_and_send_audio(self, audio_data: np.ndarray):
        """Converte o áudio gravado para WAV 16-bit e transcreve no Faster-Whisper."""
        try:
            # Converte float32 (-1.0 a 1.0) para int16
            audio_int16 = (np.clip(audio_data, -1.0, 1.0) * 32767).astype(np.int16)
            wav_io = io.BytesIO()
            with wave.open(wav_io, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                wf.writeframes(audio_int16.tobytes())
            wav_bytes = wav_io.getvalue()

            # Envia para transcrição no servidor local (CPU pode levar ~10s)
            req = urllib.request.Request(
                f"{CORE_BASE_URL}/api/transcribe",
                data=wav_bytes,
                headers={"Content-Type": "audio/wav"}
            )
            with urllib.request.urlopen(req, timeout=40) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                text = res_data.get("text", "").strip()

            _vlog(f"transcrito: '{text}'")
            if not text or len(text) < 2:
                _vlog("(transcricao vazia - ignorado)")
                return

            print(f"[NATIVE VOICE TRANSCRIBED] '{text}'")

            # ============ WAKE WORD GATE "Jarvis" + follow-up de 8s ============
            now = time.time()
            text_norm = text.lower().strip()
            starts_wake = any(text_norm.replace(",", " ", 1).split(",")[0].strip().startswith(w) or text_norm.startswith(w)
                              for w in self.wake_words)
            unlocked = now < self.conversation_unlocked_until

            if starts_wake:
                # Remove o proprio nome do comando antes de enviar
                cleaned = text
                for w in self.wake_words:
                    if text_norm.startswith(w):
                        cleaned = text[len(w):]
                        break
                cleaned = cleaned.lstrip(" \t,:;!.").strip()
                if not cleaned:
                    # Só o nome: apenas desbloqueia a conversa
                    _vlog("wake word detectada (so o nome)")
                    self.conversation_unlocked_until = now + 8.0
                    if self.on_partial_transcript:
                        try: self.on_partial_transcript("Ouvindo após Jarvis…")
                        except Exception: pass
                    return
                text = cleaned
                self.conversation_unlocked_until = now + 8.0
                _vlog(f"wake OK -> comando: '{text}'")
            elif unlocked:
                self.conversation_unlocked_until = now + 8.0  # renova o follow-up
                _vlog(f"follow-up (sem repetir Jarvis): '{text}'")
            else:
                print("[WAKE GATE] Fala ignorada (sem wake word 'Jarvis'):")
                print(f"  >> '{text[:70]}'")
                _vlog(f"DESCARTADO (sem wake word): '{text[:70]}'")
                if self.on_partial_transcript:
                    try: self.on_partial_transcript("")
                    except Exception: pass
                return

            # Wake word confirmada (ou follow-up): AGORA sim mostra a ilha / estado "ouvindo"
            if self.on_speech_start:
                try: self.on_speech_start()
                except Exception: pass

            # Envia para o chat/núcleo do JARVIS
            payload = json.dumps({"message": text}).encode("utf-8")
            chat_req = urllib.request.Request(
                f"{CORE_BASE_URL}/api/chat",
                data=payload,
                headers={"Content-Type": "application/json"}
            )
            # Núcleo no Zima pode levar até ~90s (agente + telemetria). Aguarda com folga.
            with urllib.request.urlopen(chat_req, timeout=120) as chat_resp:
                chat_data = json.loads(chat_resp.read().decode("utf-8"))
                reply = chat_data.get("reply", "")
                audio_url = chat_data.get("audio_url")

            if self.on_transcript_ready:
                try:
                    self.on_transcript_ready(text, reply, audio_url, chat_data)
                except Exception:
                    pass

            # Reproduz a resposta sintetizada em áudio no Windows
            if audio_url:
                threading.Thread(target=self._play_tts_response, args=(audio_url,), daemon=True).start()

        except Exception as e:
            print("[NATIVE AUDIO PROCESSING ERROR]:", e)

    def _play_tts_response(self, audio_url: str):
        """Reproduz a resposta do Jarvis com a voz ElevenLabs nativamente no Windows."""
        try:
            filename = audio_url.split("?")[0].lstrip("/")
            os.makedirs(os.path.join(ROOT_DIR, "logs"), exist_ok=True)
            local_path = os.path.join(ROOT_DIR, "logs", filename)
            if not os.path.exists(local_path):
                # Baixa via HTTP se não estiver direto na pasta
                full_url = f"{CORE_BASE_URL}/{filename}"
                with urllib.request.urlopen(full_url, timeout=10) as resp:
                    with open(local_path, "wb") as f:
                        f.write(resp.read())

            if os.path.exists(local_path):
                winmm = ctypes.windll.winmm
                alias = f"jarvis_voice_{int(time.time()*1000)}"
                winmm.mciSendStringW(f'open "{local_path}" type mpegvideo alias {alias}', None, 0, 0)
                winmm.mciSendStringW(f'play {alias} wait', None, 0, 0)
                winmm.mciSendStringW(f'close {alias}', None, 0, 0)
        except Exception as e:
            print("[NATIVE TTS PLAYBACK ERROR]:", e)

if __name__ == "__main__":
    listener = NativeAudioListener(
        on_speech_start=lambda: print("--> [FALANDO DETECTADO]"),
        on_speech_end=lambda: print("--> [SILÊNCIO 1.5s - PROCESSANDO]"),
        on_transcript_ready=lambda t, r: print(f"--> [USUÁRIO]: {t}\n--> [JARVIS]: {r}")
    )
    listener.start()
    print("Fale algo no microfone...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        listener.stop()
