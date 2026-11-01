# 📱 Guia: Como Enviar Notificações do WhatsApp para a Esfera J.A.R.V.I.S.

Este documento explica como enviar notificações de novas mensagens do WhatsApp (recebidas via n8n, Evolution API, Baileys ou Z-API) diretamente para a tela circular da esfera ESP32-S3 do J.A.R.V.I.S.

---

## 1. Como Funciona na Esfera
Quando uma mensagem chega:
1. **Alerta Sonoro:** A esfera emite imediatamente o som de alerta (*Wake Beep*).
2. **Brilho Máximo:** O visor salta para 100% de brilho.
3. **Card Visual WhatsApp:** Renderiza um card estilizado verde e escuro contendo:
   - Título oficial `WHATSAPP` no topo.
   - Nome ou número do **Remetente** em verde neon.
   - Texto da mensagem formatado em até 3 linhas com quebra automática de palavras.
   - Horário de recebimento da mensagem.
   - Botão interativo de toque `[ DISPENSAR ]`.
4. **Dispensar Notificação:** Basta dar um toque rápido no visor para fechar o card e voltar ao relógio de Standby.

---

## 2. Endpoint HTTP REST no Servidor ZimaOS

- **URL:** `http://45.167.187.80:8095/api/jarvis/whatsapp`
- **Método:** `POST`
- **Content-Type:** `application/json`

### Payload JSON:
```json
{
  "device_id": "jarvis_sphere_esp32s3",
  "sender": "Nome do Contato ou Grupo",
  "message": "Texto da mensagem recebida no WhatsApp",
  "time": "14:35"
}
```

> **Nota:** Se omitir `device_id`, a notificação é transmitida para todas as esferas conectadas. Se omitir `time`, será exibido o horário atual.

---

## 3. Como Configurar no n8n (Passo a Passo)

No seu fluxo do n8n (que recebe o webhook do WhatsApp):

1. **Adicione um nó `HTTP Request`** logo após o nó que recebe a mensagem do WhatsApp.
2. Configure o nó com os seguintes parâmetros:
   - **Method:** `POST`
   - **URL:** `http://45.167.187.80:8095/api/jarvis/whatsapp`
   - **Send Headers:** Ativado
     - **Name:** `Content-Type`
     - **Value:** `application/json`
   - **Send Body:** Ativado
   - **Body Content Type:** `JSON`
   - **Specify Body:** `Using JSON`
   - **JSON / Code:**
```json
{
  "device_id": "jarvis_sphere_esp32s3",
  "sender": "={{ $json.senderName || $json.pushName || $json.remoteJid }}",
  "message": "={{ $json.messageText || $json.conversation || $json.text }}",
  "time": "={{ $now.setZone('America/Sao_Paulo').toFormat('HH:mm') }}"
}
```

3. Clique em **Test step** e veja a mensagem aparecer instantaneamente na esfera!

---

## 4. Exemplos de Envio em Outras Linguagens

### cURL (Linux / macOS / PowerShell)
```bash
curl -X POST http://45.167.187.80:8095/api/jarvis/whatsapp \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "jarvis_sphere_esp32s3",
    "sender": "Dra. Ana Paula",
    "message": "Reunião confirmada para às 15h, doutor.",
    "time": "14:40"
  }'
```

### Python
```python
import requests

payload = {
    "device_id": "jarvis_sphere_esp32s3",
    "sender": "Werik Santos",
    "message": "Servidor atualizado e todos os containers rodando 100%.",
    "time": "07:25"
}

resp = requests.post("http://45.167.187.80:8095/api/jarvis/whatsapp", json=payload, timeout=5)
print(resp.json())
```

### JavaScript / Node.js
```javascript
const response = await fetch("http://45.167.187.80:8095/api/jarvis/whatsapp", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    device_id: "jarvis_sphere_esp32s3",
    sender: "Financeiro",
    message: "Pagamento aprovado com sucesso!",
    time: "11:20"
  })
});
const data = await response.json();
console.log(data);
```

---

## 5. Resposta da API
Quando a notificação é entregue com sucesso:
```json
{
  "status": "success",
  "sent_to": 1,
  "sender": "Dra. Ana Paula",
  "message": "Reunião confirmada para às 15h, doutor.",
  "time": "14:40"
}
```
Se a esfera estiver temporariamente desconectada do Wi-Fi:
```json
{
  "status": "error",
  "message": "Dispositivo sem sessão WS ativa"
}
```
