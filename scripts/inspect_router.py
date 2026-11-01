import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('45.167.187.80', 28222, 'root', 'We12wi25k#3912*', timeout=10)

def run(cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd)
    return (stdout.read() + stderr.read()).decode('utf-8', errors='ignore').strip()

print("Where is jarvis_screen_router.py:")
print(run("find /DATA/AppData/ -name 'jarvis_screen_router.py'"))
print("\nDocker ps:")
print(run("docker ps --format '{{.Names}} ({{.Ports}})'"))

ssh.close()
