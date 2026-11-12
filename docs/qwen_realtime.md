# Conversação por Voz — Qwen-Audio-3.0-Realtime-Plus + Agente MiMo

> Camada primária de conversação falada (pt-BR) da Esfera ESP32-S3 e do HUD Windows.

---

## 1. Divisão de responsabilidades

| Papel | Modelo | Quando entra |
|---|---|---|
| **Conversação por voz** (fala → fala) | `qwen-audio-3.0-realtime-plus` | Sempre que o usuário fala com a Esfera/HUD |
| **Raciocínio profundo** | Agente MiMo Pro (`mimo-v2.6-pro`, rota `deep`) | Quando o Qwen decide chamar a tool `raciocinar` |
| **Execução de ações** | Agente MiMo Flash (`mimo-v2.6-flash` + `mimo_tools`) | Quando o Qwen decide chamar a tool `executar` |

O Qwen entende a fala e responde **falando** em português do Brasil (STT + LLM + TTS
nativos, sem etapas intermediárias — latência mínima). Quando a fala exigir
raciocínio ou execução, ele dispara *function calling* e este servidor executa a
chamada no agente MiMo (`core_ai_brain.stream_direct_ai`), devolvendo o resultado
para o Qwen falar a resposta final.

## 2. Modos de operação

### 2.1 Turno manual (Esfera ESP32-S3 — `converse_turn`)
O VAD/wake-word do firmware delimita as frases; cada utterance vira um turno
(commit + `response.create`).

### 2.2 Conversa ao vivo (HUD Windows — `LiveConversation` + `qwen_live_bridge`)
Microfone **aberto continuamente** com VAD no servidor (`server_vad`): o usuário
fala naturalmente e o Qwen responde quando ele para — sem clicar nada entre as
frases. Inclui *barge-in* (falar por cima cancela a resposta) e transcrições
dos dois lados em tempo real.

- **Ponte WebSocket**: `python qwen_live_bridge.py` → `ws://127.0.0.1:8087/ws/voice`
  (auto-iniciada pelo `local_server` do HUD; processo independente do `.exe`).
- **Frontend**: `web/qwen_live_voice.js` — captura PCM 16 kHz via Web Audio,
  reproduz as respostas (24 kHz) e atualiza legendas/estados do HUD.
- **Protocolo**: binário = PCM (entrada 16 kHz / saída 24 kHz); JSON =
  `hello`, `state`, `transcript`, `tool`, `error`.

## 2. Fluxo de um turno

```
Esfera (PCM 16 kHz) ──WSS:8096──▶ server.py::_handle_utterance
                                        │
                                        ▼
                              qwen_realtime.converse_turn()
                                        │  WebSocket (session.update, tools)
                                        ▼
                        Qwen-Audio-3.0-Realtime-Plus
                           │                    │
           response.audio.delta    response.function_call_arguments.done
           (PCM 24 kHz → 16 kHz)          │
                           │               ▼
                           │      _dispatch_tool() → core_ai_brain (MiMo)
                           │               │
                           │      conversation.item.create
                           │        (function_call_output)
                           │               │
                           ▼               ▼
                  AudioPipe (pacing 640 B/19 ms) ──▶ Esfera reproduz
```

- **Turno manual** (`turn_detection: null`): o VAD/wake-word da Esfera
  (`sphere_voice.AudioTurnGate`) já delimita os turnos.
- **Interruptions**: `input_audio_buffer.speech_started` cancela a resposta em
  andamento (`response.cancel`) e descarta frames órfãos por `response_id`.
- **Sessão persistente** por dispositivo (contexto multi-turno, TTL 30 min).

## 3. Configuração (.env)

```bash
QWEN_REALTIME_API_KEY=          # ou CUBICSPACES_API_KEY / DASHSCOPE_API_KEY
QWEN_REALTIME_URL=wss://token-plan.ap-southeast-1.maas.aliyuncs.com/api-ws/v1/realtime
QWEN_REALTIME_MODEL=qwen-audio-3.0-realtime-plus
QWEN_REALTIME_VOICE=longanqian
QWEN_REALTIME_TURN_TIMEOUT=90
QWEN_LIVE_VAD=server_vad        # VAD da conversa ao vivo
QWEN_LIVE_HOST=127.0.0.1
QWEN_LIVE_PORT=8087
```

## 4. Formatos de áudio

| Sentido | Formato |
|---|---|
| Entrada (Esfera → Qwen) | PCM s16le mono **16 kHz** |
| Saída (Qwen → Esfera) | PCM s16le mono **24 kHz**, reamostrado para 16 kHz |

O `AudioPipe` aplica o mesmo pacing do pipeline clássico (640 B / 19 ms) para não
encher o buffer TCP/TLS da Esfera (close 1006).

## 5. Fallback

Sem chave configurada, com falha de conexão ou erro de turno, `converse_turn()`
retorna `False` e o `server.py` usa o pipeline clássico
**STT (Groq/MiMo ASR/Whisper local) → LLM → TTS (ElevenLabs/Edge-TTS)** integralmente.

## 6. Testes

```bash
python -m unittest tests.test_qwen_realtime -v
```

Cobre: configuração/ativação, `function_call_output`, reamostragem,
`AudioPipe` (pacing + cancel), protocolo de sessão (turno simples, tools
`raciocinar`/`executar`, erro de servidor) e o contrato de `converse_turn`.
