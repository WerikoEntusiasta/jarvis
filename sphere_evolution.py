"""
J.A.R.V.I.S. — Sphere Evolution & Autonomous Embedded Engineering Subsystem
Permite que o J.A.R.V.I.S. inspecione, reprograme, compile e grave o firmware da Esfera Física ESP32-S3
(Display circular GC9A01 240x240, LovyanGFX, Codec ES8311, microWakeWord, PlatformIO)
autonomamente via USB ou OTA sem fio a pedido do Senhor Werik.
"""

import os
import re
import sys
import time
import json
import socket
import logging
import subprocess
import urllib.request
from pathlib import Path
from typing import Dict, Any, Optional, List

logger = logging.getLogger("JarvisSphereEvolution")

REPO_ROOT = Path(__file__).resolve().parent
FIRMWARE_DIR = REPO_ROOT / "firmware_jarvis_custom"
BUILD_BIN_PATH = FIRMWARE_DIR / ".pio" / "build" / "custom_jarvis_esp32s3" / "firmware.bin"

def _get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def sphere_inspect_firmware(file_path: str = "src/main.cpp", start_line: int = 1, end_line: int = 200) -> Dict[str, Any]:
    """Inspeciona o código C++/Headers do firmware da Esfera ESP32-S3."""
    try:
        target = (FIRMWARE_DIR / file_path).resolve()
        if not str(target).startswith(str(FIRMWARE_DIR)):
            return {"ok": False, "error": "Acesso restrito ao diretório do firmware da Esfera."}
        if not target.exists():
            return {"ok": False, "error": f"Arquivo não encontrado no firmware: {file_path}"}
        
        with open(target, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            
        total = len(lines)
        s = max(1, start_line) - 1
        e = min(total, end_line)
        content = "".join(lines[s:e])
        
        return {
            "ok": True,
            "file": file_path,
            "total_lines": total,
            "start_line": s + 1,
            "end_line": e,
            "content": content
        }
    except Exception as ex:
        logger.error(f"[SphereEvolution] Erro ao inspecionar {file_path}: {ex}")
        return {"ok": False, "error": str(ex)}

def sphere_modify_firmware(file_path: str, search_target: str, replacement: str) -> Dict[str, Any]:
    """Aplica substituição cirúrgica no código-fonte do firmware da Esfera ESP32-S3."""
    try:
        target = (FIRMWARE_DIR / file_path).resolve()
        if not target.exists():
            return {"ok": False, "error": f"Arquivo não encontrado: {file_path}"}
            
        with open(target, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
            
        if search_target not in content:
            norm_content = content.replace("\r\n", "\n")
            norm_target = search_target.replace("\r\n", "\n")
            if norm_target in norm_content:
                norm_repl = replacement.replace("\r\n", "\n")
                new_content = norm_content.replace(norm_target, norm_repl, 1)
            else:
                return {"ok": False, "error": "Trecho alvo não localizado no firmware para substituição."}
        else:
            new_content = content.replace(search_target, replacement, 1)
            
        with open(target, "w", encoding="utf-8") as f:
            f.write(new_content)
            
        logger.info(f"[SphereEvolution] Firmware modificado: {file_path}")
        return {"ok": True, "file": file_path, "message": "Código do firmware atualizado com sucesso."}
    except Exception as ex:
        logger.error(f"[SphereEvolution] Erro ao modificar {file_path}: {ex}")
        return {"ok": False, "error": str(ex)}

def sphere_compile_firmware(clean: bool = False) -> Dict[str, Any]:
    """Compila o firmware PlatformIO da Esfera ESP32-S3 gerando o binário oficial firmware.bin."""
    try:
        logger.info("[SphereEvolution] Iniciando compilação PlatformIO do firmware da Esfera...")
        try:
            from core.local_server import broadcast_hud_event
            broadcast_hud_event("toast", {"message": "⚙️ Compilando firmware da Esfera ESP32-S3..."})
        except Exception:
            pass

        if clean:
            subprocess.run(["pio", "run", "-e", "custom_jarvis_esp32s3", "-t", "clean"],
                           cwd=str(FIRMWARE_DIR), capture_output=True, text=True, timeout=30)

        cmd = ["pio", "run", "-e", "custom_jarvis_esp32s3"]
        res = subprocess.run(cmd, cwd=str(FIRMWARE_DIR), capture_output=True, text=True, timeout=180)
        
        stdout = res.stdout
        stderr = res.stderr
        ok = res.returncode == 0
        
        # Extrai métricas de RAM e Flash se compilou
        ram_info = ""
        flash_info = ""
        m_ram = re.search(r"RAM:\s+\[([=\s]+)\]\s+([\d\.]+%)\s+\(used\s+(\d+)\s+bytes\s+from\s+(\d+)\s+bytes\)", stdout)
        if m_ram:
            ram_info = f"{m_ram.group(2)} ({m_ram.group(3)}/{m_ram.group(4)} bytes)"
        m_flash = re.search(r"Flash:\s+\[([=\s]+)\]\s+([\d\.]+%)\s+\(used\s+(\d+)\s+bytes\s+from\s+(\d+)\s+bytes\)", stdout)
        if m_flash:
            flash_info = f"{m_flash.group(2)} ({m_flash.group(3)}/{m_flash.group(4)} bytes)"

        bin_exists = BUILD_BIN_PATH.exists()
        bin_size = BUILD_BIN_PATH.stat().st_size if bin_exists else 0
        
        try:
            from core.local_server import broadcast_hud_event
            if ok and bin_exists:
                broadcast_hud_event("toast", {"message": f"✅ Firmware compilado com sucesso! ({round(bin_size/1024, 1)} KB)"})
                broadcast_hud_event("sphere_compile_finished", {"ok": True, "size": bin_size, "ram": ram_info, "flash": flash_info})
            else:
                broadcast_hud_event("toast", {"message": "❌ Erro na compilação do firmware da Esfera."})
        except Exception:
            pass

        return {
            "ok": ok and bin_exists,
            "returncode": res.returncode,
            "bin_path": str(BUILD_BIN_PATH),
            "bin_size_bytes": bin_size,
            "ram_usage": ram_info,
            "flash_usage": flash_info,
            "stdout_tail": "\n".join(stdout.splitlines()[-15:]) if stdout else "",
            "stderr": stderr if not ok else ""
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Timeout na compilação do firmware da Esfera (excedeu 180s)."}
    except Exception as ex:
        logger.error(f"[SphereEvolution] Falha na compilação: {ex}")
        return {"ok": False, "error": str(ex)}

def sphere_upload_usb(port: str = "COM3", baud: int = 115200) -> Dict[str, Any]:
    """Grava o firmware compilado diretamente na Esfera ESP32-S3 conectada via cabo USB."""
    try:
        if not BUILD_BIN_PATH.exists():
            comp = sphere_compile_firmware()
            if not comp.get("ok"):
                return {"ok": False, "error": f"Falha prévia ao compilar firmware: {comp.get('error')}"}

        logger.info(f"[SphereEvolution] Gravando via USB na porta {port}...")
        try:
            from core.local_server import broadcast_hud_event
            broadcast_hud_event("toast", {"message": f"⚡ Gravando firmware na Esfera via USB ({port})..."})
        except Exception:
            pass

        cmd = ["pio", "run", "-e", "custom_jarvis_esp32s3", "--target", "upload", "--upload-port", port]
        res = subprocess.run(cmd, cwd=str(FIRMWARE_DIR), capture_output=True, text=True, timeout=120)
        
        ok = res.returncode == 0
        try:
            from core.local_server import broadcast_hud_event
            msg = f"✅ Gravação USB na Esfera concluída na porta {port}!" if ok else f"❌ Falha na gravação USB na porta {port}."
            broadcast_hud_event("toast", {"message": msg})
        except Exception:
            pass

        return {
            "ok": ok,
            "port": port,
            "stdout_tail": "\n".join(res.stdout.splitlines()[-10:]) if res.stdout else "",
            "stderr": res.stderr if not ok else ""
        }
    except Exception as ex:
        return {"ok": False, "error": str(ex)}

def sphere_ota_deploy(url_firmware: Optional[str] = None, server_host: str = "45.167.187.80", server_port: int = 8095) -> Dict[str, Any]:
    """Envia o binário de firmware para o servidor e dispara atualização sem fio (OTA) na Esfera."""
    try:
        if not BUILD_BIN_PATH.exists():
            comp = sphere_compile_firmware()
            if not comp.get("ok"):
                return {"ok": False, "error": f"Falha prévia ao compilar firmware: {comp.get('error')}"}

        bin_data = BUILD_BIN_PATH.read_bytes()
        bin_size = len(bin_data)
        logger.info(f"[SphereEvolution] Preparando deploy OTA. Tamanho do binário: {bin_size} bytes.")

        # 1. Tenta fazer upload do binário para o ScreenRouter se o host externo estiver ativo
        uploaded = False
        upload_err = ""
        try:
            up_url = f"http://{server_host}:{server_port}/api/jarvis/firmware/upload"
            req_up = urllib.request.Request(up_url, data=bin_data, headers={"Content-Type": "application/octet-stream"}, method="POST")
            with urllib.request.urlopen(req_up, timeout=12) as resp:
                up_res = json.loads(resp.read().decode("utf-8"))
                if up_res.get("status") == "success":
                    uploaded = True
                    logger.info("[SphereEvolution] Upload para ScreenRouter concluído com sucesso.")
        except Exception as e_up:
            upload_err = str(e_up)
            logger.warning(f"[SphereEvolution] Upload para ScreenRouter não respondeu: {e_up}")

        # Se não forneceu URL específica, usa o endpoint remoto oficial ou o espelho local da LAN
        if not url_firmware:
            if uploaded:
                target_url = f"http://{server_host}:{server_port}/firmware.bin"
            else:
                local_ip = _get_local_ip()
                target_url = f"http://{local_ip}:8085/firmware.bin"
        else:
            target_url = url_firmware

        # 2. Dispara trigger de OTA nos endpoints disponíveis
        payload = {"url": target_url}
        trigger_endpoints = [
            f"http://{server_host}:{server_port}/api/jarvis/ota/trigger",
            "http://127.0.0.1:8095/api/jarvis/ota/trigger",
            "http://127.0.0.1:8085/api/jarvis/ota/trigger"
        ]

        triggered = False
        trigger_resp_msg = ""
        for ep in trigger_endpoints:
            try:
                req_trig = urllib.request.Request(
                    ep,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req_trig, timeout=6) as resp:
                    tr_json = json.loads(resp.read().decode("utf-8"))
                    if tr_json.get("status") in ("success", "ok"):
                        triggered = True
                        trigger_resp_msg = f"Disparado via {ep}"
                        break
            except Exception:
                continue

        try:
            from core.local_server import broadcast_hud_event
            broadcast_hud_event("toast", {"message": f"📡 OTA disparado para a Esfera ({target_url})!"})
        except Exception:
            pass

        return {
            "ok": True,
            "firmware_url": target_url,
            "binary_size_bytes": bin_size,
            "uploaded_to_router": uploaded,
            "ota_triggered": triggered,
            "details": trigger_resp_msg or ("Firmware hospedado localmente no PC Windows em " + target_url)
        }
    except Exception as ex:
        logger.error(f"[SphereEvolution] Falha no deploy OTA: {ex}")
        return {"ok": False, "error": str(ex)}

def sphere_get_status() -> Dict[str, Any]:
    """Obtém o estado atual da Esfera, código compilado e portas COM disponíveis."""
    try:
        bin_exists = BUILD_BIN_PATH.exists()
        bin_stat = BUILD_BIN_PATH.stat() if bin_exists else None
        
        # Detecta portas COM ativas
        ports = []
        try:
            res = subprocess.run(["powershell", "-Command", "Get-CimInstance Win32_SerialPort | Select-Object DeviceID, Description"],
                                 capture_output=True, text=True, timeout=5)
            for line in res.stdout.splitlines():
                if line.strip() and not line.startswith("DeviceID") and not line.startswith("---"):
                    ports.append(line.strip())
        except Exception:
            pass

        return {
            "ok": True,
            "hardware": "Spotpear SP-ESP32-S3-1.28-BOX",
            "display": "GC9A01 LCD Circular 240x240 (LovyanGFX)",
            "audio_codec": "ES8311 (I2C + I2S)",
            "wakeword": "microWakeWord TFLite Local ('Hey Jarvis')",
            "firmware_bin_exists": bin_exists,
            "firmware_bin_size_bytes": bin_stat.st_size if bin_stat else 0,
            "firmware_last_compiled": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(bin_stat.st_mtime)) if bin_stat else "Nunca",
            "active_com_ports": ports
        }
    except Exception as ex:
        return {"ok": False, "error": str(ex)}
