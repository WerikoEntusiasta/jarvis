import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(os.environ.get('ZIMA_IP', '127.0.0.1'), username='root', password=os.environ.get('ZIMA_PASS'), timeout=15)  # exporte ZIMA_PASS antes de usar

print("=== 1. STATUS DO CONTAINER NO ZIMAOS ===")
_, stdout, _ = ssh.exec_command('docker ps --filter name=jarvis-hud --format "{{.Names}} | {{.Status}} | {{.Ports}}"')
print(stdout.read().decode())

print("=== 2. ARQUIVOS PERSISTENTES NO ZIMAOS (/DATA/AppData/jarvis-hud/auth/) ===")
_, stdout, _ = ssh.exec_command('ls -lh /DATA/AppData/jarvis-hud/auth/')
print(stdout.read().decode())

print("=== 3. CONSULTA NO BANCO DE DADOS SQLITE DENTRO DO CONTAINER ===")
cmd_sql = "docker exec jarvis-hud python -c \"import sqlite3; conn = sqlite3.connect('auth/biometrics.db'); cur = conn.cursor(); cur.execute('SELECT id, name, role, registered_at, active FROM operators'); print('Operadores cadastrados no SQLite:', cur.fetchall()); conn.close()\""
_, stdout, _ = ssh.exec_command(cmd_sql)
print(stdout.read().decode())

print("=== 4. TESTE DOS ENDPOINTS HTTP PUBLICADOS NO ZIMAOS (PORTAS 8085 E 8086) ===")
_, stdout, _ = ssh.exec_command('curl -s http://localhost:8085/api/auth/face/status')
print("HUD Principal (Porta 8085 -> 8080):", stdout.read().decode())

_, stdout, _ = ssh.exec_command('curl -s http://localhost:8086/api/enroll/status')
print("Portal de Cadastro (Porta 8086 -> 8082):", stdout.read().decode())

ssh.close()
