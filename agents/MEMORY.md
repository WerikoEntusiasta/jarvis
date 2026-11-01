# MEMORY.md - Fatos Duráveis e Histórico Estratégico do Núcleo

Este documento mantém a memória consolidada e permanente do sistema J.A.R.V.I.S., garantindo continuidade após reinicializações.

---

## 🏛️ Estrutura do Ecossistema J.A.R.V.I.S.

1. **Servidor Central (ZimaOS Core):**
   - IP: `45.167.187.80`
   - Painel WebUI & API: `https://jarvis.werikspace.xyz`
   - Roteador de Tela e Áudio da Esfera: porta `8095`
   - STT Local: Faster-Whisper na porta `8000` (+ Groq Cloud turbo)
   - Motores de IA: Xiaomi MiMo TokenPlan (v2.6) + OpenRouter Nemotron 550B + Nvidia NIM Llama 3.2
   - Serviços Auxiliares: Lucia Hub (8088), WAHA WhatsApp (9455), n8n (5678)
   - Contêiner OpenClaw: isolado e desacoplado do pipeline central de IA.

2. **Nó Desktop Windows (PC Principal do Senhor Werik):**
   - Localização: `c:\JARVIS\jarvis-windows`
   - Aplicação: Stark HUD Nativo em PyQt6 com aceleração de GPU (NVIDIA GeForce GTX 1660 Ti)
   - Hotkeys: `Ctrl + Espaço` ou `Win + Shift + J` para focar imediatamente
   - Comunicação: Polling e WebSocket direto com `https://jarvis.werikspace.xyz` com token de segurança `BRIDGE_SECRET`.
   - Provedor MCP: Ferramentas nativas do Windows (PowerShell, volume, mídia, processos, telemetria).

3. **Esfera Física (Hardware ESP32-S3):**
   - Display circular touch LCD, microfone ES8311 (+30dB de ganho), alto-falante I2S integrado.
   - Conexão: WebSocket persistente com o Core em `:8095`.

---

## 🔒 Marcos e Decisões Tomadas
- **2026-10-24:** Purga total do código legado do Windows Desktop e lançamento do J.A.R.V.I.S. Windows v2 independente.
- **2026-10-25:** Migração da IA para execução direta no Núcleo do J.A.R.V.I.S. (`core_ai_brain.py`), desacoplando o OpenClaw sem excluir seu contêiner.
