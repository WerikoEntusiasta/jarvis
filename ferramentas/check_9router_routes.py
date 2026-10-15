import paramiko
import sys

sys.stdout.reconfigure(encoding='utf-8')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(os.environ.get("ZIMA_IP", "127.0.0.1"), username="root", password=os.environ.get('ZIMA_PASS'), timeout=10)

js_code = """
const fs = require('fs');
const files = ['/app/src/app/api', '/app/custom-server.js', '/app/server.js'];
console.log('Listing /app/src/app/api:');
try {
  console.log(fs.readdirSync('/app/src/app/api'));
} catch(e) {
  console.log(e.message);
}
"""

stdin, stdout, stderr = ssh.exec_command("docker exec -i 9router node", timeout=10)
stdin.write(js_code)
stdin.flush()
stdin.channel.shutdown_write()

print(stdout.read().decode('utf-8', errors='ignore'))
ssh.close()
