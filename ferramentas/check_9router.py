import json
import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(os.environ.get('ZIMA_IP', '127.0.0.1'), 22, 'root', os.environ.get("ZIMA_PASS"), timeout=8)
_, o, _ = ssh.exec_command('docker inspect 9router --format "{{json .Config.Env}}"')
print('9router env:', o.read().decode('utf-8'))
ssh.close()
