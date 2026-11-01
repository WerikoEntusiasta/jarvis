import paramiko
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("45.167.187.80", 28222, "root", "We12wi25k#3912*", timeout=10)

stdin, stdout, stderr = ssh.exec_command('head -n 50 /var/lib/casaos/apps/linuxserver-obsidian/docker-compose.yml')
content = stdout.read().decode('utf-8', errors='replace')
print(content)

ssh.close()
