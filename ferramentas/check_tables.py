import paramiko
import sys

sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(os.environ.get("ZIMA_IP", "127.0.0.1"), username="root", password=os.environ.get('ZIMA_PASS'), timeout=10)

js_code = """
const Database = require('better-sqlite3');
const db = new Database('/app/data/db/data.sqlite');
const tables = db.prepare("SELECT name FROM sqlite_master WHERE type='table'").all();
console.log('TABLES:', tables.map(t => t.name));

for (const t of tables) {
  if (t.name.toLowerCase().includes('log') || t.name.toLowerCase().includes('stat')) continue;
  try {
    const rows = db.prepare('SELECT * FROM ' + t.name).all();
    console.log(`=== TABLE: ${t.name} (${rows.length} rows) ===`);
    console.log(JSON.stringify(rows, null, 2));
  } catch(e) {
    console.log(t.name, e.message);
  }
}
"""

stdin, stdout, stderr = ssh.exec_command("docker exec -i 9router node", timeout=12)
stdin.write(js_code)
stdin.flush()
stdin.channel.shutdown_write()

print(stdout.read().decode('utf-8', errors='ignore'))
ssh.close()
