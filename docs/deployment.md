# Guia de Implantação e Deploy J.A.R.V.I.S.

> Procedimentos de Publicação em Produção, Atualização Over-The-Air (OTA) e Gestão de Infraestrutura

---

## 1. Visão Geral do Ciclo de Implantação

O ecossistema J.A.R.V.I.S. possui três fluxos de implantação independentes:

1. **Deploy de Firmware ESP32-S3:** Gravação física via USB (`COM3`) ou sem fio via OTA HTTP.
2. **Deploy do Núcleo ZimaOS Docker:** Atualização de contêineres e sincronização de binários em `45.167.187.80`.
3. **Deploy da Estação de Trabalho Windows:** Inicialização de serviços locais e interface de telemetria.

---

## 2. Implantação do Firmware da Esfera ESP32-S3

### 2.1 Método A: Gravação Física via USB (Porta COM3)

Utilize este método quando a Esfera estiver conectada via cabo USB-C ao PC Windows:

```powershell
# 1. Acesse o diretório do firmware
cd c:\JARVIS\firmware_jarvis_custom

# 2. Compile e grave diretamente na porta serial COM3
pio run -e custom_jarvis_esp32s3 --target upload --upload-port COM3

# 3. Abra o monitor serial para acompanhar a inicialização
pio device monitor -p COM3 -b 115200
```

> [!NOTE]
> A gravação via USB opera a `460800 baud` com auto-reset DTR/RTS nativo do ESP32-S3.

### 2.2 Método B: Atualização Sem Fio Over-The-Air (OTA)

Para atualizar a Esfera sem tirá-la da sua base ou conectar cabos:

1. **Compile o Binário de Produção:**
   ```powershell
   cd c:\JARVIS\firmware_jarvis_custom
   pio run -e custom_jarvis_esp32s3
   ```
   O arquivo de saída gerado será:
   `c:\JARVIS\firmware_jarvis_custom\.pio\build\custom_jarvis_esp32s3\firmware.bin`

2. **Sincronize o Binário com o Servidor ZimaOS:**
   Execute o script de sincronização automatizada (via SFTP / SSH porta 28222):
   ```powershell
   python c:\JARVIS\scripts\sync_firmware_zimaos.py
   ```
   O binário será alocado em `/DATA/AppData/jarvis-screen-router/firmware.bin`.

3. **Dispare o Trigger OTA:**
   Envie uma requisição HTTP POST para o roteador central:
   ```bash
   curl -X POST http://45.167.187.80:8095/api/jarvis/ota/trigger
   ```

4. **Comportamento Durante o Processo:**
   - A Esfera interrompe o loop padrão de áudio e exibe no display circular: `ATUALIZANDO VIA WI-FI... [Progresso %]`.
   - Ao atingir 100%, o microcontrolador realiza auto-reset e restabelece a conexão na versão recém-instalada.

---

## 3. Implantação no Núcleo ZimaOS Docker (`45.167.187.80`)

O servidor ZimaOS hospeda os containers centrais em `/DATA/AppData/`.

### 3.1 Acesso e Credenciais

- **Host:** `45.167.187.80`
- **Porta SSH:** `28222` (Porta não-padrão)
- **Usuário:** `root`

### 3.2 Atualização do Container `jarvis-screen-router`

Para aplicar atualizações no serviço de roteamento de voz e tela:

1. Copie o script atualizado para o servidor:
   ```powershell
   scp -P 28222 c:\JARVIS\scripts\jarvis_screen_router.py root@45.167.187.80:/DATA/AppData/jarvis-screen-router/jarvis_screen_router.py
   ```
2. Reinicie o contêiner Docker:
   ```bash
   ssh -p 28222 root@45.167.187.80 "docker restart jarvis-screen-router"
   ```
3. Acompanhe os logs de inicialização para garantir integridade:
   ```bash
   ssh -p 28222 root@45.167.187.80 "docker logs -f --tail 50 jarvis-screen-router"
   ```

---

## 4. Implantação na Estação de Trabalho Windows

### 4.1 Inicialização dos Serviços

No PC do Senhor Werik, os serviços locais garantem suporte a Face ID, áudio dual e telemetria:

```powershell
# Execução do Servidor Principal
python c:\JARVIS\server.py
```

### 4.2 Configuração de Autoinicialização (Opcional)

Para que os serviços iniciem automaticamente no login do Windows:
- Um atalho para o inicializador pode ser criado em:
  `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`
- O mecanismo de Single Instance Mutex garante que reinicializações ou cliques acidentais não gerem duplicidade de processos.

---

## 5. Procedimento de Rollback de Emergência

Caso um novo firmware ou serviço apresente instabilidade:

1. **Firmware ESP32-S3:**
   - O microcontrolador preserva partição de boot segura. Para reverter para uma versão anterior conhecida, conecte via cabo USB e execute a gravação do binário anterior estável arquivado em `spotpear_official_release/`.
2. **Backend ZimaOS:**
   - As versões anteriores dos scripts de roteamento são arquivadas com sufixo `.bak` antes de qualquer substituição em `/DATA/AppData/jarvis-screen-router/`.
   - Para reverter:
     ```bash
     ssh -p 28222 root@45.167.187.80 "cp /DATA/AppData/jarvis-screen-router/jarvis_screen_router.py.bak /DATA/AppData/jarvis-screen-router/jarvis_screen_router.py && docker restart jarvis-screen-router"
     ```
