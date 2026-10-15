import psutil
import subprocess
import json
import paramiko
import time

def make_ascii_bar(percent, length=10):
    filled = int(round(length * (percent / 100.0)))
    return "=" * filled + "-" * (length - filled)

def get_windows_stats():
    cpu = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    ram_used = round(mem.used / (1024**3), 1)
    ram_total = round(mem.total / (1024**3), 1)
    ram_pct = mem.percent

    gpu_temp = "N/A"
    gpu_util = "0"
    gpu_vram = "0"
    try:
        smi = subprocess.check_output(
            ['nvidia-smi', '--query-gpu=temperature.gpu,utilization.gpu,memory.used,memory.total', '--format=csv,noheader,nounits'],
            encoding='utf-8', creationflags=0x08000000
        ).strip()
        parts = [p.strip() for p in smi.split(',')]
        gpu_temp = f"{parts[0]}C"
        gpu_util = f"{parts[1]}%"
        gpu_vram = f"{round(float(parts[2])/1024, 1)}G"
    except Exception:
        pass

    return {
        "cpu": cpu,
        "ram_pct": ram_pct,
        "ram_used": ram_used,
        "ram_total": ram_total,
        "gpu_temp": gpu_temp,
        "gpu_util": gpu_util,
        "gpu_vram": gpu_vram
    }

stats = get_windows_stats()
cpu_bar = make_ascii_bar(stats['cpu'])
ram_bar = make_ascii_bar(stats['ram_pct'])

print("[+] Metricas do Windows coletadas:")
print(f"    CPU: {stats['cpu']}% [{cpu_bar}]")
print(f"    RAM: {stats['ram_pct']}% [{ram_bar}] ({stats['ram_used']}/{stats['ram_total']}GB)")
print(f"    GPU: {stats['gpu_temp']} | Uso: {stats['gpu_util']} | VRAM: {stats['gpu_vram']}")

# Formata o layout visual para a tela redonda da Esfera
formatted_message = (
    f"CPU {stats['cpu']}% [{cpu_bar}]\n"
    f"RAM {stats['ram_pct']}% [{ram_bar}]\n"
    f"GPU {stats['gpu_temp']} | {stats['gpu_util']} | {stats['gpu_vram']}"
)

payload = {
    "device_id": "jarvis_sphere_esp32s3",
    "timeout": 60,
    "screen": {
        "type": "confirmation",
        "title": "TELEMETRIA RIG",
        "message": formatted_message,
        "button1_id": "btn_spotify",
        "button1_label": "SPOTIFY",
        "button2_id": "btn_refresh",
        "button2_label": "ATUALIZAR"
    }
}

payload_json = json.dumps(payload)

# Conecta ao ZimaOS via SSH e envia o comando Canvas para o container jarvis-screen-router (porta 8095)
print("\n[*] Enviando layout bonito de telemetria para a Esfera...")
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(os.environ.get('ZIMA_IP', '127.0.0.1'), username='root', password=os.environ.get('ZIMA_PASS'), timeout=10)  # exporte ZIMA_PASS antes de usar

curl_cmd = f"curl -s -X POST http://localhost:8095/api/jarvis/show_screen -H 'Content-Type: application/json' -d '{payload_json}'"
stdin, stdout, stderr = ssh.exec_command(curl_cmd)
response = stdout.read().decode('utf-8', errors='ignore')
print("[+] Resposta do Renderizador de Telas:", response)

ssh.close()
