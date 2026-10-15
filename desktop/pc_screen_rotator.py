import socket
import psutil
import subprocess
import json
import paramiko
import time
import os
import sys

LOCK_FILE = os.path.join(os.environ.get("TEMP", "C:\\Temp"), "jarvis_pc_rotator.lock")

def acquire_single_instance_lock():
    try:
        if os.path.exists(LOCK_FILE):
            try:
                os.remove(LOCK_FILE)
            except Exception:
                pass
        lock_fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_RDWR)
        os.write(lock_fd, str(os.getpid()).encode())
        return lock_fd
    except OSError:
        print("[LOCK] Outra instancia de pc_screen_rotator ja esta em execucao! Encerrando...")
        sys.exit(0)

acquire_single_instance_lock()

SPHERE_IP = "192.168.10.16"
UDP_PORT = 8888

def make_ascii_bar(percent, length=8):
    filled = int(round(length * (percent / 100.0)))
    return "=" * filled + "-" * (length - filled)

def get_windows_stats():
    cpu = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()
    ram_used = round(mem.used / (1024**3), 1)
    ram_total = round(mem.total / (1024**3), 1)
    ram_pct = mem.percent

    gpu_temp = 0
    gpu_util = 0
    gpu_vram = "0G"
    try:
        smi = subprocess.check_output(
            ['nvidia-smi', '--query-gpu=temperature.gpu,utilization.gpu,memory.used,memory.total', '--format=csv,noheader,nounits'],
            encoding='utf-8', creationflags=0x08000000
        ).strip()
        parts = [p.strip() for p in smi.split(',')]
        gpu_temp = int(parts[0])
        gpu_util = int(parts[1])
        gpu_vram = f"{round(float(parts[2])/1024, 1)}G"
    except Exception:
        pass

    return {
        "cpu": int(cpu),
        "ram": int(ram_pct),
        "ram_used": ram_used,
        "ram_total": ram_total,
        "gpu_temp": gpu_temp,
        "gpu_util": gpu_util,
        "gpu_vram": gpu_vram
    }

def send_direct_udp_telemetry(stats, sock):
    """
    Envia pacote UDP direto na rede local para a esfera (IP Fixo + Broadcast).
    Latência < 5ms sem depender de servidores remotos.
    """
    try:
        packet = {
            "cpu": stats["cpu"],
            "ram": stats["ram"],
            "gpu_temp": stats["gpu_temp"],
            "gpu_util": stats["gpu_util"],
            "gpu_vram": stats["gpu_vram"],
            "telemetry": True
        }
        data = json.dumps(packet).encode('utf-8')
        sock.sendto(data, (SPHERE_IP, UDP_PORT))
        sock.sendto(data, ("255.255.255.255", UDP_PORT))
    except Exception as e:
        pass

def connect_ssh():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(os.environ.get('ZIMA_IP', '127.0.0.1'), username='root', password=os.environ.get('ZIMA_PASS'), timeout=5)  # exporte ZIMA_PASS antes de usar
    return ssh

def main():
    print(f"[*] Starting Direct LAN UDP & Cloud Telemetry Daemon for Jarvis Sphere...")
    print(f"[*] Target Direct IP: {SPHERE_IP}:{UDP_PORT} (Broadcast 255.255.255.255:{UDP_PORT})")
    sys.stdout.flush()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    ssh = None
    last_ssh_check = 0
    
    while True:
        loop_start = time.time()
        try:
            stats = get_windows_stats()
            
            # 1. TRANSMISSÃO DIRETA VIA UDP LOCAL (< 5ms)
            send_direct_udp_telemetry(stats, sock)

            # 2. PONTE DE BACKUP VIA ZIMAOS DOCKER (A cada 2s)
            if time.time() - last_ssh_check > 2.0:
                last_ssh_check = time.time()
                try:
                    if ssh is None or not ssh.get_transport() or not ssh.get_transport().is_active():
                        ssh = connect_ssh()
                    
                    cpu_bar = make_ascii_bar(stats['cpu'])
                    ram_bar = make_ascii_bar(stats['ram'])
                    message_text = (
                        f"CPU {stats['cpu']}% [{cpu_bar}]\n"
                        f"RAM {stats['ram']}% [{ram_bar}]\n"
                        f"GPU {stats['gpu_temp']}C | {stats['gpu_util']}% | {stats['gpu_vram']}"
                    )
                    payload = {
                        "device_id": "jarvis_sphere_esp32s3",
                        "wait": False,
                        "timeout": 0,
                        "screen": {
                            "type": "custom",
                            "event": "jarvis.telemetry",
                            "cpu": stats['cpu'],
                            "ram": stats['ram'],
                            "gpu_temp": stats['gpu_temp'],
                            "gpu_util": stats['gpu_util'],
                            "gpu_vram": stats['gpu_vram'],
                            "title": "RIG TELEMETRY",
                            "message": message_text,
                            "button1_id": "btn_spotify",
                            "button1_label": "SPOTIFY",
                            "button2_id": "btn_standby",
                            "button2_label": "STANDBY"
                        }
                    }
                    payload_json = json.dumps(payload)
                    curl_cmd = f"curl -s -w '\\nHTTP_CODE:%{{http_code}}' -X POST http://localhost:8095/api/jarvis/show_screen -H 'Content-Type: application/json' -d '{payload_json}'"
                    ssh.exec_command(curl_cmd)
                except Exception:
                    ssh = None

            print(f"[+] [{time.strftime('%H:%M:%S')}] Telemetria Direta UDP -> ESP32 | CPU: {stats['cpu']}% RAM: {stats['ram']}% GPU: {stats['gpu_temp']}C ({stats['gpu_util']}%)")
            sys.stdout.flush()

        except Exception as e:
            print(f"[!] Erro no loop de telemetria: {e}")
            sys.stdout.flush()

        elapsed = time.time() - loop_start
        sleep_time = max(0.1, 1.0 - elapsed)
        time.sleep(sleep_time)

if __name__ == "__main__":
    main()
