import paramiko
import sys

sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(os.environ.get("ZIMA_IP", "127.0.0.1"), username="root", password=os.environ.get('ZIMA_PASS'), timeout=10)

js_code = """
const Database = require('better-sqlite3');
const db = new Database('/app/data/db/data.sqlite');

const tables = ['accounts', 'providers', 'models', 'settings', 'credentials', 'api_keys', 'apikeys', 'keys'];
for (const t of tables) {
  try {
    const rows = db.prepare('SELECT * FROM ' + t).all();
    console.log(`=== TABLE: ${t} (${rows.length} rows) ===`);
    console.log(JSON.stringify(rows, null, 2));
  } catch(e) {}
}
"""

stdin, stdout, stderr = ssh.exec_command("docker exec -i 9router node", timeout=12)
stdin.write(js_code)
stdin.flush()
stdin.channel.shutdown_write()

print(stdout.read().decode('utf-8', errors='ignore'))
ssh.close()
