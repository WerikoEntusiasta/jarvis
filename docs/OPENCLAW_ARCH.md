# OpenClaw Architecture & Autonomous Agent Guide

> **Documento legado/superado.** A regra atual é o JARVIS Core único: veja [JARVIS_CORE_ARQUITETURA.md](JARVIS_CORE_ARQUITETURA.md). OpenClaw não é o núcleo de transporte, não deve ser usado diretamente pelo Windows e não deve hospedar as ferramentas/MCP JARVIS. O diagrama abaixo é histórico e não representa a arquitetura-alvo.

## 1. Visão Geral da Arquitetura OpenClaw

O **OpenClaw** é o núcleo cognitivo autônomo do J.A.R.V.I.S., hospedado na VPS remota (`https://jarvis.werikspace.xyz`). Ele orquestra modelos de inteligência artificial, ferramentas de execução, subagentes especializados e o barramento de comunicação bi-direcional.

```
┌──────────────────────────────────────────────────────────────────┐
│                      NÚCLEO OPENCLAW (VPS)                       │
│                                                                  │
│   ┌────────────────┐     ┌────────────────┐   ┌──────────────┐  │
│   │ OpenClaw Agent │ <-> │ Subagentes     │ <->│ MCP Tools    │  │
│   │ (Jarvis Core)  │     │ Especializados │   │ Integradas   │  │
│   └───────┬────────┘     └────────────────┘   └──────────────┘  │
└───────────┼──────────────────────────────────────────────────────┘
            │ WebSocket / HTTP Gateway Protocol (Porta 8080)
┌───────────▼──────────────────────────────────────────────────────┐
│                    NODE WINDOWS (JARVIS LOCAL)                   │
│                                                                  │
│   ┌────────────────┐     ┌────────────────┐   ┌──────────────┐  │
│   │ Central HUD    │ <-> │ Visual OS      │ <->│ Windows      │  │
│   │ (index.html)   │     │ Engine (JS)    │   │ Control      │  │
│   └────────────────┘     └────────────────┘   └──────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

## 2. Conceitos Fundamentais

### A. OpenClaw Gateway API
- Serviço REST e WebSocket que aceita requisições de agentes locais, Siri, comandos de voz e atalhos PWA.
- Endpoint principal: `POST /api/chat` e `/api/remote/enqueue`.

### B. Subagentes Autônomos (Concurrent Subagents)
- O OpenClaw pode invocar subagentes paralelos através da chamada de ferramentas internas (`invoke_subagent`).
- **Casos de Uso**:
  - *Pesquisa em Tempo Real*: Um subagente busca notícias no DuckDuckGo/Google enquanto outro formata a UI Specification.
  - *Análise de Código*: Um subagente inspeciona o repositório enquanto outro compila o relatório tático.

### C. Sistema de Memória Agêntica Unificado (Central Brain)
- Conecta o OpenClaw (VPS), o Antigravity (PC do Werik), o OpenCode e outros agentes a um banco vetorial/grafo comum.
- Permite persistência de contextos de projetos, preferências do usuário, regras e estado do ambiente.

### D. Visual OS Specification Protocol
- O OpenClaw não responde apenas texto: ele gera especificações estruturadas no formato:
```json
{
  "type": "weather | comparison | checklist | metric | flow | timeline | dashboard | form | controls | map",
  "title": "TÍTULO DO PAINEL",
  "subtitle": "SUBTÍTULO DA SEÇÃO",
  "content": "Texto resumido spoken_reply"
}
```
- A especificação é interceptada pelo `server.py` e renderizada em componentes dinâmicos no HUD.

## 3. Diretrizes de Invocação e Extensibilidade

1. **Liberdade Total de Criação Visual**: O assistente deve compor a melhor experiência para a natureza do dado.
2. **Respostas em Camadas**: O cliente exibe o painel gráfico em `<500ms` e reproduz áudio assíncrono em seguida.
3. **Persistência de Memória**: Toda decisão relevante é salva no banco vetorial central (`memory/`).
