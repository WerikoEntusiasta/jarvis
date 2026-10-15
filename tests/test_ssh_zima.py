import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
print('[*] Conectando ao ZimaOS via SSH (127.0.0.1)...')

try:
    ssh.connect(os.environ.get('ZIMA_IP', '127.0.0.1'), username='root', password=os.environ['ZIMA_SSH_PASSWORD'], timeout=10)
    print('[+] Conectado com sucesso!')
    
    stdin, stdout, stderr = ssh.exec_command('docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"')
    print('=== DOCKER CONTAINERS ===')
    print(stdout.read().decode('utf-8'))
    
    ssh.close()
except Exception as e:
    print('[-] Erro ao conectar via SSH:', e)
