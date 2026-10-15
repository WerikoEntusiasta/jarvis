import paramiko
import sys

sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(os.environ.get("ZIMA_IP", "127.0.0.1"), username="root", password=os.environ.get('ZIMA_PASS'), timeout=10)

files = [
    "/home/node/.openclaw/workspace-jarvis/IDENTITY.md",
    "/home/node/.openclaw/workspace-jarvis/SOUL.md",
    "/home/node/.openclaw/workspace-jarvis/AGENTS.md"
]

for f in files:
    print(f"\n==================== {f} ====================")
    stdin, stdout, stderr = ssh.exec_command(f"docker exec openclaw cat {f}", timeout=10)
    print(stdout.read().decode('utf-8', errors='ignore').strip())

ssh.close()
