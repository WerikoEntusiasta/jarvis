import paramiko
import sys

sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(os.environ.get("ZIMA_IP", "127.0.0.1"), username="root", password=os.environ.get('ZIMA_PASS'), timeout=10)

commands = [
    "docker exec openclaw ls -la /home/node/.openclaw/agents/jarvis/",
    "docker exec openclaw ls -la /home/node/.openclaw/workspace-jarvis/",
]

for cmd in commands:
    print(f"\n=== CMD: {cmd} ===")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=10)
    print(stdout.read().decode('utf-8', errors='ignore').strip())

ssh.close()
