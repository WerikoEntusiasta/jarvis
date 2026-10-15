import paramiko
import json

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(os.environ.get('ZIMA_IP', '127.0.0.1'), username='root', password=os.environ.get('ZIMA_PASS'))  # exporte ZIMA_PASS antes de usar

cmd = 'docker exec openclaw openclaw agent --agent jarvis --message "Jarvis, responda apenas: estou operando perfeitamente." --json'
stdin, stdout, stderr = ssh.exec_command(cmd)
raw = stdout.read().decode('utf-8', errors='ignore')
ssh.close()

idx = raw.find('{')
data = json.loads(raw[idx:])
print("KEYS in data:", list(data.keys()))
if "result" in data:
    print("KEYS in result:", list(data["result"].keys()))
    print("finalAssistantVisibleText:", data["result"].get("finalAssistantVisibleText"))
    payloads = data["result"].get("payloads", [])
    if payloads:
        print("KEYS in payload[0]:", list(payloads[0].keys()))
        print("payload[0] text:", payloads[0].get("text"))
