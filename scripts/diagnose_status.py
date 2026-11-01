import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('45.167.187.80', port=28222, username='root', password='We12wi25k#3912*')

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    print(f"=== {cmd} ===")
    if out:
        print(out)
    if err:
        print(f"[ERR] {err}")

run('docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"')
run('docker logs --tail 30 jarvis-screen-router')
run('curl -s -o /dev/null -w "%{http_code}" http://localhost:8095/health || echo "port 8095 down"')
run('curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health || echo "port 8000 down"')

ssh.close()
