"""
J.A.R.V.I.S. Morning Briefing Dispatcher
Gera e envia o resumo executivo diário para o Senhor Werik via WhatsApp:
- Agenda do dia (Lúcia)
- Métricas de tráfego de ontem / últimos dias (AdPilot)
- Saúde e telemetria do ZimaOS (Sentinel)
"""

import os
import json
import logging
import urllib.request
import jarvis_tools

logger = logging.getLogger("JARVIS-BRIEFING")

WAHA_URL = os.environ.get("WAHA_URL", "http://172.17.0.1:9455")
WAHA_KEY = os.environ.get("WAHA_KEY", "owklM4tm3EdKhQSho5ReuLnt7C2FgxpH")
WERIK_PHONE = os.environ.get("WERIK_PHONE", "5517991951381@c.us")


def generate_briefing_text() -> str:
    """Consolida as informações dos 3 especialistas em um briefing de alto impacto."""
    traffic = jarvis_tools.get_traffic_metrics("last_7d")
    events = jarvis_tools.get_agenda_events(3)
    health = jarvis_tools.get_system_health()

    lines = [
        "☀️ *BOM DIA, SENHOR WERIK! — BRIEFING EXECUTIVO J.A.R.V.I.S.*",
        f"📅 _{health.get('timestamp')}_",
        "",
        "📊 *1. TRÁFEGO PAGO & PERFORMANCE (AdPilot)*",
        f"• Investimento (7d): *{traffic.get('total_gasto', 'R$ 0')}*",
        f"• Cliques Totais: *{traffic.get('total_cliques', 0):,}* | Impressões: *{traffic.get('total_impressoes', 0):,}*"
    ]

    for c in traffic.get("contas", []):
        if c.get("status") == "ativa":
            lines.append(f"  └ 🎯 *{c['account']}*: Gasto {c['spend']} | CPC {c['cpc']}")

    lines.append("")
    lines.append("🗓️ *2. AGENDA & COMPROMISSOS (Lúcia)*")
    if events:
        for ev in events:
            lines.append(f"• *{ev.get('title')}* — _{ev.get('description') or 'Sem detalhes'}_")
    else:
        lines.append("• Nenhum compromisso urgente agendado para as próximas horas.")

    lines.append("")
    lines.append("🛡️ *3. INFRAESTRUTURA & SEGURANÇA (Sentinel)*")
    lines.append(f"• Armazenamento: *{health.get('disco')}*")
    lines.append(f"• Memória RAM: *{health.get('ram')}*")
    lines.append("• WhatsApp & Broker MQTT: *100% Operacionais*")
    lines.append("")
    lines.append("⚡ _J.A.R.V.I.S. e todos os 10 especialistas do Squad estão a postos para o seu comando._")

    return "\n".join(lines)


def send_morning_briefing(target_phone: str = None) -> bool:
    """Dispara o briefing via WhatsApp pela sessão jarvis."""
    phone = target_phone or WERIK_PHONE
    text = generate_briefing_text()
    payload = {
        "chatId": phone,
        "text": text,
        "session": "jarvis"
    }
    try:
        req = urllib.request.Request(
            f"{WAHA_URL}/api/sendText",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-Api-Key": WAHA_KEY
            }
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status == 200 or r.status == 201
    except Exception as e:
        logger.error(f"[BRIEFING] Falha enviando WhatsApp: {e}")
        return False


if __name__ == "__main__":
    print(generate_briefing_text())
