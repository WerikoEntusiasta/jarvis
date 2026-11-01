"""
J.A.R.V.I.S. Multi-Agent Squad Engine
Gerencia, roteia e orquestra os 10 Agentes Especialistas da Amplifica Marketing e Infraestrutura.
Conecta com a memória unificada (PostgreSQL + Redis), carrega SOUL.md e credenciais .env.
Motor Principal: Xiaomi MiMo API com Roteamento Dinâmico (Flash para tarefas simples, Pro para complexas).
Fallback Secundário: 9Router / Gemini 3.8.
"""

import os
import re
import json
import logging
import urllib.request
import urllib.parse
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger("JARVIS-SQUAD")

BASE_DIR = Path(__file__).resolve().parent
AGENTS_DIR = Path(os.environ.get("JARVIS_AGENTS_DIR", "/DATA/AppData/jarvis-hud/agents"))
if not AGENTS_DIR.exists():
    AGENTS_DIR = BASE_DIR / "agents"

ENV_FILE = AGENTS_DIR / ".env"

if ENV_FILE.exists():
    with open(ENV_FILE, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

# Motor Principal: Xiaomi MiMo API
MIMO_API_BASE = os.environ.get("MIMO_API_BASE", "https://token-plan-sgp.xiaomimimo.com/v1")
MIMO_API_KEY = os.environ.get("MIMO_API_KEY", "tp-shj7qyndg8imsci7kvfgcbjrus518hemr1pu2p1m0tvtafeb")
MIMO_MODEL_FLASH = "mimo-v2.6-flash"
MIMO_MODEL_PRO = "mimo-v2.6-pro"

# Motor Secundário (Fallback de Emergência)
ROUTER_URL = os.environ.get("ROUTER_URL", "http://172.17.0.1:20128/v1")
ROUTER_PUBLIC_URL = os.environ.get("ROUTER_PUBLIC_URL", "http://45.167.187.80:20128/v1")
ROUTER_API_KEY = os.environ.get("ROUTER_API_KEY", "sk-13905ec81e7deff0-zzde14-273bfa02")

PG_HOST = os.environ.get("PG_HOST", "172.17.0.11")
PG_PORT = int(os.environ.get("PG_PORT", 5432))
PG_USER = os.environ.get("PG_USER", "casaos")
PG_PASSWORD = os.environ.get("PG_PASSWORD", "Casaos_Db_Sec2026!")
PG_DATABASE = os.environ.get("PG_DATABASE", "jarvis_memory")


def select_mimo_model(message: str, history: Optional[List[Dict[str, str]]] = None, agent_id: str = "") -> Dict[str, Any]:
    """
    Roteador Inteligente de Complexidade:
    - Retorna 'mimo-v2.6-flash' para tarefas rápidas, saudações, comandos diretos ou consultas curtas.
    - Retorna 'mimo-v2.6-pro' para tarefas complexas (análise estratégica, métricas, código, copy completa, auditorias, fluxos n8n).
    """
    msg_clean = message.strip()
    msg_lower = msg_clean.lower()

    # Indicadores explícitos de alta complexidade
    complex_triggers = [
        # Análise e Tráfego / Marketing Estratégico
        "analise", "análise", "estrategia", "estratégia", "diagnostico", "diagnóstico",
        "plano", "planejamento", "escala", "escalar", "otimizar", "otimizacao", "otimização",
        "cpa", "roas", "roi", "conversao", "conversão", "funil", "metricas", "métricas",
        "budget", "orçamento", "orcamento", "benchmark", "kpi", "segmentação", "segmentacao",
        # Copywriting e Conteúdo Completo
        "escreva copy", "redija", "roteiro completo", "storytelling", "carrossel",
        "vsl", "carta de vendas", "newsletter", "artigo", "headline", "persuasivo",
        # Automação, Código e Cibersegurança
        "n8n", "workflow", "webhook", "codigo", "código", "script", "json", "endpoint",
        "api", "database", "postgres", "redis", "docker", "firewall", "sentinel",
        "vulnerabilidade", "intrusão", "intrusao", "ciberdefesa", "segurança", "seguranca",
        # Criação e Arquitetura de Agentes
        "criar agente", "novo agente", "soul.md", "identity.md", "persona", "especificacao", "especificação",
        # Raciocínio Profundo / Comparativos
        "por que", "explique detalhadamente", "passo a passo", "comparativo", "arquitetura"
    ]

    is_complex_keyword = any(trig in msg_lower for trig in complex_triggers)
    is_long_text = len(msg_clean) > 200
    has_code_or_structure = ("```" in msg_clean or "\n1." in msg_clean or "\n-" in msg_clean or msg_clean.count("?") > 1)
    is_deep_history = (len(history) >= 6) if history else False

    if is_complex_keyword or is_long_text or has_code_or_structure or is_deep_history:
        return {
            "model": MIMO_MODEL_PRO,
            "tier": "pro",
            "max_tokens": 2048,
            "temperature": 0.4,
            "reason": "Alta complexidade detectada (análise estratégica, métricas, código ou estrutura aprofundada)."
        }

    return {
        "model": MIMO_MODEL_FLASH,
        "tier": "flash",
        "max_tokens": 1200,
        "temperature": 0.3,
        "reason": "Interação rápida, conversacional ou comando direto."
    }


def list_squad_agents() -> List[Dict[str, Any]]:
    """Retorna lista de todos os agentes configurados no Squad com status e metadados."""
    agents = []
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=PG_HOST, port=PG_PORT, user=PG_USER, password=PG_PASSWORD, dbname=PG_DATABASE, connect_timeout=2
        )
        cur = conn.cursor()
        cur.execute("SELECT id, name, emoji, role, model, status, tools, stats FROM jarvis_agents ORDER BY id;")
        for r in cur.fetchall():
            agents.append({
                "id": r[0],
                "name": r[1],
                "emoji": r[2],
                "role": r[3],
                "model": "Xiaomi MiMo (Flash / Pro Dinâmico)",
                "status": r[5],
                "tools": r[6] if isinstance(r[6], list) else json.loads(r[6] or "[]"),
                "stats": r[7] if isinstance(r[7], dict) else json.loads(r[7] or "{}")
            })
        cur.close()
        conn.close()
    except Exception as e:
        logger.warning("[SQUAD] Fallback sem DB direto: %s", e)

    if not agents and AGENTS_DIR.exists():
        for adir in AGENTS_DIR.iterdir():
            if adir.is_dir() and not adir.name.startswith("."):
                name = adir.name.replace("-", " ").title()
                emoji = "🤖"
                soul_path = adir / "SOUL.md"
                desc = "Agente Especialista do ecossistema J.A.R.V.I.S."
                if soul_path.exists():
                    with open(soul_path, "r", encoding="utf-8", errors="replace") as f:
                        lines = [l.strip() for l in f.readlines() if l.strip() and not l.startswith("#")]
                        if lines:
                            desc = lines[0][:150]
                agents.append({
                    "id": adir.name,
                    "name": name,
                    "emoji": emoji,
                    "role": desc,
                    "model": "Xiaomi MiMo (Flash / Pro Dinâmico)",
                    "status": "online",
                    "tools": ["general"],
                    "stats": {"tasks_completed": 100, "rating": "100%"}
                })
    return agents


def get_agent_profile(agent_id: str) -> Optional[Dict[str, Any]]:
    """Carrega perfil completo, SOUL.md e IDENTITY.md do agente."""
    target_dir = AGENTS_DIR / agent_id
    soul_content = ""
    identity_content = ""
    user_rules = ""

    if target_dir.exists():
        for fname in ["SOUL.md", "soul.md"]:
            p = target_dir / fname
            if p.exists():
                with open(p, "r", encoding="utf-8", errors="replace") as f:
                    soul_content = f.read()
                break

        for fname in ["IDENTITY.md", "identity.md"]:
            p = target_dir / fname
            if p.exists():
                with open(p, "r", encoding="utf-8", errors="replace") as f:
                    identity_content = f.read()
                break

        for fname in ["USER.md", "user.md"]:
            p = target_dir / fname
            if p.exists():
                with open(p, "r", encoding="utf-8", errors="replace") as f:
                    user_rules = f.read()
                break

    agents = list_squad_agents()
    meta = next((a for a in agents if a["id"] == agent_id), {
        "id": agent_id,
        "name": agent_id.replace("-", " ").title(),
        "emoji": "🤖",
        "role": "Especialista J.A.R.V.I.S.",
        "model": "Xiaomi MiMo (Flash / Pro Dinâmico)",
        "status": "online",
        "tools": [],
        "stats": {}
    })

    return {
        **meta,
        "soul": soul_content,
        "identity": identity_content,
        "user_rules": user_rules,
        "workspace": str(target_dir)
    }


def _parse_sse_response(raw_text: str) -> str:
    """Extrai conteúdo de streaming SSE (data: {...}) retornado pelo 9Router caso fallback seja ativado."""
    chunks = []
    for line in raw_text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            data_str = line[5:].strip()
            if data_str == "[DONE]":
                break
            try:
                chunk_obj = json.loads(data_str)
                choices = chunk_obj.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        chunks.append(content)
            except Exception:
                pass
    return "".join(chunks)


def chat_with_agent(agent_id: str, message: str, history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    """
    Processa uma mensagem enviada a um agente específico do Squad.
    Roteia primariamente para a API Xiaomi MiMo (Flash para simples, Pro para complexo).
    Fallback resiliente para 9Router / Gemini caso o MiMo oscile.
    """
    profile = get_agent_profile(agent_id)
    if not profile:
        return {"success": False, "error": f"Agente '{agent_id}' não encontrado no Squad."}

    # Injeção de Contexto em Tempo Real (Modo 100% Somente-Leitura)
    realtime_context = ""
    lower_msg = message.lower()
    try:
        import jarvis_tools
        if agent_id in ["adpilot", "jarvis"] and any(k in lower_msg for k in ["tráfego", "trafego", "ads", "meta", "cpa", "roas", "gasto", "campanha", "clique"]):
            metrics = jarvis_tools.get_traffic_metrics("last_7d")
            realtime_context += f"\n\n--- DADOS REAIS DE TRÁFEGO PAGO (SOMENTE LEITURA - META ADS) ---\n{json.dumps(metrics, ensure_ascii=False, indent=2)}\n"
        if agent_id in ["lucia", "jarvis"] and any(k in lower_msg for k in ["agenda", "reunião", "reuniao", "compromisso", "evento", "hoje", "amanhã", "amanha"]):
            events = jarvis_tools.get_agenda_events(5)
            realtime_context += f"\n\n--- AGENDA E COMPROMISSOS ATIVOS (LÚCIA HUB) ---\n{json.dumps(events, ensure_ascii=False, indent=2)}\n"
        if agent_id in ["sentinel", "jarvis"] and any(k in lower_msg for k in ["servidor", "zimaos", "disco", "ram", "saúde", "saude", "memória", "memoria", "status"]):
            health = jarvis_tools.get_system_health()
            realtime_context += f"\n\n--- SAÚDE DO SERVIDOR ZIMAOS (SENTINEL) ---\n{json.dumps(health, ensure_ascii=False, indent=2)}\n"
    except Exception as ex_ctx:
        logger.warning("[SQUAD] Falha injetando contexto em tempo real: %s", ex_ctx)

    # 1. Monta o System Prompt preservando SOUL.md e IDENTITY.md
    system_prompt = f"""Você é {profile['name']} ({profile['emoji']}), especialista de elite do J.A.R.V.I.S. Squad e da Amplifica Marketing.
Seu líder e comandante é o Senhor Werik.

--- DIRETIVAS DO SEU SOUL.MD ---
{profile.get('soul') or profile.get('role')}

--- SUA IDENTIDADE ---
{profile.get('identity') or profile.get('name')}

--- REGRAS DE CONVIVÊNCIA COM O USUÁRIO ---
- Dirija-se sempre ao usuário com máximo respeito e prontidão como "Senhor Werik".
- Seja altamente resolutivo, técnico, direto, ágil e leal.
- Responda em Português do Brasil com qualidade impecável.
- OPERAÇÃO SOMENTE LEITURA: Você relata dados, analisa e informa. Você NUNCA altera campanhas nem atende clientes no WhatsApp.
{realtime_context}
"""

    messages = [{"role": "system", "content": system_prompt}]
    if history:
        for h in history[-8:]:
            messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})

    messages.append({"role": "user", "content": message})

    # 2. Roteamento Inteligente de Complexidade MiMo
    routing = select_mimo_model(message, history, agent_id)
    selected_model = routing["model"]
    model_tier = routing["tier"]
    max_tokens = routing["max_tokens"]
    temperature = routing["temperature"]

    logger.info("[SQUAD-ROUTER] Agente: %s | Modelo: %s (%s) | Motivo: %s",
                agent_id, selected_model, model_tier, routing["reason"])

    reply_text = ""
    provider_used = f"Xiaomi MiMo ({selected_model})"
    last_err = None

    # Tenta 1 (PRINCIPAL): Xiaomi MiMo API Oficial
    try:
        mimo_payload = {
            "model": selected_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        req = urllib.request.Request(
            f"{MIMO_API_BASE}/chat/completions",
            data=json.dumps(mimo_payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {MIMO_API_KEY}"
            }
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            choice = data.get("choices", [{}])[0]
            msg_obj = choice.get("message", {})
            reply_text = msg_obj.get("content", "").strip()
            
            # Se vier sem content mas com reasoning_content, utiliza como resposta
            if not reply_text and "reasoning_content" in msg_obj:
                reply_text = msg_obj.get("reasoning_content", "").strip()
    except Exception as e_mimo:
        last_err = f"MiMo ({selected_model}) Error: {e_mimo}"
        logger.warning("[SQUAD-ROUTER] Falha na MiMo API: %s. Acionando Fallback 9Router...", e_mimo)

    # Tenta 2 (FALLBACK DE EMERGÊNCIA): 9Router
    if not reply_text:
        req_urls = [
            f"{ROUTER_URL}/chat/completions",
            f"{ROUTER_PUBLIC_URL}/chat/completions"
        ]
        fallback_payload = {
            "model": "ag/gemini-3.8-flash",
            "messages": messages,
            "temperature": 0.4,
            "max_tokens": 1500
        }
        for u in req_urls:
            try:
                req = urllib.request.Request(
                    u,
                    data=json.dumps(fallback_payload).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {ROUTER_API_KEY}"
                    }
                )
                with urllib.request.urlopen(req, timeout=12) as resp:
                    raw_resp = resp.read().decode("utf-8", errors="replace")
                    if "data: {" in raw_resp:
                        reply_text = _parse_sse_response(raw_resp)
                    else:
                        data = json.loads(raw_resp)
                        reply_text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    if reply_text:
                        provider_used = "9Router / Gemini 3.8 Flash (Fallback)"
                        break
            except Exception as e_fb:
                last_err = f"{last_err} | 9Router: {e_fb}"
                continue

    if not reply_text:
        return {
            "success": False,
            "error": f"Falha na resposta do agente {profile['name']}: {last_err}",
            "reply": f"Senhor Werik, ocorreu uma oscilação na rota de IA do {profile['name']}."
        }

    if "<tool_call>" in reply_text:
        clean = re.sub(r'<tool_call>.*?</tool_call>', '', reply_text, flags=re.DOTALL).strip()
        if clean:
            reply_text = clean
        else:
            reply_text = f"Olá Senhor Werik! Sou o {profile['name']}. Estou com as diretivas operacionais e ferramentas ativas. Como posso auxiliá-lo estrategicamente agora?"

    return {
        "success": True,
        "agent": {
            "id": profile["id"],
            "name": profile["name"],
            "emoji": profile["emoji"],
            "model": selected_model
        },
        "routing": {
            "tier": model_tier,
            "model": selected_model,
            "provider": provider_used,
            "reason": routing["reason"]
        },
        "reply": reply_text
    }


def dispatch_smart_routing(user_text: str) -> str:
    """Classifica automaticamente o texto e indica qual agente deve responder."""
    t = user_text.lower()

    if any(k in t for k in ["anúncio", "anuncio", "tráfego", "trafego", "cpa", "roas", "meta ads", "campanha", "adclient"]):
        return "adpilot"
    if any(k in t for k in ["copy", "roteiro", "gancho", "hook", "carrossel", "texto persuasivo", "cta"]):
        return "copywriter"
    if any(k in t for k in ["design", "layout", "visual", "paleta", "cor", "criativo", "arte"]):
        return "designer"
    if any(k in t for k in ["vídeo", "video", "hyperframes", "mp4", "motion", "corte"]):
        return "video-editor"
    if any(k in t for k in ["n8n", "workflow", "webhook", "fluxo"]):
        return "n8n-pilot"
    if any(k in t for k in ["contrato", "agenda", "reunião", "reuniao", "tarefa", "autentique", "calendário"]):
        return "lucia"
    if any(k in t for k in ["segurança", "seguranca", "sentinel", "intrusão", "minerador", "porta", "firewall", "zimaos"]):
        return "sentinel"
    if any(k in t for k in ["resumo", "obsidian", "segundo cérebro", "segundo cerebro", "artigo", "conhecimento"]):
        return "curator"
    if any(k in t for k in ["criar agente", "novo agente", "artesão", "artesao", "especificação"]):
        return "artesao"

    return "jarvis"
