import os
import posixpath
import paramiko


def upload_dir(sftp, local_dir, remote_dir, skip=("__pycache__",)):
    """Envia recursivamente um diretório local para o ZimaOS via SFTP."""
    try:
        sftp.mkdir(remote_dir)
    except IOError:
        pass
    for name in os.listdir(local_dir):
        if name in skip:
            continue
        local_path = os.path.join(local_dir, name)
        remote_path = posixpath.join(remote_dir, name)
        if os.path.isdir(local_path):
            upload_dir(sftp, local_path, remote_path, skip)
        else:
            print(f"Uploading {local_path} -> {remote_path}")
            sftp.put(local_path, remote_path)


print("[*] Conectando ao ZimaOS...")
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(os.environ.get('ZIMA_IP', '127.0.0.1'), username='root', password=os.environ['ZIMA_SSH_PASSWORD'], timeout=20)
sftp = ssh.open_sftp()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # scripts/ -> raiz do projeto
REMOTE_APP = '/DATA/AppData/jarvis-hud'

# 1. Código backend
core_files = [
    ('server.py', 'server.py'),
    ('biometrics.py', 'biometrics.py'),
    ('jev_laya.py', 'jev_laya.py'),
    ('mcp_hud_server.py', 'mcp_hud_server.py'),
    ('hardware_control.py', 'hardware_control.py'),
]
for src, dst in core_files:
    local = os.path.join(ROOT, src)
    print(f"Uploading {local} -> {REMOTE_APP}/{dst}")
    sftp.put(local, f"{REMOTE_APP}/{dst}")

# 2. Frontend e assets visuais
frontend_files = [
    ('web/index.html', 'index.html'),
    ('web/enroll.html', 'enroll.html'),
    ('web/manifest.json', 'manifest.json'),
    ('web/sw.js', 'sw.js'),
    ('web/icon-512.png', 'icon-512.png'),
    ('web/icon-192.png', 'icon-192.png'),
    ('web/apple-touch-icon.png', 'apple-touch-icon.png'),
    ('web/cobe.esm.js', 'cobe.esm.js'),
    ('web/jarvis_ui_engine.js', 'jarvis_ui_engine.js'),
    ('web/nodes.html', 'nodes.html'),
    ('welcome_werik.mp3', 'welcome_werik.mp3'),
]
for src, dst in frontend_files:
    local = os.path.join(ROOT, src)
    if os.path.exists(local):
        print(f"Uploading {local} -> {REMOTE_APP}/{dst}")
        sftp.put(local, f"{REMOTE_APP}/{dst}")
    else:
        print(f"[!] Pulando arquivo ausente: {local}")

# 3. Visão computacional (fallback headless no Docker, mas mantida sincronizada)
upload_dir(sftp, os.path.join(ROOT, 'vision'), f"{REMOTE_APP}/vision")

# 3.1 Modelos face-api (reconhecimento facial COMPLETO — inclui o .bin de 6,44 MB)
upload_dir(sftp, os.path.join(ROOT, 'models'), f"{REMOTE_APP}/models")

# 4. Build do Docker (imagem com dependências completas)
build_files = [
    ('Dockerfile', f"{REMOTE_APP}/Dockerfile"),
    ('requirements.txt', f"{REMOTE_APP}/requirements.txt"),
]
for src, dst in build_files:
    local = os.path.join(ROOT, src)
    print(f"Uploading {local} -> {dst}")
    sftp.put(local, dst)

# 5. Docker Compose: app + CasaOS
compose_files = [
    ('docker-compose.yml', f"{REMOTE_APP}/docker-compose.yml"),
    ('docker-compose.yml', '/var/lib/casaos/apps/jarvis-hud/docker-compose.yml'),
    ('web/icon-512.png', '/var/lib/casaos/apps/jarvis-hud/icon.png'),
]
for src, dst in compose_files:
    local = os.path.join(ROOT, src)
    print(f"Uploading {local} -> {dst}")
    sftp.put(local, dst)

sftp.close()

print("[*] Reconstruindo a imagem e reiniciando o container jarvis-hud (com --build)...")
cmd = (
    "cd /DATA/AppData/jarvis-hud && "
    "HOME=/DATA DOCKER_CONFIG=/DATA/.docker docker compose down && "
    "HOME=/DATA DOCKER_CONFIG=/DATA/.docker docker compose up -d --build"
)
stdin, stdout, stderr = ssh.exec_command(cmd)
out = stdout.read().decode()
err = stderr.read().decode()
if out.strip():
    print("STDOUT:\n", out)
if err.strip():
    print("STDERR:\n", err)

print("[*] Verificando containers em execução no ZimaOS...")
stdin, stdout, stderr = ssh.exec_command("docker ps --filter name=jarvis-hud --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'")
print(stdout.read().decode())

ssh.close()
print("[+] Deploy no ZimaOS finalizado com sucesso!")
