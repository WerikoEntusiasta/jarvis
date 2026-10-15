import paramiko
import sys
import json

sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(os.environ.get("ZIMA_IP", "127.0.0.1"), username="root", password=os.environ.get('ZIMA_PASS'), timeout=10)

commands = [
    "curl -s http://localhost:20128/v1/models",
    "docker inspect 9router --format '{{json .Config.Env}}'",
    "docker exec 9router env 2>/dev/null | cut -d= -f1",
    "docker exec 9router ls -la /app 2>/dev/null || docker exec 9router ls -la / 2>/dev/null"
]

for cmd in commands:
    print(f"\n=== CMD: {cmd} ===")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=8)
    res = stdout.read().decode('utf-8', errors='ignore').strip()
    try:
        data = json.loads(res)
        print(json.dumps(data, indent=2))
    except Exception:
        print(res[:1500])

ssh.close()
