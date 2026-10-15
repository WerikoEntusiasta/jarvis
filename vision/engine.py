import os
import cv2
import time
import threading
from typing import Dict, Any, Optional, Callable, List
import numpy as np

from .config import VisionConfig
from .camera import CameraCapture
from .gestures import GestureDetector
from .events import VisionEventBus, VisionEvent
from .actions import WindowsActions

GESTURE_EMOJIS = {
    "thumbs_up": "👍",
    "thumbs_down": "👎",
    "open_hand": "✋",
    "fist": "✊",
    "point_up": "☝️",
    "point_down": "👇",
    "point_right": "👉",
    "point_left": "👈",
    "peace_sign": "✌️",
    "three_fingers": "🖖",
    "swipe_right": "➡️",
    "swipe_left": "⬅️",
    "swipe_up": "⬆️",
    "swipe_down": "⬇️",
    "zoom_in": "🔍+",
    "zoom_out": "🔍-"
}

GESTURE_DETAILS_PT = {
    "thumbs_up": {
        "nome": "Joinha",
        "acao": "Confirmar ação",
        "descricao": "Confirma o comando atual ou responde afirmativamente",
        "emoji": "👍"
    },
    "thumbs_down": {
        "nome": "Polegar para Baixo",
        "acao": "Cancelar ação",
        "descricao": "Cancela a operação atual ou responde negativamente",
        "emoji": "👎"
    },
    "open_hand": {
        "nome": "Mão Aberta (Palma)",
        "acao": "Play / Pausar mídia",
        "descricao": "Pausa ou retoma a reprodução de vídeo ou música",
        "emoji": "✋"
    },
    "fist": {
        "nome": "Punho Fechado",
        "acao": "Minimizar tudo",
        "descricao": "Minimiza todas as janelas para a área de trabalho",
        "emoji": "✊"
    },
    "point_up": {
        "nome": "Indicador para Cima",
        "acao": "Aumentar Volume (+10%)",
        "descricao": "Aumenta o volume do computador",
        "emoji": "☝️"
    },
    "point_down": {
        "nome": "Indicador para Baixo",
        "acao": "Diminuir Volume (-10%)",
        "descricao": "Diminui o volume do computador",
        "emoji": "👇"
    },
    "point_right": {
        "nome": "Indicador para Direita",
        "acao": "Próxima Mídia",
        "descricao": "Avança para a próxima música ou vídeo",
        "emoji": "👉"
    },
    "point_left": {
        "nome": "Indicador para Esquerda",
        "acao": "Mídia Anterior",
        "descricao": "Retorna para a música ou vídeo anterior",
        "emoji": "👈"
    },
    "peace_sign": {
        "nome": "Dois Dedos (Paz)",
        "acao": "Silenciar Áudio (Mudo)",
        "descricao": "Ativa ou desativa o mudo do computador",
        "emoji": "✌️"
    },
    "three_fingers": {
        "nome": "Três Dedos",
        "acao": "Alternar Janelas",
        "descricao": "Alterna entre aplicativos abertos (Alt+Tab)",
        "emoji": "🖖"
    },
    "swipe_right": {
        "nome": "Arrastar para Direita",
        "acao": "Avançar Próximo Item",
        "descricao": "Passa para o próximo slide, foto ou aba",
        "emoji": "➡️"
    },
    "swipe_left": {
        "nome": "Arrastar para Esquerda",
        "acao": "Voltar Item Anterior",
        "descricao": "Retorna para o slide, foto ou aba anterior",
        "emoji": "⬅️"
    },
    "swipe_up": {
        "nome": "Arrastar para Cima",
        "acao": "Rolar para Cima",
        "descricao": "Executa rolagem da página para cima",
        "emoji": "⬆️"
    },
    "swipe_down": {
        "nome": "Arrastar para Baixo",
        "acao": "Rolar para Baixo",
        "descricao": "Executa rolagem da página para baixo",
        "emoji": "⬇️"
    },
    "zoom_in": {
        "nome": "Aproximar a Mão",
        "acao": "Ampliar (Zoom +)",
        "descricao": "Aumenta o zoom da tela ou do conteúdo",
        "emoji": "🔍+"
    },
    "zoom_out": {
        "nome": "Afastar a Mão",
        "acao": "Reduzir (Zoom -)",
        "descricao": "Diminui o zoom da tela ou do conteúdo",
        "emoji": "🔍-"
    }
}

class VisionEngine:
    """
    Main Multi-Modal Vision Subsystem for J.A.R.V.I.S.
    Coordinates Camera, MediaPipe Tracking, Event Bus, Windows Automation and OpenClaw bridges.
    """

    def __init__(self, config_path: Optional[str] = None):
        self.config = VisionConfig(config_path) if config_path else VisionConfig()
        
        # Carrega parâmetros de câmera
        cam_cfg = self.config.get("camera", default={})
        dev_idx = cam_cfg.get("device_index", 0)
        w = cam_cfg.get("width", 640)
        h = cam_cfg.get("height", 480)
        fps = cam_cfg.get("fps_target", 30)

        self.camera = CameraCapture(device_index=dev_idx, width=w, height=h, fps_target=fps)
        self.detector = GestureDetector()
        
        det_cfg = self.config.get("detection", default={})
        g_cool = det_cfg.get("gesture_cooldown_seconds", 1.4)
        p_cool = det_cfg.get("presence_cooldown_seconds", 3.0)
        self.event_bus = VisionEventBus(gesture_cooldown_sec=g_cool, presence_cooldown_sec=p_cool)
        
        self.windows_actions = WindowsActions(config=self.config)

        # Callbacks externos para HUD e OpenClaw
        self.on_hud_broadcast: Optional[Callable[[Dict[str, Any]], None]] = None
        self.on_openclaw_dispatch: Optional[Callable[[VisionEvent], None]] = None

        self._is_running = False
        self._thread: Optional[threading.Thread] = None
        self._annotated_jpeg: Optional[bytes] = None
        self._jpeg_lock = threading.Lock()

        # Telemetria em tempo real
        self._latest_gesture = "none"
        self._latest_confidence = 0.0
        self._latest_hand = "none"
        self._is_user_present = False
        self._last_event_time = 0.0
        self._last_event_summary = "Aguardando ativação..."
        self._openclaw_connected = True
        
        # Buffer de estabilidade temporal (impede ativação acidental)
        self._pending_gesture: Optional[str] = None
        self._pending_frames: int = 0

        # Configura listeners internos
        self._setup_internal_listeners()

    def _setup_internal_listeners(self):
        """Conecta o barramento de eventos ao despachante de ações e broadcasts."""
        def handle_event(event: VisionEvent):
            self._last_event_time = event.timestamp
            
            # 1. Trata gestos com mapeamento de ações
            if event.type == "vision.gesture" and event.gesture:
                self._latest_gesture = event.gesture
                self._latest_confidence = event.confidence
                self._latest_hand = "Direita" if (event.hand or "right").lower() in ["right", "direita"] else "Esquerda"
                
                details = GESTURE_DETAILS_PT.get(event.gesture, {
                    "nome": event.gesture,
                    "acao": "Ação detectada",
                    "descricao": "",
                    "emoji": GESTURE_EMOJIS.get(event.gesture, "🖐")
                })
                emoji = details.get("emoji", "🖐")
                self._last_event_summary = f"{emoji} {details.get('nome')} ➔ {details.get('acao')}"

                # Executa ação do Windows associada ao gesto
                mapping = self.config.get_action_for_gesture(event.gesture)
                if mapping:
                    action_name = mapping.get("action", "")
                    target = mapping.get("target", "")
                    risk = mapping.get("risk_level", "low")
                    act_res = self.windows_actions.execute(action_name, target=target, risk_level=risk)
                    event.metadata = {
                        "action_executed": action_name,
                        "action_result": act_res,
                        "gesture_pt": details.get("nome"),
                        "action_pt": details.get("acao"),
                        "emoji": emoji
                    }

            elif event.type == "vision.presence":
                self._is_user_present = bool(event.present)
                status_str = "Presente" if event.present else "Ausente"
                self._last_event_summary = f"Presença: {status_str}"

            # 2. Notifica HUD via SSE
            if self.on_hud_broadcast:
                try:
                    hud_payload = {
                        "action": "vision_event",
                        "event": event.to_dict(),
                        "summary": self._last_event_summary,
                        "status": self.get_status()
                    }
                    self.on_hud_broadcast(hud_payload)
                except Exception as e:
                    print(f"[VisionEngine] Erro ao enviar para HUD: {e}")

            # 3. Notifica OpenClaw
            if self.on_openclaw_dispatch:
                try:
                    self.on_openclaw_dispatch(event)
                except Exception as e:
                    print(f"[VisionEngine] Erro ao despachar para OpenClaw: {e}")

        self.event_bus.subscribe(handle_event)

    def start(self):
        """Inicia os subsistemas de captura e processamento em background."""
        if self._is_running:
            return
        self._is_running = True
        self.camera.start()

        # Inicia habilitada se configurado
        if self.config.get("camera", "enabled_by_default", default=True):
            self.camera.enable()

        self._thread = threading.Thread(target=self._processing_loop, daemon=True, name="JarvisVisionProcessThread")
        self._thread.start()
        print("[VisionEngine] Motor de visão computacional J.A.R.V.I.S. ativo.")

    def enable_camera(self):
        self.camera.enable()

    def disable_camera(self):
        self.camera.disable()
        self._latest_gesture = "none"
        self._latest_confidence = 0.0

    def toggle_camera(self) -> bool:
        return self.camera.toggle()

    def is_camera_enabled(self) -> bool:
        return self.camera.is_enabled()

    def get_status(self) -> Dict[str, Any]:
        cam_stats = self.camera.get_stats()
        emoji = GESTURE_EMOJIS.get(self._latest_gesture, "🖐")
        details = GESTURE_DETAILS_PT.get(self._latest_gesture, {
            "nome": self._latest_gesture,
            "acao": "Nenhuma ação",
            "descricao": ""
        })

        # Verifica se o navegador está enviando quadros ativamente
        browser_active = getattr(self, "_browser_active", False) and (time.time() - getattr(self, "_browser_last_ts", 0) < 3.5)
        is_enabled = browser_active or cam_stats.get("enabled", False)
        fps_val = getattr(self, "_browser_fps", 0.0) if browser_active else cam_stats.get("fps", 0.0)
        device_name = "Navegador Web (Webcam HTML5)" if browser_active else cam_stats.get("device", "Camera")

        return {
            "enabled": is_enabled,
            "fps": fps_val,
            "camera_device": device_name,
            "resolution": cam_stats.get("resolution", "640x480"),
            "gesture": self._latest_gesture,
            "gesture_pt": details.get("nome"),
            "action_pt": details.get("acao"),
            "gesture_emoji": emoji if self._latest_gesture != "none" else "",
            "confidence": self._latest_confidence,
            "confidence_pct": int(self._latest_confidence * 100),
            "hand": self._latest_hand.capitalize() if self._latest_hand != "none" else "Nenhuma",
            "user_present": self._is_user_present,
            "openclaw_connected": self._openclaw_connected,
            "last_event_summary": self._last_event_summary,
            "last_event_time": time.strftime("%H:%M:%S", time.localtime(self._last_event_time)) if self._last_event_time else "--:--:--",
            "supported_gestures": GESTURE_DETAILS_PT
        }

    def process_browser_frame(self, frame_bytes: bytes) -> Dict[str, Any]:
        """
        Processa um quadro de vídeo enviado pela webcam do navegador.
        Executa MediaPipe GestureRecognizer e regras geométricas localmente com alta performance.
        """
        if not frame_bytes:
            return {"status": "error", "error": "Empty frame"}

        np_arr = np.frombuffer(frame_bytes, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if frame is None:
            return {"status": "error", "error": "Decode failed"}

        now = time.time()
        if not hasattr(self, "_browser_fps_times"):
            self._browser_fps_times = []
        self._browser_fps_times.append(now)
        if len(self._browser_fps_times) > 20:
            self._browser_fps_times.pop(0)
        if len(self._browser_fps_times) >= 2:
            dt = self._browser_fps_times[-1] - self._browser_fps_times[0]
            self._browser_fps = round((len(self._browser_fps_times) - 1) / dt, 1) if dt > 0 else 24.0
        else:
            self._browser_fps = 24.0

        self._browser_active = True
        self._browser_last_ts = now

        # Processa detecção com MediaPipe + Regras Geométricas
        res = self.detector.process_frame(frame)

        # Publica evento de presença se detectado
        if "user_present" in res:
            self.event_bus.publish_presence(res["user_present"], res.get("presence_confidence", 0.95))

        # Publica gesto estático se detectado com confiança mínima
        min_conf = self.config.get("detection", "min_gesture_confidence", default=0.60)
        if res.get("gesture") and res["gesture"] != "none" and res["confidence"] >= min_conf:
            self.event_bus.publish_gesture(
                gesture=res["gesture"],
                confidence=res["confidence"],
                hand=res.get("hand", "right")
            )

        # Publica gesto dinâmico (Swipe/Zoom) se detectado
        dyn = res.get("dynamic_gesture")
        if dyn and dyn.get("gesture") and dyn.get("confidence", 0.60) >= min_conf:
            self.event_bus.publish_gesture(
                gesture=dyn["gesture"],
                confidence=dyn.get("confidence", 0.60),
                hand=res.get("hand", "right"),
                metadata=dyn
            )

        # Renderiza overlay visual e anotações para o preview MJPEG do HUD
        self._render_overlay_and_store(frame, res)

        gest_name = res.get("gesture", "none")
        details = GESTURE_DETAILS_PT.get(gest_name, {
            "nome": gest_name,
            "acao": "Nenhuma ação",
            "descricao": ""
        })
        emoji = details.get("emoji", GESTURE_EMOJIS.get(gest_name, "🖐"))
        hand_pt = "Direita" if (res.get("hand", "none")).lower() in ["right", "direita"] else ("Esquerda" if (res.get("hand", "none")).lower() in ["left", "esquerda"] else "Nenhuma")

        return {
            "status": "ok",
            "gesture": gest_name,
            "gesture_pt": details.get("nome"),
            "action_pt": details.get("acao"),
            "gesture_emoji": emoji if gest_name != "none" else "",
            "confidence": res.get("confidence", 0.0),
            "confidence_pct": int(res.get("confidence", 0.0) * 100),
            "hand": hand_pt,
            "user_present": res.get("user_present", False),
            "landmarks": res.get("landmarks", []),
            "fps": self._browser_fps,
            "last_event": self._last_event_summary
        }

    def get_annotated_jpeg(self) -> Optional[bytes]:
        with self._jpeg_lock:
            return self._annotated_jpeg

    def _processing_loop(self):
        while self._is_running:
            if not self.camera.is_enabled():
                time.sleep(0.1)
                continue

            success, frame, timestamp = self.camera.get_frame()
            if not success or frame is None:
                time.sleep(0.02)
                continue

            # Processa detecção com MediaPipe + Regras Geométricas
            res = self.detector.process_frame(frame)

            # Publica evento de presença se detectado
            if "user_present" in res:
                self.event_bus.publish_presence(res["user_present"], res.get("presence_confidence", 0.95))

            # Publica gesto estático se detectado com estabilidade temporal (mínimo de frames consecutivos)
            min_conf = self.config.get("detection", "min_gesture_confidence", default=0.60)
            req_frames = self.config.get("detection", "gesture_hold_frames", default=8)
            current_gest = res.get("gesture", "none")
            current_conf = res.get("confidence", 0.0)

            if current_gest != "none" and current_conf >= min_conf:
                if current_gest == self._pending_gesture:
                    self._pending_frames += 1
                else:
                    self._pending_gesture = current_gest
                    self._pending_frames = 1

                # Dispara SOMENTE se a mão for mantida estável por frames consecutivos (evita falso positivo acidental)
                if self._pending_frames >= req_frames:
                    self.event_bus.publish_gesture(
                        gesture=current_gest,
                        confidence=current_conf,
                        hand=res.get("hand", "right")
                    )
                    self._pending_gesture = None
                    self._pending_frames = 0
            else:
                self._pending_gesture = None
                self._pending_frames = 0

            # Publica gesto dinâmico (Swipe/Zoom) se detectado
            dyn = res.get("dynamic_gesture")
            if dyn and dyn.get("gesture") and dyn.get("confidence", 0.60) >= min_conf:
                self.event_bus.publish_gesture(
                    gesture=dyn["gesture"],
                    confidence=dyn.get("confidence", 0.60),
                    hand=res.get("hand", "right"),
                    metadata=dyn
                )

            # Renderiza overlay visual e anotações para o preview MJPEG do HUD
            self._render_overlay_and_store(frame, res)

            time.sleep(0.01)

    def _render_overlay_and_store(self, frame: np.ndarray, res: Dict[str, Any]):
        """Desenha anotações cibernéticas Stark HUD no frame e codifica em JPEG."""
        h, w = frame.shape[:2]
        annotated = frame.copy()

        # Desenha nós e conexões dos 21 pontos da mão (estilo holográfico Stark)
        landmarks = res.get("landmarks", [])
        if landmarks and len(landmarks) == 21:
            points = [(int(lm["x"] * w), int(lm["y"] * h)) for lm in landmarks]
            
            # Conexões básicas dos dedos
            connections = [
                (0,1),(1,2),(2,3),(3,4),       # Polegar
                (0,5),(5,6),(6,7),(7,8),       # Indicador
                (0,9),(9,10),(10,11),(11,12),  # Médio
                (0,13),(13,14),(14,15),(15,16),# Anelar
                (0,17),(17,18),(18,19),(19,20),# Mínimo
                (5,9),(9,13),(13,17)           # Palma
            ]
            for p1, p2 in connections:
                cv2.line(annotated, points[p1], points[p2], (255, 230, 0), 1, cv2.LINE_AA)
            for pt in points:
                cv2.circle(annotated, pt, 3, (0, 240, 255), -1, cv2.LINE_AA)

        # Banner holográfico no topo do frame
        cv2.rectangle(annotated, (0, 0), (w, 36), (10, 15, 30), -1)
        cv2.line(annotated, (0, 36), (w, 36), (0, 210, 255), 1)

        fps_val = self.camera.get_stats().get("fps", 0)
        gest = res.get("gesture", "none")
        conf = int(res.get("confidence", 0) * 100)
        hand = res.get("hand", "none").upper()

        text_left = f"J.A.R.V.I.S. VISION // {fps_val} FPS"
        cv2.putText(annotated, text_left, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 240, 255), 1, cv2.LINE_AA)

        if gest != "none":
            text_right = f"[{hand}] {gest.upper()} ({conf}%)"
            cv2.putText(annotated, text_right, (w - 240, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (50, 255, 150), 1, cv2.LINE_AA)

        # Codifica para JPEG
        ret, jpeg = cv2.imencode('.jpg', annotated, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
        if ret:
            with self._jpeg_lock:
                self._annotated_jpeg = jpeg.tobytes()

    def stop(self):
        self._is_running = False
        self.camera.stop()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
