import sys
import os
import paramiko

sys.stdout.reconfigure(encoding='utf-8')

ZIMA_IP = os.environ.get("ZIMA_IP", "127.0.0.1")
ZIMA_USER = os.environ.get("ZIMA_USER", "root")
ZIMA_PASS = os.environ.get("ZIMA_PASS", "")
REMOTE_DIR = "/DATA/AppData/jarvis-memory"

LOCAL_DIR = os.path.dirname(os.path.abspath(__file__))
FILES_TO_UPLOAD = [
    "docker-compose.yml",
    "Dockerfile",
    "memory_server.py",
    "jarvis_memory.py",
    "brain_dashboard.html",
    "jarvis_memory.db"
]

def deploy():
    print(f"[1/4] Conectando via SSH ao ZimaOS ({ZIMA_IP})...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(ZIMA_IP, username=ZIMA_USER, password=ZIMA_PASS, timeout=15)
    
    print(f"[2/4] Criando diretório remoto {REMOTE_DIR}...")
    stdin, stdout, stderr = ssh.exec_command(f"mkdir -p {REMOTE_DIR}")
    stdout.channel.recv_exit_status()
    
    print("[3/4] Enviando arquivos via SFTP...")
    sftp = ssh.open_sftp()
    for filename in FILES_TO_UPLOAD:
        local_path = os.path.join(LOCAL_DIR, filename)
        remote_path = f"{REMOTE_DIR}/{filename}"
        if os.path.exists(local_path):
            print(f"  -> Uploading {filename}...")
            sftp.put(local_path, remote_path)
        else:
            print(f"  [AVISO] Arquivo {filename} não encontrado localmente.")
    sftp.close()
    
    print("[4/4] Executando docker compose up no ZimaOS...")
    cmd = f"export DOCKER_CONFIG=/tmp/.docker && mkdir -p /tmp/.docker && cd {REMOTE_DIR} && docker compose up -d --build"
    stdin, stdout, stderr = ssh.exec_command(cmd)
    stdout.channel.recv_exit_status()
    out = stdout.read().decode('utf-8', errors='ignore')
    err = stderr.read().decode('utf-8', errors='ignore')
    print("STDOUT:", out)
    if err:
        print("STDERR:", err)
        
    print("\nVerificando status dos containers no ZimaOS...")
    stdin, stdout, stderr = ssh.exec_command("docker ps | grep jarvis-memory")
    stdout.channel.recv_exit_status()
    ps_out = stdout.read().decode('utf-8', errors='ignore')
    print(ps_out)
    
    ssh.close()
    print("[SUCCESS] Deploy no ZimaOS finalizado com sucesso!")

if __name__ == "__main__":
    deploy()
