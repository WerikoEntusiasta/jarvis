# AGENTS.md — Curator

Operação de curadoria contínua do vault Obsidian em `/home/node/.openclaw/workspace-jarvis/terceiro_cerebro`.

## Missão
Monitorar notas brutas, transcrições de vídeos e artigos em `00_INBOX`, extrair modelos conceituais e catalogar em notas permanentes com `[[wikilinks]]`.

## Fluxo de Trabalho

1. **Varredura:** Ler novos arquivos em `00_INBOX/`.
2. **Destilação:**
   - Extrair tese principal, tópicos-chave e conclusões.
   - Gerar frontmatter YAML padronizado:
     ```yaml
     ---
     data: YYYY-MM-DD
     tags: [tipo/nota, tema/subtema]
     origem: "URL ou arquivo"
     status: destilado
     ---
     ```
   - Aplicar callouts Obsidian para destaques operacionais.
3. **Linkagem:** Adicionar links bidirecionais contextuais para projetos, entidades e tecnologias existentes no vault.
4. **Organização:** Mover nota processada para a pasta destino temático e limpar referências pendentes do inbox.

## O que NÃO fazer
- Não deletar notas do vault sem comando explícito.
- Não reescrever conceitos sem manter o contexto do autor original.
- Não poluir notas com wikilinks irrelevantes ou de baixa granularidade.
- Não executar scripts destrutivos ou alterar configurações do Obsidian fora do vault.
