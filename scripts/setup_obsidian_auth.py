import paramiko
import sys
import re

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("45.167.187.80", 28222, "root", "We12wi25k#3912*", timeout=10)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode('utf-8', errors='replace').strip()
    err = stderr.read().decode('utf-8', errors='replace').strip()
    return out if out else err

compose_path = "/var/lib/casaos/apps/linuxserver-obsidian/docker-compose.yml"
print("[+] Lendo docker-compose.yml...")
content = run(f"cat {compose_path}")

# Atualiza environment
old_env = '    environment:\n      PGID: ""\n      PUID: ""\n      TZ: ""'

new_env = '    environment:\n      CUSTOM_USER: "werik"\n      PASSWORD: "We12wi25k#3912*"\n      PGID: "1000"\n      PUID: "1000"\n      TZ: "America/Sao_Paulo"'

if old_env in content:
    content = content.replace(old_env, new_env)
else:
    content = re.sub(r'environment:\s*\n(?:\s+[A-Za-z0-9_]+:[^\n]*\n)+', new_env + '\n', content)

# Remove a porta duplicada 8080 se presente
old_ports = '    ports:\n      - target: 3000\n        published: "3000"\n        protocol: tcp\n      - target: 3000\n        published: "8080"\n        protocol: tcp\n      - target: 3001\n        published: "3001"\n        protocol: tcp'

new_ports = '    ports:\n      - target: 3000\n        published: "3000"\n        protocol: tcp\n      - target: 3001\n        published: "3001"\n        protocol: tcp'

if old_ports in content:
    content = content.replace(old_ports, new_ports)

# Salva arquivo atualizado
sftp = ssh.open_sftp()
with sftp.file(compose_path, 'w') as f:
    f.write(content)
sftp.close()
print("[OK] docker-compose.yml atualizado com CUSTOM_USER e PASSWORD!")

# Limpa regras de DROP no iptables para as portas legítimas
print("[+] Ajustando iptables...")
run("iptables -D INPUT -p tcp --dport 3000 -j DROP 2>/dev/null || true")
run("iptables -D INPUT -p tcp --dport 3001 -j DROP 2>/dev/null || true")
run("iptables -D INPUT -p tcp --dport 8080 -j DROP 2>/dev/null || true")

# Recria o container via docker compose
print("[+] Recriando container Obsidian com autenticação...")
run("cd /var/lib/casaos/apps/linuxserver-obsidian && docker compose down && docker compose up -d")

# Testa autenticacao
print("[+] Testando acesso sem senha:")
sem_auth = run("curl -s -o /dev/null -w '%{http_code}' http://localhost:3000/")
print(f"Status HTTP sem senha: {sem_auth}")

print("[+] Testando acesso com usuario werik e senha:")
com_auth = run("curl -s -o /dev/null -w '%{http_code}' -u werik:'We12wi25k#3912*' http://localhost:3000/")
print(f"Status HTTP com senha: {com_auth}")

ssh.close()
