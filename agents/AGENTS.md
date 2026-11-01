# AGENTS.md - Arquitetura de Agentes Autônomos do Núcleo J.A.R.V.I.S.

Este documento define os papéis, canais, ferramentas e hierarquia dos agentes cognitivos executando **diretamente no Núcleo JARVIS (ZimaOS Core)**, sem qualquer intermediação do OpenClaw.

---

## 🤖 Catálogo de Agentes do Núcleo

### 1. J.A.R.V.I.S. (Agente Principal / Core Orchestrator)
* **Função:** Orquestrador central, interlocutor direto do Senhor Werik, tomada de decisão e síntese geral.
* **Modelos Neurais:** MiMo v2.6 Flash / Pro (Xiaomi TokenPlan 1M context) + Nemotron Ultra 550B (OpenRouter) + Llama 3.2 11B Vision (NVIDIA NIM).
* **Voz:** George (ElevenLabs TTS via `/api/tts_pcm` ou Edge-TTS).
* **Superfícies Ativas:**
  * **Desktop Windows:** Stark HUD Nativo (`jarvis-windows`).
  * **Esfera Física ESP32-S3:** LCD Touch, Mic ES8311 (+30dB), canal WebSocket `:8095` e `:8096`.
  * **WebUI PWA:** Visor tático mobile / desktop (`https://jarvis.werikspace.xyz`).
* **Ferramentas Conectadas (MCP):**
  * Windows Bridge: Abrir/fechar apps, PowerShell, controle de volume, janelas e mídia.
  * Telemetria: Monitoramento de hardware (CPU, RAM, GPU NVIDIA GTX 1660 Ti, ZimaOS Docker).
  * Clima & Notícias: Panorama meteorológico Catanduva/SP e feed em tempo real.

### 2. F.R.I.D.A.Y. (Agente Tática de Contingência)
* **Função:** Sub-rotina de monitoramento operacional, segurança de firewall, verificação de integridade e voz de backup.
* **Modelo:** Xiaomi MiMo v2.6 Fast.

### 3. LUCIA (Inteligência Comercial & CRM)
* **Função:** Gestão de contatos, contratos, rastreio de propostas e disparo de notificações push táticas via `lucia-hub` (:8088).

### 4. RADAR (Agente de Percepção & Monitoramento)
* **Função:** Processamento de visão computacional, radar aéreo ADS-B 3D da Terra e biometria facial Stark Face ID.

---

## 🛠️ Protocolo de Execução de Ferramentas (Function Calling Nativo)

1. Todas as chamadas de ferramentas usam o padrão **Model Context Protocol (MCP)** e chamadas de funções em formato JSON.
2. Nenhuma ferramenta passa pelo OpenClaw. A rota de execução é direta:
   `Prompt do Usuário -> Core Brain -> Despacho Local MCP (:8087) / Windows Bridge -> Retorno da Ação`.
3. Todas as ações físicas executadas (como alterar volume do Windows ou abrir aplicativos) disparam um card de confirmação ou toast visual no HUD.

---

## 📂 Ciclo de Vida da Memória

- `memory/USER.md`: Preferências permanentes e diretivas invioláveis do usuário.
- `memory/MEMORY.md`: Fatos duráveis, histórico de decisões e contexto consolidado.
- `memory/daily/YYYY-MM-DD.md`: Logs cronológicos de eventos diários para aprendizado contínuo.
