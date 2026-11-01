# Guia do Desenvolvedor & Padrões de Engenharia J.A.R.V.I.S.

> Diretrizes de Desenvolvimento, Padrões de Código e Configuração de Ambiente

---

## 1. Princípios de Engenharia

Todo código submetido ao ecossistema J.A.R.V.I.S. deve atender aos requisitos do documento mestre [`AGENTS.md`](file:///c:/JARVIS/AGENTS.md):

1. **Clareza e Legibilidade:** Escreva código autoexplicativo, com tipos explícitos e responsabilidade única por módulo.
2. **Tratamento de Exceções:** Nunca capture exceções com blocos vazios (`except: pass`). Trate os erros especificamente, registrando o contexto e aplicando comportamento de fallback seguro.
3. **Imutabilidade e Segurança:** Credenciais, tokens e chaves privadas nunca devem ser versionados em texto puro. Utilize sempre arquivos `.env` ou headers de segredo isolados (`include/jarvis_sphere_secrets.h`).

---

## 2. Configuração do Ambiente de Desenvolvimento

### 2.1 Backend Python (Windows PC)

- **Versão:** Python 3.11.x recomendada.
- **Passos de Inicialização:**
  ```powershell
  # Na raiz do repositório
  python -m venv venv
  .\venv\Scripts\Activate.ps1
  pip install --upgrade pip
  pip install -r requirements.txt
  ```
- **Verificação de Dependências Críticas:**
  - `aiohttp` e `websockets`: Comunicação assíncrona.
  - `psutil` e `pynvml`: Monitoramento de hardware para telemetria.
  - `paramiko`: Automação SSH com ZimaOS.
  - `pycaw` e `pywin32`: Controle nativo do Windows.

### 2.2 Firmware Embarcado ESP32-S3 (PlatformIO)

- **Instalação da Ferramenta:** PlatformIO Core (CLI) ou extensão oficial no VS Code.
- **Estrutura de Compilação:**
  O projeto reside em `c:\JARVIS\firmware_jarvis_custom\`.
- **Configuração no `platformio.ini`:**
  - Board: `esp32-s3-devkitc-1`
  - Flash Mode: `dio`, 16MB (`board_upload.flash_size = 16MB`)
  - PSRAM: `qio_opi` habilitada
  - Partições: `default_16MB.csv` (garante espaço adequado para OTA e binários de tamanho médio)

---

## 3. Convenções de Código

### 3.1 Desenvolvimento em C++ (Firmware ESP32-S3)

O código-fonte em `src/main.cpp` segue estritamente as diretrizes do **Google C++ Style Guide**:

- **Nomes de Tipos e Classes:** PascalCase (ex.: `DisplayMode`, `BatteryStatus`).
- **Nomes de Constantes Globais:** prefixadas por `k` em PascalCase (ex.: `kScreenWidth = 240`, `kBatteryAdcPin = 1`).
- **Nomes de Variáveis Globais:** prefixadas por `g_` em snake_case (ex.: `g_web_socket`, `g_battery_pct`).
- **Nomes de Funções:** PascalCase (ex.: `DrawStandbyClockWeather()`, `ExecuteHttpOtaUpdate()`).
- **Nomes de Variáveis Locais e Parâmetros:** snake_case (ex.: `start_time`, `candidate_name`).

#### Geometria Circular Obrigatória no Display GC9A01:
Para desenhar elementos na tela circular de $240 \times 240$, sempre verifique se a largura do elemento respeita a largura cordal na altura $y$:
```cpp
int cord_width = 2 * (int)sqrt(120 * 120 - (y - 120) * (y - 120));
```
Para centralização vertical de textos em cartões, utilize `textdatum_t::middle_center` ou `textdatum_t::middle_right` para evitar desalinhamento visual ou colisão com bordas superiores.

### 3.2 Desenvolvimento em Python

- **PEP 8:** Obrigatório. Nomes de funções e variáveis em `snake_case`, classes em `PascalCase`, constantes em `UPPER_SNAKE_CASE`.
- **Tipagem Estática:** Utilize anotações de tipo (`typing`, `Union`, `Optional`) em todas as funções públicas.
- **Tratamento Assíncrono:** Utilize `async`/`await` de maneira idiomática com timeouts explícitos em chamadas de rede:
  ```python
  async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5.0)) as session:
      async with session.get(url) as response:
          data = await response.json()
  ```

---

## 4. Como Adicionar um Novo Modo de Tela à Esfera

Para introduzir um novo modo de exibição na Esfera física:

1. **Atualize o Enum `DisplayMode`:**
   Em `firmware_jarvis_custom/src/main.cpp`:
   ```cpp
   enum class DisplayMode {
     kStandby,
     kHappy,
     kSpotify,
     kTelemetry,
     kElection,
     kNovoModo, // Seu novo modo
     kSad,
     kAngry,
     kCard
   };
   ```
2. **Implemente a Função de Renderização:**
   ```cpp
   void DrawNovoModoScreen() {
     g_canvas.fillScreen(TFT_BLACK);
     // Renderize os elementos gráficos respeitando os limites cordais
     g_canvas.pushSprite(0, 0);
   }
   ```
3. **Adicione ao Ciclo de Telas:**
   No loop principal ou na rotina de alternância de toque, adicione o tratamento do novo estado.
4. **Vincule a Eventos WebSocket:**
   Em `WebSocketEvent()`, trate mensagens com evento específico (ex.: `jarvis.novo_modo`) para alternar para a tela instantaneamente:
   ```cpp
   if (event == "jarvis.novo_modo") {
     SetDisplayMode(DisplayMode::kNovoModo);
   }
   ```

---

## 5. Gerenciamento e Ciclo de Vida de Processos

No nó Windows, execute apenas uma instância de cada serviço essencial. Antes de iniciar testes locais, execute:
```powershell
python -c "import psutil; [p.terminate() for p in psutil.process_iter(['name', 'cmdline']) if 'python' in p.info['name'] and any('server.py' in arg for arg in p.info.get('cmdline') or [])]"
```
Isso garante que portas não fiquem bloqueadas (`Address already in use`) e evita concorrência indesejada.
