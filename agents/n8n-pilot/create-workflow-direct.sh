#!/bin/bash

# Prepara o código do workflow escapado para JSON
WORKFLOW_CODE='import { workflow, node, trigger, expr } from '"'"'@n8n/workflow-sdk'"'"';

const whatsappTrigger = trigger({
  type: '"'"'n8n-nodes-wwebjs-api.wWebJsApiTrigger'"'"',
  version: 1,
  config: {
    name: '"'"'WhatsApp Messages'"'"',
    parameters: {
      events: ['"'"'message'"'"']
    }
  }
});

const extractMessageData = node({
  type: '"'"'n8n-nodes-base.set'"'"',
  version: 3.5,
  config: {
    name: '"'"'Extract Message Data'"'"',
    parameters: {
      mode: '"'"'manual'"'"',
      duplicateItem: false,
      includeOtherFields: false,
      assignments: {
        assignments: [
          { id: '"'"'timestamp'"'"', name: '"'"'timestamp'"'"', value: expr('"'"'{{ $json.body.timestamp }}'"'"'), type: '"'"'string'"'"' },
          { id: '"'"'datetime'"'"', name: '"'"'datetime'"'"', value: expr('"'"'{{ new Date($json.body.timestamp * 1000).toISOString() }}'"'"'), type: '"'"'string'"'"' },
          { id: '"'"'from'"'"', name: '"'"'from'"'"', value: expr('"'"'{{ $json.body.from }}'"'"'), type: '"'"'string'"'"' },
          { id: '"'"'fromMe'"'"', name: '"'"'fromMe'"'"', value: expr('"'"'{{ $json.body.fromMe }}'"'"'), type: '"'"'boolean'"'"' },
          { id: '"'"'isGroup'"'"', name: '"'"'isGroup'"'"', value: expr('"'"'{{ $json.body.isGroup ?? false }}'"'"'), type: '"'"'boolean'"'"' },
          { id: '"'"'chatName'"'"', name: '"'"'chatName'"'"', value: expr('"'"'{{ $json.body.chat?.name ?? $json.body.contact?.name ?? $json.body.contact?.pushname ?? "Unknown" }}'"'"'), type: '"'"'string'"'"' },
          { id: '"'"'senderName'"'"', name: '"'"'senderName'"'"', value: expr('"'"'{{ $json.body.contact?.name ?? $json.body.contact?.pushname ?? $json.body.from }}'"'"'), type: '"'"'string'"'"' },
          { id: '"'"'messageBody'"'"', name: '"'"'messageBody'"'"', value: expr('"'"'{{ $json.body.body ?? "" }}'"'"'), type: '"'"'string'"'"' },
          { id: '"'"'messageType'"'"', name: '"'"'messageType'"'"', value: expr('"'"'{{ $json.body.isGroup ? "group" : "private" }}'"'"'), type: '"'"'string'"'"' }
        ]
      }
    }
  }
});

const formatMarkdown = node({
  type: '"'"'n8n-nodes-base.code'"'"',
  version: 2,
  config: {
    name: '"'"'Format Markdown'"'"',
    parameters: {
      language: '"'"'javaScript'"'"',
      jsCode: '"'"'const item = $input.item.json; const date = new Date(item.timestamp * 1000); const dateStr = date.toISOString().split(\"T\")[0]; const timeStr = date.toTimeString().split(\" \")[0]; let markdown = '"'"''"'"''"'"'; if (item.isGroup) { markdown = \"### Grupo: \" + item.chatName + \"\\n\" + \"**Enviado por:** \" + item.senderName + \"\\n\" + \"**Data/Hora:** \" + dateStr + \" \" + timeStr + \"\\n\" + \"**Número:** \" + item.from + \"\\n\\n\" + \"> \" + item.messageBody + \"\\n\\n\" + \"---\\n\\n\"; } else { markdown = \"### Mensagem Privada\\n\" + \"**De:** \" + item.senderName + \"\\n\" + \"**Data/Hora:** \" + dateStr + \" \" + timeStr + \"\\n\" + \"**Número:** \" + item.from + \"\\n\" + \"**Enviado por mim:** \" + (item.fromMe ? \"Sim\" : \"Não\") + \"\\n\\n\" + \"> \" + item.messageBody + \"\\n\\n\" + \"---\\n\\n\"; } return { markdown, dateStr, messageType: item.messageType, chatName: item.chatName };'"'"'
    }
  }
});

const ensureDailyFile = node({
  type: '"'"'n8n-nodes-base.code'"'"',
  version: 2,
  config: {
    name: '"'"'Ensure Daily File'"'"',
    parameters: {
      language: '"'"'javaScript'"'"',
      jsCode: '"'"'const fs = require(\"fs\"); const path = require(\"path\"); const item = $input.item.json; const logDir = \"/home/node/.openclaw/workspace-acessor/whatsapp-logs\"; const filePath = path.join(logDir, item.dateStr + \".md\"); if (!fs.existsSync(logDir)) { fs.mkdirSync(logDir, { recursive: true }); } if (!fs.existsSync(filePath)) { const header = \"# WhatsApp Messages - \" + item.dateStr + \"\\n\\n\" + \"Registro automático de mensagens extraídas do WhatsApp.\\n\\n\" + \"---\\n\\n\"; fs.writeFileSync(filePath, header, \"utf8\"); } return item;'"'"'
    }
  }
});

const appendToFile = node({
  type: '"'"'n8n-nodes-base.readWriteFile'"'"',
  version: 1.1,
  config: {
    name: '"'"'Append to Daily Log'"'"',
    parameters: {
      operation: '"'"'append'"'"',
      fileName: expr('"'"'{{ "/home/node/.openclaw/workspace-acessor/whatsapp-logs/" + $json.dateStr + ".md" }}'"'"'),
      dataPropertyName: '"'"'markdown'"'"'
    }
  }
});

export default workflow('"'"'waha-message-extractor'"'"', '"'"'WAHA Message Extractor'"'"')
  .add(whatsappTrigger)
  .to(extractMessageData)
  .to(formatMarkdown)
  .to(ensureDailyFile)
  .to(appendToFile);'

echo "Código do workflow preparado. Tentando criar via n8n CLI..."
echo "$WORKFLOW_CODE" > /tmp/waha-workflow-temp.js
cat /tmp/waha-workflow-temp.js

