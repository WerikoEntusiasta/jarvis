"""Local wake-word and speech-turn handling for the J.A.R.V.I.S. sphere.

The sphere currently sends 16 kHz, mono, signed 16-bit PCM frames. This module
keeps those frames in memory, gates transcription behind a wake-word detector,
and emits completed turns only after neural VAD observes the end of speech.
No captured audio is written to disk by this module.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math
import os
import re
import time
import unicodedata
from typing import Callable, Deque, Iterable, Optional

import numpy as np


SAMPLE_RATE = 16_000
BYTES_PER_SAMPLE = 2
VAD_FRAME_SAMPLES = 512  # Silero's 16 kHz streaming window (32 ms)
WAKE_FRAME_SAMPLES = 1_280  # openWakeWord's efficient 80 ms inference window


@dataclass(frozen=True)
class GateEvent:
    kind: str
    audio: bytes = b""
    score: float = 0.0


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()


def strip_wake_word(text: str) -> tuple[str, bool]:
    """Remove a leading Jarvis wake phrase; return (command, wake_only)."""
    original = (text or "").strip()
    match = re.match(
        r"^\s*(?:(?:hey|ei)\s+)?(?:jarvis|jarvez|jarvi|javis)\b\s*[,.:;!?-]*\s*",
        original,
        flags=re.IGNORECASE,
    )
    if not match:
        return original, False
    command = original[match.end():].strip()
    return command, not bool(command)


def classify_fast_command(text: str) -> Optional[str]:
    """Identify low-risk, deterministic voice commands without invoking an LLM."""
    normalized = _fold(text)
    if not normalized:
        return None

    if re.search(r"\b(alarme|despertador)\b", normalized):
        return "alarm"
    if re.search(r"\b(timer|temporizador|cronometro)\b", normalized):
        return "timer"
    if re.search(r"\b(que horas|hora atual|horario agora|me diga as horas|sao que horas)\b", normalized):
        return "time"
    if re.search(r"\b(clima|tempo|previsao|temperatura|chuva)\b", normalized):
        return "weather"
    return None


_NUMBER_WORDS = {
    "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4,
    "cinco": 5, "seis": 6, "sete": 7, "oito": 8, "nove": 9, "dez": 10,
    "onze": 11, "doze": 12, "treze": 13, "quatorze": 14, "catorze": 14,
    "quinze": 15, "dezesseis": 16, "dezessete": 17, "dezoito": 18,
    "dezenove": 19, "vinte": 20, "trinta": 30, "quarenta": 40,
    "cinquenta": 50, "sessenta": 60, "meia": 30,
}


def _number(value: str) -> Optional[int]:
    token = _fold(value).strip()
    if token.isdigit():
        return int(token)
    return _NUMBER_WORDS.get(token)


def parse_timer_seconds(text: str) -> Optional[int]:
    normalized = _fold(text)
    match = re.search(
        r"\b(\d+|[a-z]+)\s+(segundos?|seg|s|minutos?|min|m|horas?|h)\b",
        normalized,
    )
    if not match:
        return None
    value = _number(match.group(1))
    if value is None or value <= 0:
        return None
    unit = match.group(2)
    multiplier = 3600 if unit.startswith("h") else 60 if unit.startswith("m") else 1
    seconds = value * multiplier
    return seconds if seconds <= 24 * 3600 else None


def parse_alarm_time(text: str) -> Optional[tuple[int, int]]:
    normalized = _fold(text)
    match = re.search(r"\b(\d{1,2})(?::|h)(\d{2})?\b", normalized)
    if not match:
        match = re.search(r"\bas\s+(\d{1,2})\s*(?:horas?)?\b", normalized)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    if hour > 23 or minute > 59:
        return None
    return hour, minute


class _RmsVadFallback:
    """Conservative fallback used only when Silero is unavailable."""

    def __init__(self, silence_ms: int):
        self.silence_frames = max(1, math.ceil(silence_ms / 32))
        self.silence_count = 0
        self.speech_frames = 0
        self.speaking = False
        self.noise_floor = 180.0

    def __call__(self, samples: np.ndarray) -> Optional[str]:
        rms = float(np.sqrt(np.mean(np.square(samples.astype(np.float32)))))
        threshold = max(480.0, self.noise_floor * 2.7)
        if not self.speaking:
            self.noise_floor = self.noise_floor * 0.98 + min(rms, 1200.0) * 0.02
            if rms >= threshold:
                self.speech_frames += 1
                if self.speech_frames >= 2:
                    self.speaking = True
                    self.silence_count = 0
                    return "start"
            else:
                self.speech_frames = 0
            return None

        if rms < threshold * 0.72:
            self.silence_count += 1
            if self.silence_count >= self.silence_frames:
                self.speaking = False
                self.speech_frames = 0
                self.silence_count = 0
                return "end"
        else:
            self.silence_count = 0
        return None


class _SileroOnnxVad:
    """Small, stateful Silero ONNX runner; no PyTorch runtime is needed."""

    def __init__(self, model_path: str, silence_ms: int, threshold: float):
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.inter_op_num_threads = 1
        options.intra_op_num_threads = 1
        self.session = ort.InferenceSession(
            model_path, providers=["CPUExecutionProvider"], sess_options=options
        )
        self.threshold = threshold
        self.silence_frames_required = max(1, math.ceil(silence_ms / 32))
        self.reset()

    def reset(self):
        self.state = np.zeros((2, 1, 128), dtype=np.float32)
        self.context = np.zeros((1, 64), dtype=np.float32)
        self.speaking = False
        self.speech_frames = 0
        self.silence_frames = 0

    def __call__(self, samples: np.ndarray) -> Optional[str]:
        if samples.size != VAD_FRAME_SAMPLES:
            return None
        normalized = (samples.astype(np.float32) / 32768.0).reshape(1, VAD_FRAME_SAMPLES)
        model_input = np.concatenate((self.context, normalized), axis=1)
        outputs = self.session.run(
            None,
            {
                "input": model_input,
                "state": self.state,
                "sr": np.asarray(SAMPLE_RATE, dtype=np.int64),
            },
        )
        probability = float(np.asarray(outputs[0]).reshape(-1)[0])
        self.state = np.asarray(outputs[1], dtype=np.float32)
        self.context = model_input[:, -64:]

        if probability >= self.threshold:
            self.speech_frames += 1
            self.silence_frames = 0
            if not self.speaking and self.speech_frames >= 2:
                self.speaking = True
                return "start"
            return None

        self.speech_frames = 0
        if self.speaking:
            self.silence_frames += 1
            if self.silence_frames >= self.silence_frames_required:
                self.speaking = False
                self.silence_frames = 0
                return "end"
        return None


def create_silero_vad(
    silence_ms: int = 1000,
    model_path: Optional[str] = None,
) -> Callable[[np.ndarray], Optional[str]]:
    """Create streaming Silero VAD on CPU; fall back safely if unavailable."""
    try:
        selected_model = model_path or os.environ.get(
            "SPHERE_VAD_MODEL", "/opt/jarvis/models/silero_vad.onnx"
        )
        detector = _SileroOnnxVad(
            selected_model,
            silence_ms,
            float(os.environ.get("SPHERE_VAD_THRESHOLD", "0.55")),
        )
        print(f"[ESFERA ÁUDIO] Silero VAD ONNX ativo (16 kHz, CPU, fim de fala {silence_ms} ms).")
        return detector
    except Exception as exc:
        print(f"[ESFERA ÁUDIO] Silero indisponível ({type(exc).__name__}); usando VAD RMS de contingência.")
        return _RmsVadFallback(silence_ms)


class OpenWakeWordDetector:
    """Streaming detector with a custom-model override and official Jarvis fallback."""

    def __init__(self, model_dir: str, custom_model: str = "", threshold: float = 0.10):
        self.threshold = threshold
        self.model = None
        self.model_name = ""
        try:
            from openwakeword.model import Model
            import openwakeword.utils as wake_utils

            os.makedirs(model_dir, exist_ok=True)
            selected = custom_model.strip()
            if selected and os.path.isfile(selected):
                model_path = selected
                self.model_name = os.path.basename(selected)
            else:
                model_path = os.path.join(model_dir, "hey_jarvis_v0.1.onnx")
                if not os.path.isfile(model_path):
                    wake_utils.download_models(
                        model_names=["hey_jarvis_v0.1"], target_directory=model_dir
                    )
                self.model_name = "hey_jarvis_v0.1"

            self.model = Model(
                wakeword_models=[model_path],
                inference_framework="onnx",
                melspec_model_path=os.path.join(model_dir, "melspectrogram.onnx"),
                embedding_model_path=os.path.join(model_dir, "embedding_model.onnx"),
            )
            print(f"[ESFERA ÁUDIO] Wake word ativo: {self.model_name}; limiar {threshold:.2f}.")
        except Exception as exc:
            self.model = None
            print(f"[ESFERA ÁUDIO] Wake word indisponível ({type(exc).__name__}); áudio fechado por segurança até o modelo carregar.")

    def __call__(self, samples: np.ndarray) -> float:
        if self.model is None:
            return 0.0
        result = self.model.predict(samples.astype(np.int16, copy=False))
        return max((float(score) for score in result.values()), default=0.0)

    def reset(self) -> None:
        if self.model is not None:
            reset = getattr(self.model, "reset", None)
            if reset:
                reset()


class AudioTurnGate:
    """Bounded in-memory PCM gate; only emits speech after wake or in follow-up window."""

    def __init__(
        self,
        wakeword_score: Callable[[np.ndarray], float],
        vad: Callable[[np.ndarray], Optional[str]],
        wake_threshold: float = 0.30,
        followup_seconds: float = 12.0,
        history_seconds: float = 1.5,
        max_utterance_seconds: float = 15.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.wakeword_score = wakeword_score
        self.vad = vad
        self.wake_threshold = wake_threshold
        self.followup_seconds = followup_seconds
        self.clock = clock
        self._pending = bytearray()
        self._wake_pending = bytearray()
        self._history: Deque[bytes] = deque(
            maxlen=max(1, math.ceil(history_seconds * SAMPLE_RATE / VAD_FRAME_SAMPLES))
        )
        self._speaking = False
        self._utterance = bytearray()
        self._conversation_until = 0.0
        self._wake_cooldown_until = 0.0
        self._active = False
        self._last_score = 0.0
        self._wake_score_streak = 0
        self._min_utterance_bytes = int(0.24 * SAMPLE_RATE * BYTES_PER_SAMPLE)
        self._max_utterance_bytes = int(max_utterance_seconds * SAMPLE_RATE * BYTES_PER_SAMPLE)

    @property
    def conversation_active(self) -> bool:
        return self.clock() < self._conversation_until

    def extend_conversation(self, seconds: Optional[float] = None) -> None:
        self._conversation_until = self.clock() + (seconds or self.followup_seconds)
        self._active = True

    def _wake_frames(self, frame_bytes: bytes, now: float, events: list[GateEvent]) -> bool:
        self._wake_pending.extend(frame_bytes)
        wake_size = WAKE_FRAME_SAMPLES * BYTES_PER_SAMPLE
        detected = False
        while len(self._wake_pending) >= wake_size:
            raw = bytes(self._wake_pending[:wake_size])
            del self._wake_pending[:wake_size]
            samples = np.frombuffer(raw, dtype="<i2")
            score = self.wakeword_score(samples)
            self._last_score = score
            # A score by itself must not wake the display during ambient noise.
            # Require actual neural-VAD speech plus two adjacent wake scores.
            if score >= self.wake_threshold and self._speaking:
                self._wake_score_streak += 1
            else:
                self._wake_score_streak = 0

            if self._wake_score_streak >= 2 and now >= self._wake_cooldown_until:
                was_idle = not self._active or now >= self._conversation_until
                self._wake_cooldown_until = now + 2.0
                self._conversation_until = now + self.followup_seconds
                if was_idle:
                    events.append(GateEvent("wake", score=score))
                self._active = True
                detected = True
                self._wake_score_streak = 0
        return detected

    def feed(self, pcm: bytes) -> list[GateEvent]:
        if not pcm:
            return []
        self._pending.extend(pcm[: len(pcm) - (len(pcm) % BYTES_PER_SAMPLE)])
        frame_bytes = VAD_FRAME_SAMPLES * BYTES_PER_SAMPLE
        events: list[GateEvent] = []
        now = self.clock()

        while len(self._pending) >= frame_bytes:
            frame = bytes(self._pending[:frame_bytes])
            del self._pending[:frame_bytes]
            self._history.append(frame)

            samples = np.frombuffer(frame, dtype="<i2")
            vad_event = self.vad(samples)
            was_speaking = self._speaking
            started = vad_event == "start"
            ended = vad_event == "end"

            if started:
                self._speaking = True
                self._utterance = bytearray(b"".join(self._history))
            elif was_speaking:
                self._utterance.extend(frame)

            just_woke = self._wake_frames(frame, now, events)
            if just_woke and self._speaking and not self._utterance:
                self._utterance = bytearray(b"".join(self._history))

            if ended or (was_speaking and len(self._utterance) >= self._max_utterance_bytes):
                self._speaking = False
                audio = bytes(self._utterance)
                self._utterance.clear()
                if len(audio) >= self._min_utterance_bytes and self.conversation_active:
                    events.append(GateEvent("utterance", audio=audio, score=self._last_score))

        if self._active and now >= self._conversation_until and not self._speaking:
            self._active = False
            self._wake_pending.clear()
            reset = getattr(self.vad, "reset", None)
            if reset:
                reset()
            events.append(GateEvent("idle"))

        return events


def create_audio_turn_gate(root_dir: str) -> AudioTurnGate:
    threshold = float(os.environ.get("SPHERE_WAKEWORD_THRESHOLD", "0.10"))
    followup = float(os.environ.get("SPHERE_FOLLOWUP_SECONDS", "8"))
    model_dir = os.environ.get(
        "SPHERE_WAKEWORD_CACHE", os.path.join(root_dir, "models", "wakeword")
    )
    custom_model = os.environ.get("SPHERE_WAKEWORD_MODEL", "")
    detector = OpenWakeWordDetector(model_dir, custom_model, threshold)
    vad = create_silero_vad(
        silence_ms=1000,
        model_path=os.environ.get("SPHERE_VAD_MODEL", "/opt/jarvis/models/silero_vad.onnx"),
    )
    return AudioTurnGate(
        detector,
        vad,
        wake_threshold=threshold,
        followup_seconds=followup,
        max_utterance_seconds=float(os.environ.get("SPHERE_MAX_UTTERANCE_S", "15")),
    )

