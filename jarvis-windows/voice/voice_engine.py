"""
Motor de Voz, Wake Word e Hotkey Global do J.A.R.V.I.S. Windows v3 — conversa contínua estilo ChatGPT.

Pipeline (latência-alvo ~1,5 s do fim da fala ao início da resposta):
  1. Captura contínua do microfone + VAD adaptativo (fim de fala em ~0,7 s de silêncio)
  2. STT Groq Whisper (~300 ms)  [opcional: áudio nativo direto no MiMo, JARVIS_NATIVE_AUDIO=1]
  3. Cérebro em STREAMING (core_ai_brain.stream_direct_ai): atalho local de luzes, camada rápida,
     ferramentas, visão da tela e raciocínio profundo
  4. Frases saem do LLM direto para o TTS MiMo (voz neural pt-BR) enquanto a próxima já é sintetizada;
     se o TTS falhar/demorar, cai para a voz SAPI do Windows
  5. Modo conversa: após responder, escuta a continuação por alguns segundos sem precisar de wake word
  6. Interrupção (barge-in): hotkey/wake word cala a fala imediatamente
"""

import io
import os
import re
import sys
import time
import wave
import ctypes
import ctypes.wintypes
import logging
import queue
import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

import sounddevice as sd
import numpy as np

try:
    from config.settings import (
        CORE_URL, BRIDGE_SECRET, HOTKEY_MODIFIERS, HOTKEY_VK, HOTKEY_ID
    )
except ImportError:
    from ..config.settings import (
        CORE_URL, BRIDGE_SECRET, HOTKEY_MODIFIERS, HOTKEY_VK, HOTKEY_ID
    )

logger = logging.getLogger("VoiceEngine")
user32 = ctypes.windll.user32

TTS_RATE = 24000
FOLLOWUP_SECONDS = float(os.environ.get("JARVIS_FOLLOWUP_SECONDS", "7"))
SILENCE_BLOCKS = int(os.environ.get("JARVIS_SILENCE_BLOCKS", "9"))  # 9 x 80 ms = 0,72 s
# Voz: "local" (SAPI pt-BR, instantânea, pronúncia correta) | "design" | "clone" | "preset" (MiMo TTS, opt-in:
# a pronúncia em português ainda é fraca e a latência é de 3-5 s por frase).
TTS_ENGINE = os.environ.get("JARVIS_TTS_MODE", "edge").lower()
NATIVE_AUDIO = os.environ.get("JARVIS_NATIVE_AUDIO", "0") == "1"
BARGE_IN_VOICE = os.environ.get("JARVIS_BARGE_IN_VOICE", "0") == "1"  # exige fones (evita eco do alto-falante)
WAKE_WORD_THRESHOLD = float(os.environ.get("JARVIS_WAKE_WORD_THRESHOLD", "0.65"))
WAKE_WORD_MODEL_NAME = os.environ.get("JARVIS_WAKE_WORD_MODEL", "hey_jarvis_v0.1.onnx")

_CURRENT_VOICE_ENGINE: Optional["JarvisVoiceEngine"] = None

def get_voice_engine() -> Optional["JarvisVoiceEngine"]:
    return _CURRENT_VOICE_ENGINE

def get_voice_status() -> dict:
    eng = _CURRENT_VOICE_ENGINE
    if not eng:
        return {
            "active": False,
            "wake_word_loaded": False,
            "wake_threshold": WAKE_WORD_THRESHOLD,
            "wake_model": WAKE_WORD_MODEL_NAME,
            "tts_engine": TTS_ENGINE
        }
    return {
        "active": eng.is_alive(),
        "state": eng.state,
        "wake_word_loaded": eng.wake_model is not None,
        "wake_model_name": getattr(eng, "wake_model_name", WAKE_WORD_MODEL_NAME),
        "wake_threshold": getattr(eng, "wake_threshold", WAKE_WORD_THRESHOLD),
        "tts_engine": TTS_ENGINE,
        "sample_rate": eng.sample_rate
    }

_STOP_PHRASES = {
    "para", "pare", "cancela", "cancelar", "chega", "silencio", "silêncio", "esquece", "deixa pra lá", "deixa pra la",
}
_END_CONVERSATION = (
    "obrigado", "obrigada", "valeu", "é só isso", "e so isso", "só isso", "so isso", "pode ir", "tchau", "até mais",
    "ate mais", "encerrar conversa", "fim da conversa",
)


def _norm(t: str) -> str:
    return re.sub(r"[^\w\s]", "", (t or "").lower()).strip()


_STOP_PATTERNS = [
    r"\b(?:para|pare|cancela|cancelar|interromp\w*|abort\w*)\s+(?:tudo|isso|agora|o\s+que\s+(?:voc[eê]\s+)?t[aá]\s+fazendo|o\s+que\s+(?:voc[eê]\s+)?est[aá]\s+fazendo)\b",
    r"\b(?:pode\s+parar|chega|sil[eê]ncio|cala\s+a\s+boca|quieto|para\s+a[ií])\b",
    r"^(?:para|pare|cancela|parar|quieto)\b",
]

def is_stop_command(cmd: str) -> bool:
    clean = _norm(cmd)
    if not clean:
        return False
    if clean in _STOP_PHRASES:
        return True
    return any(re.search(pat, clean) for pat in _STOP_PATTERNS)



class _Speaker:
    """Reprodução sequencial de fala com TTS em pipeline e interrupção imediata."""

    def __init__(self):
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="TTS")
        self.active = False

    def stop(self):
        """Interrompe a fala atual (barge-in)."""
        self._stop.set()
        try:
            sd.stop()
        except Exception as e:
            logger.debug("sd.stop: %s", e)

    def _sapi_speak(self, text: str):
        """Fallback offline: voz SAPI do Windows, interrompível."""
        try:
            import comtypes
            import comtypes.client
            comtypes.CoInitialize()
            try:
                sp = comtypes.client.CreateObject("SAPI.SpVoice")
                for v in sp.GetVoices():  # prefere voz pt-BR instalada
                    if "Portuguese" in v.GetDescription() or "pt-BR" in v.GetDescription():
                        sp.Voice = v
                        break
                sp.Rate = 1  # um pouco mais ágil que o padrão
                sp.Speak(text, 1)  # assíncrono
                while not sp.WaitUntilDone(80):
                    if self._stop.is_set():
                        sp.Speak("", 3)  # purge
                        return
            finally:
                comtypes.CoUninitialize()
        except Exception as e:
            logger.warning("SAPI indisponível: %s", e)

    def _play_pcm(self, pcm: bytes):
        if not pcm:
            return
        audio = np.frombuffer(pcm, dtype=np.int16)
        try:
            with sd.OutputStream(samplerate=TTS_RATE, channels=1, dtype="int16") as out:
                step = TTS_RATE // 10  # 100 ms
                for i in range(0, len(audio), step):
                    if self._stop.is_set():
                        return
                    out.write(audio[i:i + step])
        except Exception as e:
            logger.error("Falha ao reproduzir áudio: %s", e)

    def speak(self, sentences, on_first_audio: Optional[Callable[[], None]] = None) -> bool:
        """
        Fala um iterável de frases. A síntese da frase N+1 ocorre enquanto a N toca.
        Retorna True se terminou sem interrupção.
        """
        from mimo_tts import synthesize, TTSError

        with self._lock:  # uma fala por vez
            self._stop.clear()
            self.active = True
            q: "queue.Queue" = queue.Queue(maxsize=3)
            done = object()

            def producer():
                try:
                    for s in sentences:
                        if self._stop.is_set():
                            break
                        clean = re.sub(r"```[\s\S]*?```", "", s)
                        clean = re.sub(r"[\*\#\_`~]", "", clean).strip()
                        if clean:
                            q.put((clean, self._pool.submit(synthesize, clean) if TTS_ENGINE != "local" else None))
                except Exception as e:
                    logger.error("Falha ao gerar frases: %s", e)
                finally:
                    q.put(done)

            threading.Thread(target=producer, daemon=True, name="SpeakProducer").start()
            first = True
            try:
                while True:
                    item = q.get()
                    if item is done:
                        break
                    text, fut = item
                    if self._stop.is_set():
                        continue
                    try:
                        pcm = fut.result(timeout=14) if fut else b""
                    except TTSError as e:
                        logger.warning("TTS MiMo falhou (%s) — usando voz do Windows.", e)
                        pcm = b""
                    except Exception as e:
                        logger.warning("TTS erro inesperado (%s) — usando voz do Windows.", e)
                        pcm = b""
                    if first and on_first_audio:
                        on_first_audio()
                    first = False
                    if pcm:
                        self._play_pcm(pcm)
                    else:
                        self._sapi_speak(text)
                return not self._stop.is_set()
            finally:
                self.active = False


class JarvisVoiceEngine(threading.Thread):
    def __init__(self,
                 on_hotkey: Optional[Callable[[], None]] = None,
                 on_wake_word: Optional[Callable[[], None]] = None,
                 on_speech_recognized: Optional[Callable[[str], None]] = None,
                 on_speech_reply: Optional[Callable[[str], None]] = None,
                 on_audio_level: Optional[Callable[[float], None]] = None):
        super().__init__(daemon=True, name="JarvisVoiceWorker")
        self.on_hotkey = on_hotkey
        self.on_wake_word = on_wake_word
        self.on_speech_recognized = on_speech_recognized
        self.on_speech_reply = on_speech_reply
        self.on_audio_level = on_audio_level

        self._running = True
        self.sample_rate = 16000
        self.block_size = 1280  # 80 ms

        self.state = "WAKEWORD"  # WAKEWORD | RECORDING | PROCESSING
        self.recorded_frames = []
        self.silence_count = 0
        self.has_spoken = False
        self.record_start_ts = 0.0
        self.followup_mode = False
        self.followup_deadline = 0.0
        self._noise_floor = 120.0
        self._barge_hits = 0
        self._turn_id = 0  # invalida turnos antigos quando o usuário interrompe
        self._wake_hits = 0
        self._last_wake_time = 0.0

        self.speaker = _Speaker()
        self.history = deque(maxlen=8)
        self._turn_lock = threading.Lock()

        global _CURRENT_VOICE_ENGINE
        _CURRENT_VOICE_ENGINE = self

        self.wake_threshold = WAKE_WORD_THRESHOLD
        self.wake_model_name = WAKE_WORD_MODEL_NAME
        self.wake_model = None
        self._init_wake_model()

        try:
            if TTS_ENGINE != "local":
                from mimo_tts import warm_cache
                warm_cache()
        except Exception as e:
            logger.warning("Pré-aquecimento TTS indisponível: %s", e)

    # ------------------------------------------------------------------ wake word / hotkey
    def _init_wake_model(self):
        try:
            import openwakeword
            from openwakeword.model import Model

            models_search_dirs = []
            if hasattr(sys, '_MEIPASS'):
                models_search_dirs.append(os.path.join(sys._MEIPASS, 'openwakeword', 'resources', 'models'))
            if hasattr(sys, 'executable'):
                models_search_dirs.append(os.path.join(os.path.dirname(sys.executable), '_internal', 'openwakeword', 'resources', 'models'))
            try:
                models_search_dirs.append(os.path.join(os.path.dirname(openwakeword.__file__), 'resources', 'models'))
            except Exception:
                pass
            models_search_dirs.append(os.path.join(r"C:\Users\werik\AppData\Local\hermes\hermes-agent\venv\Lib\site-packages\openwakeword\resources\models"))

            model_file = None
            melspec_file = None
            embedding_file = None

            for d in models_search_dirs:
                if not model_file:
                    cand = os.path.join(d, 'hey_jarvis_v0.1.onnx')
                    if os.path.exists(cand):
                        model_file = cand
                if not melspec_file:
                    cand = os.path.join(d, 'melspectrogram.onnx')
                    if os.path.exists(cand):
                        melspec_file = cand
                if not embedding_file:
                    cand = os.path.join(d, 'embedding_model.onnx')
                    if os.path.exists(cand):
                        embedding_file = cand

            kwargs = {'inference_framework': 'onnx'}
            if melspec_file:
                kwargs['melspec_model_path'] = melspec_file
            if embedding_file:
                kwargs['embedding_model_path'] = embedding_file

            if model_file:
                kwargs['wakeword_models'] = [model_file]
            else:
                kwargs['wakeword_models'] = ['hey_jarvis_v0.1']

            self.wake_model = Model(**kwargs)
            print(f"[VoiceEngine] Wake Word hey_jarvis_v0.1 carregado com sucesso via {model_file or 'padrao'}")
            try:
                from main import _log
                _log(f"[VoiceEngine] Wake Word carregado com sucesso: {model_file}")
            except Exception:
                pass
        except BaseException as e:
            import traceback
            tb = traceback.format_exc()
            try:
                from main import _log
                _log(f"[VoiceEngine] Erro ao carregar OpenWakeWord: {e}\n{tb}")
            except Exception:
                pass
            print(f"[VoiceEngine] Aviso: Wake Word neural indisponivel ({e}). Escuta por hotkey ativa.")
            self.wake_model = None

    def run(self):
        for hid, mods, vk in ((HOTKEY_ID, HOTKEY_MODIFIERS, HOTKEY_VK), (HOTKEY_ID + 1, 0x0008 | 0x0004, 0x4A)):
            try:
                user32.RegisterHotKey(None, hid, mods, vk)
            except Exception as e:
                logger.warning("Falha ao registrar hotkey %s: %s", hid, e)

        threading.Thread(target=self._audio_stream_loop, daemon=True, name="JarvisAudioLoop").start()

        msg = ctypes.wintypes.MSG()
        while self._running:
            try:
                if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                    if msg.message == 0x0312:  # WM_HOTKEY
                        print("[VoiceEngine] Hotkey global ativada!")
                        self.trigger_manual_listen()
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
            except Exception as e:
                logger.debug("Loop de mensagens: %s", e)
            time.sleep(0.05)

        for hid in (HOTKEY_ID, HOTKEY_ID + 1):
            try:
                user32.UnregisterHotKey(None, hid)
            except Exception as e:
                logger.debug("UnregisterHotKey: %s", e)

    # ------------------------------------------------------------------ captura de áudio
    def _vad_threshold(self) -> float:
        return max(320.0, self._noise_floor * 3.2)

    def _audio_stream_loop(self):
        def callback(indata, frames, time_info, status):
            if not self._running:
                raise sd.CallbackStop()

            pcm16 = indata[:, 0].copy()
            rms = float(np.sqrt(np.mean(pcm16.astype(np.float32) ** 2)))
            if self.on_audio_level and self.state == "RECORDING":
                self.on_audio_level(min(rms / 1200.0, 1.0))

            if self.state in ("WAKEWORD", "PROCESSING"):
                # Piso de ruído adaptativo (apenas em silêncio relativo e sem fala da própria IA)
                if not self.speaker.active and rms < 900:
                    self._noise_floor = 0.97 * self._noise_floor + 0.03 * rms

                if self.speaker.active and BARGE_IN_VOICE:
                    self._barge_hits = self._barge_hits + 1 if rms > max(1500.0, self._noise_floor * 8) else 0
                    if self._barge_hits >= 4:
                        self._barge_hits = 0
                        print("[VoiceEngine] Barge-in por voz detectado.")
                        self.trigger_manual_listen()
                        return

                if self.wake_model is not None:
                    try:
                        scores = self.wake_model.predict(pcm16)
                        now_ts = time.time()
                        for k, score in scores.items():
                            # Cooldown: evita re-disparo em eco nos 2.0s seguintes
                            if now_ts - self._last_wake_time < 2.0:
                                break
                            
                            # Confirmação robusta:
                            # 1) Disparo com score muito alto (>= 0.75)
                            # 2) Disparo se 2 blocos consecutivos atingirem o limiar (>= self.wake_threshold)
                            if score >= 0.75 or (score >= self.wake_threshold and self._wake_hits >= 1):
                                self._wake_hits = 0
                                self._last_wake_time = now_ts
                                log_msg = f"[VoiceEngine] ⚡ Wake Word '{k}' confirmado com confiança ({score:.2f} >= {self.wake_threshold:.2f})!"
                                print(log_msg)
                                logger.info(log_msg)
                                if hasattr(self.wake_model, "reset"):
                                    self.wake_model.reset()
                                self.trigger_manual_listen()
                                break
                            elif score >= self.wake_threshold:
                                self._wake_hits += 1
                            else:
                                self._wake_hits = 0
                    except Exception as e:
                        logger.debug("Wake model: %s", e)

            elif self.state == "RECORDING":
                self.recorded_frames.append(pcm16)
                thr = self._vad_threshold()
                if rms > thr:
                    self.has_spoken = True
                    self.silence_count = 0
                elif self.has_spoken:
                    self.silence_count += 1
                    if self.silence_count >= SILENCE_BLOCKS:
                        print("[VoiceEngine] Fim da fala (VAD). Processando...")
                        self._finish_recording_and_process()
                        return

                now = time.time()
                # Se não houve fala nenhuma após 4.0s do acionamento, aborta e volta ao repouso sem enviar silêncio à IA
                if not self.has_spoken and (now - self.record_start_ts >= 4.0):
                    print("[VoiceEngine] Nenhuma fala detectada após acionamento (4s). Cancelando gravação e voltando ao repouso.")
                    self._end_conversation()
                    return

                if self.followup_mode and not self.has_spoken and now > self.followup_deadline:
                    print("[VoiceEngine] Janela de conversa encerrada sem fala. Voltando ao modo de espera.")
                    self._end_conversation()
                    return
                if now - self.record_start_ts >= 14.0:
                    print("[VoiceEngine] Tempo limite de fala (14s). Processando...")
                    self._finish_recording_and_process()

        try:
            with sd.InputStream(samplerate=self.sample_rate, blocksize=self.block_size,
                                channels=1, dtype="int16", callback=callback):
                while self._running:
                    time.sleep(0.1)
        except Exception as e:
            print(f"[VoiceEngine] Erro no stream de áudio do microfone: {e}")

    # ------------------------------------------------------------------ controle de turnos
    def trigger_manual_listen(self):
        """Hotkey/wake word: ativa o ÚNICO sistema de voz (QwenLiveVoice no HUD).

        Unificação de voz (2026-11-13): este engine virou apenas DETECTOR de
        gatilho — nao grava audio nem roda STT/LLM/TTS locais (que geravam a
        'voz masculina' duplicada junto com a do Qwen). Ele toca o chime e
        emite on_wake_word (sinal Qt cross-thread) para o HUD ligar a
        conversa ao vivo com o Qwen. Sem pipeline proprio, state permanece
        em WAKEWORD e a detecção continua ativa.
        """
        if self.state == "RECORDING" and not self.followup_mode:
            return
        self.speaker.stop()  # barge-in: cala qualquer TTS local pendente
        if self.on_wake_word:
            self.on_wake_word()
        self._play_wake_chime()

    def _begin_recording(self, followup: bool):
        self._turn_id += 1
        self.recorded_frames = []
        self.silence_count = 0
        self.has_spoken = False
        self.record_start_ts = time.time()
        self.followup_mode = followup
        self.followup_deadline = time.time() + FOLLOWUP_SECONDS
        self.state = "RECORDING"

    def _end_conversation(self):
        self.followup_mode = False
        self.recorded_frames = []
        self.state = "WAKEWORD"

    def _finish_recording_and_process(self):
        frames = list(self.recorded_frames)
        self.recorded_frames = []
        self.followup_mode = False
        self.state = "PROCESSING"
        if not frames or not self.has_spoken or len(frames) < 6:
            print("[VoiceEngine] Áudio sem fala confirmada ou muito curto (<480ms). Descartado.")
            self.state = "WAKEWORD"
            return
        threading.Thread(target=self._process_turn_worker, args=(frames, self._turn_id), daemon=True, name="VoiceTurn").start()

    @staticmethod
    def _frames_to_wav(frames, rate: int) -> bytes:
        audio_data = np.concatenate(frames, axis=0)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(rate)
            wf.writeframes(audio_data.tobytes())
        return buf.getvalue()

    def _process_turn_worker(self, frames, tid: int):
        keep_listening = False
        try:
            with self._turn_lock:
                t_start = time.time()
                wav_bytes = self._frames_to_wav(frames, self.sample_rate)

                text = ""
                audio_for_llm = None
                if NATIVE_AUDIO:
                    audio_for_llm = wav_bytes
                    text = ""
                else:
                    from stt_engine import transcribe_audio, clean_hallucinations
                    # Cascata completa: Groq -> MiMo ASR -> Whisper local.
                    raw_text = transcribe_audio(wav_bytes, language="pt")
                    if not raw_text or len(raw_text.strip()) < 2:
                        return
                    cleaned = clean_hallucinations(raw_text)
                    if not cleaned:
                        print(f"[VoiceEngine] Áudio descartado como ruído/alucinação ('{raw_text}')")
                        return
                    text = re.sub(
                        r"^\s*(?:(?:hey|ei|oi|olá|ola)\s+)?(?:jarvis|jarvez|jarvi|javis)\b\s*[,.:;!?-]*\s*",
                        "", cleaned, flags=re.IGNORECASE).strip() or cleaned
                    if not text or len(text.strip()) < 2:
                        print("[VoiceEngine] Apenas nome detectado sem comando adicional. Retornando ao repouso.")
                        return
                    print(f"[VoiceEngine] Transcrição ({time.time() - t_start:.2f}s): '{text}'")
                    if self.on_speech_recognized:
                        self.on_speech_recognized(text)

                    n = _norm(text)
                    # 1. Interrupção e comando de parada imediata
                    if is_stop_command(text):
                        print(f"[VoiceEngine] 🛑 Comando de parada imediata recebido: '{text}'")
                        self.speaker.stop()
                        try:
                            from subagent_manager import get_subagent_manager
                            get_subagent_manager().cancel_all()
                        except Exception as e:
                            logger.debug("Cancel subagents: %s", e)
                        try:
                            from jarvis_laya_agent import get_laya_agent
                            get_laya_agent().close_screen()
                        except Exception as e:
                            logger.debug("Close laya screen: %s", e)
                        self._speak_text_blocking("Parando imediatamente, Senhor Werik.")
                        return

                    if any(n.startswith(p) or n == p for p in _END_CONVERSATION) and len(n.split()) <= 6:
                        self._speak_text_blocking("Às suas ordens, Senhor Werik.")
                        return

                    # Interrompe fala anterior e processa a nova instrucao diretamente
                    self.speaker.stop()

                keep_listening = self._respond(text, audio_for_llm, t_start, tid)
        except Exception as e:
            logger.exception("Erro no processamento do turno de voz: %s", e)
            print(f"[VoiceEngine] Erro no processamento do turno de voz: {e}")
        finally:
            if self._turn_id != tid:
                pass  # o usuário interrompeu: o novo turno já controla o estado
            elif keep_listening and self._running:
                time.sleep(0.25)  # deixa a cauda do alto-falante dissipar antes de ouvir
                self._begin_recording(followup=True)
            else:
                self.state = "WAKEWORD"

    def _respond(self, text: str, audio_wav: Optional[bytes], t_start: float, tid: int) -> bool:
        """Gera e fala a resposta em streaming. Retorna True para manter a janela de conversa."""
        from core_ai_brain import stream_direct_ai, sentence_stream

        spoken_started = threading.Event()
        reply_parts = []

        def _ack_if_slow():
            # Se nada começou a tocar em 1,8 s, preenche o silêncio com uma confirmação curta em cache
            if spoken_started.wait(1.8):
                return
            try:
                if TTS_ENGINE == "local":
                    if not spoken_started.is_set():
                        self.speaker._sapi_speak("Um momento, Senhor.")
                    return
                from mimo_tts import synthesize
                pcm = synthesize("Um momento, Senhor.", use_cache=True)
                if pcm and not spoken_started.is_set():
                    self.speaker._play_pcm(pcm)
            except Exception as e:
                logger.debug("Ack indisponível: %s", e)

        threading.Thread(target=_ack_if_slow, daemon=True, name="SlowAck").start()

        def tee():
            for delta in stream_direct_ai(text, voice=True, history=list(self.history), audio_wav=audio_wav):
                if self._turn_id != tid:  # interrompido por novo comando
                    return
                reply_parts.append(delta)
                yield delta

        def on_first_audio():
            spoken_started.set()
            print(f"[VoiceEngine] Primeira fala após {time.time() - t_start:.2f}s do fim da captura.")

        completed = self.speaker.speak(sentence_stream(tee()), on_first_audio=on_first_audio)
        if self._turn_id != tid:
            return False
        spoken_started.set()

        reply = "".join(reply_parts).strip()
        print(f"[VoiceEngine] Resposta J.A.R.V.I.S.: '{reply}'")
        if reply:
            if text:
                self.history.append({"role": "user", "content": text})
            self.history.append({"role": "assistant", "content": reply})
            if self.on_speech_reply:
                self.on_speech_reply(reply)
        return bool(completed and reply)

    # ------------------------------------------------------------------ fala avulsa
    def _speak_text_blocking(self, text: str):
        self.speaker.speak(iter([text]))

    def speak_text(self, text: str):
        """Fala um texto completo (notificações/respostas externas) com a mesma voz neural."""
        if not text:
            return
        from core_ai_brain import sentence_stream
        self.speaker.speak(sentence_stream(iter([text])))

    def _play_wake_chime(self):
        """Bip holográfico curto de ativação (80 ms)."""
        try:
            sr = 16000
            t = np.linspace(0, 0.08, int(sr * 0.08), False)
            tone = (np.sin(2 * np.pi * 880 * t) * 0.2 * 32767).astype(np.int16)
            sd.play(tone, samplerate=sr)
        except Exception as e:
            logger.debug("Chime: %s", e)

    def stop(self):
        self._running = False
        self.speaker.stop()
