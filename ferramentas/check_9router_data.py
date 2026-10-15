import paramiko
import sys
import json

sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(os.environ.get("ZIMA_IP", "127.0.0.1"), username="root", password=os.environ.get('ZIMA_PASS'), timeout=10)

commands = [
    "docker exec 9router ls -la /app/data",
    "docker exec 9router cat /app/data/settings.json 2>/dev/null",
    "docker exec 9router cat /app/data/config.json 2>/dev/null",
    "docker exec 9router find /app/data -type f"
]

for cmd in commands:
    print(f"\n=== CMD: {cmd} ===")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=8)
    res = stdout.read().decode('utf-8', errors='ignore').strip()
    print(res[:1500])

ssh.close()
