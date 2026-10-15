import os
import paramiko
import json
import urllib.request

def test_zima():
    print("[*] Conectando ao ZimaOS...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(os.environ.get('ZIMA_IP', '127.0.0.1'), username='root', password=os.environ.get('ZIMA_PASS'), timeout=10)  # exporte ZIMA_PASS antes de usar
        stdin, stdout, stderr = ssh.exec_command('uptime; docker ps --format "{{.Names}}: {{.Status}}"')
        out = stdout.read().decode('utf-8', errors='ignore')
        print("=== ZimaOS Status & Containers ===")
        print(out)
        ssh.close()
    except Exception as e:
        print("[!] Erro ZimaOS:", e)

def test_pluggy():
    print("[*] Consultando Pluggy API...")
    try:
        url = "https://api.pluggy.ai/auth"
        payload = json.dumps({
            "clientId": os.environ.get("PLUGGY_CLIENT_ID", ""),
            "clientSecret": os.environ.get("PLUGGY_CLIENT_SECRET", "")
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            api_key = data["apiKey"]
            print("[+] Pluggy Autenticado! API Key obtida.")

        req_acc = urllib.request.Request("https://api.pluggy.ai/accounts?itemId=" + os.environ.get("PLUGGY_ITEM_ID", "") + "", headers={"X-API-KEY": api_key})
        with urllib.request.urlopen(req_acc, timeout=10) as resp:
            accs = json.loads(resp.read().decode("utf-8"))
            print(f"[+] Contas encontradas: {len(accs.get('results', []))}")
            for a in accs.get('results', []):
                print(f" - {a.get('name')} ({a.get('type')}): R$ {a.get('balance')}")
    except Exception as e:
        print("[!] Erro Pluggy:", e)

if __name__ == "__main__":
    test_zima()
    test_pluggy()
