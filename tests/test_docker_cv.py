import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(os.environ.get('ZIMA_IP', '127.0.0.1'), 22, 'root', os.environ.get("ZIMA_PASS"), timeout=10)
stdin, stdout, stderr = ssh.exec_command("docker exec jarvis-hud python -c 'import cv2; import mediapipe; print(\"OK\")'")
out = stdout.read().decode('utf-8', errors='ignore')
err = stderr.read().decode('utf-8', errors='ignore')
print("STDOUT:", out)
print("STDERR:", err)
ssh.close()
