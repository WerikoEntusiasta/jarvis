import paramiko
import sys
import json

sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(os.environ.get("ZIMA_IP", "127.0.0.1"), username="root", password=os.environ.get('ZIMA_PASS'), timeout=10)

js_code = """
const Database = require('better-sqlite3');
const db = new Database('/app/data/db/data.sqlite');
const accounts = db.prepare('SELECT id, name, provider, apiKey, isDefault, isActive, createdAt FROM accounts').all();
console.log('ACCOUNTS:', JSON.stringify(accounts, null, 2));
"""

stdin, stdout, stderr = ssh.exec_command("docker exec -i 9router node", timeout=10)
stdin.write(js_code)
stdin.flush()
stdin.channel.shutdown_write()

print(stdout.read().decode('utf-8', errors='ignore'))
ssh.close()
