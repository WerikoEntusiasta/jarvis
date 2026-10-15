import paramiko
import json

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(os.environ.get('ZIMA_IP', '127.0.0.1'), username='root', password=os.environ.get('ZIMA_PASS'), timeout=15)  # exporte ZIMA_PASS antes de usar
stdin, stdout, stderr = ssh.exec_command('docker exec openclaw openclaw agent --agent jarvis --message "Jarvis, diga olá." --json')
out = stdout.read().decode('utf-8', errors='ignore')
print("JSON OUT RAW:")
print(out)
ssh.close()
