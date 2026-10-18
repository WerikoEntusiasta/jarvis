import socket
import psutil
import subprocess
import json
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

def get_windows_stats():
    cpu = psutil.cpu_percent(interval=None)
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

def main():
    print("[*] Starting Direct LAN UDP Telemetry Streamer for Jarvis Sphere...")
    print(f"[*] Target Direct IP: {SPHERE_IP}:{UDP_PORT} (Broadcast 255.255.255.255:{UDP_PORT})")
    sys.stdout.flush()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    # Prime psutil cpu measurement
    psutil.cpu_percent(interval=None)

    while True:
        loop_start = time.time()
        try:
            stats = get_windows_stats()
            send_direct_udp_telemetry(stats, sock)
            print(f"[+] [{time.strftime('%H:%M:%S')}] UDP -> ESP32 | CPU: {stats['cpu']}% RAM: {stats['ram']}% GPU: {stats['gpu_temp']}C ({stats['gpu_util']}%) VRAM: {stats['gpu_vram']}")
            sys.stdout.flush()
        except Exception as e:
            print(f"[!] Erro no loop de telemetria: {e}")
            sys.stdout.flush()

        time.sleep(1.0)

if __name__ == "__main__":
    main()
