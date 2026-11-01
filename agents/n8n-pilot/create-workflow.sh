#!/bin/bash

# Lê o código do workflow
WORKFLOW_CODE=$(cat waha-extractor-workflow.js)

# Cria o payload JSON
cat > payload.json << PAYLOAD
{
  "workflowCode": $(echo "$WORKFLOW_CODE" | jq -Rs .),
  "description": "Extrai mensagens do WhatsApp via WWebJS e salva em arquivos Markdown diários organizados por data"
}
PAYLOAD

# Envia para o MCP server do n8n
curl -X POST http://192.168.3.6:5678/mcp-server/http \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $N8N_MCP_TPKEN" \
  -d @payload.json

