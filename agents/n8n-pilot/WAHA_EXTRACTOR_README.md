# WAHA Message Extractor - Workflow de Extração de Mensagens WhatsApp

## Visão Geral

Workflow que captura todas as mensagens recebidas pelo WhatsApp (via WWebJS API) e as organiza em arquivos Markdown diários no workspace do agente acessor.

## Estrutura do Workflow

```
WhatsApp Messages (Trigger)
    ↓
Extract Message Data (Set)
    ↓
Format Markdown (Code)
    ↓
Ensure Daily File (Code)
    ↓
Append to Daily Log (ReadWriteFile)
```

## Componentes

### 1. WhatsApp Messages (Trigger)
- **Tipo:** `n8n-nodes-wwebjs-api.wWebJsApiTrigger`
- **Função:** Recebe mensagens em tempo real do WhatsApp
- **Configuração:** Escuta evento `message`

### 2. Extract Message Data (Set)
- **Tipo:** `n8n-nodes-base.set`
- **Função:** Normaliza os dados da mensagem recebida
- **Campos extraídos:**
  - `timestamp` - timestamp original
  - `datetime` - ISO 8601 formatado
  - `from` - número do remetente
  - `fromMe` - boolean se foi enviada por você
  - `isGroup` - boolean se é mensagem de grupo
  - `chatName` - nome do chat/contato
  - `senderName` - nome de quem enviou
  - `messageBody` - conteúdo da mensagem
  - `messageType` - "group" ou "private"

### 3. Format Markdown (Code)
- **Tipo:** `n8n-nodes-base.code`
- **Função:** Formata a mensagem em Markdown
- **Formato para mensagens privadas:**
  ```markdown
  ### Mensagem Privada
  **De:** Nome do Contato
  **Data/Hora:** 2026-09-18 14:30:45
  **Número:** 5511999999999@c.us
  **Enviado por mim:** Não
  
  > Conteúdo da mensagem
  
  ---
  ```

- **Formato para mensagens de grupo:**
  ```markdown
  ### Grupo: Nome do Grupo
  **Enviado por:** Nome do Remetente
  **Data/Hora:** 2026-09-18 14:30:45
  **Número:** 5511999999999@c.us
  
  > Conteúdo da mensagem
  
  ---
  ```

### 4. Ensure Daily File (Code)
- **Tipo:** `n8n-nodes-base.code`
- **Função:** Garante que o diretório e arquivo diário existem
- **Ações:**
  - Cria `/home/node/.openclaw/workspace-acessor/whatsapp-logs/` se não existir
  - Cria arquivo `YYYY-MM-DD.md` com cabeçalho se não existir

### 5. Append to Daily Log (ReadWriteFile)
- **Tipo:** `n8n-nodes-base.readWriteFile`
- **Função:** Adiciona a mensagem formatada ao arquivo do dia
- **Operação:** append (adiciona ao final do arquivo)

## Estrutura de Arquivos Gerados

```
/home/node/.openclaw/workspace-acessor/whatsapp-logs/
├── 2026-09-18.md
├── 2026-09-19.md
└── 2026-09-20.md
```

Cada arquivo contém todas as mensagens daquele dia, organizadas cronologicamente.

## Próximos Passos

1. **Criar o workflow na instância n8n**
2. **Configurar credenciais WWebJS** (se necessário)
3. **Ativar o workflow**
4. **Testar com uma mensagem real**

## Requisitos

- Instância n8n com o plugin **WWebJS API** instalado
- Conexão WhatsApp ativa via WWebJS
- Permissões de escrita em `/home/node/.openclaw/workspace-acessor/whatsapp-logs/`

## Observações

- As mensagens são salvas em tempo real conforme chegam
- Um arquivo novo é criado automaticamente a cada dia
- O formato Markdown facilita a leitura e busca posterior
- Mensagens de grupo identificam claramente o grupo e o remetente individual
