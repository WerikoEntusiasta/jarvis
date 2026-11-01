import shutil
import os
import paramiko
import urllib.request
import json
import time

bin_src = r"c:\JARVIS\firmware_jarvis_custom\.pio\build\custom_jarvis_esp32s3\firmware.bin"
desktop_dest = r"C:\Users\werik\Desktop\BACKUP_FIRMWARE_JARVIS_ESFERA_ESP32S3\binarios_prontos_para_gravar\firmware.bin"
z_dest = r"Z:\Projetos Agenticos\PROJETO AGENTES\PROJETO ( JARVIS )\firmware.bin"

if os.path.exists(bin_src):
    try:
        shutil.copy2(bin_src, desktop_dest)
        print("[OK] Backup copiado para Desktop")
    except Exception as e:
        print("[-] Erro desktop:", e)
    try:
        shutil.copy2(bin_src, z_dest)
        print("[OK] Backup copiado para Drive Z:")
    except Exception as e:
        print("[-] Erro Z:", e)

# Upload para ZimaOS OTA
try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect("45.167.187.80", port=28222, username="root", password="We12wi25k#3912*", timeout=10)
    sftp = ssh.open_sftp()
    sftp.put(bin_src, "/DATA/AppData/jarvis-screen-router/firmware.bin")
    sftp.put(bin_src, "/DATA/AppData/jarvis-hud/firmware.bin")
    sftp.close()
    ssh.close()
    print("[OK] Upload para ZimaOS OTA concluído!")
except Exception as e:
    print("[-] Erro OTA ZimaOS:", e)

time.sleep(3)

# Enviar teste de WhatsApp via Router HTTP
try:
    req = urllib.request.Request(
        "http://45.167.187.80:8095/api/jarvis/whatsapp",
        data=json.dumps({
            "sender": "Werik (WhatsApp)",
            "message": "Mensagem n8n recebida no J.A.R.V.I.S. com sucesso!",
            "time": "10:55"
        }).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        print("[OK] Notificação WhatsApp enviada via Router:")
        print(resp.read().decode("utf-8"))
except Exception as e:
    print("[-] Erro teste whatsapp:", e)
