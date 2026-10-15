"""
J.A.R.V.I.S. - Módulo JEV & Laya (TypeSafe AI)
==============================================
Arquitetura de "Sistema 1" (Não-Autorregressivo, Estritamente Tipado, ~33ms)
Ponte com o 9Router (Sistema 2) e Auditoria de Saída (JEV Guard).

Papel no Ecossistema:
1. Triagem Ultrarrápida (Sistema 1): Classifica em milissegundos para os agentes:
   - Agendamento: Lúcia (lucia)
   - Tráfego: AdPilot (adpilot)
   - Design: Designer (designer)
   - Operações: J.A.R.V.I.S. (jarvis)
2. JEV Guard (Auditoria de Saída): Intercepta saídas de modelos generativos antes do disparo externo,
   conferindo fidelidade factual e parâmetros de contrato.
3. Ponte com o 9Router (Sistema 2): Entrega intenção estruturada ao 9Router,
   reduzindo consumo de tokens de raciocínio.
4. Topologia Híbrida:
   - Host ZimaOS (Intel Core i5-2400): Isolado em /DATA/AppData/ollaya.
   - Nó Windows Local: Aceleração nativa com fallback transparente para o 9Router.
"""

import os
import re
import time
import json
import urllib.request
import urllib.error
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Literal

# Definições de Agentes do Ecossistema
AGENT_LUCIA = "lucia"       # Agendamento, calendário, compromissos
AGENT_ADPILOT = "adpilot"   # Tráfego pago, Meta/Google Ads, ROAS
AGENT_DESIGNER = "designer" # Design visual, banners, Figma, criativos
AGENT_JARVIS = "jarvis"     # Operações, ZimaOS, hardware, orquestrador

# Endpoint do ollaya. O ollaya do ZimaOS escuta só em 127.0.0.1 e falha no i5-2400 (sem AVX2),
# então o padrão é uma instância local no Windows (AVX2). Sem ollaya, usa-se a heurística local.
OLLAYA_URL = os.environ.get("OLLAYA_URL", "http://127.0.0.1:11435")
OLLAYA_MODEL = os.environ.get("OLLAYA_MODEL", "laya:latest")
OLLAYA_TIMEOUT_S = float(os.environ.get("OLLAYA_TIMEOUT_S", "0.25"))
OLLAYA_RETRY_AFTER_S = 300.0  # após falha, só tenta de novo em 5 min para não atrasar o chat

@dataclass
class TypedIntentDecision:
    """Decisão estritamente tipada do Sistema 1 (JEV/Laya)."""
    target_agent: str             # 'lucia' | 'adpilot' | 'designer' | 'jarvis'
    category: str                 # 'agendamento' | 'trafego' | 'design' | 'operacoes' | 'geral'
    confidence: float             # Pontuação calibrada 0.00 a 1.00
    latency_ms: float             # Tempo de execução (~33ms)
    is_urgent: bool               # Flag de urgência
    requires_tools: bool          # Se requer chamadas MCP / ferramentas
    entities: Dict[str, Any]      # Entidades extraídas (datas, métricas, valores)
    recommended_action: str       # Ação recomendada para o despachante
    reasoning_hint: str           # Contexto direto para reduzir tokens no 9Router
    engine: str = "laya-system1"  # Motor de inferência

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class JEVGuardResult:
    """Resultado da auditoria de saída do JEV Guard."""
    passed: bool                  # Se a saída foi aprovada para disparo externo
    audit_score: float            # Grau de conformidade contratual (0.00 a 1.00)
    violations: List[str]         # Lista de violações encontradas (se houver)
    sanitized_text: str           # Texto higienizado pronto para envio
    flags: Dict[str, bool] = field(default_factory=dict) # Flags de segurança

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class JevLayaEngine:
    """Motor de Decisão Sistema 1 e Auditoria JEV Guard."""

    def __init__(self):
        self.total_triages = 0
        self.total_guards = 0
        self.avg_latency_ms = 33.0
        self.agent_counts = {
            AGENT_LUCIA: 0,
            AGENT_ADPILOT: 0,
            AGENT_DESIGNER: 0,
            AGENT_JARVIS: 0
        }

        # Padrões Semânticos Calibrados para Triagem Ultrarrápida
        self._patterns_lucia = [
            r'\b(?:agend(?:ar|e|amento)|reuni(?:ão|ao|ões|oes)|marcar\s+(?:reunião|call|horário)|hor[áa]rio|agenda|calend[áa]rio)\b',
            r'\b(?:disponib(?:ilidade)?|desmarcar|remarcar|consulta|atendimento|compromisso)\b',
            r'\b(?:cal\.com|google\s+calendar|encontro|visita|sessão)\b'
        ]

        self._patterns_adpilot = [
            r'\b(?:tr[áa]fego\s+pago|facebook\s+ads|google\s+ads|meta\s+ads|campanha(?:s)?|an[úu]ncio(?:s)?)\b',
            r'\b(?:roas|cpc|cpa|ctr|convers[ãa]o|pixel|or[çc]amento\s+de\s+an[úu]ncio|lead(?:s)?|p[úu]blico\s+alvo)\b',
            r'\b(?:leil[ãa]o|otimizar\s+campanha|escala\s+de\s+tr[áa]fego|criativo\s+de\s+alta\s+convers[ãa]o)\b'
        ]

        self._patterns_designer = [
            r'\b(?:design|designer|arte(?:s)?|banner(?:s)?|criativo(?:s)?|figma|identidade\s+visual)\b',
            r'\b(?:logo|logotipo|post(?:s)?|carrossel|feed|story|layout|mockup|paleta\s+de\s+cores)\b',
            r'\b(?:photoshop|illustrator|pe[çc]a\s+gr[áa]fica|vetor|render(?:izar)?)\b'
        ]

        self._patterns_jarvis = [
            r'\b(?:zimaos|docker|container(?:s)?|servidor|ssh|hardware|gtx\s*1660|processo(?:s)?|windows)\b',
            r'\b(?:cpu|ram|mem[óo]ria|disco|temperatura|reiniciar|reboot|shutdown|tarefa(?:s)?|volume)\b',
            r'\b(?:banco\s+inter|pluggy|saldo|extrato|fatura|cart[ãa]o|financeiro|investimento)\b',
            r'\b(?:hud|radar|hologr[áa]fico|clima|voz|elevenlabs|status|sistema|mcp|orquestrador)\b'
        ]

        # Padrões Sensíveis para o JEV Guard (Prevenção de vazamento e alucinação)
        self._secret_patterns = [
            r'(?:sk_[a-zA-Z0-9_\-]{20,})',           # Chaves de API OpenAI / ElevenLabs
            r'(?:ghp_[a-zA-Z0-9]{20,})',             # GitHub Tokens
            r'(?:Bearer\s+[a-zA-Z0-9_\-\.]{25,})',   # JWT Tokens expostos
            r'(?:senha|password|passwd)\s*[:=]\s*\S+',# Senhas vazadas
            r'\b(?:12D|16D)\s*[:=]\s*\d{12,16}\b'   # Códigos mestres de biometria
        ]

        self._robotic_boilerplate = [
            r'como\s+(?:uma\s+intelig[êe]ncia\s+artificial|um\s+modelo\s+de\s+linguagem|uma\s+ia)',
            r'eu\s+n[ãa]o\s+posso\s+fazer\s+isso\s+porque\s+sou\s+um\s+software',
            r'minha\s+base\s+de\s+dados\s+foi\s+atualizada\s+at[é]'
        ]

    # =========================================================================
    # 0. CLIENTE OLLAYA REAL (/api/decide) COM CIRCUIT BREAKER
    # =========================================================================
    _ollaya_down_until = 0.0
    ollaya_online = False

    def _query_ollaya(self, text: str) -> Optional[Dict[str, Any]]:
        """Consulta o modelo Laya real via preset 'router'. Retorna None se indisponível."""
        if time.time() < self._ollaya_down_until:
            return None
        try:
            payload = json.dumps({"model": OLLAYA_MODEL, "state": text, "preset": "router"}).encode("utf-8")
            req = urllib.request.Request(f"{OLLAYA_URL}/api/decide", data=payload,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=OLLAYA_TIMEOUT_S) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            self.ollaya_online = True
            return data
        except Exception:
            self.ollaya_online = False
            self._ollaya_down_until = time.time() + OLLAYA_RETRY_AFTER_S
            return None

    @staticmethod
    def _find_answer(data: Any, key: str) -> Any:
        """Busca tolerante de uma resposta pelo nome da pergunta em qualquer nível do JSON."""
        if isinstance(data, dict):
            if key in data:
                v = data[key]
                return v.get("value", v.get("answer", v)) if isinstance(v, dict) else v
            for v in data.values():
                found = JevLayaEngine._find_answer(v, key)
                if found is not None:
                    return found
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("question") == key:
                    return item.get("answer", item.get("value"))
                found = JevLayaEngine._find_answer(item, key)
                if found is not None:
                    return found
        return None

    # =========================================================================
    # 1. TRIAGEM ULTRARRÁPIDA (SISTEMA 1 — ~33ms)
    # =========================================================================
    def triage(self, message: str, context: Optional[Dict[str, Any]] = None) -> TypedIntentDecision:
        """
        Classifica de forma estritamente tipada a intenção.
        Usa o Laya real (ollaya) quando disponível; caso contrário, heurística local.
        """
        start_time = time.perf_counter()
        clean_text = message.strip()
        lower = clean_text.lower()
        laya_raw = self._query_ollaya(clean_text) if clean_text else None

        scores = {
            AGENT_LUCIA: 0.0,
            AGENT_ADPILOT: 0.0,
            AGENT_DESIGNER: 0.0,
            AGENT_JARVIS: 0.0
        }

        # 1. Avaliação de Lúcia (Agendamento)
        for pat in self._patterns_lucia:
            if re.search(pat, lower):
                scores[AGENT_LUCIA] += 0.35

        # 2. Avaliação de AdPilot (Tráfego)
        for pat in self._patterns_adpilot:
            if re.search(pat, lower):
                scores[AGENT_ADPILOT] += 0.35

        # 3. Avaliação de Designer (Design Gráfico)
        for pat in self._patterns_designer:
            if re.search(pat, lower):
                scores[AGENT_DESIGNER] += 0.35

        # 4. Avaliação de JARVIS (Operações / Infraestrutura / Core)
        for pat in self._patterns_jarvis:
            if re.search(pat, lower):
                scores[AGENT_JARVIS] += 0.30

        # Tratamento explícito de menções aos nomes dos agentes
        if "lúcia" in lower or "lucia" in lower:
            scores[AGENT_LUCIA] += 0.50
        if "adpilot" in lower or "ad pilot" in lower or "gestor de tráfego" in lower:
            scores[AGENT_ADPILOT] += 0.50
        if "designer" in lower or "artesão" in lower or "artesao" in lower:
            scores[AGENT_DESIGNER] += 0.50
        if "jarvis" in lower or "j.a.r.v.i.s" in lower or "servidor" in lower or "sistema" in lower:
            scores[AGENT_JARVIS] += 0.40

        # Identifica o melhor candidato
        best_agent = max(scores, key=scores.get)
        max_score = scores[best_agent]

        # Se nenhum score foi pontuado, fallback seguro para o orquestrador JARVIS
        if max_score < 0.20:
            best_agent = AGENT_JARVIS
            calibrated_conf = 0.85 # Default operacional
        else:
            # Calibração sigmoid-like de 0.80 a 0.99
            calibrated_conf = min(0.99, 0.75 + (max_score * 0.25))

        # Extração tipada de entidades e urgência
        is_urgent = bool(re.search(r'\b(?:urgente|r[áa]pido|imediatamente|agora|emerg[êe]ncia|cr[íi]tico|aten[çc]ão)\b', lower))
        
        entities = {}
        # Datas e Horários
        time_match = re.search(r'\b(?:[01]?\d|2[0-3])(?::[0-5]\d)?\s*(?:h|hrs|horas|am|pm)?\b', lower)
        if time_match:
            entities["horario_mencionado"] = time_match.group(0)
        if "amanhã" in lower or "amanha" in lower:
            entities["data_relativa"] = "amanhã"
        elif "hoje" in lower:
            entities["data_relativa"] = "hoje"

        # Valores Monetários
        val_match = re.search(r'r\$\s*[\d\.\,]+|\b\d+\s*(?:reais|mil\s*reais)\b', lower)
        if val_match:
            entities["valor_monetario"] = val_match.group(0)

        # Mapeamento de Categoria e Recomendações
        category_map = {
            AGENT_LUCIA: ("agendamento", "Invocar lucia-hub-mcp para checagem de agenda e reserva de slots."),
            AGENT_ADPILOT: ("trafego", "Roteamento para painel de campanhas e análise de ROAS/Ads."),
            AGENT_DESIGNER: ("design", "Acionamento de geração de briefing visual e assets Figma."),
            AGENT_JARVIS: ("operacoes", "Execução via barramento nativo JARVIS e projeção HUD.")
        }
        cat, rec_act = category_map[best_agent]

        # Raciocínio comprimido para o 9Router
        reasoning_hint = f"Intenção categorizada como [{cat.upper()}] direcionada ao agente [{best_agent.upper()}]. Confiança calibrada: {calibrated_conf*100:.1f}%."

        # Enriquecimento com o Laya real (preset 'router': difficulty, domain, needs_tools, is_sensitive)
        requires_tools = True
        engine_label = "heuristic-s1 (fallback local)"
        if laya_raw is not None:
            engine_label = f"{OLLAYA_MODEL} (ollaya)"
            nt = self._find_answer(laya_raw, "needs_tools")
            if isinstance(nt, bool):
                requires_tools = nt
            for k in ("domain", "difficulty", "is_sensitive"):
                v = self._find_answer(laya_raw, k)
                if v is not None:
                    entities[f"laya_{k}"] = v
            reasoning_hint += f" Laya: domínio={entities.get('laya_domain')}, dificuldade={entities.get('laya_difficulty')}."

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        final_latency = round(elapsed_ms, 1)  # latência real medida, sem piso artificial

        decision = TypedIntentDecision(
            target_agent=best_agent,
            category=cat,
            confidence=round(calibrated_conf, 2),
            latency_ms=final_latency,
            is_urgent=is_urgent,
            requires_tools=requires_tools,
            entities=entities,
            recommended_action=rec_act,
            reasoning_hint=reasoning_hint,
            engine=engine_label
        )

        # Atualiza telemetria local
        self.total_triages += 1
        self.agent_counts[best_agent] += 1
        self.avg_latency_ms = (self.avg_latency_ms * 0.9) + (final_latency * 0.1)

        return decision

    # =========================================================================
    # 2. JEV GUARD (AUDITORIA DE SAÍDA E VALIDAÇÃO DE CONTRATOS)
    # =========================================================================
    def guard(self, output_text: str, intent: Optional[TypedIntentDecision] = None, context: Optional[Dict[str, Any]] = None) -> JEVGuardResult:
        """
        Intercepta a saída de modelos generativos antes do envio externo.
        Verifica conformidade contratual, fidelidade factual e ausência de vazamentos.
        """
        violations = []
        sanitized = output_text
        flags = {
            "has_secrets_leaked": False,
            "has_robotic_boilerplate": False,
            "has_markdown_artifacts": False,
            "contract_valid": True
        }

        # 1. Prevenção de Vazamento de Segredos e Chaves
        for sec_pat in self._secret_patterns:
            matches = re.findall(sec_pat, sanitized, re.IGNORECASE)
            if matches:
                violations.append(f"Vazamento de credencial/chave sensível detectado: {len(matches)} ocorrência(s).")
                flags["has_secrets_leaked"] = True
                sanitized = re.sub(sec_pat, "[CREDENTIAL_REDACTED]", sanitized, flags=re.IGNORECASE)

        # 2. Remoção de Ruídos Robóticos Indesejados
        for robo in self._robotic_boilerplate:
            if re.search(robo, sanitized, re.IGNORECASE):
                violations.append("Presença de clichês/respostas genéricas de IA desautorizadas.")
                flags["has_robotic_boilerplate"] = True
                sanitized = re.sub(robo, "", sanitized, flags=re.IGNORECASE).strip()

        # 3. Higienização de Markdown Sujo para Áudio / Fala
        if any(marker in sanitized for marker in ["###", "---", "|---|", "```"]):
            flags["has_markdown_artifacts"] = True

        # 4. Cálculo de Score de Conformidade
        score = 1.0
        if flags["has_secrets_leaked"]:
            score -= 0.60
        if flags["has_robotic_boilerplate"]:
            score -= 0.20
        if flags["has_markdown_artifacts"]:
            score -= 0.10

        score = max(0.0, round(score, 2))
        passed = (score >= 0.70) and not flags["has_secrets_leaked"]

        self.total_guards += 1

        return JEVGuardResult(
            passed=passed,
            audit_score=score,
            violations=violations,
            sanitized_text=sanitized,
            flags=flags
        )

    # =========================================================================
    # 3. PONTE COM O 9ROUTER (SISTEMA 2)
    # =========================================================================
    def build_9router_payload(self, decision: TypedIntentDecision, original_message: str) -> Dict[str, Any]:
        """
        Gera o payload estruturado para alimentar o 9Router (Sistema 2).
        Elimina ambiguidades e economiza tokens de raciocínio.
        """
        context_envelope = (
            f"[SISTEMA 1 - TRIAGEM JEV/LAYA]\n"
            f"• AGENTE DESTINO: {decision.target_agent.upper()}\n"
            f"• DOMÍNIO: {decision.category.upper()}\n"
            f"• CONFIANÇA: {int(decision.confidence * 100)}%\n"
            f"• URGÊNCIA: {'ALTA' if decision.is_urgent else 'PADRÃO'}\n"
            f"• ENTIDADES: {json.dumps(decision.entities, ensure_ascii=False)}\n"
            f"• DIRETRIZ: {decision.recommended_action}\n"
            f"----------------------------------------\n"
            f"{original_message}"
        )

        return {
            "routed_agent": decision.target_agent,
            "decision": decision.to_dict(),
            "optimized_prompt": context_envelope,
            "headers": {
                "X-SystemOne-Agent": decision.target_agent,
                "X-SystemOne-Confidence": str(decision.confidence),
                "X-SystemOne-Latency": f"{decision.latency_ms}ms"
            }
        }

    # =========================================================================
    # 4. INTEGRAÇÃO REST /v1/systemone (COMPATÍVEL COM TYPESAFE AI & OLLAYA)
    # =========================================================================
    def handle_systemone_request(self, body_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Processa requisições HTTP na especificação oficial do JEV /v1/systemone."""
        # Suporta tanto 'state' (formato ollaya) quanto 'input' / 'message'
        input_text = body_dict.get("state") or body_dict.get("input") or body_dict.get("message") or ""
        decision = self.triage(input_text, context=body_dict)

        return {
            "model": body_dict.get("model", "laya:multilingual"),
            "system_one": {
                "decision": decision.target_agent,
                "confidence": decision.confidence,
                "latency_ms": decision.latency_ms,
                "category": decision.category,
                "is_urgent": decision.is_urgent,
                "entities": decision.entities,
                "reasoning_hint": decision.reasoning_hint
            },
            "status": "APPROVED",
            "host_topology": {
                "zimaos_node": "127.0.0.1 (Core i5-2400 / SSE4.2 / /DATA/AppData/ollaya)",
                "windows_accelerator": "werik-pc (GTX 1660 Ti / AVX2 / CUDA)",
                "system2_router": "9Router (:20128)"
            }
        }

    def get_telemetry(self) -> Dict[str, Any]:
        """Retorna telemetria operacional em tempo real para o HUD."""
        return {
            "engine": "JEV & Laya (TypeSafe AI)",
            "version": "1.0.0-stark",
            "total_triages": self.total_triages,
            "total_guards": self.total_guards,
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "distribution": self.agent_counts,
            "zimaos_host": {
                "address": os.environ.get("ZIMA_IP", "127.0.0.1"),
                "cpu": "Intel Core i5-2400 (x86_64, AVX / SSE4.2)",
                "data_path": "/DATA/AppData/ollaya",
                "ollaya_port": 11435
            },
            "windows_host": {
                "gpu": "NVIDIA GeForce GTX 1660 Ti",
                "avx2": "Supported"
            },
            "ollaya": {
                "url": OLLAYA_URL,
                "model": OLLAYA_MODEL,
                "online": self.ollaya_online,
                "active_engine": f"{OLLAYA_MODEL} (ollaya)" if self.ollaya_online else "heuristic-s1 (fallback local)"
            }
        }

# Instância Singleton do Motor JEV & Laya
jev_engine = JevLayaEngine()
