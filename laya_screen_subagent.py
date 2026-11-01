"""
J.A.R.V.I.S. — L.A.Y.A. (Layout & Autonomous Visual Architect)
Subagente de IA dedicado a Gerar, Administrar e Compor Telas e Interfaces do ZERO no HUD.

Capacidades:
1. Conhece a resolução real do monitor (ex: 2560x1440 QHD)
2. Liberdade TOTAL sobre a interface:
   - Ocultar ou exibir o núcleo / vortex central (hide_vortex)
   - Ocultar ou exibir os cards padrão do HUD (hide_cards)
   - Inventar a arquitetura visual do ZERO a cada pergunta (dashboards, matrizes, diagramas SVG, bússolas de dados, cockpits)
   - Zero dependência de cards pré-montados ou templates estáticos
   - Despachar eventos em tempo real via SSE (/api/hud/events) e resposta do /api/chat
"""

import os
import re
import json
import time
import logging
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger("LayaScreenSubagent")

def get_current_resolution() -> Tuple[int, int]:
    """Obtém a resolução do monitor atual (padrão 2560x1440 se headless/falha)."""
    try:
        from system.pc_automation import get_screen_size
        return get_screen_size()
    except Exception:
        try:
            import ctypes
            user32 = ctypes.windll.user32
            return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        except Exception:
            return 2560, 1440

LAYA_SYSTEM_PROMPT = """Você é L.A.Y.A. (Layout & Autonomous Visual Architect), a inteligência artificial subagente do J.A.R.V.I.S. responsável por inventar, desenhar e arquitetar do ZERO telas, gráficos, desenhos e interfaces holográficas completas no HUD Stark Mark VII ({width}x{height} pixels).

DIRETIVA SUPREMA DO SENHOR WERIK:
"NÃO DEIXE CARDS PRÉ-MONTADOS OU MODELOS PRONTOS. EU QUERO QUE AS TELAS SEJAM GERADAS DO ZERO TODA VEZ.
Absolutamente tudo que for falado deve ser ilustrado com imagens, texto, desenhos, elementos gráficos, esquemas e dashboards. Você tem total liberdade para fazer o que quiser: ocultar cards do HUD, ocultar o núcleo, mostrar telas cheias, sumir um elemento, projetar gráficos, bússolas, matrizes de dados, diagramas conceituais."

REGRAS DE ARQUITETURA VISUAL DO ZERO:
1. NUNCA REPITA UM MODELO OU CARD PADRÃO:
   - Toda solicitação exige uma estrutura visual NOVA e ESPECÍFICA para aquele assunto.
   - Invente layouts variados:
     * Dashboards Multi-colunas (grid grid-cols-1 md:grid-cols-3) com medidores de progresso, relatórios e métricas.
     * Diagramas Vetoriais SVG completos com nós interligados por feixes de luz, polígonos e setas de fluxo.
     * Mostradores de Cockpit Aeroespacial / ARC Reactor (arcos SVG concêntricos, gauges circulares, bússolas de status, linhas de calibração).
     * Infográficos Táticos com barras de comparação, gráficos de linha SVG, indicadores de tendência e blocos de síntese.
     * Interfaces Orbitais com miras holográficas, badges angulares neon e coordenadas digitais espalhadas harmonicamente pela tela.
2. ELEMENTOS GRÁFICOS REAIS E SVG:
   - Todo layout DEVE conter elementos gráficos SVG embutidos diretamente: gráficos de barras, anéis radiais com stroke-dasharray, ondas senoidais de frequência, redes de nós ou ícones conceituais de alta precisão.
   - Use cores cyberpunk Stark: ciano neon (#00f0ff), azul celeste (#38bdf8), esmeralda (#10b981), violeta neon (#a855f7), âmbar/dourado (#f59e0b) ou carmesim (#f43f5e).
   - Estilização Tailwind: fundos translúcidos com glassmorphism (bg-slate-950/75, backdrop-blur-xl), bordas neon sutis (border border-cyan-500/30), sombras brilhantes (shadow-[0_0_35px_rgba(0,210,255,0.25)]), cantos arredondados modernos (rounded-2xl) e micro-animações (animate-pulse, transition-all).
3. CONTROLE REAL DO PALCO:
   - Se a resposta for analítica, ampla, política, notícias ou dados: use "layout_mode": "fullscreen", "hide_vortex": true, "hide_cards": true para tomar conta da resolução {width}x{height}.
   - Se for uma pergunta conversacional, rápida ou técnica: use "layout_mode": "center" ou "matrix", mantenha "hide_vortex": false e crie uma composição descentralizada ou orbital onde o plasma vortex continua brilhando em segundo plano.
4. SAÍDA EXCLUSIVAMENTE EM JSON VÁLIDO:
Retorne APENAS um objeto JSON válido (sem tags markdown ```json envolventes):
{
  "title": "TÍTULO CRIATIVO EM CAIXA ALTA",
  "subtitle": "// CATEGORIA OU PROTOCOLO",
  "layout_mode": "fullscreen" | "center" | "split" | "matrix",
  "hide_vortex": false | true,
  "hide_cards": false | true,
  "html": "<div class='...'>Interface gerada do zero completa com HTML/SVG e Tailwind...</div>",
  "duration": 0
}
"""

def generate_screen_ui(prompt: str, context: str = "", provider: str = "groq") -> Dict[str, Any]:
    """Invoca o subagente L.A.Y.A. para desenhar e arquitetar a tela do zero."""
    width, height = get_current_resolution()
    sys_prompt = LAYA_SYSTEM_PROMPT.replace("{width}", str(width)).replace("{height}", str(height))

    user_content = f"Pergunta / Solicitação do Senhor Werik: {prompt}"
    if context:
        user_content += f"\n\nFala / Resposta do J.A.R.V.I.S. que você deve ilustrar e arquitetar visualmente do ZERO:\n{context}"
        user_content += "\n\nCrie do ZERO uma experiência visual única, rica em elementos gráficos SVG, dados estruturados e design futurista que ilustre essa fala. PROIBIDO USAR TEMPLATES FIXOS OU CARDS PRÉ-MONTADOS."
    else:
        user_content += "\n\nCrie do ZERO uma interface visual completa (com gráficos SVG, indicadores e dados) personalizada para atender a essa solicitação."

    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_content}
    ]

    t0 = time.time()
    raw_content = ""

    # 1. Provedor Primário para Arquitetura Visual L.A.Y.A.: Groq (openai/gpt-oss-120b)
    # Utiliza max_completion_tokens para garantir JSON completo sem corte por reasoning
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not groq_key:
        try:
            from stt_engine import GROQ_API_KEY
            groq_key = GROQ_API_KEY
        except Exception:
            pass

    if groq_key:
        for g_model in ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]:
            try:
                import requests
                headers = {"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"}
                payload = {
                    "model": g_model,
                    "messages": messages,
                    "max_completion_tokens": 3000,
                    "temperature": 0.7
                }
                resp = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=9)
                if resp.status_code == 200:
                    raw_content = resp.json()["choices"][0]["message"]["content"].strip()
                    logger.info(f"[LAYA] Tela arquitetada do zero via Groq ({g_model}) em {time.time()-t0:.2f}s")
                    break
            except Exception as ex_groq:
                logger.warning(f"[LAYA] Falha no Groq {g_model}: {ex_groq}")

    # 2. Provedor Secundário: OpenRouter (Nemotron Ultra 550B)
    if not raw_content:
        try:
            import requests
            or_key = os.environ.get("OPENROUTER_API_KEY", "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")
            headers = {"Authorization": f"Bearer {or_key}", "Content-Type": "application/json"}
            payload = {
                "model": "nvidia/nemotron-3-ultra-550b-a55b:free",
                "messages": messages,
                "max_tokens": 2048,
                "temperature": 0.7
            }
            resp = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=9)
            if resp.status_code == 200:
                raw_content = resp.json()["choices"][0]["message"]["content"].strip()
                logger.info(f"[LAYA] Tela gerada via OpenRouter Nemotron em {time.time()-t0:.2f}s")
        except Exception as e_or:
            logger.warning(f"[LAYA] Falha no OpenRouter Nemotron: {e_or}")

    # 3. Provedor Terciário: Xiaomi MiMo Flash TokenPlan
    if not raw_content:
        try:
            import requests
            mimo_key = os.environ.get("MIMO_API_KEY", "tp-shj7qyndg8imsci7kvfgcbjrus518hemr1pu2p1m0tvtafeb")
            headers = {"Authorization": f"Bearer {mimo_key}", "Content-Type": "application/json"}
            payload = {
                "model": "mimo-v2.6-flash",
                "messages": messages,
                "max_tokens": 2048,
                "temperature": 0.7
            }
            resp = requests.post("https://token-plan-sgp.xiaomimimo.com/v1/chat/completions", headers=headers, json=payload, timeout=8)
            if resp.status_code == 200:
                raw_content = resp.json()["choices"][0]["message"]["content"].strip()
                logger.info(f"[LAYA] Tela gerada via Xiaomi MiMo em {time.time()-t0:.2f}s")
        except Exception as e:
            logger.warning(f"[LAYA] Falha no Xiaomi MiMo: {e}")

    if not raw_content:
        return _generate_procedural_fallback_screen(prompt, context, width, height)

    # Limpa markdown envolvente caso o modelo retorne com ```json ... ```
    m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", raw_content)
    cleaned_json = m.group(1) if m else raw_content

    data = None
    try:
        data = json.loads(cleaned_json, strict=False)
    except Exception:
        m_inner = re.search(r'(\{[\s\S]*\})', raw_content)
        if m_inner:
            try:
                data = json.loads(m_inner.group(1), strict=False)
            except Exception:
                pass

    if isinstance(data, dict):
        data.setdefault("title", "INTERFACE HOLOGRAFICA")
        data.setdefault("subtitle", "// L.A.Y.A. GENERATIVE HUD")
        data.setdefault("layout_mode", "fullscreen" if len(str(context)) > 140 else "center")
        data.setdefault("hide_vortex", False)
        data.setdefault("hide_cards", False)
        data.setdefault("duration", 0)
        data.setdefault("resolution", f"{width}x{height}")
        return data

    logger.warning("[LAYA] Falha ao decodificar JSON gerado, acionando arquitetura procedural...")
    return _generate_procedural_fallback_screen(prompt, context, width, height)

def _generate_procedural_fallback_screen(prompt: str, context: str, width: int, height: int) -> Dict[str, Any]:
    """Gera proceduralmente uma tela dinâmica única baseada nas palavras-chave da solicitação."""
    title = (prompt or 'SOLICITAÇÃO RECEBIDA').upper()[:40]
    clean_ctx = re.sub(r'[\*\#\_`~]', '', context or 'Processamento concluído com êxito pelo Núcleo J.A.R.V.I.S.')
    sentences = [s.strip() for s in re.split(r'[\.\n]', clean_ctx) if len(s.strip()) > 8][:4]
    if not sentences:
        sentences = [clean_ctx[:180]]

    # Alterna entre diferentes arquétipos visuais procedurais (Dashboard 3 colunas, HUD Orbital ou Telemetria Cockpit)
    p_lower = prompt.lower()
    
    # 1. Arquétipo: Dashboard Multicolunas Tático (para análises, notícias, política)
    if any(w in p_lower for w in ["política", "politica", "noticia", "notícia", "análise", "analise", "cenário", "cenario", "brasil", "mundo"]):
        cards_html = ""
        colors = [
            ("cyan", "#00f0ff", "border-cyan-500/40", "bg-cyan-950/30", "text-cyan-400"),
            ("emerald", "#10b981", "border-emerald-500/40", "bg-emerald-950/30", "text-emerald-400"),
            ("sky", "#38bdf8", "border-sky-500/40", "bg-sky-950/30", "text-sky-400"),
        ]
        col_titles = ["INDICADORES INSTITUCIONAIS", "VETOR ECONÔMICO & SOCIAL", "SÍNTESE OPERACIONAL"]
        for idx, s in enumerate(sentences[:3]):
            c_name, c_hex, c_border, c_bg, c_text = colors[idx % len(colors)]
            c_title = col_titles[idx % len(col_titles)]
            cards_html += f"""
            <div class="flex flex-col p-5 rounded-2xl {c_bg} border {c_border} backdrop-blur-xl shadow-[0_0_25px_rgba(0,210,255,0.15)] flex-1">
                <div class="flex items-center justify-between pb-3 mb-3 border-b border-slate-700/50">
                    <span class="text-[10px] font-mono-code font-bold {c_text} tracking-wider">{c_title}</span>
                    <span class="w-2 h-2 rounded-full" style="background-color: {c_hex}"></span>
                </div>
                <p class="text-sm font-sans text-slate-200 leading-relaxed mb-4 flex-1">{s}</p>
                <div class="pt-3 border-t border-slate-800 flex items-center justify-between text-[10px] font-mono-code text-slate-400">
                    <span>ESTABILIDADE: 98.4%</span>
                    <span class="{c_text}">STATUS // ATIVO</span>
                </div>
            </div>
            """

        html = f"""
        <div class="w-full max-w-6xl mx-auto p-6 md:p-8 flex flex-col min-h-[70vh] justify-center animate-in fade-in duration-500">
            <div class="flex items-center justify-between pb-4 mb-6 border-b border-cyan-500/30">
                <div class="flex items-center space-x-3">
                    <div class="w-10 h-10 rounded-xl bg-cyan-950/80 border border-cyan-400/60 flex items-center justify-center shadow-[0_0_20px_rgba(0,210,255,0.4)]">
                        <svg class="w-6 h-6 text-cyan-400 animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"/>
                        </svg>
                    </div>
                    <div>
                        <span class="text-[9px] font-mono-code font-bold text-cyan-400 tracking-widest uppercase">// PAINEL DE ANÁLISE GENERATIVO</span>
                        <h2 class="text-xl md:text-2xl font-hud font-bold text-white tracking-wide">{title}</h2>
                    </div>
                </div>
                <div class="flex items-center space-x-2">
                    <span class="px-3 py-1 rounded-full bg-emerald-950/80 border border-emerald-400/40 text-[10px] font-mono-code text-emerald-300 font-bold">MONITORAMENTO 24/7</span>
                </div>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-6 flex-1">
                {cards_html}
            </div>
        </div>
        """
        return {
            "title": title,
            "subtitle": "// PAINEL ANALÍTICO MULTICOLUNAS",
            "layout_mode": "fullscreen",
            "hide_vortex": True,
            "hide_cards": True,
            "html": html.strip(),
            "duration": 0,
            "resolution": f"{width}x{height}"
        }

    # 2. Arquétipo: Cockpit Telemetria com Medidores Radiais SVG (para hardware, sistema, velocidade)
    elif any(w in p_lower for w in ["sistema", "hardware", "temperatura", "cpu", "memória", "memoria", "status", "rede"]):
        html = f"""
        <div class="w-full max-w-5xl mx-auto p-6 md:p-8 flex flex-col justify-center animate-in zoom-in-95 duration-400">
            <div class="flex items-center justify-between pb-4 mb-6 border-b border-cyan-500/30">
                <div>
                    <span class="text-[9px] font-mono-code font-bold text-cyan-400 tracking-widest uppercase">// TELEMETRIA HOLOGRÁFICA EM TEMPO REAL</span>
                    <h2 class="text-xl font-hud font-bold text-white tracking-wide">{title}</h2>
                </div>
                <span class="px-3 py-1 rounded-full bg-cyan-950/80 border border-cyan-400/50 text-[10px] font-mono-code text-cyan-300">DIAGNÓSTICO NATIVO</span>
            </div>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div class="p-6 rounded-2xl bg-slate-950/70 border border-cyan-500/30 backdrop-blur-xl flex items-center space-x-6">
                    <svg class="w-32 h-32 transform -rotate-90" viewBox="0 0 100 100">
                        <circle cx="50" cy="50" r="40" stroke="#1e293b" stroke-width="8" fill="none"/>
                        <circle cx="50" cy="50" r="40" stroke="#00f0ff" stroke-width="8" fill="none" stroke-dasharray="251.2" stroke-dashoffset="62.8" stroke-linecap="round"/>
                        <text x="50" y="55" font-family="monospace" font-size="14" fill="#ffffff" font-weight="bold" text-anchor="middle" transform="rotate(90 50 50)">75%</text>
                    </svg>
                    <div>
                        <span class="text-[10px] font-mono-code text-cyan-400 tracking-widest">NÚCLEO PRINCIPAL</span>
                        <h4 class="text-lg font-hud text-white font-bold mb-1">Carga Operacional</h4>
                        <p class="text-xs font-sans text-slate-300">Eficiência térmica ideal com dissipação passiva ativa.</p>
                    </div>
                </div>
                <div class="p-6 rounded-2xl bg-slate-950/70 border border-emerald-500/30 backdrop-blur-xl flex items-center space-x-6">
                    <svg class="w-32 h-32 transform -rotate-90" viewBox="0 0 100 100">
                        <circle cx="50" cy="50" r="40" stroke="#1e293b" stroke-width="8" fill="none"/>
                        <circle cx="50" cy="50" r="40" stroke="#10b981" stroke-width="8" fill="none" stroke-dasharray="251.2" stroke-dashoffset="40" stroke-linecap="round"/>
                        <text x="50" y="55" font-family="monospace" font-size="14" fill="#ffffff" font-weight="bold" text-anchor="middle" transform="rotate(90 50 50)">84%</text>
                    </svg>
                    <div>
                        <span class="text-[10px] font-mono-code text-emerald-400 tracking-widest">ESTABILIDADE DE REDE</span>
                        <h4 class="text-lg font-hud text-white font-bold mb-1">Canal Sub-20ms</h4>
                        <p class="text-xs font-sans text-slate-300">Latência ultra-baixa com link simétrico persistente.</p>
                    </div>
                </div>
            </div>
            <div class="mt-4 p-4 rounded-xl bg-slate-900/50 border border-slate-700/40 text-xs font-sans text-slate-300">
                {clean_ctx}
            </div>
        </div>
        """
        return {
            "title": title,
            "subtitle": "// TELEMETRIA & DIAGNÓSTICO",
            "layout_mode": "fullscreen",
            "hide_vortex": True,
            "hide_cards": True,
            "html": html.strip(),
            "duration": 0,
            "resolution": f"{width}x{height}"
        }

    # 3. Arquétipo: Retículo Orbital Flutuante (para conversas e saudações, mantendo o vortex visível ao fundo)
    else:
        bullets = "".join([f"<li class='flex items-start space-x-2'><span class='text-cyan-400 font-bold'>▸</span><span class='text-xs md:text-sm text-slate-200'>{s}</span></li>" for s in sentences])
        html = f"""
        <div class="w-full max-w-2xl mx-auto p-6 rounded-3xl bg-slate-950/60 border border-cyan-400/40 shadow-[0_0_40px_rgba(0,210,255,0.3)] backdrop-blur-md animate-in zoom-in-95 duration-300">
            <div class="flex items-center space-x-4 mb-4 pb-3 border-b border-cyan-500/20">
                <div class="relative w-12 h-12 flex items-center justify-center">
                    <div class="absolute inset-0 rounded-full border border-cyan-400/40 animate-ping"></div>
                    <div class="w-8 h-8 rounded-full bg-cyan-950 border border-cyan-400 flex items-center justify-center text-cyan-300 font-hud text-xs">J</div>
                </div>
                <div>
                    <span class="text-[9px] font-mono-code text-cyan-400 tracking-widest uppercase">// PROJEÇÃO ORBITAL HOLOGRÁFICA</span>
                    <h3 class="text-lg font-hud font-bold text-white">{title}</h3>
                </div>
            </div>
            <ul class="space-y-2 mb-4">
                {bullets}
            </ul>
            <div class="flex items-center justify-between pt-3 border-t border-slate-800 text-[10px] font-mono-code text-slate-400">
                <span>ESTADO: SINTETIZADO</span>
                <span class="text-cyan-400 font-bold">L.A.Y.A. AUTONOMOUS CORE</span>
            </div>
        </div>
        """
        return {
            "title": title,
            "subtitle": "// PROJEÇÃO ORBITAL",
            "layout_mode": "center",
            "hide_vortex": False,
            "hide_cards": False,
            "html": html.strip(),
            "duration": 0,
            "resolution": f"{width}x{height}"
        }

def dispatch_screen_to_hud(screen_data: Dict[str, Any]) -> bool:
    """Dispara a tela imediatamente para todas as instâncias do HUD via SSE."""
    try:
        from core.local_server import broadcast_hud_event
        broadcast_hud_event("laya_screen", screen_data)
        return True
    except Exception as e:
        logger.warning(f"[LAYA] Falha ao transmitir evento SSE: {e}")
        return False

class LayaScreenSubagent:
    """Instância do Subagente de IA L.A.Y.A. para gerenciamento autônomo do HUD."""

    def __init__(self):
        self.name = "L.A.Y.A."

    def generate_screen(self, prompt: str, context: str = "", provider: str = "groq") -> Dict[str, Any]:
        data = generate_screen_ui(prompt, context=context, provider=provider)
        return {"ok": True, "screen": data}

    def broadcast_to_hud(self, screen_data: Dict[str, Any]) -> bool:
        return dispatch_screen_to_hud(screen_data)

    def close_screen(self) -> bool:
        try:
            from core.local_server import broadcast_hud_event
            broadcast_hud_event("close_laya_screen", {})
            return True
        except Exception:
            return False

_INSTANCE: Optional[LayaScreenSubagent] = None

def get_laya_agent() -> LayaScreenSubagent:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = LayaScreenSubagent()
    return _INSTANCE
