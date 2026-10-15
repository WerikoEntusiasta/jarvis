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
const rows = db.prepare('SELECT id, provider, authType, name, isActive, data FROM providerConnections').all();
console.log('PROVIDER CONNECTIONS:');
for (const r of rows) {
  console.log(`- Provider: ${r.provider}, Name: ${r.name}, Active: ${r.isActive}`);
  try {
    const d = JSON.parse(r.data);
    console.log('  Data keys:', Object.keys(d));
    if (r.provider.toLowerCase().includes('eleven') || (r.name && r.name.toLowerCase().includes('eleven'))) {
      console.log('  ElevenLabs config:', JSON.stringify(d, null, 2));
    }
  } catch(e) {
    console.log('  Data:', r.data);
  }
}
"""

stdin, stdout, stderr = ssh.exec_command("docker exec -i 9router node", timeout=10)
stdin.write(js_code)
stdin.flush()
stdin.channel.shutdown_write()

print(stdout.read().decode('utf-8', errors='ignore'))
ssh.close()
