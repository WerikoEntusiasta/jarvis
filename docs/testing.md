# Guia de Testes, Validação e Diagnóstico J.A.R.V.I.S.

> Protocolos de Verificação, Testes Automatizados e Diagnóstico de Hardware/Software

---

## 1. Filosofia de Testes

De acordo com o **Padrão de Engenharia de Software Sênior**:
- Nunca assuma que uma alteração funciona apenas porque compila sem erros.
- Toda modificação em firmware, backend ou interface deve ser validada por meio de testes práticos com comandos reais e inspeção de logs de execução.
- Erros de rede, timeouts e desconexões devem ser testados simulando cenários adversos.

---

## 2. Testes de Hardware & Firmware ESP32-S3

### 2.1 Monitoramento de Serial via USB (COM3)

Para verificar o ciclo de boot, reconexão Wi-Fi, handshake WebSocket e status de bateria:

```powershell
# Usando PlatformIO CLI
pio device monitor -p COM3 -b 115200

# Ou via script Python dedicado com auto-reconexão
python scratch/read_com3_logs.py
```

**Padrão de Saída Esperado (Boot Saudável):**
```text
[WiFi] Conectando a Jarvis...
[WiFi] Conectado! IP: 192.168.10.16 RSSI: -31 dBm
[WebSocket] Conectado ao servidor 45.167.187.80:8095/ws
[Battery] Vbat: 3.88V (64%) | Carregando: SIM
[Display] Modo alterado para: Standby
```

### 2.2 Teste de Conexão WebSocket e Fallback Wi-Fi

1. **Simulação de Queda de Rede Primária:** Desligue o ponto de acesso `Jarvis`.
2. **Comportamento Esperado:** O firmware detecta desconexão em até 5 segundos, comuta as credenciais para `WEGI_2G` e estabelece nova conexão sem reiniciar o microcontrolador.
3. **Reconexão WebSocket:** Após restauração do IP, o cliente C++ restabelece a conexão com o ZimaOS na porta 8095.

---

## 3. Testes dos Serviços de Backend (ZimaOS & Windows)

### 3.1 Verificação de Endpoints HTTP e WebSocket

Verifique a saúde dos endpoints centrais utilizando `curl` ou PowerShell:

```powershell
# 1. Healthcheck do ZimaOS Screen Router
curl -i http://45.167.187.80:8095/healthz

# 2. Verificação do Binário de Firmware OTA
curl -I http://45.167.187.80:8095/firmware.bin

# 3. Status do Servidor Local Windows
curl -i http://127.0.0.1:8085/api/status
```

### 3.2 Diagnóstico Integrado dos Containers Docker

Para inspecionar remotamente os containers no ZimaOS (`45.167.187.80`, porta SSH 28222):

```powershell
python scripts/diagnose_status.py
```

O script verifica:
- Container `jarvis-screen-router`: Escuta ativa na porta 8095 e logs sem exceções não tratadas.
- Container `jarvis-hud`: Status da interface web e integridade do storage.
- Consumo de CPU e memória RAM no host Debian/ZimaOS.

---

## 4. Testes da Pipeline de Voz e Áudio Dual

### 4.1 Teste de Sensibilidade do Microfone e Detecção de Wake Word

1. Aproxime-se da Esfera física e pronuncie de forma clara: *"Hey Jarvis"*.
2. **Validações:**
   - O display da Esfera deve imediatamente clarear para 100% de brilho e exibir o rosto robótico ciano (`DisplayMode::kHappy`).
   - O log do roteador em ZimaOS deve registrar: `[VOICE] Wake word detectada via áudio PCM da Esfera`.
   - Nenhuma janela indesejada (ex.: Dynamic Island) deve se abrir no monitor do Windows PC.

### 4.2 Teste de Áudio Dual Simultâneo

1. Envie um comando de teste pelo servidor local:
   ```powershell
   curl -X POST http://127.0.0.1:8085/api/chat -H "Content-Type: application/json" -d '{"message": "Status do sistema"}'
   ```
2. **Validações:**
   - O áudio sintetizado deve soar no alto-falante físico da Esfera (via streaming binário WebSocket).
   - O áudio idêntico deve soar nos alto-falantes principais do Windows PC sem atrasos perceptíveis.

---

## 5. Testes da Tela de Apuração Oficial TSE 2026

Para validar a renderização e atualização contínua da tela eleitoral:

1. **Disparo Manual de Atualização de Tela:**
   ```powershell
   python scripts/send_windows_stats_to_sphere.py
   ```
2. **Critérios de Aceite Visual na Esfera:**
   - Todos os números de votos e percentuais em branco puro (`TFT_WHITE`).
   - Centralização perfeita dos percentuais nos cartões (`middle_right` em $y = kCardY + 26$).
   - Nomes simplificados: `LULA` e `FLAVIO` (sem números de urna e sem sobrenomes extensos).
   - Ausência do termo redundante "votos".
   - Percentual total apurado posicionado na parte inferior com data e hora oficiais do TSE.
   - A tela permanece fixa e só retorna para Standby caso o usuário toque na tela física.

---

## 6. Checklist de Resolução de Problemas (Troubleshooting)

| Sintoma | Causa Mais Provável | Ação de Correção |
|---|---|---|
| Esfera não conecta ao Wi-Fi | Senha incorreta ou SSID inacessível | Verifique `include/jarvis_sphere_secrets.h` e recompile com `pio run -e custom_jarvis_esp32s3`. |
| Erro de SSH com ZimaOS | Porta SSH incorreta | Lembre-se de especificar a porta `28222` (`ssh -p 28222 root@45.167.187.80`). |
| Tela LCD preta ou sem luz de fundo | Nível de brilho zerado ou falha de SPI | Verifique se a chamada `SetBacklight(100)` é executada no `setup()`. |
| Port 8085 já em uso no Windows | Processo Python zumbi em background | Execute o comando de encerramento de processos órfãos via `psutil`. |
