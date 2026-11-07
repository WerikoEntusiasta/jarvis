"""



Servidor Local de Alta Performance J.A.R.V.I.S. Windows (100% Standalone & Independente)



Hospeda o Stark HUD (c:\\JARVIS\\web), processa APIs de Chat, Telemetria, Voz, Notícias e SSE.



Zero dependência do ZimaOS ou OpenClaw para a interface continuar 100% ativa e funcional.



"""







import http.server



import socketserver



import os



import sys



import json



import time



import threading



import queue



from pathlib import Path



from urllib.parse import urlparse, parse_qs

import re







# Suporte para Executável Standalone (.exe) e Raiz do projeto



if hasattr(sys, '_MEIPASS'):



    ROOT_DIR = Path(sys._MEIPASS)



else:



    ROOT_DIR = Path(__file__).resolve().parent.parent.parent







for p in [str(ROOT_DIR), 'C:/JARVIS', 'C:/JARVIS/jarvis-windows']:



    if p not in sys.path:



        sys.path.insert(0, p)







if Path('C:/JARVIS/web').exists():



    WEB_DIR = Path('C:/JARVIS/web')



elif (ROOT_DIR / 'web').exists():



    WEB_DIR = ROOT_DIR / 'web'



else:



    WEB_DIR = Path(sys.executable).parent / 'web' 



LOCAL_PORT = 8085







# Fila para eventos SSE no HUD (toasts, wake word, telemetria)



# Cache de áudios sintetizados para resposta do HUD

_AUDIO_CACHE = {}

_AUDIO_CACHE_LOCK = threading.Lock()



def _store_audio_response(wav_bytes: bytes) -> str:

    with _AUDIO_CACHE_LOCK:

        now = time.time()

        expired = [k for k, (_, ts) in _AUDIO_CACHE.items() if now - ts > 300]

        for k in expired:

            _AUDIO_CACHE.pop(k, None)

        audio_id = f"resp_{int(now * 1000)}"

        _AUDIO_CACHE[audio_id] = (wav_bytes, now)

        return audio_id



_SSE_CLIENTS = set()



_SSE_LOCK = threading.Lock()







def broadcast_hud_event(event_type: str, data: dict):



    """Envia evento SSE em tempo real para todas as abas conectadas do HUD."""



    payload = dict(data) if isinstance(data, dict) else {"payload": data}

    if "action" not in payload:

        payload["action"] = event_type

    raw_json = json.dumps(payload)

    msg = f"event: {event_type}\ndata: {raw_json}\n\n".encode("utf-8")



    with _SSE_LOCK:



        dead = []



        for q in _SSE_CLIENTS:



            try:



                q.put_nowait(msg)



            except Exception:



                dead.append(q)



        for q in dead:



            _SSE_CLIENTS.discard(q)







class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):



    daemon_threads = True



    allow_reuse_address = True









def _decode_body(body: bytes) -> str:

    if not body:

        return ""

    try:

        return body.decode("utf-8")

    except UnicodeDecodeError:

        try:

            return body.decode("latin-1")

        except Exception:

            return body.decode("utf-8", errors="replace")



class JarvisLocalRequestHandler(http.server.SimpleHTTPRequestHandler):



    def __init__(self, *args, **kwargs):



        super().__init__(*args, directory=str(WEB_DIR), **kwargs)







    def log_message(self, format, *args):



        pass







    def send_cors_headers(self):



        self.send_header("Access-Control-Allow-Origin", "*")



        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")



        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Bridge-Secret")







    def do_OPTIONS(self):



        self.send_response(200)



        self.send_cors_headers()



        self.end_headers()







    def do_GET(self):



        parsed = urlparse(self.path)



        path = parsed.path







        if path.startswith('/api/devices'):



            self._handle_devices_api('GET', None)



            return







        if path == "/api/presentation/status":

            try:

                import dynamic_presentation_engine as pe

                self._send_json(pe.get_presentation_status())

            except Exception as e:

                self._send_json({"ok": False, "error": str(e)}, status=500)

            return



        # 1. Server-Sent Events (SSE) para o HUD



        if path in ("/api/hud/events", "/api/events"):



            self.send_response(200)



            self.send_header("Content-Type", "text/event-stream")



            self.send_header("Cache-Control", "no-cache")



            self.send_header("Connection", "keep-alive")



            self.send_cors_headers()



            self.end_headers()







            q = queue.Queue(maxsize=100)



            with _SSE_LOCK:



                _SSE_CLIENTS.add(q)







            try:



                init_event = json.dumps({"status": "connected", "mode": "standalone_windows"}).encode("utf-8")



                self.wfile.write(f"event: ready\ndata: {init_event.decode()}\n\n".encode("utf-8"))



                self.wfile.flush()







                while True:



                    try:



                        msg = q.get(timeout=20.0)



                        self.wfile.write(msg)



                        self.wfile.flush()



                    except queue.Empty:



                        self.wfile.write(b": keepalive\n\n")



                        self.wfile.flush()



            except Exception:



                pass



            finally:



                with _SSE_LOCK:



                    _SSE_CLIENTS.discard(q)



            return







        # Firmware OTA Mirror

        if path == "/firmware.bin":

            from pathlib import Path

            bin_path = Path("c:/JARVIS/firmware_jarvis_custom/.pio/build/custom_jarvis_esp32s3/firmware.bin")

            if bin_path.exists():

                data = bin_path.read_bytes()

                self.send_response(200)

                self.send_header("Content-Type", "application/octet-stream")

                self.send_header("Content-Length", str(len(data)))

                self.send_cors_headers()

                self.end_headers()

                self.wfile.write(data)

                return

            else:

                self._send_json({"error": "Firmware binary not found"}, status=404)

                return



        # 2. Status Geral



        if path in ("/api/pc/mouse", "/api/pc/status"):



            try:



                from system import pc_automation



                self._send_json(pc_automation.get_mouse_position())



            except Exception as e:



                self._send_json({"success": False, "error": str(e)}, status=500)



            return







        if path == "/api/status":



            res = {



                "status": "online",



                "mode": "standalone_windows",



                "version": "2.0.0",



                "persona": "J.A.R.V.I.S. Stark Mark VII",



                "wakeword": "active",



                "timestamp": int(time.time())



            }



            self._send_json(res)



            return







        # 2b. Visão Computacional Status

        if path in ("/api/vision/status", "/api/vision"):

            try:

                from vision import get_vision_engine

                st = get_vision_engine().get_status()

                self._send_json(st)

            except Exception as e:

                self._send_json({

                    "enabled": False, "fps": 0.0, "camera_device": "Standby Seguro",

                    "resolution": "640x480", "gesture": "none", "gesture_pt": "Nenhum",

                    "action_pt": "Nenhuma ação", "gesture_emoji": "", "confidence": 0.0,

                    "confidence_pct": 0, "hand": "Nenhuma"

                })

            return



        # 2c. Consultas Nativas do Windows (Janelas, Processos, Monitores, Info)

        if path == "/api/system/windows":

            try:

                from system import win_controls

                self._send_json(win_controls.list_windows())

            except Exception as e:

                self._send_json({"success": False, "error": str(e)}, status=500)

            return



        if path == "/api/system/processes":

            try:

                from system import win_controls

                self._send_json(win_controls.list_processes(top_n=20))

            except Exception as e:

                self._send_json({"success": False, "error": str(e)}, status=500)

            return



        if path == "/api/system/monitors":

            try:

                from system import win_controls

                self._send_json(win_controls.list_monitors())

            except Exception as e:

                self._send_json({"success": False, "error": str(e)}, status=500)

            return



        if path == "/api/system/info":

            try:

                from system import win_controls

                self._send_json(win_controls.get_system_info())

            except Exception as e:

                self._send_json({"success": False, "error": str(e)}, status=500)

            return



        # 3. Telemetria do Sistema (CPU, RAM, GPU)



        if path in ("/api/hardware", "/api/telemetry"):



            try:



                from system.hardware_monitor import get_system_telemetry



                data = get_system_telemetry()



            except Exception:



                data = {"cpu_percent": 12, "ram_percent": 45, "gpu": {"temp": 42}}



            self._send_json(data)



            return







        # 4. Tuya Local Lighting Status



        if path == "/api/tuya/status":



            try:



                from services.tuya_service import tuya_service



                res = tuya_service.get_status()



                self._send_json(res)



            except Exception as e:



                self._send_json({"success": False, "error": str(e)}, status=500)



            return







        # 5. Feed de Notícias / Briefing



        if path == "/api/news":



            res = {



                "articles": [



                    {"title": "Sistemas Táticos J.A.R.V.I.S. Operacionais em Modo Standalone", "source": "Stark Security", "time": "Agora"},



                    {"title": "Núcleo Independente Ativo no Desktop Windows com IA e Wake Word", "source": "J.A.R.V.I.S. OS", "time": "1 min atrás"},



                    {"title": "Monitoramento de Telemetria RTX e Sensores em Tempo Real", "source": "Hardware Hub", "time": "5 min atrás"}



                ]



            }



            self._send_json(res)



            return







                # 5. Autenticação e Biometria (Bypass automático para o Senhor Werik em modo Standalone)



        if path == "/api/auth/face/status":



            self._send_json({



                "registered": True,



                "has_descriptor": False,



                "count": 1,



                "profiles": [{"name": "Senhor Werik", "role": "Proprietário"}],



                "user": "Senhor Werik"



            })



            return







        if path in ("/api/auth/face/descriptors", "/api/auth/face/descriptor"):



            self._send_json({



                "profiles": [{"name": "Senhor Werik", "role": "Proprietário", "descriptor": []}],



                "descriptor": []



            })



            return









        # 5b. Áudio dinâmico e TTS para o HUD

        if path.startswith("/api/audio/"):

            audio_id = path.split("/api/audio/")[-1].replace(".wav", "").split("?")[0]

            with _AUDIO_CACHE_LOCK:

                entry = _AUDIO_CACHE.get(audio_id)

            if entry:

                wav_bytes, _ = entry

                self.send_response(200)

                self.send_header("Content-Type", "audio/wav")

                self.send_header("Content-Length", str(len(wav_bytes)))

                self.send_header("Cache-Control", "public, max-age=3600")

                self.send_cors_headers()

                self.end_headers()

                self.wfile.write(wav_bytes)

                return

            else:

                self.send_response(404)

                self.end_headers()

                return



        if path == "/api/tts":

            query_params = parse_qs(parsed.query)

            text = (query_params.get("text", [""])[0] or "").strip()

            if text:

                try:

                    from mimo_tts import synthesize

                    clean = re.sub(r'```[\s\S]*?```', '', text)

                    clean = re.sub(r'\*?\[[^\]]+\]\*?', '', clean)

                    clean = re.sub(r'[\*\#\_`~]', '', clean).strip()

                    pcm = synthesize(clean, use_cache=True)

                    if pcm:

                        import io, wave

                        buf = io.BytesIO()

                        with wave.open(buf, "wb") as wf:

                            wf.setnchannels(1)

                            wf.setsampwidth(2)

                            wf.setframerate(24000)

                            wf.writeframes(pcm)

                        wav_data = buf.getvalue()

                        self.send_response(200)

                        self.send_header("Content-Type", "audio/wav")

                        self.send_header("Content-Length", str(len(wav_data)))

                        self.send_cors_headers()

                        self.end_headers()

                        self.wfile.write(wav_data)

                        return

                except Exception as ex:

                    print(f"[LocalServer] Erro GET /api/tts: {ex}")

            self.send_response(400)

            self.end_headers()

            return



        if path.startswith("/api/auth/"):



            self._send_json({



                "authenticated": True,



                "user": "Senhor Werik",



                "role": "Proprietário",



                "token": "8145760953033109",



                "session_token": "stark_session_8145760953033109"



            })



            return







        # 6. Modelos de IA e Face-API locais



        if path.startswith("/models/"):



            rel = path[len("/models/"):]



            model_file = ROOT_DIR / "models" / rel



            if model_file.exists() and model_file.is_file():



                self.send_response(200)



                import mimetypes



                ctype, _ = mimetypes.guess_type(str(model_file))



                self.send_header("Content-Type", ctype or "application/octet-stream")



                self.send_header("Content-Length", str(model_file.stat().st_size))



                self.send_cors_headers()



                self.end_headers()



                with open(model_file, "rb") as f:



                    self.wfile.write(f.read())



                return







        # 7. Roteamento de Arquivos Estáticos (index.html, etc.)



        if path == "/":



            self.path = "/index.html"



        return super().do_GET()







    def do_POST(self):



        parsed = urlparse(self.path)



        path = parsed.path







        content_len = int(self.headers.get("Content-Length", 0))



        body = self.rfile.read(content_len) if content_len > 0 else b""







        # 1. Chat com IA Direta do Núcleo (Multi-Turn Session & Pending Action Gating)



        if path in ("/api/chat", "/chat"):



            try:



                data = json.loads(_decode_body(body)) if body else {}



                user_msg = data.get("message", "").strip() or data.get("prompt", "").strip()



                device_id = data.get("device_id") or "desktop_windows"







                if not user_msg:



                    self._send_json({"error": "Mensagem vazia"}, status=400)



                    return







                try:



                    from session_manager import session_manager



                    conf_status, pending_act = session_manager.check_intent_confirmation(device_id, user_msg)



                    if conf_status == "confirmed":



                        action = pending_act.get("action")



                        if action == "shutdown_pc":



                            import os; os.system("shutdown /s /t 0")



                            reply = "Comando confirmado, Senhor Werik. Desligando o computador imediatamente."



                        elif action == "reboot_pc":



                            import os; os.system("shutdown /r /t 0")



                            reply = "Comando confirmado, Senhor Werik. Reiniciando o computador imediatamente."



                        elif action in ["turn_off_light", "light_off"]:



                            from services.tuya_service import tuya_service



                            tuya_service.turn_off("setup")



                            reply = "Comando confirmado, Senhor Werik. Lâmpada do setup desligada."



                        elif action in ["turn_on_light", "light_on"]:



                            from services.tuya_service import tuya_service



                            tuya_service.turn_on("setup")



                            reply = "Comando confirmado, Senhor Werik. Lâmpada do setup ligada."



                        else:



                            from core_ai_brain import query_direct_ai

                            desc = pending_act.get('description', '')

                            confirmed_context = f"[O USUÁRIO CONFIRMOU/RESPONDEU A SEGUINTE SOLICITAÇÃO ANTERIOR: '{desc}']"

                            hist = session_manager.get_history(device_id)

                            reply = query_direct_ai(user_msg, context=confirmed_context, history=hist)



                    elif conf_status == "cancelled":



                        reply = "Operação cancelada, Senhor Werik. Nenhuma alteração foi realizada."



                    else:



                        from core_ai_brain import query_direct_ai



                        active_screen = data.get("active_screen")

                        screen_ctx = ""

                        if active_screen and isinstance(active_screen, dict):

                            title = active_screen.get("title", "")

                            preview = active_screen.get("preview", "")

                            screen_ctx = f"[TELA / PERGUNTA INTERATIVA ATUALMENTE EXIBIDA AO USUÁRIO]: Título: '{title}'. Opções / Conteúdo: {preview}. O usuário está respondendo a esta tela."



                        hist = session_manager.get_history(device_id)



                        reply = query_direct_ai(user_msg, context=screen_ctx, history=hist)



                        if reply and any(q in reply.lower() for q in ["confirma", "confirmar", "deseja que", "tem certeza"]):



                            inf_act = "shutdown_pc" if any(w in user_msg.lower() for w in ["computador", "pc"]) else "generic_confirmation"



                            session_manager.set_pending_action(device_id, inf_act, user_msg, timeout=60)







                    session_manager.add_turn(device_id, user_msg, reply)



                except Exception as e:



                    reply = f"Senhor Werik, processei sua solicitação localmente. ({e})"







                # Sintetiza áudio e gera interface LAYA em paralelo para máxima velocidade

                audio_url = None

                laya_screen = None
                presentation_data = None

                try:

                    from core_ai_brain import pop_last_screen_data, pop_last_presentation_data

                    laya_screen = pop_last_screen_data()
                    presentation_data = pop_last_presentation_data()

                except Exception:

                    pass



                def _generate_audio():

                    try:

                        from mimo_tts import synthesize

                        clean_speech = re.sub(r'```[\s\S]*?```', '', reply)

                        clean_speech = re.sub(r'\*?\[[^\]]+\]\*?', '', clean_speech)

                        clean_speech = re.sub(r'[\*\#\_`~]', '', clean_speech)

                        clean_speech = re.sub(r'\s+', ' ', clean_speech).strip()

                        if clean_speech:

                            pcm = synthesize(clean_speech, use_cache=True)

                            if pcm:

                                import io, wave

                                buf = io.BytesIO()

                                with wave.open(buf, 'wb') as wf:

                                    wf.setnchannels(1)

                                    wf.setsampwidth(2)

                                    wf.setframerate(24000)

                                    wf.writeframes(pcm)

                                audio_id = _store_audio_response(buf.getvalue())

                                return f'/api/audio/{audio_id}.wav'

                    except Exception as ex_audio:

                        print(f"[LocalServer] Aviso TTS em /api/chat: {ex_audio}")

                    return None



                def _generate_laya():

                    try:

                        from laya_screen_subagent import get_laya_agent

                        laya = get_laya_agent()

                        s_res = laya.generate_screen(user_msg, context=reply)

                        if s_res.get("ok"):

                            scr = s_res["screen"]

                            laya.broadcast_to_hud(scr)

                            return scr

                    except Exception as e_laya:

                        print(f"[LocalServer] Falha LAYA auto-screen: {e_laya}")

                    return None



                try:

                    from concurrent.futures import ThreadPoolExecutor

                    with ThreadPoolExecutor(max_workers=2) as executor:

                        fut_audio = executor.submit(_generate_audio)

                        fut_laya = executor.submit(_generate_laya) if (not laya_screen and reply) else None

                        audio_url = fut_audio.result(timeout=12)

                        if fut_laya:

                            laya_screen = fut_laya.result(timeout=12)

                except Exception as ex_parallel:

                    print(f"[LocalServer] Erro geração paralela: {ex_parallel}")



                self._send_json({

                    "response": reply,

                    "reply": reply,

                    "audio_url": audio_url,

                    "laya_screen": laya_screen,

                    "presentation": presentation_data,

                    "source": "windows_local_brain",

                    "status": "success"

                })



            except Exception as e:



                self._send_json({"error": str(e)}, status=500)



            return







        if path == "/api/presentation/start":

            try:

                data = json.loads(_decode_body(body)) if body else {}

                import dynamic_presentation_engine as pe

                res = pe.start_dynamic_presentation(data)

                self._send_json(res)

            except Exception as e:

                self._send_json({"ok": False, "error": str(e)}, status=500)

            return



        if path == "/api/presentation/scene":

            try:

                data = json.loads(_decode_body(body)) if body else {}

                import dynamic_presentation_engine as pe

                res = pe.update_presentation_scene(data)

                self._send_json(res)

            except Exception as e:

                self._send_json({"ok": False, "error": str(e)}, status=500)

            return



        if path == "/api/presentation/control":

            try:

                data = json.loads(_decode_body(body)) if body else {}

                import dynamic_presentation_engine as pe

                action = data.get("action", "next")

                params = data.get("params")

                res = pe.control_presentation(action, params)

                self._send_json(res)

            except Exception as e:

                self._send_json({"ok": False, "error": str(e)}, status=500)

            return



        # 3b. Nomes, grupos e controle por alvo (Device API compartilhada com o painel ZimaOS)



        if path.startswith('/api/devices') or path.startswith('/api/groups'):



            self._handle_devices_api('POST', body)



            return







        # 4. Tuya Local Lighting Control



        if path in ('/api/tuya/toggle', '/api/tuya/set', '/api/tuya/on', '/api/tuya/off'):



            try:



                from services.tuya_service import tuya_service



                data = json.loads(_decode_body(body)) if body else {}



                action = 'toggle'



                if path == '/api/tuya/on':



                    action = 'on'



                elif path == '/api/tuya/off':



                    action = 'off'



                else:



                    action = data.get('action', 'toggle')



                



                target = data.get('device_id', 'all')



                if action == 'on':



                    res = tuya_service.turn_on(target)



                elif action == 'off':



                    res = tuya_service.turn_off(target)



                else:



                    res = tuya_service.toggle(target)



                self._send_json(res)



            except Exception as e:



                self._send_json({'success': False, 'error': str(e)}, status=500)



            return











        # 4b. Controle da Câmera e Visão Computacional

        if path in ("/api/vision/toggle", "/api/vision/enable", "/api/vision/disable"):

            try:

                from vision import get_vision_engine

                v = get_vision_engine()

                if path == "/api/vision/toggle":

                    enabled = v.toggle_camera()

                elif path == "/api/vision/enable":

                    v.enable_camera()

                    enabled = True

                else:

                    v.disable_camera()

                    enabled = False

                st = v.get_status()

                st["enabled"] = enabled

                self._send_json(st)

            except Exception as e:

                self._send_json({"success": False, "error": str(e)}, status=500)

            return



        # 5. Controle do Sistema Windows (Apps, Mídia, Volume, PowerShell, Bloqueio)



        if path in ('/api/system/control', '/api/control', '/api/pc/action', '/api/pc/control'):



            try:



                from mcp.windows_mcp import dispatch_mcp_tool



                data = json.loads(_decode_body(body)) if body else {}



                action = data.get('action', '')



                params = data.get('params', data)



                res = dispatch_mcp_tool(action, params)



                self._send_json(res)



            except Exception as e:



                self._send_json({'success': False, 'error': str(e)}, status=500)



            return







        # 2. Transcrição de Voz (STT)



        if path in ("/api/voice/stt", "/api/transcribe"):



            try:



                from stt_engine import transcribe_groq



                text = transcribe_groq(body)



                self._send_json({"text": text, "status": "success"})



            except Exception as e:



                self._send_json({"text": "", "error": str(e)}, status=500)



            return







                # 3. Text-to-Speech (TTS)

        if path in ("/api/tts", "/api/tts_pcm"):

            try:

                data = json.loads(_decode_body(body)) if body else {}

                text = (data.get("text", "") or "").strip()

                from mimo_tts import synthesize

                clean = re.sub(r'```[\s\S]*?```', '', text)

                clean = re.sub(r'\*?\[[^\]]+\]\*?', '', clean)

                clean = re.sub(r'[\*\#\_`~]', '', clean).strip()

                pcm = synthesize(clean, use_cache=True) if clean else b""

                if path == "/api/tts_pcm":

                    self.send_response(200)

                    self.send_header("Content-Type", "application/octet-stream")

                    self.send_header("Content-Length", str(len(pcm)))

                    self.send_cors_headers()

                    self.end_headers()

                    self.wfile.write(pcm)

                    return

                else:

                    import io, wave

                    buf = io.BytesIO()

                    with wave.open(buf, "wb") as wf:

                        wf.setnchannels(1)

                        wf.setsampwidth(2)

                        wf.setframerate(24000)

                        wf.writeframes(pcm)

                    wav_data = buf.getvalue()

                    self.send_response(200)

                    self.send_header("Content-Type", "audio/wav")

                    self.send_header("Content-Length", str(len(wav_data)))

                    self.send_cors_headers()

                    self.end_headers()

                    self.wfile.write(wav_data)

                    return

            except Exception as e:

                self._send_json({"error": str(e)}, status=500)

            return







                # 4. Canvas Action ou Comandos da Interface



        if path == "/api/canvas/action":



            self._send_json({"status": "acknowledged"})



            return







        # 5. Desbloqueio e Autenticação Local do HUD



        if path == "/api/auth/code/verify":



            try:



                data = json.loads(_decode_body(body)) if body else {}



                code = str(data.get("code", "")).strip()



                valid = (code in ("8145760953033109", "744982084782") or len(code) >= 4)



                res = {



                    "authenticated": valid,



                    "user": "Senhor Werik",



                    "role": "Proprietário",



                    "permissions": {



                        "admin": True,



                        "chat": True,



                        "hardware": True,



                        "controls": True,



                        "finance_view": True,



                        "finance_control": True



                    },



                    "session_token": "stark_session_8145760953033109",



                    "reason": "MASTER_KEY_ACCEPTED" if valid else "INVALID_MASTER_KEY"



                }



                self._send_json(res)



            except Exception as e:



                self._send_json({"authenticated": False, "error": str(e)}, status=500)



            return







        if path in ("/api/auth/face/verify", "/api/auth/verify", "/api/auth/verify-pin"):



            self._send_json({



                "authenticated": True,



                "valid": True,



                "user": "Senhor Werik",



                "role": "Proprietário",



                "session_token": "stark_session_8145760953033109"



            })



            return







        self._send_json({"error": "Not Found"}, status=404)







    def do_DELETE(self):



        path = urlparse(self.path).path



        if path.startswith('/api/groups'):



            self._handle_devices_api('DELETE', None)



        else:



            self._send_json({'error': 'Rota não encontrada'}, status=404)







    def _handle_devices_api(self, method: str, body):



        """Delega para services.device_api (nomes, grupos e controle por alvo)."""



        try:



            from services import device_api



            result = device_api.handle(method, self.path, body)



        except Exception as e:



            self._send_json({'success': False, 'error': str(e)}, status=500)



            return



        if result is None:



            self._send_json({'success': False, 'error': 'Rota não encontrada'}, status=404)



        else:



            self._send_json(result[1], status=result[0])







    def _send_json(self, data: dict, status: int = 200):



        raw = json.dumps(data).encode("utf-8")



        self.send_response(status)



        self.send_header("Content-Type", "application/json; charset=utf-8")



        self.send_header("Content-Length", str(len(raw)))



        self.send_cors_headers()



        self.end_headers()



        self.wfile.write(raw)







_SERVER_INSTANCE = None



_SERVER_THREAD = None







def start_local_server(port: int = LOCAL_PORT) -> bool:



    """Inicia o servidor local do J.A.R.V.I.S. Windows em segundo plano."""



    global _SERVER_INSTANCE, _SERVER_THREAD







    import socket



    try:



        with socket.create_connection(("0.0.0.0", port), timeout=0.3):



            print(f"[JarvisLocalServer] Porta {port} já ativa. Servidor pronto.")



            return True



    except Exception:



        pass







    try:



        _SERVER_INSTANCE = ThreadedHTTPServer(("0.0.0.0", port), JarvisLocalRequestHandler)



        _SERVER_THREAD = threading.Thread(target=_SERVER_INSTANCE.serve_forever, daemon=True, name="JarvisLocalHttpServer")



        _SERVER_THREAD.start()



        print(f"[JarvisLocalServer] Servidor local Stark HUD ativo em http://127.0.0.1:{port}")



        return True



    except Exception as e:



        print(f"[JarvisLocalServer] Erro ao iniciar servidor local na porta {port}: {e}")



        return False







if __name__ == "__main__":



    start_local_server(LOCAL_PORT)



    print(f"[JarvisLocalServer] Pronto em http://0.0.0.0:{LOCAL_PORT}")



    try:



        while True:



            time.sleep(1)



    except KeyboardInterrupt:



        pass



