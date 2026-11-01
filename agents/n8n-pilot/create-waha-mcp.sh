#!/bin/bash

# Lê o código do workflow
WORKFLOW_CODE=$(cat waha-extractor-workflow.js)

# Cria o payload JSON para o MCP
cat > mcp-create-workflow.json << EOF
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "create_workflow_from_code",
    "arguments": {
      "code": $(echo "$WORKFLOW_CODE" | node -e "const fs = require('fs'); const data = fs.readFileSync(0, 'utf-8'); process.stdout.write(JSON.stringify(data));"),
      "description": "Extrai mensagens do WhatsApp via WWebJS e salva em arquivos Markdown diários organizados por data"
    }
  }
}
EOF

# Envia via MCP
curl -s 'http://192.168.3.6:5678/mcp-server/http' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -H "Authorization: Bearer $N8N_MCP_TPKEN" \
  --data @mcp-create-workflow.json

