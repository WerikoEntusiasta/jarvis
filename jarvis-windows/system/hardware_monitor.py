"""
Monitor de Hardware em Tempo Real para Windows (CPU, RAM, GPU NVIDIA, Disco, Bateria)
"""

import shutil
import subprocess
import psutil

def get_system_telemetry() -> dict:
    cpu_percent = psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("C:\\")

    gpu_info = {
        "temp": 0,
        "util": 0,
        "vram_used": "0 MB",
        "vram_total": "0 MB",
        "name": "N/A"
    }

    if shutil.which("nvidia-smi"):
        try:
            cmd = [
                "nvidia-smi",
                "--query-gpu=temperature.gpu,utilization.gpu,memory.used,memory.total,name",
                "--format=csv,noheader,nounits"
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=1.5, creationflags=subprocess.CREATE_NO_WINDOW)
            if res.returncode == 0 and res.stdout.strip():
                parts = [p.strip() for p in res.stdout.strip().split(",")]
                if len(parts) >= 5:
                    gpu_info["temp"] = int(parts[0])
                    gpu_info["util"] = int(parts[1])
                    gpu_info["vram_used"] = f"{parts[2]} MB"
                    gpu_info["vram_total"] = f"{parts[3]} MB"
                    gpu_info["name"] = parts[4]
        except Exception:
            pass

    return {
        "cpu_percent": round(cpu_percent, 1),
        "ram_percent": round(mem.percent, 1),
        "ram_used_gb": round(mem.used / (1024**3), 1),
        "ram_total_gb": round(mem.total / (1024**3), 1),
        "disk_percent": round(disk.percent, 1),
        "disk_free_gb": round(disk.free / (1024**3), 1),
        "gpu": gpu_info
    }
