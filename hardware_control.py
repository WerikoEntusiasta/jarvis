"""
J.A.R.V.I.S. Hardware, OS & Media Controller (Mark-LV Architecture Port)
Nativo para Windows 10/11 - ZERO contas, ZERO chaves de API externas.
- Controle de Volume do Windows (pycaw)
- Lançador de Aplicativos (VS Code, Spotify, Chrome, etc.)
- Telemetria de Hardware (NVIDIA GTX 1660 Ti GPU, CPU, RAM, Discos via psutil & nvidia-smi)
- Busca de Vídeos no YouTube (DDGS)
- Busca de Notícias em Tempo Real (DDGS)
"""

import os
import subprocess  # noqa
CREATE_NO_WINDOW = 0x08000000
import re
import sys
import json
import time
import subprocess
import psutil
from typing import Dict, Any, Optional, List

# 1. TELEMETRIA DE HARDWARE NATIVA & ECONOMIA LOCAL (Mark-LV / OpenJarvis Port)
_LOCAL_SAVINGS = {
    "whisper_transcriptions": 0,
    "local_actions": 0,
    "tokens_saved": 0,
    "money_saved_brl": 0.0,
    "start_time": time.time()
}

def record_local_whisper(duration_sec: float = 3.0):
    _LOCAL_SAVINGS["whisper_transcriptions"] += 1
    # Cada transcrição local economiza aprox 800 tokens + API Whisper ($0.006/min)
    _LOCAL_SAVINGS["tokens_saved"] += 850
    _LOCAL_SAVINGS["money_saved_brl"] = round(_LOCAL_SAVINGS["money_saved_brl"] + 0.12, 2)

def record_local_action(action: str = "tool"):
    _LOCAL_SAVINGS["local_actions"] += 1
    _LOCAL_SAVINGS["tokens_saved"] += 1200
    _LOCAL_SAVINGS["money_saved_brl"] = round(_LOCAL_SAVINGS["money_saved_brl"] + 0.15, 2)

def get_local_savings_telemetry() -> Dict[str, Any]:
    tokens_k = f"{_LOCAL_SAVINGS['tokens_saved'] / 1000:.1f}k"
    return {
        "whisper_runs": _LOCAL_SAVINGS["whisper_transcriptions"],
        "local_actions": _LOCAL_SAVINGS["local_actions"],
        "tokens_saved": _LOCAL_SAVINGS["tokens_saved"],
        "tokens_saved_fmt": tokens_k,
        "money_saved_brl": _LOCAL_SAVINGS["money_saved_brl"],
        "money_saved_fmt": f"R$ {_LOCAL_SAVINGS['money_saved_brl']:.2f}".replace('.', ','),
        "gpu_efficiency": "100% OFFLINE • GTX 1660 Ti",
        "intelligence_per_watt": "30W LOCAL (0 TOKENS CLOUD)"
    }

def get_hardware_telemetry() -> Dict[str, Any]:
    # CPU & RAM
    cpu_pct = psutil.cpu_percent(interval=0.1)
    ram = psutil.virtual_memory()
    ram_used_gb = ram.used / (1024 ** 3)
    ram_total_gb = ram.total / (1024 ** 3)
    ram_pct = ram.percent

    # Disco C: (Windows) ou / (Linux)
    try:
        disk_path = 'C:' if os.name == 'nt' else '/'
        disk = psutil.disk_usage(disk_path)
    except Exception:
        disk = psutil.disk_usage('/')
    disk_free_gb = disk.free / (1024 ** 3)
    disk_total_gb = disk.total / (1024 ** 3)
    disk_pct = disk.percent

    # GPU NVIDIA GTX 1660 Ti via nvidia-smi
    gpu_data = {
        "name": "NVIDIA GeForce GTX 1660 Ti",
        "utilization": 0,
        "temperature": 0,
        "vram_used_mb": 0,
        "vram_total_mb": 6144,
        "vram_pct": 0,
        "status": "ONLINE"
    }
    try:
        cmd = 'nvidia-smi --query-gpu=utilization.gpu,temperature.gpu,memory.used,memory.total --format=csv,noheader,nounits'
        out = subprocess.check_output(cmd, shell=True, timeout=3, creationflags=CREATE_NO_WINDOW).decode('utf-8', errors='ignore').strip()
        parts = [p.strip() for p in out.split(',')]
        if len(parts) >= 4:
            gpu_util = int(parts[0])
            gpu_temp = int(parts[1])
            vram_used = int(parts[2])
            vram_total = int(parts[3])
            vram_pct = round((vram_used / vram_total) * 100, 1) if vram_total > 0 else 0

            gpu_data["utilization"] = gpu_util
            gpu_data["temperature"] = gpu_temp
            gpu_data["vram_used_mb"] = vram_used
            gpu_data["vram_total_mb"] = vram_total
            gpu_data["vram_pct"] = vram_pct
    except Exception as e:
        gpu_data["status"] = f"Warning: {e}"

    return {
        "cpu_percent": cpu_pct,
        "ram_percent": ram_pct,
        "ram_used_gb": round(ram_used_gb, 2),
        "ram_total_gb": round(ram_total_gb, 2),
        "disk_c_percent": disk_pct,
        "disk_c_free_gb": round(disk_free_gb, 1),
        "disk_c_total_gb": round(disk_total_gb, 1),
        "gpu": gpu_data,
        "savings": get_local_savings_telemetry(),
        "timestamp": time.strftime("%H:%M:%S")
    }

# 2. CONTROLE DE VOLUME DO WINDOWS NATIVO (pycaw)
def get_windows_volume() -> int:
    try:
        from pycaw.pycaw import AudioUtilities
        speakers = AudioUtilities.GetSpeakers()
        if hasattr(speakers, 'EndpointVolume'):
            scalar = speakers.EndpointVolume.GetMasterVolumeLevelScalar()
            return int(round(scalar * 100))
    except Exception as e:
        print("[!] Erro ao ler volume:", e)
    return 50

def set_windows_volume(target_percent: int) -> int:
    target_percent = max(0, min(100, target_percent))
    try:
        from pycaw.pycaw import AudioUtilities
        speakers = AudioUtilities.GetSpeakers()
        if hasattr(speakers, 'EndpointVolume'):
            vol = speakers.EndpointVolume
            vol.SetMasterVolumeLevelScalar(target_percent / 100.0, None)
            vol.SetMute(0, None)
            return target_percent
    except Exception as e:
        print("[!] Erro ao ajustar volume:", e)
    return target_percent

def change_windows_volume(delta: int) -> int:
    cur = get_windows_volume()
    return set_windows_volume(cur + delta)

def mute_windows_volume(mute: bool = True) -> bool:
    try:
        from pycaw.pycaw import AudioUtilities
        speakers = AudioUtilities.GetSpeakers()
        if hasattr(speakers, 'EndpointVolume'):
            speakers.EndpointVolume.SetMute(1 if mute else 0, None)
            return True
    except Exception as e:
        print("[!] Erro ao mutar:", e)
    return False

def is_windows_muted() -> bool:
    """Retorna o estado atual de mudo do volume mestre do Windows (True = silenciado)."""
    try:
        from pycaw.pycaw import AudioUtilities
        speakers = AudioUtilities.GetSpeakers()
        if hasattr(speakers, 'EndpointVolume'):
            return bool(speakers.EndpointVolume.GetMute())
    except Exception as e:
        print("[!] Erro ao ler estado de mudo:", e)
    return False

# 3. LANÇADOR DE APLICATIVOS WINDOWS (open_app)
APP_SHORTCUTS = {
    "vscode": "code",
    "vs code": "code",
    "visual studio code": "code",
    "spotify": "spotify:",
    "musica": "spotify:",
    "chrome": "chrome",
    "navegador": "chrome",
    "google": "chrome",
    "discord": "discord",
    "telegram": "telegram",
    "calculadora": "calc",
    "calc": "calc",
    "bloco de notas": "notepad",
    "notepad": "notepad",
    "terminal": "wt",
    "powershell": "powershell",
    "cmd": "cmd",
    "explorer": "explorer",
    "arquivos": "explorer",
    "painel de controle": "control",
    "configuracoes": "ms-settings:"
}

def open_windows_app(app_name: str) -> bool:
    app_lower = app_name.lower().strip()
    target = APP_SHORTCUTS.get(app_lower, app_lower)
    try:
        if target.endswith(":") or target in ["calc", "notepad", "explorer", "control", "code", "chrome", "wt", "powershell"]:
            subprocess.Popen(f"start {target}", shell=True, creationflags=CREATE_NO_WINDOW,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        else:
            subprocess.Popen(f'start "" "{target}"', shell=True, creationflags=CREATE_NO_WINDOW,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
    except Exception as e:
        print(f"[!] Erro ao abrir app {app_name}:", e)
        return False

# 4. GERENCIAMENTO DE JANELAS E SISTEMA (MINIMIZAR, BLOQUEAR)
def minimize_all_windows():
    try:
        subprocess.run(["powershell", "-Command", "(New-Object -ComObject Shell.Application).MinimizeAll()"], check=True)
        return True
    except Exception as e:
        print("[!] Erro ao minimizar janelas:", e)
        return False

def lock_workstation():
    try:
        subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], check=True)
        return True
    except Exception as e:
        print("[!] Erro ao bloquear estação:", e)
        return False

# 5. BUSCADOR DO YOUTUBE SEM API (DDGS - Zero Contas)
def search_youtube_video(query: str) -> Optional[Dict[str, str]]:
    try:
        from ddgs import DDGS
        clean_q = query.replace("youtube", "").replace("toca", "").replace("coloca", "").replace("pesquisa", "").replace("video", "").strip()
        search_term = f"{clean_q} site:youtube.com/watch"
        results = DDGS().text(search_term, max_results=5)
        
        for r in results:
            href = r.get("href", "")
            # Extrai o video ID do YouTube
            match = re.search(r'(?:v=|\/embed\/|youtu\.be\/)([a-zA-Z0-9_-]{11})', href)
            if match:
                vid = match.group(1)
                title = r.get("title", "").replace(" - YouTube", "").replace("YouTube", "").strip()
                if not title or len(title) < 2:
                    title = clean_q.title()
                return {
                    "video_id": vid,
                    "title": title,
                    "url": f"https://www.youtube.com/watch?v={vid}",
                    "embed_url": f"https://www.youtube.com/embed/{vid}?autoplay=1&enablejsapi=1"
                }
    except Exception as e:
        print("[!] Erro ao buscar no YouTube via DDGS:", e)
    return None

# 6. BUSCA DE NOTÍCIAS EM TEMPO REAL SEM API (DDGS - Zero Contas)
def search_realtime_news(topic: str = "Catanduva SP", max_results: int = 4) -> List[Dict[str, Any]]:
    news_items = []
    social_blacklist = ["facebook.com", "twitter.com", "x.com", "instagram.com", "youtube.com", "tiktok.com", "soccerway.com"]
    try:
        from ddgs import DDGS
        raw_news = []
        try:
            raw_news = list(DDGS().news(topic, max_results=max_results + 4))
        except Exception as e:
            print("[!] Aviso DDGS news, tentando fallback text:", e)
        
        if not raw_news:
            raw_news = list(DDGS().text(f"{topic} noticias hoje", max_results=max_results + 4))
            
        for r in raw_news:
            url = r.get("url") or r.get("href") or ""
            if not url or any(s in url.lower() for s in social_blacklist):
                continue
            
            title = r.get("title", "").strip()
            body = r.get("body", "").strip()
            image = r.get("image") or None
            source = r.get("source") or ""
            
            item = {
                "title": title,
                "body": body,
                "url": url,
                "image_url": image,
                "source": source,
                "paragraphs": [],
                "full_text": body
            }
            news_items.append(item)
            if len(news_items) >= max_results:
                break
                
        # Enriquece a matéria principal com detalhes reais (og:image e parágrafos completos)
        if news_items:
            first = news_items[0]
            det = fetch_article_details(first["url"])
            if not first.get("image_url") and det.get("image_url"):
                first["image_url"] = det["image_url"]
            if det.get("source") and not first.get("source"):
                first["source"] = det["source"]
            if det.get("paragraphs"):
                first["paragraphs"] = det["paragraphs"]
                first["full_text"] = det["full_text"]
            
    except Exception as e:
        print(f"[!] Erro ao buscar notícias ({topic}):", e)
        
    return news_items

# 7. EXTRAÇÃO DE CONTEÚDO REAL E IMAGEM DO ARTIGO DE NOTÍCIA (ZERO CONTAS)
def fetch_article_details(url: str, timeout: int = 4) -> Dict[str, Any]:
    import urllib.request
    details = {
        "image_url": None,
        "paragraphs": [],
        "full_text": "",
        "source": "PORTAL REGIONAL"
    }
    if not url:
        return details
    try:
        domain_match = re.search(r'https?://(?:www\.)?([^/]+)', url)
        if domain_match:
            details["source"] = domain_match.group(1).upper()
        
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
            }
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
            
            # Extração de imagem de destaque (og:image ou twitter:image)
            og_match = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
            if not og_match:
                og_match = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', html, re.I)
            if not og_match:
                og_match = re.search(r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']', html, re.I)
            if og_match:
                img_src = og_match.group(1).strip().replace('&amp;', '&')
                if img_src.startswith('//'):
                    img_src = 'https:' + img_src
                if img_src.startswith('http'):
                    details["image_url"] = img_src
            
            # Limpeza de scripts, css e blocos de navegação
            clean_html = re.sub(r'<(script|style|nav|header|footer|aside)[^>]*>.*?</\1>', '', html, flags=re.DOTALL | re.I)
            raw_paras = re.findall(r'<p[^>]*>(.*?)</p>', clean_html, flags=re.DOTALL | re.I)
            
            paras = []
            for p in raw_paras:
                clean_p = re.sub(r'<[^>]+>', '', p).strip()
                clean_p = re.sub(r'\s+', ' ', clean_p).strip()
                if len(clean_p) > 50 and not any(w in clean_p.lower() for w in ["cookie", "todos os direitos reservados", "compartilhe:", "leia também", "inscreva-se", "assine"]):
                    paras.append(clean_p)
            
            if paras:
                details["paragraphs"] = paras[:6]
                details["full_text"] = "\n\n".join(paras[:6])
    except Exception as e:
        print(f"[!] Erro ao extrair artigo ({url}):", e)
    return details


# 5. GERENCIADOR DE PROCESSOS DO WINDOWS & CONECTIVIDADE REAL (ZERO DADOS FAKE)
def get_top_windows_processes(limit: int = 8) -> List[Dict[str, Any]]:
    """Lê processos reais em execução no Windows, ordenados por consumo de memória RAM."""
    procs = []
    for p in psutil.process_iter(['pid', 'name', 'memory_info', 'cpu_percent']):
        try:
            mem_mb = round(p.info['memory_info'].rss / (1024 * 1024), 1)
            cpu = round(p.info.get('cpu_percent') or 0.0, 1)
            name = p.info.get('name') or "processo"
            procs.append({
                "pid": p.info['pid'],
                "name": name,
                "mem_mb": mem_mb,
                "cpu_percent": cpu
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    procs.sort(key=lambda x: x["mem_mb"], reverse=True)
    return procs[:limit]

def kill_windows_process(pid: int) -> bool:
    """Finaliza um processo do Windows pelo PID."""
    try:
        p = psutil.Process(int(pid))
        p.terminate()
        return True
    except Exception as e:
        print(f"[!] Erro ao matar PID {pid}:", e)
        return False

def test_system_connectivity() -> List[Dict[str, Any]]:
    """Mede a latência TCP real em milissegundos para serviços essenciais."""
    import socket
    targets = [
        {"name": "ZimaOS SSH", "host": os.environ.get("ZIMA_IP", os.environ.get("ZIMA_IP", "127.0.0.1")), "port": 22, "service": "Infraestrutura"},
        {"name": "Nginx Proxy", "host": os.environ.get("ZIMA_IP", os.environ.get("ZIMA_IP", "127.0.0.1")), "port": 80, "service": "Roteamento Web"},
        {"name": "n8n Workflows", "host": os.environ.get("ZIMA_IP", os.environ.get("ZIMA_IP", "127.0.0.1")), "port": 5678, "service": "Automações"},
        {"name": "WAHA WhatsApp", "host": os.environ.get("ZIMA_IP", os.environ.get("ZIMA_IP", "127.0.0.1")), "port": 3000, "service": "Mensageria"},
        {"name": "Internet Core", "host": "8.8.8.8", "port": 53, "service": "Conectividade Global"}
    ]
    results = []
    for t in targets:
        t0 = time.time()
        try:
            s = socket.create_connection((t["host"], t["port"]), timeout=1.2)
            latency_ms = round((time.time() - t0) * 1000, 1)
            s.close()
            results.append({
                "name": t["name"],
                "service": t["service"],
                "host": f"{t['host']}:{t['port']}",
                "status": "ONLINE",
                "latency_ms": latency_ms,
                "color": "emerald" if latency_ms < 50 else "amber"
            })
        except Exception:
            results.append({
                "name": t["name"],
                "service": t["service"],
                "host": f"{t['host']}:{t['port']}",
                "status": "OFFLINE",
                "latency_ms": None,
                "color": "rose"
            })
    return results

