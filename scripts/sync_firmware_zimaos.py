import paramiko
import os
import shutil

def main():
    local_bin = r"c:\JARVIS\firmware_jarvis_custom\.pio\build\custom_jarvis_esp32s3\firmware.bin"
    if not os.path.exists(local_bin):
        print(f"Error: {local_bin} not found")
        return

    # Backup to Desktop
    desktop_bin = r"C:\Users\werik\Desktop\firmware_jarvis_latest.bin"
    try:
        shutil.copyfile(local_bin, desktop_bin)
        print(f"Copied latest firmware to Desktop: {desktop_bin}")
    except Exception as e:
        print(f"Could not copy to Desktop: {e}")

    # SFTP to ZimaOS
    host = "45.167.187.80"
    port = 28222
    user = "root"
    password = "We12wi25k#3912*"

    print(f"Connecting to ZimaOS {host}:{port}...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, port=port, username=user, password=password, timeout=15)

    sftp = ssh.open_sftp()
    remote_path = "/DATA/AppData/jarvis-screen-router/firmware.bin"
    print(f"Uploading {local_bin} -> {remote_path}...")
    sftp.put(local_bin, remote_path)
    sftp.close()
    ssh.close()
    print("Firmware uploaded to ZimaOS OTA successfully!")

if __name__ == "__main__":
    main()
