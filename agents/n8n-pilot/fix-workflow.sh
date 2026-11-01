#!/bin/bash

# Payload para update_workflow: substituir o nó "Append to Daily Log" por um Code node
# que faz fs.appendFileSync corretamente

cat > mcp-fix.json << 'EOF'
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "update_workflow",
    "arguments": {
      "workflowId": "7ErNDW6zKpwZfU2e",
      "operations": [
        {
          "op": "setNodeParameters",
          "nodeName": "Append to Daily Log",
          "parameters": {
            "jsCode": "const fs = require('fs');\nconst item = $input.item.json;\nconst filePath = '/home/node/.openclaw/workspace-acessor/whatsapp-logs/' + item.dateStr + '.md';\n\nfs.appendFileSync(filePath, item.markdown, 'utf8');\n\nreturn { success: true, file: filePath };"
          }
        },
        {
          "op": "setNodeType",
          "nodeName": "Append to Daily Log",
          "nodeType": "n8n-nodes-base.code",
          "typeVersion": 2
        }
      ]
    }
  }
}
EOF

curl -s 'http://192.168.3.6:5678/mcp-server/http' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -H "Authorization: Bearer ***" \
  --data @mcp-fix.json

