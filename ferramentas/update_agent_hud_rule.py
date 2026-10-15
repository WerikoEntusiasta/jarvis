import paramiko
import sys

sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(os.environ.get("ZIMA_IP", "127.0.0.1"), username="root", password=os.environ.get('ZIMA_PASS'), timeout=10)

new_section = """

## 🖥️ PAINEL HOLOGRÁFICO WEB JARVIS & FERRAMENTAS MCP (jarvis-hud)
Sempre que você identificar que a mensagem recebida veio do **PAINEL WEB JARVIS** (identificada pela tag [PAINEL WEB HOLOGRAFICO JARVIS] ou consultas do HUD):
* **REGRA OBRIGATORIA DE PROJECAO VISUAL:** Você DEVE SEMPRE ACIONAR as ferramentas do servidor MCP 'jarvis-hud' para projetar a tela ou card correspondente no painel holográfico do usuário ENQUANTO VOCÊ FALA!
  - **Finanças / Bancos:** Invoque a ferramenta MCP para projetar o card financeiro ou abrir tela de finanças com os dados do Banco Inter.
  - **Timers / Cronômetros:** Se o usuário pedir um timer (ex: 5 min, 10 min), invoque obrigatoriamente a ferramenta MCP 'iniciar_timer_hud' com a duração em minutos.
  - **Clima / Temperatura:** Invoque a ferramenta MCP 'abrir_tela_hud' para clima ou 'criar_card_customizado'.
  - **Qualquer outro comando, dúvida, tarefa, resumo ou cálculo:** Invoque OBRIGATORIAMENTE 'criar_card_customizado' com a síntese visual dos dados para projetar na tela holográfica enquanto sintetiza a voz!
* NUNCA responda a uma mensagem vinda do painel web sem acionar uma ferramenta de projeção do MCP 'jarvis-hud'. O usuário deve sempre ver o card correspondente na tela enquanto você fala.
"""

cmd = "docker exec -i openclaw tee -a /home/node/.openclaw/workspace-jarvis/AGENTS.md > /dev/null"
stdin, stdout, stderr = ssh.exec_command(cmd, timeout=10)
stdin.write(new_section)
stdin.flush()
stdin.channel.shutdown_write()

err = stderr.read().decode('utf-8', errors='ignore')
if err:
    print("ERR:", err)
else:
    print("Regra anexada com sucesso em AGENTS.md!")

# Verificar o final do arquivo
stdin, stdout, stderr = ssh.exec_command('docker exec openclaw tail -n 20 /home/node/.openclaw/workspace-jarvis/AGENTS.md', timeout=10)
print("\n=== FINAL DE AGENTS.MD ===")
print(stdout.read().decode('utf-8', errors='ignore').strip())

ssh.close()
