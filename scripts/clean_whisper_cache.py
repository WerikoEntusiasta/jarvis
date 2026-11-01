import paramiko
import sys

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('45.167.187.80', port=28222, username='root', password='We12wi25k#3912*')

def run(cmd):
    print(f"=== {cmd} ===", flush=True)
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=30)
    out = stdout.read().decode()
    err = stderr.read().decode()
    if out:
        print(out.strip(), flush=True)
    if err:
        print(f"[ERR] {err.strip()}", flush=True)

# 1. Limpar pastas de áudio e saída transitória do Whisper
run('rm -rf /DATA/whisper/audio/* /DATA/whisper/output/*')

# 2. Limpar arquivos temporários de gravação na máquina host
run('rm -f /tmp/utt*.wav')

# 3. Limpar caches internos de build/uv/matplotlib e temporários no container whisper
run('docker exec whisper sh -c "rm -rf /root/.cache/uv /root/.cache/matplotlib /tmp/* 2>/dev/null || true"')

# 4. Truncar logs acumulados do container para liberar espaço
run('truncate -s 0 $(docker inspect --format="{{.LogPath}}" whisper 2>/dev/null) 2>/dev/null || true')

# 5. Reiniciar container whisper para liberar memória RAM e cache de inferência
run('docker restart -t 5 whisper')

# 6. Checar saúde do serviço após reinício
run('docker ps --filter name=whisper --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"')
run('docker exec whisper curl -s http://127.0.0.1:8000/health || echo "starting..."')

ssh.close()
print("CLEANUP_DONE", flush=True)
