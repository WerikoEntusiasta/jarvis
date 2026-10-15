import paramiko
import sys

def test_openclaw_jarvis():
    print("[*] Enviando mensagem para o agente JARVIS no OpenClaw via SSH...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(os.environ.get('ZIMA_IP', '127.0.0.1'), username='root', password=os.environ.get('ZIMA_PASS'), timeout=15)  # exporte ZIMA_PASS antes de usar
        # Executa o agente jarvis
        cmd = 'docker exec openclaw openclaw agent --agent jarvis --message "Jarvis, confirme seu status operacional para o senhor Werik em uma frase curta."'
        stdin, stdout, stderr = ssh.exec_command(cmd, timeout=30)
        out = stdout.read().decode('utf-8', errors='ignore')
        err = stderr.read().decode('utf-8', errors='ignore')
        print("=== RESPOSTA DO JARVIS (OPENCLAW) ===")
        print(out)
        if err:
            print("=== STDERR ===")
            print(err)
        ssh.close()
    except Exception as e:
        print("[!] Erro ao chamar Jarvis no OpenClaw:", e)

if __name__ == "__main__":
    test_openclaw_jarvis()
