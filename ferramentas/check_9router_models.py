import paramiko
import sys
import json

sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(os.environ.get("ZIMA_IP", "127.0.0.1"), username="root", password=os.environ.get('ZIMA_PASS'), timeout=10)

cmd = "curl -s -H 'Authorization: Bearer " + os.environ.get("NINEROUTER_API_KEY", "") + "' http://localhost:20128/v1/models"
stdin, stdout, stderr = ssh.exec_command(cmd, timeout=10)
res = stdout.read().decode('utf-8', errors='ignore')

try:
    data = json.loads(res)
    models = [m.get('id') for m in data.get('data', [])]
    print(f"Total models: {len(models)}")
    print("ElevenLabs / Voice models:", [m for m in models if 'eleven' in m.lower() or 'voice' in m.lower() or 'tts' in m.lower()])
    print("All models preview:\n", models[:30])
except Exception as e:
    print("Error parsing / response:", res[:1000])

ssh.close()
