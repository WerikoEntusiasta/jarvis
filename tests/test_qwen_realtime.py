import asyncio
import base64
import json
import os
import unittest
from unittest.mock import patch

import numpy as np

from qwen_realtime import (
    AudioPipe,
    QwenRealtimeSession,
    build_function_call_output,
    build_session_config,
    converse_turn,
    is_enabled,
    resample_pcm16,
    QWEN_AGENT_TOOLS,
)


def _pcm16(freq_hz: float, segundos: float, taxa: int = 16000) -> bytes:
    t = np.linspace(0, segundos, int(taxa * segundos), endpoint=False)
    onda = (0.4 * np.sin(2 * np.pi * freq_hz * t) * 32767).astype("<i2")
    return onda.tobytes()


class TestConfig(unittest.TestCase):
    def test_is_enabled_exige_chave(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(is_enabled())
        with patch.dict(os.environ, {"QWEN_REALTIME_API_KEY": "sk-teste"}, clear=True):
            self.assertTrue(is_enabled())

    def test_is_enabled_aceita_chaves_alternativas(self):
        for var in ("CUBICSPACES_API_KEY", "DASHSCOPE_API_KEY"):
            with patch.dict(os.environ, {var: "sk-teste"}, clear=True):
                self.assertTrue(is_enabled(), var)

    def test_session_config_voz_ptbr_e_tools(self):
        with patch.dict(os.environ, {"QWEN_REALTIME_VOICE": "longanqian"}, clear=True):
            cfg = build_session_config()
        self.assertEqual(cfg["voice"], "longanqian")
        self.assertIn("portugues do Brasil", cfg["instructions"])
        self.assertIn("Senhor Werik", cfg["instructions"])
        self.assertIsNone(cfg["turn_detection"])  # turno manual (VAD da esfera)
        self.assertEqual(cfg["modalities"], ["text", "audio"])
        from qwen_realtime import carregar_tools_conversa
        self.assertEqual(cfg["tools"], carregar_tools_conversa())

    def test_tools_tem_raciocinar_e_subagente(self):
        nomes = [t["function"]["name"] for t in QWEN_AGENT_TOOLS]
        self.assertEqual(nomes, ["raciocinar", "subagente"])
        for tool in QWEN_AGENT_TOOLS:
            self.assertEqual(tool["type"], "function")
            params = tool["function"]["parameters"]
            self.assertEqual(params["type"], "object")
            self.assertTrue(params["required"])

    def test_catalogo_direto_inclui_comandos_e_exclui_sensiveis(self):
        from qwen_realtime import carregar_tools_conversa, _TOOLS_DELEGADAS

        nomes = [t["function"]["name"] for t in carregar_tools_conversa()]
        # comandos do dia a dia executados direto pelo modelo de conversa
        for esperado in ("pc_volume", "open_app", "control_lights",
                         "start_dynamic_presentation", "generate_and_show_screen"):
            self.assertIn(esperado, nomes)
        # operacoes sensiveis/complexas ficam disponiveis via 'subagente'
        for delegada in _TOOLS_DELEGADAS:
            self.assertNotIn(delegada, nomes)
        # delegacoes sempre presentes
        self.assertIn("raciocinar", nomes)
        self.assertIn("subagente", nomes)

    def test_toda_tool_tem_name_e_description(self):
        """Regressao: a API do Qwen valida o schema - toda tool precisa de name."""
        import mimo_tools

        nomes = []
        for i, t in enumerate(mimo_tools.TOOLS):
            fn = t.get("function") or {}
            self.assertTrue(fn.get("name"), f"tool #{i} sem name: {str(t)[:120]}")
            self.assertTrue(fn.get("description"), f"tool #{i} sem description")
            nomes.append(fn["name"])
        self.assertEqual(len(nomes), len(set(nomes)), "nomes de tool duplicados")
        self.assertIn("start_dynamic_presentation", nomes)


class TestFunctionCallOutput(unittest.TestCase):
    def test_output_e_json_string(self):
        item = build_function_call_output("call-1", "resultado qualquer")
        self.assertEqual(item["type"], "function_call_output")
        self.assertEqual(item["call_id"], "call-1")
        self.assertIsInstance(item["output"], str)
        payload = json.loads(item["output"])
        self.assertEqual(payload["resultado"], "resultado qualquer")


class TestResample(unittest.TestCase):
    def test_identidade_quando_taxas_iguais(self):
        dados = b"\x01\x02\x03\x04"
        self.assertEqual(resample_pcm16(dados, 16000, 16000), dados)

    def test_vazio(self):
        self.assertEqual(resample_pcm16(b"", 24000, 16000), b"")

    def test_24k_para_16k_duracao_correta(self):
        pcm = _pcm16(440, 1.0, 24000)  # 1 s @ 24 kHz
        saida = resample_pcm16(pcm, 24000, 16000)
        self.assertEqual(len(saida), 16000 * 2)  # 1 s @ 16 kHz s16le

    def test_16k_para_24k_duracao_correta(self):
        pcm = _pcm16(440, 1.0, 16000)
        saida = resample_pcm16(pcm, 16000, 24000)
        self.assertEqual(len(saida), 24000 * 2)

    def test_preserva_amplitude_aproximada(self):
        pcm = _pcm16(440, 0.5, 24000)
        saida = resample_pcm16(pcm, 24000, 16000)
        entrada = np.frombuffer(pcm, dtype="<i2").astype(np.float32)
        saida_np = np.frombuffer(saida, dtype="<i2").astype(np.float32)
        self.assertLess(
            abs(float(np.abs(entrada).max()) - float(np.abs(saida_np).max())) / 32767.0,
            0.05,
        )

    def test_bytes_impares_sao_truncados(self):
        saida = resample_pcm16(b"\x01\x02\x03", 24000, 16000)
        self.assertEqual(len(saida) % 2, 0)


class TestAudioPipe(unittest.TestCase):
    def test_envia_frames_com_pacing_e_eventos(self):
        frames = []

        async def _run():
            pipe = AudioPipe(
                lambda f: frames.append(f),
                on_start=lambda: frames.append("start"),
                on_stop=lambda: frames.append("stop"),
            )
            pipe.start()
            pipe.submit("r1", b"\x01\x02" * 2000)  # ~4000 B -> 7 frames de 640
            pipe.end_response()
            await pipe.drain(timeout=5)

        asyncio.run(_run())
        self.assertEqual(frames[0], "start")
        self.assertEqual(frames[-1], "stop")
        blocos = [f for f in frames if isinstance(f, bytes)]
        self.assertEqual(sum(len(b) for b in blocos), 4000)

    def test_cancel_descarta_frames_da_resposta(self):
        frames = []

        async def _run():
            pipe = AudioPipe(lambda f: frames.append(f))
            pipe.start()
            pipe.submit("r1", b"\x01\x02" * 2000)
            pipe.cancel("r1")
            pipe.end_response()
            await pipe.drain(timeout=5)

        asyncio.run(_run())
        self.assertEqual(frames, [])


class _FalsoWS:
    """WebSocket falso: registra envios e devolve eventos scriptados."""

    def __init__(self, eventos):
        self.enviados = []
        self._eventos = list(eventos)
        self.closed = False

    async def send(self, mensagem):
        self.enviados.append(json.loads(mensagem))

    async def __aiter__(self):
        for evento in self._eventos:
            yield json.dumps(evento)
        # mantem a conexao "aberta" aguardando (o recv_task e cancelado no close)
        await asyncio.Event().wait()

    async def close(self):
        self.closed = True


class _StubWebsockets:
    """Substitui o modulo websockets devolvendo um _FalsoWS no connect()."""

    def __init__(self, ws):
        self._ws = ws
        self.url = None

    async def connect(self, url, **kwargs):
        self.url = url
        return self._ws


class TestSessaoProtocolo(unittest.TestCase):
    def _rodar(self, eventos, audio, resposta_tool=None):
        frames = []
        ws = _FalsoWS(eventos)
        stub = _StubWebsockets(ws)

        async def _run():
            pipe = AudioPipe(lambda f: frames.append(f))
            sessao = QwenRealtimeSession("dev-1", pipe)
            with patch("qwen_realtime.websockets", stub):
                if resposta_tool is not None:
                    with patch("qwen_realtime._run_agent_sync", return_value=resposta_tool):
                        ok = await sessao.converse(audio, timeout=5)
                else:
                    ok = await sessao.converse(audio, timeout=5)
            await sessao.close()
            return ok

        return asyncio.run(_run()), ws, frames

    def test_turno_simples_texto_e_audio(self):
        pcm24 = _pcm16(440, 0.5, 24000)
        eventos = [
            {"type": "session.created", "session": {"id": "s1"}},
            {"type": "response.created", "response": {"id": "r1"}},
            {"type": "response.audio.delta", "response_id": "r1",
             "delta": base64.b64encode(pcm24).decode()},
            {"type": "response.done", "response": {"status": "completed"}},
        ]
        ok, ws, frames = self._rodar(eventos, _pcm16(300, 0.3, 16000))
        self.assertTrue(ok)
        tipos = [m["type"] for m in ws.enviados]
        self.assertIn("session.update", tipos)
        self.assertIn("input_audio_buffer.append", tipos)
        self.assertIn("input_audio_buffer.commit", tipos)
        self.assertIn("response.create", tipos)
        # audio de saida reamostrado 24k -> 16k
        enviados = [f for f in frames if isinstance(f, bytes)]
        self.assertGreater(sum(len(f) for f in enviados), 0)

    def test_function_call_executa_agente_e_devolve_output(self):
        pcm24 = _pcm16(440, 0.2, 24000)
        eventos = [
            {"type": "response.created", "response": {"id": "r1"}},
            {
                "type": "response.function_call_arguments.done",
                "call_id": "c1",
                "name": "raciocinar",
                "arguments": json.dumps({"pergunta": "qual a raiz de 144?"}),
            },
            {"type": "response.done", "response": {"status": "completed"}},
            {"type": "response.created", "response": {"id": "r2"}},
            {"type": "response.audio.delta", "response_id": "r2",
             "delta": base64.b64encode(pcm24).decode()},
            {"type": "response.done", "response": {"status": "completed"}},
        ]
        ok, ws, _ = self._rodar(eventos, _pcm16(300, 0.2, 16000), resposta_tool="12")
        self.assertTrue(ok)
        outputs = [
            m for m in ws.enviados
            if m.get("type") == "conversation.item.create"
            and m.get("item", {}).get("type") == "function_call_output"
        ]
        self.assertEqual(len(outputs), 1)
        self.assertEqual(outputs[0]["item"]["call_id"], "c1")
        self.assertEqual(json.loads(outputs[0]["item"]["output"])["resultado"], "12")
        creates = [m for m in ws.enviados if m.get("type") == "response.create"]
        self.assertEqual(len(creates), 2)  # um por turno + um apos a tool

    def test_function_call_comando_direto_executa_sem_agente(self):
        eventos = [
            {"type": "response.created", "response": {"id": "r1"}},
            {
                "type": "response.function_call_arguments.done",
                "call_id": "c1",
                "name": "pc_volume",
                "arguments": json.dumps({"action": "up"}),
            },
            {"type": "response.done", "response": {"status": "completed"}},
            {"type": "response.done", "response": {"status": "completed"}},
        ]
        capturas = {}

        def _fake_execute_tool(name, args):
            capturas["name"] = name
            capturas["args"] = args
            return {"ok": True, "volume": 80}

        with patch("mimo_tools.execute_tool", side_effect=_fake_execute_tool) as ex:
            frames = []
            ws = _FalsoWS(eventos)
            stub = _StubWebsockets(ws)

            async def _run():
                pipe = AudioPipe(lambda f: frames.append(f))
                sessao = QwenRealtimeSession("dev-1", pipe)
                with patch("qwen_realtime.websockets", stub), \
                     patch("qwen_realtime._run_agent_sync") as agente:
                    ok = await sessao.converse(_pcm16(300, 0.1, 16000), timeout=5)
                await sessao.close()
                return ok, agente.called

            ok, agente_chamado = asyncio.run(_run())

        self.assertTrue(ok)
        self.assertTrue(ex.called)           # comando executado diretamente
        self.assertFalse(agente_chamado)     # SEM passar pelo LLM/agente
        self.assertEqual(capturas["name"], "pc_volume")
        self.assertEqual(capturas["args"], {"action": "up"})
        outputs = [m for m in ws.enviados
                   if m.get("type") == "conversation.item.create"
                   and m.get("item", {}).get("type") == "function_call_output"]
        self.assertEqual(len(outputs), 1)
        self.assertIn("volume", outputs[0]["item"]["output"])

    def test_function_call_subagente_delega_ao_mimo(self):
        eventos = [
            {"type": "response.created", "response": {"id": "r1"}},
            {
                "type": "response.function_call_arguments.done",
                "call_id": "c1",
                "name": "subagente",
                "arguments": json.dumps({"tarefa": "refatore o firmware da esfera"}),
            },
            {"type": "response.done", "response": {"status": "completed"}},
            {"type": "response.done", "response": {"status": "completed"}},
        ]
        capturas = {}

        def _fake_agent(prompt, force_route, allow_tools):
            capturas["prompt"] = prompt
            capturas["force_route"] = force_route
            capturas["allow_tools"] = allow_tools
            return "tarefa complexa concluida"

        with patch("qwen_realtime._run_agent_sync", side_effect=_fake_agent):
            frames = []
            ws = _FalsoWS(eventos)
            stub = _StubWebsockets(ws)

            async def _run():
                pipe = AudioPipe(lambda f: frames.append(f))
                sessao = QwenRealtimeSession("dev-1", pipe)
                with patch("qwen_realtime.websockets", stub):
                    ok = await sessao.converse(_pcm16(300, 0.1, 16000), timeout=5)
                await sessao.close()
                return ok

            ok = asyncio.run(_run())

        self.assertTrue(ok)
        self.assertIn("SUBAGENTE COMPLEXO", capturas["prompt"])
        self.assertIsNone(capturas["force_route"])  # agente completo MiMo
        self.assertTrue(capturas["allow_tools"])    # com todas as ferramentas internas

    def test_erro_do_servidor_falha_turno(self):
        eventos = [{"type": "error", "error": {"message": "boom"}}]
        ok, _, _ = self._rodar(eventos, _pcm16(300, 0.1, 16000))
        self.assertFalse(ok)

    def test_corrida_vad_response_nao_falha_turno(self):
        """Erros benignos de corrida (VAD x response.create) nao quebram o turno."""
        eventos = [
            {"type": "response.created", "response": {"id": "r1"}},
            {"type": "error", "error": {"message":
                "Server VAD turn committed but no response was created because a manual response is already in progress."}},
            {"type": "error", "error": {"message":
                "Cannot create response while another response is in progress."}},
            {"type": "response.audio.delta", "response_id": "r1",
             "delta": base64.b64encode(_pcm16(440, 0.1, 24000)).decode()},
            {"type": "response.done", "response": {"status": "completed"}},
        ]
        ok, _, _ = self._rodar(eventos, _pcm16(300, 0.1, 16000))
        self.assertTrue(ok)  # turno completou apesar das corridas


class TestConverseTurn(unittest.TestCase):
    def test_sem_chave_retorna_false_sem_enviar(self):
        enviados = []

        async def _run():
            return await converse_turn(
                "dev-1", b"\x00\x00" * 100,
                send_json=lambda p: enviados.append(p),
                send_bin=lambda f: asyncio.sleep(0),
            )

        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(asyncio.run(_run()))
        self.assertEqual(enviados, [])

    def test_audio_vazio_retorna_false(self):
        async def _run():
            return await converse_turn(
                "dev-1", b"",
                send_json=lambda p: None,
                send_bin=lambda f: asyncio.sleep(0),
            )

        with patch.dict(os.environ, {"QWEN_REALTIME_API_KEY": "sk"}, clear=True):
            self.assertFalse(asyncio.run(_run()))


class TestLiveConversation(unittest.TestCase):
    """Conversa ao vivo: streaming continuo com VAD no servidor."""

    def _rodar(self, eventos, alimentar_pcm=None):
        audios, estados, transcricoes, tools = [], [], [], []
        ws = _FalsoWS(eventos)
        stub = _StubWebsockets(ws)

        async def _run():
            from qwen_realtime import LiveConversation

            conv = LiveConversation(
                on_audio=lambda pcm: audios.append(pcm),
                on_transcript=lambda papel, texto: transcricoes.append((papel, texto)),
                on_state=lambda estado: estados.append(estado),
                on_tool=lambda name, args: tools.append((name, args)),
            )
            with patch("qwen_realtime.websockets", stub):
                await conv.start()
                if alimentar_pcm:
                    await conv.send_audio(alimentar_pcm)
                # da tempo do recv consumir os eventos scriptados
                for _ in range(30):
                    await asyncio.sleep(0.01)
                await conv.close()

        asyncio.run(_run())
        return ws, audios, estados, transcricoes, tools

    def test_fluxo_fala_fala_com_transcricoes(self):
        pcm24 = _pcm16(440, 0.3, 24000)
        eventos = [
            {"type": "session.created", "session": {"id": "s1"}},
            {"type": "session.updated", "session": {"id": "s1"}},
            {"type": "input_audio_buffer.speech_started"},
            {"type": "conversation.item.input_audio_transcription.completed",
             "transcript": "que horas sao?"},
            {"type": "response.created", "response": {"id": "r1"}},
            {"type": "response.audio_transcript.delta", "delta": "Sao dez."},
            {"type": "response.audio.delta", "response_id": "r1",
             "delta": base64.b64encode(pcm24).decode()},
            {"type": "response.done", "response": {"status": "completed"}},
        ]
        ws, audios, estados, transcricoes, tools = self._rodar(
            eventos, alimentar_pcm=b"\x01\x02" * 1600
        )
        tipos = [m["type"] for m in ws.enviados]
        self.assertIn("session.update", tipos)
        self.assertIn("input_audio_buffer.append", tipos)
        # resposta falada chegou (24 kHz puro, sem reamostrar)
        self.assertEqual(b"".join(audios), pcm24)
        self.assertIn(("user", "que horas sao?"), transcricoes)
        self.assertIn(("assistant", "Sao dez."), transcricoes)
        self.assertIn("speaking", estados)
        self.assertIn("listening", estados)
        self.assertEqual(tools, [])

    def test_turn_detection_configuravel(self):
        eventos = [{"type": "session.created", "session": {"id": "s"}},
                   {"type": "session.updated", "session": {"id": "s"}}]
        ws, _, _, _, _ = self._rodar(eventos)
        cfg = next(m for m in ws.enviados if m["type"] == "session.update")["session"]
        self.assertEqual(cfg["turn_detection"], {"type": "server_vad"})

    def test_barge_in_limpa_estado_para_interrupt(self):
        eventos = [
            {"type": "response.created", "response": {"id": "r1"}},
            {"type": "response.audio.delta", "response_id": "r1",
             "delta": base64.b64encode(_pcm16(440, 0.1, 24000)).decode()},
            {"type": "input_audio_buffer.speech_started"},  # usuario falou por cima
        ]
        _, _, estados, _, _ = self._rodar(eventos)
        self.assertIn("interrupt", estados)
        self.assertGreater(estados.count("listening"), 0)

    def test_function_call_na_conversa_roteia_para_agente(self):
        eventos = [
            {"type": "response.created", "response": {"id": "r1"}},
            {"type": "response.function_call_arguments.done",
             "call_id": "c1", "name": "subagente",
             "arguments": json.dumps({"tarefa": "refatore o firmware da esfera"})},
            {"type": "response.done", "response": {"status": "completed"}},
            {"type": "response.done", "response": {"status": "completed"}},
        ]
        ws = _FalsoWS(eventos)
        stub = _StubWebsockets(ws)
        audios, estados, transcricoes, tools = [], [], [], []

        async def _run():
            from qwen_realtime import LiveConversation

            conv = LiveConversation(
                on_audio=lambda pcm: audios.append(pcm),
                on_transcript=lambda papel, texto: transcricoes.append((papel, texto)),
                on_state=lambda estado: estados.append(estado),
                on_tool=lambda name, args: tools.append((name, args)),
            )
            with patch("qwen_realtime.websockets", stub), \
                 patch("qwen_realtime._run_agent_sync", return_value="tarefa concluida") as agente:
                await conv.start()
                await conv.send_audio(b"\x01\x02" * 1600)
                for _ in range(50):
                    await asyncio.sleep(0.01)
                await conv.close()
                return agente.called

        chamado = asyncio.run(_run())
        self.assertTrue(chamado)  # tool foi roteada para o agente MiMo
        self.assertEqual(tools, [("subagente", json.dumps({"tarefa": "refatore o firmware da esfera"}))])
        outputs = [m for m in ws.enviados
                   if m.get("type") == "conversation.item.create"
                   and m.get("item", {}).get("type") == "function_call_output"]
        self.assertEqual(len(outputs), 1)
        self.assertIn("thinking", estados)

    def test_comando_direto_na_conversa_executa_sem_agente(self):
        eventos = [
            {"type": "response.created", "response": {"id": "r1"}},
            {"type": "response.function_call_arguments.done",
             "call_id": "c1", "name": "pc_volume",
             "arguments": json.dumps({"action": "up"})},
            {"type": "response.done", "response": {"status": "completed"}},
            {"type": "response.done", "response": {"status": "completed"}},
        ]
        ws = _FalsoWS(eventos)
        stub = _StubWebsockets(ws)
        audios, estados, transcricoes, tools = [], [], [], []

        async def _run():
            from qwen_realtime import LiveConversation

            conv = LiveConversation(
                on_audio=lambda pcm: audios.append(pcm),
                on_transcript=lambda papel, texto: transcricoes.append((papel, texto)),
                on_state=lambda estado: estados.append(estado),
                on_tool=lambda name, args: tools.append((name, args)),
            )
            with patch("qwen_realtime.websockets", stub), \
                 patch("mimo_tools.execute_tool",
                       return_value={"ok": True, "volume": 80}) as ex, \
                 patch("qwen_realtime._run_agent_sync") as agente:
                await conv.start()
                await conv.send_audio(b"\x01\x02" * 1600)
                for _ in range(50):
                    await asyncio.sleep(0.01)
                await conv.close()
                return ex.called, agente.called

        ex_chamado, agente_chamado = asyncio.run(_run())
        self.assertTrue(ex_chamado)        # executado direto pelo modelo de conversa
        self.assertFalse(agente_chamado)   # sem MiMo no meio


class TestBridge(unittest.TestCase):
    def test_ponte_recusa_cliente_sem_chave(self):
        import qwen_live_bridge as bridge

        async def _run():
            ws = _FalsoWS([])
            handler = bridge._ClientBridge(ws)
            with patch.dict(os.environ, {}, clear=True):
                await handler.rodar()
            return ws

        ws = asyncio.run(_run())
        erros = [m for m in ws.enviados if m.get("type") == "error"]
        self.assertTrue(erros)
        self.assertIn("QWEN_REALTIME_API_KEY", erros[0]["message"])


if __name__ == "__main__":
    unittest.main()
