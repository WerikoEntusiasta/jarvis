# J.A.R.V.I.S. - HUD holográfico, voz e automação

Assistente pessoal híbrido inspirado no J.A.R.V.I.S. do Homem de Ferro, composto por:

- **HUD web** (`web/index.html`) - painel holográfico PWA com clima, finanças, radar de voos, notícias e YouTube
- **Core Server** (`server.py`) - backend HTTP na porta 8080 com APIs, SSE e ponte OpenClaw
- **MCP Server** (`mcp_hud_server.py`) - servidor MCP (porta 8081) para o agente Jarvis controlar o HUD
- **Nó Windows** (`desktop/`) - cliente nativo com Dynamic Island, tray, watchers e controle do Windows
- **Visão computacional** (`vision/`) - gestos por webcam (MediaPipe) com ações no Windows
- **Biometria** (`biometrics.py` + `web/enroll.html`) - login facial 128D com SQLite e portal de cadastro

## Requisitos

- Windows 10/11 (nó local) ou Docker (ZimaOS/VPS)
- Python 3.11+
- Webcam e microfone (recursos do nó local)

## Instalação local (Windows)

```bat
setup_env.bat
```

Cria o ambiente virtual próprio do projeto (`.venv`) e instala todas as dependências do `requirements.txt` (incluindo as exclusivas do Windows: pywin32, pyautogui, pycaw, faster-whisper, mediapipe etc).

Em seguida, copie `.env.example` para `.env` e preencha as credenciais (ZimaOS, Pluggy, ElevenLabs).

## Execução

```bat
run_jarvis_desktop.bat
```

Inicia o Core Server (`server.py`, porta 8080) e o cliente desktop (`desktop/app.py`).

- HUD: http://localhost:8080
- Portal de cadastro facial: http://localhost:8082 (enroll.html)
- Dynamic Island separada: `iniciar_island.bat`

Autoinicialização com o Windows:

```bat
python install_desktop.py
```

## MCP (para o OpenClaw / agentes)

```bat
.venv\Scripts\python.exe mcp_hud_server.py
```

Sobe o servidor MCP `jarvis-hud` em SSE na porta 8081 com ferramentas de projeção do HUD (telas, cards, canvas, timers, finanças, hardware, YouTube etc). As ferramentas chamam o Core Server em `HUD_SERVER_URL`.

## Deploy no ZimaOS (Docker)

```bat
python scripts/deploy_zima.py
```

Envia código, frontend, `Dockerfile` e `requirements.txt` para `/DATA/AppData/jarvis-hud`, reconstrói a imagem (`docker compose up -d --build`) e reinicia o container.

Portas publicadas no host ZimaOS:

| Externa | Interna | Serviço |
|---------|---------|---------|
| 8085 | 8080 | HUD / Core Server |
| 8087 | 8081 | MCP Server (SSE) |
| 8086 | 8082 | Portal de cadastro facial |

Verificação pós-deploy:

```bat
python verify_zima.py
```

## Biometria facial

- Cadastro: `http://localhost:8082` (portal protegido por chave de 12 dígitos) ou botão de cadastro no HUD
- Login: comparação do vetor 128D (face-api.js) contra os operadores do SQLite (`auth/biometrics.db`)
- Código mestre de emergência: 16 dígitos (`/api/auth/code/verify`)
- Ativar/desativar portal: variável `ENROLLMENT_PORTAL_ENABLED` ou endpoint `/api/enroll/toggle`

## Configuração

Todas as credenciais vêm de `.env` (local) ou variáveis de ambiente (Docker). Nunca ficam hardcoded no código. Ordem de precedência: variável de ambiente real > `.env`.

## Estrutura de portas (nó local)

| Porta | Serviço |
|-------|---------|
| 8080 | Core Server (HUD, APIs, SSE) |
| 8081 | MCP Server |
| 8082 | Portal de cadastro facial |

## Arquitetura de agentes (JEV & Laya - Sistema 1)

`jev_laya.py` faz a triagem ultrarrápida (~33ms) das mensagens entre os agentes do ecossistema: **Lúcia** (agendamento), **AdPilot** (tráfego), **Designer** (criativos) e **JARVIS** (operações). Inclui o **JEV Guard**, auditoria de saída que bloqueia vazamento de segredos e texto robótico. Tenta o modelo local `ollaya` (`OLLAYA_URL`, padrão `http://127.0.0.1:11435`) e cai para heurística local com circuit breaker.

## Segurança

- Comandos de alto risco no nó Windows (cmd, delete, kill de processos) exigem confirmação explícita (`CommandBus._classify_risk`). Para um nó com **acesso total**, defina `security.auto_confirm_high_risk: true` no `config/jarvis_desktop_config.json` — cada PC com o app instalado é registrado como um nó controlável pelo agente (capabilities + `node.register` via gateway OpenClaw).
- `security.blocked_commands` no config do nó = bloqueio absoluto, independente de confirmação.
- Credenciais fora do código: `.env` local / env vars no Docker

## RBAC - Comportamento por usuário (biometria facial)

O JARVIS se adapta a cada pessoa autenticada via Face ID:

- **Proprietário (Werik)**: acesso total (Windows, infra, energia, finanças, WoL, tudo)
- **Operador Autorizado**: por padrão apenas conversa, voz e controle de mídia — o Werik decide o que liberar
- **Convidado**: apenas conversa e comandos de voz gerais

Como funciona:

1. O login facial (`/api/auth/face/verify`) identifica o operador no SQLite e emite um **token de sessão assinado (HMAC, 12h)** com as permissões da pessoa
2. O frontend envia o token no header `X-Jarvis-Session` em `/api/chat`, `/api/canvas/action` etc.
3. O servidor valida a permissão exigida por cada intenção (volume → `media_control`; desligar → `power_control`; Docker → `infra_control`; saldos → `finance_view`; ligar PC → `wake_on_lan`) e responde 403/`forbidden` para quem não tem
4. Requisições do nó local (127.0.0.1) e do MCP são tratadas como Proprietário (`JARVIS_TRUST_LOCAL=0` endurece isso)
5. O agente no OpenClaw recebe o nome e papel do usuário autenticado e adapta o tom e o escopo das respostas

Gerenciar permissões (reservado ao Proprietário):

```bat
python -c "import urllib.request,json; req=urllib.request.Request('http://localhost:8080/api/operators', data=json.dumps({'name':'Willian','permissions':{'chat':True,'voice_commands':True,'media_control':True}}).encode(), headers={'Content-Type':'application/json','X-Master-Key':'<CHAVE 16D>'}); print(urllib.request.urlopen(req).read().decode())"
```

Ou via ferramentas MCP: `listar_operadores_permissoes` e `configurar_permissoes_operador`.

## Wake-on-LAN (ligar PCs remotamente)

O servidor (incluindo o container Docker no ZimaOS) envia o pacote mágico via UDP broadcast:

```json
POST /api/wol { "action": "wake", "mac": "AA:BB:CC:DD:EE:FF", "ip": "192.168.0.255", "port": 9 }
```

- Dispositivos ficam em `config/wol_devices.json` (cadastre via API ou MCP `cadastrar_dispositivo_wol`)
- **Mesma rede**: use o broadcast da subnet (ex.: `192.168.0.255`)
- **Outra rede com IP fixo**: informe o broadcast da rede remota (ex.: `200.100.50.255`) com *directed broadcast* liberado no roteador, ou o IP fixo do host se houver relay
- Por voz: "Jarvis, liga o PC do escritório" (permissão `wake_on_lan`)
- Ferramentas MCP: `enviar_wake_on_lan`, `listar_dispositivos_wol`, `cadastrar_dispositivo_wol`

Referência completa de endpoints: `api_endpoints.md`

## Segurança de rede

- Endpoints de energia, Docker e processos exigem permissão RBAC; ainda assim, não exponha as portas do Core Server publicamente sem um proxy com autenticação adicional (Nginx Proxy Manager + HTTPS)
- O token de sessão é assinado com `auth/session_secret.key` (ou env `JARVIS_SESSION_SECRET`); um segredo por instalação

## Limitações conhecidas

- No Docker/ZimaOS a visão computacional opera em fallback headless (sem webcam); gestos e biometria por imagem rodam apenas no nó Windows
- A transcrição de voz (`/api/transcribe`) requer `faster-whisper`; sem ele, o endpoint responde 503 com mensagem clara
- O servidor MCP usa `HUD_SERVER_URL` para alcançar o Core Server; em Docker eles sobem juntos no mesmo container
