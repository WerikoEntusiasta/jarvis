"""
J.A.R.V.I.S. — LG Smart TV (webOS) Manager & ZimaOS Multi-Node Integration
=============================================================================
Painel visual de demonstrações e saída de voz conectado diretamente ao Núcleo ZimaOS:
- Permite que qualquer nó (Esfera ESP32, Windows PC, Mobile, Web) acione a TV remotamente.
- Liga a TV via Wake-on-LAN (WoL / WoWLAN) na sub-rede local (MAC 78:dd:12:38:4f:8e).
- Projeta telas, apresentações e dashboards em 1080p nativo.
- Fala verbalmente através dos alto-falantes da Smart TV LG.
"""

import os
import sys
import time
import json
import socket
import logging
import subprocess
from typing import Dict, Any, Optional

logger = logging.getLogger("JarvisLgTvManager")

LG_TV_IP = os.environ.get("LG_TV_IP", "192.168.3.9")
LG_TV_MAC = os.environ.get("LG_TV_MAC", "78:dd:12:38:4f:8e")
LG_TV_APP_ID = "com.jarvis.tv"
DEV_PORT = 9922

ZIMA_ROUTER_URL = os.environ.get("ZIMA_ROUTER_URL", "http://45.167.187.80:8095")

def _dispatch_to_zimaos_tv(payload: dict) -> bool:
    """Encaminha o comando/projeção para o núcleo ZimaOS repassar via WebSocket à TV com resiliência LAN/WAN."""
    urls = [
        "http://192.168.3.6:8095/api/jarvis/tv/project",
        "http://45.167.187.80:8095/api/jarvis/tv/project"
    ]
    import urllib.request
    for url in urls:
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                if resp.status == 200:
                    return True
        except Exception as e:
            logger.debug(f"[LgTvManager] ZimaOS TV dispatch error via {url}: {e}")
            continue
    return False

def _broadcast_to_hud(event_type: str, data: dict) -> bool:
    """Envia evento para o barramento SSE do HUD local com tolerância ao path de execução."""
    try:
        try:
            from core.local_server import broadcast_hud_event
            broadcast_hud_event(event_type, data)
            return True
        except ImportError:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            jw_dir = os.path.join(base_dir, "jarvis-windows")
            if jw_dir not in sys.path:
                sys.path.insert(0, jw_dir)
            from core.local_server import broadcast_hud_event
            broadcast_hud_event(event_type, data)
            return True
    except Exception as e:
        logger.debug(f"[LgTvManager] Falha no broadcast SSE: {e}")
        return False

def send_wake_on_lan(mac: str = LG_TV_MAC, broadcast_ip: str = "192.168.3.255", port: int = 9) -> bool:
    """Envia o Magic Packet padrão Wake-on-LAN para ligar a TV LG pela rede."""
    try:
        clean_mac = mac.replace(":", "").replace("-", "")
        if len(clean_mac) != 12:
            raise ValueError(f"MAC address inválido: {mac}")
            
        payload = b"\xff" * 6 + bytes.fromhex(clean_mac) * 16
        
        # Envia em broadcast subnet e broadcast global
        for target in (broadcast_ip, "255.255.255.255"):
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                s.sendto(payload, (target, port))
                
        logger.info(f"[LgTvManager] Magic Packet Wake-on-LAN enviado para {mac} ({broadcast_ip}:{port})")
        return True
    except Exception as e:
        logger.error(f"[LgTvManager] Erro ao enviar WoL para a TV: {e}")
        return False

def is_tv_online(timeout: float = 1.0) -> bool:
    """Verifica se a TV está respondendo na rede local ou na porta do Developer Mode."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        res = s.connect_ex((LG_TV_IP, DEV_PORT))
        s.close()
        return res == 0
    except Exception:
        return False

def launch_tv_app(app_id: str = LG_TV_APP_ID) -> Dict[str, Any]:
    """Abre o aplicativo do J.A.R.V.I.S. na TV LG em tela cheia via ares-launch."""
    try:
        res = subprocess.run(
            ["ares-launch", app_id],
            capture_output=True, text=True, timeout=12, shell=True
        )
        ok = res.returncode == 0
        output = res.stdout.strip() or res.stderr.strip()
        logger.info(f"[LgTvManager] ares-launch {app_id}: {output}")
        return {"ok": ok, "app_id": app_id, "message": output}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def close_tv_app(app_id: str = LG_TV_APP_ID) -> Dict[str, Any]:
    """Fecha o aplicativo na TV LG voltando para a interface padrão."""
    try:
        res = subprocess.run(
            ["ares-launch", "-c", app_id],
            capture_output=True, text=True, timeout=10, shell=True
        )
        ok = res.returncode == 0
        return {"ok": ok, "message": res.stdout.strip() or res.stderr.strip()}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def power_on_and_open_app(app_id: str = LG_TV_APP_ID, max_wait: int = 15) -> Dict[str, Any]:
    """Liga a TV via Wake-on-LAN e abre o aplicativo do J.A.R.V.I.S. assim que a TV inicializar."""
    wol_ok = send_wake_on_lan()
    
    # Se já estiver online, abre imediatamente
    if is_tv_online(0.8):
        launch_res = launch_tv_app(app_id)
        return {
            "ok": True,
            "wol_sent": wol_ok,
            "already_online": True,
            "message": "A TV LG já estava ligada. O J.A.R.V.I.S. TV foi aberto em tela cheia.",
            "launch": launch_res
        }
        
    # Aguarda a TV ligar e subir os serviços de rede (geralmente 3 a 8 segundos)
    start_t = time.time()
    online = False
    while time.time() - start_t < max_wait:
        time.sleep(1.0)
        if is_tv_online(0.8):
            online = True
            break
            
    if online:
        time.sleep(1.5)  # Breve pausa para estabilização do subsistema gráfico do webOS
        launch_res = launch_tv_app(app_id)
        return {
            "ok": True,
            "wol_sent": wol_ok,
            "boot_time_sec": round(time.time() - start_t, 1),
            "message": "TV LG ligada via Wake-on-LAN com sucesso! Aplicativo J.A.R.V.I.S. TV aberto em tela cheia.",
            "launch": launch_res
        }
    else:
        return {
            "ok": False,
            "wol_sent": wol_ok,
            "error": "A TV LG recebeu o pacote Wake-on-LAN mas não respondeu na rede dentro do tempo limite. Verifique se o recurso 'Mobile TV On' / 'Ligar via Wi-Fi' está ativo nas configurações da TV."
        }

def project_screen_to_tv(
    title: str = "J.A.R.V.I.S.", 
    html_or_text: str = "", 
    html: str = "",
    speech_text: str = "",
    audio_url: str = ""
) -> Dict[str, Any]:
    """Projeta um card/tela holográfica em tela cheia no app da TV LG e reproduz a fala."""
    content = html if html else html_or_text
    try:
        # Se a TV estiver respondendo e o app não estiver em execução, inicia o app
        if is_tv_online(0.5):
            launch_tv_app()

        payload = {
            "type": "project_screen",
            "title": title,
            "html": content,
            "speech_text": speech_text,
            "audio_url": audio_url
        }

        # 1. Despacha para o ZimaOS repassar à TV conectada via WebSocket
        zima_ok = _dispatch_to_zimaos_tv(payload)

        # 2. Despacha via SSE local como contingência
        _broadcast_to_hud("project_screen", payload)
        _broadcast_to_hud("toast", {"message": f"📺 Projeção enviada para a TV LG: '{title}'"})

        return {
            "ok": True, 
            "title": title, 
            "message": f"Tela '{title}' projetada em tela cheia na Smart TV LG.",
            "zimaos_routed": zima_ok
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}

def speak_on_tv(speech_text: str, audio_url: str = "") -> Dict[str, Any]:
    """Fala verbalmente através dos alto-falantes da Smart TV LG exibindo legenda em tempo real."""
    try:
        if is_tv_online(0.5):
            launch_tv_app()

        payload = {
            "type": "voice_reply",
            "reply": speech_text,
            "text": speech_text,
            "speech_text": speech_text,
            "audio_url": audio_url
        }

        zima_ok = _dispatch_to_zimaos_tv(payload)
        _broadcast_to_hud("voice_reply", payload)

        return {
            "ok": True,
            "speech_text": speech_text,
            "message": "Áudio e fala transmitidos para a Smart TV LG com sucesso.",
            "zimaos_routed": zima_ok
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}

def close_projected_screen() -> Dict[str, Any]:
    """Fecha a projeção ativa na TV LG, retornando ao Reator Arc central."""
    try:
        payload = {"type": "close_screen", "action": "close"}
        _dispatch_to_zimaos_tv(payload)
        _broadcast_to_hud("close_screen", {})
        return {"ok": True, "message": "Projeção da TV encerrada. Retornando ao modo Arc Reactor."}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def get_tv_status() -> Dict[str, Any]:
    """Obtém status de conexão, energia e apps da Smart TV LG."""
    online = is_tv_online(1.0)
    running_apps = []
    if online:
        try:
            res = subprocess.run(["ares-launch", "-r"], capture_output=True, text=True, timeout=5, shell=True)
            for line in res.stdout.splitlines():
                if line.strip() and not "target device" in line:
                    running_apps.append(line.strip())
        except Exception:
            pass

    return {
        "ok": True,
        "device": "Smart TV LG 55UM7650PSB (webOS 4.10)",
        "ip": LG_TV_IP,
        "mac": LG_TV_MAC,
        "online": online,
        "power_state": "Ligada" if online else "Standby / Desligada",
        "jarvis_app_installed": True,
        "running_apps": running_apps,
        "jarvis_app_active": LG_TV_APP_ID in running_apps,
        "role": "Painel Visual Soberano para Demonstrações & Saída de Voz (ZimaOS Core)"
    }
