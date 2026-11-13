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


class TestValidadorApresentacao(unittest.TestCase):
    """Regressao: campos estruturados do content dict chegam ao HUD.

    Bug real: o modelo manda table em {content:{columns,rows}} e comparison em
    {content:{items}} - o validador so lia chaves de topo, entao tabelas e
    comparacoes chegavam vazias no canvas.
    """

    def _validar(self, scenes):
        from dynamic_presentation_engine import validate_presentation_script
        return validate_presentation_script({"title": "T", "scenes": scenes})

    def test_table_extraido_do_content_dict(self):
        v = self._validar([{
            "title": "Mercado", "component_type": "table",
            "content": {"heading": "Taxas", "columns": ["Regiao", "Taxa"],
                        "rows": [["EUA", "3.7"], ["Brasil", "7.8"]]}
        }])
        s = v["scenes"][0]
        self.assertEqual(s["headers"], ["Regiao", "Taxa"])
        self.assertEqual(len(s["rows"]), 2)
        self.assertEqual(s["content"], "Taxas")

    def test_comparison_items_extraido_do_content_dict(self):
        v = self._validar([{
            "title": "Desafios", "component_type": "comparison",
            "content": {"heading": "Pro/con", "items": [
                {"title": "Inflacao", "pro": "Politica", "con": "Pressao"}]}
        }])
        s = v["scenes"][0]
        self.assertEqual(len(s["items"]), 1)
        self.assertEqual(s["items"][0]["title"], "Inflacao")

    def test_chart_data_preservado_como_opcoes_amigaveis(self):
        v = self._validar([{
            "title": "Temp", "component_type": "chart",
            "content": {"chart_type": "line", "categories": ["06h", "09h"],
                        "series": [{"name": "T", "data": [22, 25]}]}
        }])
        d = v["scenes"][0]["data"]
        self.assertEqual(d["chart_type"], "line")
        self.assertEqual(d["categories"], ["06h", "09h"])
        self.assertEqual(d["series"][0]["data"], [22, 25])

    def test_campos_de_topaindem_contam(self):
        # Cenas antigas usavam chaves de topo - nao podem quebrar
        v = self._validar([{
            "title": "Old", "component_type": "table",
            "headers": ["A"], "rows": [["1"]],
            "content": "texto livre"
        }])
        s = v["scenes"][0]
        self.assertEqual(s["headers"], ["A"])
        self.assertEqual(s["rows"], [["1"]])
        self.assertEqual(s["content"], "texto livre")

    def test_toda_tool_schema_ainda_valido(self):
        # Garante que a edicao da description nao quebrou o schema
        import json
        import mimo_tools
        json.dumps(mimo_tools.TOOLS)
        alvo = [t for t in mimo_tools.TOOLS
                if t["function"]["name"] == "start_dynamic_presentation"]
        self.assertEqual(len(alvo), 1)
        # a orientacao de formatos fica na description do array "scenes"
        scenes_desc = (alvo[0]["function"]["parameters"]
                       .get("properties", {})
                       .get("scenes", {})
                       .get("description", ""))
        self.assertIn("columns", scenes_desc)
        self.assertIn("items", scenes_desc)
        self.assertIn("chart_type", scenes_desc)


class TestShowCardUniversal(unittest.TestCase):
    """Card universal: toda resposta do JARVIS vira card visual no HUD."""

    def test_show_card_presente_no_catalogo(self):
        import mimo_tools
        nomes = [t["function"]["name"] for t in mimo_tools.TOOLS]
        self.assertIn("show_card", nomes)
        alvo = [t for t in mimo_tools.TOOLS
                if t["function"]["name"] == "show_card"][0]
        enum = alvo["function"]["parameters"]["properties"]["type"]["enum"]
        self.assertEqual(sorted(enum), ["news", "text", "weather"])

    def test_show_card_text_retorna_summary(self):
        from mimo_tools import execute_tool
        r = execute_tool("show_card", {
            "type": "text",
            "title": "Resposta",
            "text": "A Selic esta em 12,75% ao ano.",
        })
        self.assertTrue(r.get("ok"), r)
        self.assertEqual(r["card_type"], "text")
        self.assertIn("Selic", r["summary"])

    def test_show_card_text_sem_texto_erro(self):
        from mimo_tools import execute_tool
        r = execute_tool("show_card", {"type": "text", "title": "Vazio"})
        self.assertFalse(r.get("ok"))
        self.assertIn("text", r.get("error", ""))

    def test_show_card_weather_real(self):
        from mimo_tools import execute_tool
        r = execute_tool("show_card", {
            "type": "weather", "title": "Tempo", "city": "São Paulo", "days": 7,
        })
        self.assertTrue(r.get("ok"), r)
        self.assertIn("máxima", r["summary"])

    def test_show_card_weather_sem_cidade_erro(self):
        from mimo_tools import execute_tool
        r = execute_tool("show_card", {"type": "weather", "title": "Tempo"})
        self.assertFalse(r.get("ok"))
        self.assertIn("city", r.get("error", ""))

    def test_show_card_news_real(self):
        from mimo_tools import execute_tool
        r = execute_tool("show_card", {
            "type": "news", "title": "Noticias",
            "query": "tecnologia", "limit": 4,
        })
        self.assertTrue(r.get("ok"), r)
        self.assertTrue(r["summary"].startswith("Manchetes"))

    def test_cena_text_passa_no_validador(self):
        # a cena gerada precisa sobreviver ao validador do HUD
        from dynamic_presentation_engine import validate_presentation_script
        v = validate_presentation_script({"title": "t", "scenes": [{
            "title": "Resposta", "component_type": "text",
            "content": "texto da resposta", "copy_text": "texto da resposta",
        }]})
        s = v["scenes"][0]
        self.assertEqual(s["component_type"], "text")
        self.assertEqual(s["copy_text"], "texto da resposta")

    def test_tipos_novos_validos_no_validador(self):
        from dynamic_presentation_engine import validate_presentation_script
        for ct in ("text", "news", "weather"):
            v = validate_presentation_script({"title": "t", "scenes": [
                {"title": "x", "component_type": ct, "content": "c"}]})
            self.assertEqual(v["scenes"][0]["component_type"], ct, ct)


class TestWebIntel(unittest.TestCase):
    """Web intel via infra self-hosted no ZimaOS (SearXNG + Crawl4ai)."""

    def test_tools_web_no_catalogo(self):
        import mimo_tools
        nomes = [t["function"]["name"] for t in mimo_tools.TOOLS]
        for esperado in ("web_search", "read_webpage", "web_research"):
            self.assertIn(esperado, nomes)

    def test_tools_web_chegam_ao_qwen(self):
        from qwen_realtime import carregar_tools_conversa, _TOOLS_DELEGADAS
        nomes = [t["function"]["name"] for t in carregar_tools_conversa()]
        for esperado in ("web_search", "read_webpage", "web_research"):
            self.assertIn(esperado, nomes)
            self.assertNotIn(esperado, _TOOLS_DELEGADAS)

    def test_web_search_real(self):
        from mimo_tools import execute_tool
        r = execute_tool("web_search", {"query": "python language", "limit": 3})
        self.assertTrue(r.get("ok"), r)
        self.assertGreaterEqual(len(r["results"]), 1)
        self.assertIn("summary", r)
        self.assertIn("url", r["results"][0])

    def test_web_search_query_vazia_erro(self):
        from mimo_tools import execute_tool
        r = execute_tool("web_search", {"query": ""})
        self.assertFalse(r.get("ok"))

    def test_read_webpage_real(self):
        from mimo_tools import execute_tool
        r = execute_tool("read_webpage", {
            "url": "https://example.com", "max_chars": 2000})
        self.assertTrue(r.get("ok"), r)
        self.assertGreater(r["length"], 100)
        self.assertIn("markdown", r)

    def test_read_webpage_sem_esquema_normaliza(self):
        # URL sem https:// deve ser normalizada
        from web_intel import read_url
        r = read_url("example.com", limite=1000)
        self.assertTrue(r.get("ok"), r)
        self.assertTrue(r["url"].startswith("https://"))

    def test_web_research_retorna_dossie(self):
        from mimo_tools import execute_tool
        r = execute_tool("web_research", {"query": "historia do brasil", "depth": 2})
        self.assertTrue(r.get("ok"), r)
        self.assertIn("results", r)
        self.assertIn("pages", r)
        self.assertGreaterEqual(r["pages_read"], 1)

    def test_content_type_json_no_post(self):
        # Regressao: sem Content-Type o urllib envia x-www-form-urlencoded
        # e o Crawl4ai responde 422
        from web_intel import _http
        import urllib.request
        capturado = {}
        orig = urllib.request.urlopen

        def fake(req, *a, **k):
            capturado["ct"] = req.get_header("Content-type")
            capturado["data"] = req.data
            raise KeyboardInterrupt  # so captura, nao envia
        urllib.request.urlopen = fake
        try:
            with self.assertRaises(KeyboardInterrupt):
                _http("http://x/crawl", payload={"urls": ["https://x"]})
        finally:
            urllib.request.urlopen = orig
        self.assertEqual(capturado["ct"], "application/json")


class TestWhatsApp(unittest.TestCase):
    """WhatsApp via WAHA self-hosted (ZimaOS) - tools + card + endpoints."""

    def test_tools_whatsapp_no_catalogo_e_no_qwen(self):
        import mimo_tools
        from qwen_realtime import carregar_tools_conversa, _TOOLS_DELEGADAS
        esperadas = ("whatsapp_status", "whatsapp_qr", "whatsapp_unread",
                     "whatsapp_read", "whatsapp_send")
        nomes_total = [t["function"]["name"] for t in mimo_tools.TOOLS]
        nomes_qwen = [t["function"]["name"] for t in carregar_tools_conversa()]
        for esp in esperadas:
            self.assertIn(esp, nomes_total)
            self.assertIn(esp, nomes_qwen)
            self.assertNotIn(esp, _TOOLS_DELEGADAS)

    def test_waha_sessions_reais(self):
        # contra o WAHA real do ZimaOS: sessions do JARVIS existem
        import waha_client as wa
        r = wa.get_sessions()
        self.assertTrue(r.get("ok"), r)
        nomes = {s["name"]: s for s in r["sessions"]}
        self.assertIn("jarvis", nomes)
        self.assertIn("Businees", nomes)
        self.assertEqual(nomes["jarvis"]["role"], "pessoal")
        self.assertEqual(nomes["Businees"]["role"], "comercial")
        # o comercial deve estar conectado (estado conhecido)
        self.assertEqual(nomes["Businees"]["status"], "WORKING")

    def test_qr_pessoal_dataurl(self):
        import waha_client as wa
        r = wa.get_qr("jarvis")
        self.assertTrue(r.get("ok"), r)
        if r.get("connected"):
            return  # conectado nao precisa de QR
        self.assertTrue(r["qr"].startswith("data:image/"), "QR nao e dataURL")

    def test_unread_shape(self):
        import waha_client as wa
        r = wa.get_unread()
        self.assertTrue(r.get("ok"), r)
        self.assertIn("messages", r)
        self.assertIn("total_unread", r)
        self.assertIn("summary", r)
        for m in r["messages"]:
            for campo in ("session", "chat_id", "name", "unread", "label"):
                self.assertIn(campo, m)

    def test_send_sem_args_erro(self):
        import waha_client as wa
        r = wa.send_text("", "")
        self.assertFalse(r.get("ok"))
        r2 = wa.send_text("5500000000000@c.us", "")
        self.assertFalse(r2.get("ok"))

    def test_tool_status_via_execute(self):
        from mimo_tools import execute_tool
        r = execute_tool("whatsapp_status", {})
        self.assertTrue(r.get("ok"), r)
        self.assertTrue(any(s["name"] == "Businees" for s in r["sessions"]))

    def test_tool_qr_broadcast_sem_base64_ao_modelo(self):
        # a tool nao deve devolver o dataURL ao modelo (gasta tokens)
        from mimo_tools import execute_tool
        r = execute_tool("whatsapp_qr", {"session": "jarvis"})
        self.assertTrue(r.get("ok"), r)
        self.assertNotIn("qr", r, "dataURL vazou para o modelo")
        self.assertIn("message", r)

    def test_card_whatsapp_no_validador(self):
        from dynamic_presentation_engine import validate_presentation_script
        v = validate_presentation_script({"title": "t", "scenes": [{
            "title": "Zap", "component_type": "whatsapp",
            "content": "2 nao lidas",
            "messages": [{"name": "X", "unread": 1, "label": "oi",
                          "chat_id": "5511@c.us"}],
            "total_unread": 2, "role": "pessoal",
        }]})
        s = v["scenes"][0]
        self.assertEqual(s["component_type"], "whatsapp")
        self.assertEqual(len(s["messages"]), 1)
        self.assertEqual(s["total_unread"], 2)

    def test_endpoints_http_no_local_server(self):
        # os handlers GET/POST existem no arquivo do servidor
        from pathlib import Path
        src = Path(r"C:\JARVIS\jarvis-windows\core\local_server.py").read_text(
            encoding="utf-8", errors="replace")
        self.assertIn('"/api/whatsapp/status"', src)
        self.assertIn('"/api/whatsapp/qr"', src)
        self.assertIn('"/api/whatsapp/unread"', src)
        self.assertIn('"/api/whatsapp/reply"', src)

    def test_sem_import_interno_urlparse_no_local_server(self):
        # REGRESSAO: 'from urllib.parse import urlparse' declarado DENTRO de
        # um metodo transforma urlparse em variavel LOCAL da funcao inteira;
        # a linha inicial do do_GET (parsed = urlparse(self.path)) entao lanca
        # UnboundLocalError e TODOS os GET do HUD morrem com conexao fechada.
        from pathlib import Path
        import re
        src = Path(r"C:\JARVIS\jarvis-windows\core\local_server.py").read_text(
            encoding="utf-8", errors="replace")
        internos = [
            ln for ln in src.splitlines()
            if re.match(r"^\s+from urllib\.parse import", ln)
        ]
        self.assertEqual(
            internos, [],
            f"imports internos de urllib.parse quebram o handler: {internos}")

    def test_qr_handler_le_query_de_parsed_query(self):
        # REGRESSAO: path no do_GET e so parsed.path (SEM query string).
        # Um handler que busca '?' em path nunca ve o param e devolve o
        # QR da session errada (jarvis em vez da pedida).
        from pathlib import Path
        src = Path(r"C:\JARVIS\jarvis-windows\core\local_server.py").read_text(
            encoding="utf-8", errors="replace")
        # o handler de qr precisa ler parsed.query
        self.assertIn("qs = parse_qs(parsed.query)", src)
        # e NAO deve depender de '?' em path
        self.assertNotIn('"?" in path', src)
        self.assertNotIn("'?' in path", src)

    def test_endpoints_whatsapp_reais_via_http(self):
        # sub-executa o servidor local em porta alternativa e valida os
        # endpoints ponta a ponta (inclusive query string de session)
        import os
        import sys
        import time
        import http.client
        import json as _json

        porta = 8099
        cwd = os.getcwd()
        env_port = os.environ.get("LOCAL_SERVER_PORT")
        try:
            os.environ["LOCAL_SERVER_PORT"] = str(porta)
            sys.path.insert(0, r"C:\JARVIS\jarvis-windows")
            from core import local_server
            local_server.start_local_server(port=porta)
            time.sleep(1.0)

            def _get(path, timeout=25):
                conn = http.client.HTTPConnection("127.0.0.1", porta,
                                                  timeout=timeout)
                conn.request("GET", path)
                resp = conn.getresponse()
                body = resp.read()
                conn.close()
                return resp.status, body

            st, body = _get("/api/status")
            self.assertEqual(st, 200)

            st, body = _get("/api/whatsapp/status")
            self.assertEqual(st, 200)
            d = _json.loads(body)
            self.assertTrue(d.get("ok"))

            # query string: a session pedida deve voltar identificada
            st, body = _get("/api/whatsapp/qr?session=Businees")
            self.assertEqual(st, 200)
            d = _json.loads(body)
            self.assertEqual(d.get("session"), "Businees",
                             "query session ignorada pelo handler")
            # Businees e WORKING conhecido -> connected True (sem QR)
            self.assertTrue(d.get("connected"))

            st, body = _get("/api/whatsapp/unread?limit=3")
            self.assertEqual(st, 200)
            self.assertTrue(_json.loads(body).get("ok"))
        finally:
            os.chdir(cwd)
            if env_port is None:
                os.environ.pop("LOCAL_SERVER_PORT", None)
            else:
                os.environ["LOCAL_SERVER_PORT"] = env_port


if __name__ == "__main__":
    unittest.main()
