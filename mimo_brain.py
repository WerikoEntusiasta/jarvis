"""
mimo_brain.py — Módulo de Inteligência Artificial Xiaomi MiMo para o J.A.R.V.I.S.
Integração nativa com Token Plan (Singapore Cluster):
1. Raciocínio tático com mimo-v2.6-flash e mimo-v2.6-pro (1M tokens).
2. Fala tática com vozes secundárias (Mia = F.R.I.D.A.Y., Dean = Tática/Emergência) e fallback para ElevenLabs.
3. Transcrição de áudio Speech-to-Text em nuvem com mimo-v2.5-asr.
4. Roteamento ultrarrápido de telas para o HUD Stark Mark VII.
"""

import os
import sys
import json
import time
import base64
import requests
import urllib.request
import urllib.error

# Carrega variáveis de ambiente
MIMO_API_BASE = os.environ.get("MIMO_API_BASE", "https://token-plan-sgp.xiaomimimo.com/v1").rstrip("/")
MIMO_API_KEY = os.environ.get("MIMO_API_KEY", "tp-shj7qyndg8imsci7kvfgcbjrus518hemr1pu2p1m0tvtafeb").strip()
MIMO_MODEL = os.environ.get("MIMO_MODEL", "mimo-v2.6-flash").strip()

# Prompt do Sistema que rege o comportamento do J.A.R.V.I.S.
SYSTEM_PROMPT = """Você é o J.A.R.V.I.S. (Just A Rather Very Intelligent System), a inteligência artificial tática e pessoal do Senhor Werik.
Seu tom é cortês, sofisticado, britânico e extremamente eficiente.

Você possui controle direto sobre:
1. O que será FALADO pelo sintetizador de voz.
2. Qual TELA ou ESTÁGIO visual será projetado no monitor principal do Senhor Werik.
3. Qual EXPRESSÃO e MENSAGEM será exibida na tela da Esfera física ESP32.

SUA RESPOSTA DEVE SER ESTRITAMENTE UM JSON VÁLIDO no formato:
{
  "speech": "Frase curta, britânica, elegante e direta. NUNCA use markdown, emojis ou asteriscos no speech.",
  "screen": {
    "action": "set_stage",
    "stage": 1,
    "title": "TÍTULO DA TELA",
    "subtitle": "SUBTÍTULO TÁTICO"
  },
  "esfera": {
    "emotion": "happy",
    "text": "Texto curtíssimo de até 25 caracteres para a tela de 240px da esfera"
  }
}

Regras para escolha do "stage":
- stage 1: Modo Padrão / Standby / Holograma Central dos Anéis Pulsantes (clima geral, saudações, conversa casual, ordem de voltar ao início).
- stage 2: Finanças Executivas / Contas Banco Inter / Cartão MEI / Balanços / Faturas.
- stage 3: Radar de Notícias / Clipping Regional de Catanduva / Notícias de Tecnologia e Mundo.
- stage 4: Telemetria de Hardware / GPU GTX / Uso de CPU e RAM / Temperatura do Computador.
- stage 5: Radar Aéreo 3D da Terra / Globo Orbital COBE / Rastreamento de Voos.

Se o usuário pedir para abrir algo no computador (ex: abrir Spotify, Chrome, volume, print), confirme a ação em "speech" e mantenha a tela no estágio atual ou apropriado.
Seja sempre leal, conciso e chame o usuário de "Senhor Werik" ou "Senhor".
"""

def call_mimo_jarvis(message: str, telemetry_context: str = None, timeout: float = 12.0) -> dict:
    """
    Chama a API do Xiaomi MiMo Token Plan via protocolo OpenAI /v1/chat/completions.
    Retorna um dicionário padronizado com speech, screen e esfera.
    """
    if not MIMO_API_KEY:
        return _fallback_response(message, "Chave da API MiMo não configurada.")

    url = f"{MIMO_API_BASE}/chat/completions"
    headers = {
        "api-key": MIMO_API_KEY,
        "Authorization": f"Bearer {MIMO_API_KEY}",
        "Content-Type": "application/json",
        "User-Agent": "JARVIS-Core/2.0 (Xiaomi-MiMo)"
    }

    full_system = SYSTEM_PROMPT
    if telemetry_context:
        full_system += f"\n\n[TELEMETRIA AO VIVO DOS SISTEMAS DO SENHOR WERIK]\n{telemetry_context}"

    if any(w in message.lower() for w in ["notícia", "noticia", "novidade", "manchete", "jornal", "acontecendo"]):
        try:
            from news_engine import get_news_summary_for_ai
            news_summary = get_news_summary_for_ai(limit=3)
            if news_summary:
                full_system += f"\n\n[MANCHETES REAIS DE AGORA (NEWS ENGINES)]\n{news_summary}\nSua fala deve citar brevemente 1 ou 2 dessas manchetes reais de forma dinâmica e elegante."
        except Exception:
            pass

    payload = {
        "model": MIMO_MODEL,
        "messages": [
            {"role": "system", "content": full_system},
            {"role": "user", "content": message}
        ],
        "temperature": 0.2,
        "max_tokens": 400
    }

    t0 = time.time()
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as response:
            res_body = response.read().decode("utf-8")
            data = json.loads(res_body)
            raw_text = data["choices"][0]["message"]["content"].strip()
            elapsed = time.time() - t0

            # Limpa wrappers markdown json
            clean_json = raw_text
            if "```" in clean_json:
                import re
                m = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', clean_json)
                if m:
                    clean_json = m.group(1)

            parsed = json.loads(clean_json)
            return {
                "ok": True,
                "speech": parsed.get("speech", "Às suas ordens, Senhor Werik."),
                "screen": parsed.get("screen", {"action": "set_stage", "stage": 1, "title": "STANDBY", "subtitle": "SISTEMAS OPERACIONAIS"}),
                "esfera": parsed.get("esfera", {"emotion": "happy", "text": "ONLINE"}),
                "model": MIMO_MODEL,
                "latency_s": round(elapsed, 2)
            }
    except Exception as ex:
        print(f"[MiMo Brain] Erro de conexão/parse: {ex}")
        return _fallback_response(message, str(ex))

def generate_mimo_tts(text: str, voice: str = "Mia", output_file: str = None, timeout: float = 14.0) -> bytes:
    """
    Sintetizador de Voz Secundário via MiMo (mimo-v2.5-tts):
    - voice='Mia': Persona F.R.I.D.A.Y. (Feminina, técnica, notificações de segurança e status).
    - voice='Dean': Persona Tática / Emergência (Masculina firme, alertas de segurança e firewall).
    - voice='mimo_default': Fallback geral sem custos caso o ElevenLabs atinja limite.
    """
    if not MIMO_API_KEY:
        return b""

    url = f"{MIMO_API_BASE}/chat/completions"
    headers = {
        "Authorization": f"Bearer {MIMO_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "mimo-v2.5-tts",
        "messages": [{"role": "assistant", "content": text}],
        "modalities": ["audio"],
        "audio": {"voice": voice, "format": "mp3"}
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        if resp.status_code == 200:
            choice = resp.json().get("choices", [{}])[0]
            audio_obj = choice.get("message", {}).get("audio", {})
            data_b64 = audio_obj.get("data", "")
            if data_b64:
                raw_bytes = base64.b64decode(data_b64)
                if output_file and len(raw_bytes) > 500:
                    with open(output_file, "wb") as f:
                        f.write(raw_bytes)
                return raw_bytes
    except Exception as e:
        print(f"[MiMo TTS] Erro ao sintetizar áudio ({voice}): {e}")
    return b""

def transcribe_mimo_asr(audio_bytes: bytes, timeout: float = 10.0) -> str:
    """
    Transcrição de Voz Redundante via MiMo (mimo-v2.5-asr):
    Segundo canal de Speech-to-Text em nuvem para apoiar o Groq Whisper.
    """
    if not MIMO_API_KEY or not audio_bytes:
        return ""

    try:
        # Garante cabeçalho WAV padrão
        if not audio_bytes.startswith(b"RIFF"):
            import io, wave
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(audio_bytes)
            audio_bytes = buf.getvalue()

        b64_data = base64.b64encode(audio_bytes).decode("utf-8")
        url = f"{MIMO_API_BASE}/chat/completions"
        headers = {
            "Authorization": f"Bearer {MIMO_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "mimo-v2.5-asr",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": {
                                "data": b64_data,
                                "format": "wav"
                            }
                        }
                    ]
                }
            ]
        }
        t0 = time.time()
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            choice = data.get("choices", [{}])[0]
            txt = (choice.get("message", {}).get("content") or "").strip()
            # Filtra símbolos de silêncio ou pontuação espúria
            # Filtra símbolos de silêncio, caracteres asiáticos ou pontuação espúria em áudio vazio
            if txt and len(txt) > 1:
                import re
                if re.search(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]", txt):
                    return ""
                if txt.startswith(("。", "...", "silence")):
                    return ""
                try:
                    safe_txt = txt.encode("ascii", "replace").decode("ascii")
                    print(f"[MiMo ASR] Transcrito com sucesso em {time.time()-t0:.2f}s: {safe_txt!r}")
                except Exception:
                    pass
                return txt
    except Exception as e:
        try:
            safe_err = str(e).encode("ascii", "replace").decode("ascii")
            print(f"[MiMo ASR] Falha na transcricao: {safe_err}")
        except Exception:
            pass
    return ""

def _fallback_response(user_msg: str, reason: str = "") -> dict:
    """Fallback seguro caso a API sofra timeout ou instabilidade de rede."""
    msg_low = user_msg.lower()
    stage = 1
    title = "SISTEMAS ONLINE"
    sub = "MODO CONTINGÊNCIA"

    if any(w in msg_low for w in ["financeiro", "gasto", "saldo", "banco", "inter", "mei", "conta"]):
        stage = 2
        title = "PAINEL FINANCEIRO"
        sub = "DADOS BANCÁRIOS"
        speech = "Projetando suas finanças e contas na tela principal, Senhor."
    elif any(w in msg_low for w in ["notícia", "noticia", "jornal", "acontecendo", "radar"]):
        stage = 3
        title = "RADAR DE NOTÍCIAS"
        sub = "CATANDUVA & MUNDO"
        speech = "Abrindo o clipping de notícias e informações no monitor."
    elif any(w in msg_low for w in ["hardware", "gpu", "cpu", "temperatura", "memória", "ram"]):
        stage = 4
        title = "TELEMETRIA DE RIG"
        sub = "HARDWARE LOCAL"
        speech = "Exibindo telemetria completa da máquina física, Senhor."
    elif any(w in msg_low for w in ["globo", "terra", "voo", "aéreo", "aereo", "radar 3d"]):
        stage = 5
        title = "RADAR ORBITAL 3D"
        sub = "RASTREAMENTO GLOBAL"
        speech = "Inicializando a projeção orbital tridimensional."
    else:
        speech = "Sistemas sincronizados e operando. Como posso auxiliá-lo, Senhor Werik?"

    return {
        "ok": False,
        "speech": speech,
        "screen": {"action": "set_stage", "stage": stage, "title": title, "subtitle": sub},
        "esfera": {"emotion": "happy", "text": "J.A.R.V.I.S."},
        "fallback_reason": reason
    }
