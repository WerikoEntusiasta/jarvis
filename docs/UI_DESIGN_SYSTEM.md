# 🎨 J.A.R.V.I.S. Frontend UI & Animation Design System

Guia de referência dos principais ecossistemas de componentes e animações integrados ao J.A.R.V.I.S.:

---

## 🚀 1. HeroUI (antigo NextUI)
- **URL**: [https://heroui.com/en/docs/react/components](https://heroui.com/en/docs/react/components)
- **Estilo**: Design futurista com efeito de vidro fosco (*Glassmorphism*), gradientes escuros, neon e bordas arredondadas (`rounded-2xl`).
- **Componentes Principais**:
  - `Card`: Cartões de telemetria, clima, hardware e cotações.
  - `Modal`: Janela de diálogo e confirmações de ações.
  - `Chip` & `Badge`: Marcadores de status (Online, Standby, Executando).
  - `Progress Bar`: Indicador de uso de CPU/GPU e tarefas ativas.
  - `Table`: Exibição de extratos Open Finance (Pluggy) e processos.

---

## 🧩 2. shadcn/ui (Radix Primitives + Tailwind)
- **URL**: [https://ui.shadcn.com/docs/components](https://ui.shadcn.com/docs/components)
- **Estilo**: Componentes desacoplados, limpos e acessíveis sobre Radix UI.
- **Componentes Principais**:
  - `Command (⌘ K)`: Paleta de comandos flutuante para atalhos rápidos.
  - `Sheet` / `Drawer`: Painéis laterais deslizantes para configurações.
  - `Dialog` & `Popover`: Notificações rápidas e detalhes ao passar o mouse.
  - `Skeleton`: Animação de carregamento enquanto o áudio e os dados chegam via SSE.

---

## 🏛️ 3. Material UI (MUI)
- **URL**: [https://mui.com/material-ui/all-components/](https://mui.com/material-ui/all-components/)
- **Estilo**: Sistema robusto de componentes enterprise baseado em Material Design.
- **Componentes Principais**:
  - `Speed Dial`: Ações rápidas de atalho flutuante no canto da tela.
  - `Data Grid`: Tabelas avançadas com ordenação, filtros e paginação.
  - `Stepper`: Fluxo passo-a-passo de onboarding e cadastro biométrico.

---

## 🟡 4. Display Circular Esfera ESP32-S3 (240x240 GC9A01 + Touch CST816D)
- **Documentação de Referência**: `gabarito_esfera_esp32_display_touch.md`
- **Geometria**: Matriz $240 \times 240$ pixels, Raio $R = 120\text{px}$, Centro $(120, 120)$.
- **Canais de Transmissão 100% Sem Fio (Wi-Fi)**:
  1. **WebSocket (`:8095/ws`)**: Transmissão em tempo real bidirecional do firmware com o container `jarvis-screen-router`.
  2. **HTTP REST (`/api/jarvis/show_screen` / `/api/esfera/show_screen`)**: Endpoints de envio de telas e cards interativos.
  3. **Ferramentas MCP (`jarvis-hud__exibir_na_esfera`)**: Controle de exibição via agentes de IA e OpenClaw.
  4. **UDP Direto Local (Porta 8888)**: Streaming em tempo real para telemetria com latência $< 5\text{ms}$.
- **Regras Invioláveis de Design para a Esfera**:
  1. **Transmissão Sem Fio Obrigatória**: As telas e cards devem SEMPRE ser disparados remotamente pela rede sem fio (Wi-Fi), sem fios físicos.
  2. **Largura Útil Variável**: A largura horizontal visível $W(Y) = 2 \sqrt{120^2 - (Y - 120)^2}$.
  3. **Safe Area Interna**: Manter conteúdos críticos e botões dentro de $(X-120)^2 + (Y-120)^2 \le 100^2$.
  4. **Corte nos Cantos**: Os 4 cantos ($X < 35, Y < 35$ etc.) são fisicamente cobertos pelo bisel redondo do hardware.
  5. **Gabarito de Botões Duplos/Triplos na Base**:
     - 2 Botões: $X \in [35, 110]$ e $X \in [130, 205]$ em $Y \in [168, 206]$.
     - 3 Botões: $X \in [18, 82]$, $X \in [88, 152]$ e $X \in [158, 222]$ em $Y \in [168, 206]$.
  6. **Cabeçalho no Topo**: Centrado em $X=120, Y=18$, largura máx $120\text{px}$.


