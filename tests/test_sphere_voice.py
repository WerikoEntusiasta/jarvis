import unittest
import json
import os
import asyncio
from unittest.mock import patch

import numpy as np

from sphere_voice import (
    AudioTurnGate,
    classify_fast_command,
    parse_alarm_time,
    parse_timer_seconds,
    strip_wake_word,
)
from sphere_audio_bridge import _load_device_tokens, _proof, serve_sphere_audio


class _SequenceVad:
    def __init__(self, events):
        self.events = iter(events)

    def __call__(self, _samples):
        return next(self.events, None)


class _LoopVad:
    def __init__(self):
        self.index = 0

    def __call__(self, _samples):
        phase = self.index % 8
        self.index += 1
        return "start" if phase == 0 else "end" if phase == 7 else None


class SphereVoiceTests(unittest.TestCase):
    def test_strip_wake_word_preserves_command(self):
        self.assertEqual(strip_wake_word("Jarvis, que horas são?"), ("que horas são?", False))
        self.assertEqual(strip_wake_word("Hey Jarvis!"), ("", True))
        self.assertEqual(strip_wake_word("abra o Spotify"), ("abra o Spotify", False))

    def test_fast_command_classification(self):
        self.assertEqual(classify_fast_command("como está o clima?"), "weather")
        self.assertEqual(classify_fast_command("que horas são agora"), "time")
        self.assertEqual(classify_fast_command("inicie um timer"), "timer")
        self.assertEqual(classify_fast_command("programe o despertador"), "alarm")

    def test_timer_and_alarm_parsing(self):
        self.assertEqual(parse_timer_seconds("timer para dois minutos"), 120)
        self.assertEqual(parse_timer_seconds("alarme em 30 segundos"), 30)
        self.assertEqual(parse_alarm_time("alarme para às 7:05"), (7, 5))
        self.assertIsNone(parse_alarm_time("alarme às 25:90"))

    def test_audio_is_not_emitted_without_wake_word(self):
        vad = _SequenceVad(["start", None, None, None, None, None, None, "end"])
        gate = AudioTurnGate(
            wakeword_score=lambda _frame: 0.0,
            vad=vad,
            wake_threshold=0.3,
        )
        frame = np.full(512, 1200, dtype="<i2").tobytes()
        events = []
        for _ in range(8):
            events.extend(gate.feed(frame))
        self.assertFalse(any(event.kind == "utterance" for event in events))

    def test_wake_word_opens_gate_and_emits_completed_speech(self):
        vad = _SequenceVad(["start", None, None, None, None, None, None, "end"])
        gate = AudioTurnGate(
            wakeword_score=lambda _frame: 0.5,
            vad=vad,
            wake_threshold=0.3,
        )
        frame = np.full(512, 1200, dtype="<i2").tobytes()
        events = []
        for _ in range(8):
            events.extend(gate.feed(frame))
        self.assertTrue(any(event.kind == "wake" for event in events))
        utterance = next(event for event in events if event.kind == "utterance")
        self.assertGreaterEqual(len(utterance.audio), 7680)

    def test_wake_score_during_silence_does_not_wake_display(self):
        gate = AudioTurnGate(
            wakeword_score=lambda _frame: 0.99,
            vad=_SequenceVad([]),
            wake_threshold=0.10,
        )
        frame = np.zeros(512, dtype="<i2").tobytes()
        events = []
        for _ in range(32):
            events.extend(gate.feed(frame))
        self.assertFalse(any(event.kind == "wake" for event in events))

    def test_wake_becomes_available_again_after_followup_window_expires(self):
        now = [0.0]
        gate = AudioTurnGate(
            wakeword_score=lambda _frame: 0.5,
            vad=_LoopVad(),
            wake_threshold=0.3,
            followup_seconds=20,
            clock=lambda: now[0],
        )
        frame = np.full(512, 1200, dtype="<i2").tobytes()
        first_round = []
        for _ in range(8):
            first_round.extend(gate.feed(frame))
        self.assertTrue(any(event.kind == "wake" for event in first_round))

        now[0] = 30.0
        second_round = []
        for _ in range(8):
            second_round.extend(gate.feed(frame))
        self.assertTrue(any(event.kind == "wake" for event in second_round))

    def test_device_auth_requires_long_token_and_nonce_bound_proof(self):
        token = "a" * 64
        with patch.dict(os.environ, {"SPHERE_DEVICE_TOKENS": json.dumps({
            "jarvis_sphere_esp32s3": token,
            "invalid-device": "too-short",
        })}):
            self.assertEqual(_load_device_tokens(), {"jarvis_sphere_esp32s3": token})
        first = _proof(token, "jarvis_sphere_esp32s3", "nonce-one")
        self.assertNotEqual(first, _proof(token, "jarvis_sphere_esp32s3", "nonce-two"))
        self.assertNotEqual(first, _proof(token, "another-device", "nonce-one"))

    def test_bridge_refuses_to_listen_without_tls_and_device_token(self):
        async def unused_audio_callback(_device_id, _audio, _socket):
            return None

        with patch.dict(os.environ, {
            "SPHERE_WS_CERTFILE": "",
            "SPHERE_WS_KEYFILE": "",
            "SPHERE_DEVICE_TOKENS": "",
        }):
            with self.assertRaisesRegex(RuntimeError, "desativada"):
                asyncio.run(serve_sphere_audio(unused_audio_callback))


if __name__ == "__main__":
    unittest.main()
