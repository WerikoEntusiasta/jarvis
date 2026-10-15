import paramiko
import sys

sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(os.environ.get("ZIMA_IP", "127.0.0.1"), username="root", password=os.environ.get('ZIMA_PASS'), timeout=10)

cmd = "docker exec 9router sqlite3 /app/data/db/data.sqlite \".tables\""
stdin, stdout, stderr = ssh.exec_command(cmd, timeout=8)
print("TABLES:", stdout.read().decode('utf-8', errors='ignore').strip())

cmd2 = "docker exec 9router sqlite3 /app/data/db/data.sqlite \"SELECT * FROM providers;\" 2>/dev/null || docker exec 9router sqlite3 /app/data/db/data.sqlite \"SELECT tbl_name FROM sqlite_master WHERE type='table';\""
stdin, stdout, stderr = ssh.exec_command(cmd2, timeout=8)
print("TABLES/PROVIDERS:\n", stdout.read().decode('utf-8', errors='ignore').strip())

ssh.close()
