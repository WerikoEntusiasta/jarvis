import os
import cv2
import time
import math
from typing import Dict, Any, List, Optional, Tuple
from collections import deque
import numpy as np
import mediapipe as mp

MODEL_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models", "gesture_recognizer.task")
HAAR_FACE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models", "haarcascade_frontalface_default.xml")

class GestureDetector:
    """
    Local Edge Hand & Motion Gesture Detector for Jarvis.
    - Zero cloud AI calls (100% on-device CPU/GPU).
    - MediaPipe Gesture Recognizer + Custom Geometric Rules + Temporal Motion Tracking.
    - User Presence detection via ultra-fast Face Cascade.
    """

    def __init__(self, model_path: str = MODEL_PATH, haar_path: str = HAAR_FACE_PATH):
        self.model_path = model_path
        self.haar_path = haar_path
        
        # Inicializa MediaPipe GestureRecognizer
        self._recognizer = None
        self._init_recognizer()

        # Inicializa Detector de Presença Facial
        self._face_cascade = None
        if os.path.exists(self.haar_path):
            try:
                self._face_cascade = cv2.CascadeClassifier(self.haar_path)
            except Exception as e:
                print(f"[GestureDetector] Aviso ao carregar Haar Cascade: {e}")

        # Buffer temporal de posições do pulso para gestos dinâmicos (Swipes e Zoom)
        self._wrist_history = deque(maxlen=25)
        self._hand_size_history = deque(maxlen=20)
        self._last_swipe_time = 0.0
        self._last_zoom_time = 0.0

    def _init_recognizer(self):
        try:
            BaseOptions = mp.tasks.BaseOptions
            GestureRecognizer = mp.tasks.vision.GestureRecognizer
            GestureRecognizerOptions = mp.tasks.vision.GestureRecognizerOptions
            VisionRunningMode = mp.tasks.vision.RunningMode

            options = GestureRecognizerOptions(
                base_options=BaseOptions(model_asset_path=self.model_path),
                running_mode=VisionRunningMode.IMAGE,
                num_hands=2,
                min_hand_detection_confidence=0.5,
                min_hand_presence_confidence=0.5,
                min_tracking_confidence=0.5
            )
            self._recognizer = GestureRecognizer.create_from_options(options)
            print("[GestureDetector] MediaPipe GestureRecognizer inicializado com sucesso.")
        except Exception as e:
            print(f"[GestureDetector] Erro ao inicializar MediaPipe GestureRecognizer: {e}")

    def process_frame(self, frame_bgr: np.ndarray) -> Dict[str, Any]:
        """
        Analisa um frame de vídeo e extrai:
        - Gestos estáticos das mãos (joinha, punho, mão aberta, dedos, etc.)
        - Gestos dinâmicos temporais (swipes, aproximação/afastamento)
        - Presença do usuário diante da câmera
        - Landmarks para anotação visual
        """
        now = time.time()
        h, w = frame_bgr.shape[:2]

        result = {
            "gesture": "none",
            "confidence": 0.0,
            "hand": "none",
            "landmarks": [],
            "user_present": False,
            "presence_confidence": 0.0,
            "dynamic_gesture": None,
            "timestamp": now
        }

        # 1. DETECÇÃO DE PRESENÇA DO USUÁRIO (Rosto frontal)
        if self._face_cascade is not None and not self._face_cascade.empty():
            try:
                # Downscale para velocidade extrema (< 2ms)
                small_gray = cv2.cvtColor(cv2.resize(frame_bgr, (320, 240)), cv2.COLOR_BGR2GRAY)
                faces = self._face_cascade.detectMultiScale(small_gray, scaleFactor=1.2, minNeighbors=4, minSize=(30, 30))
                if len(faces) > 0:
                    result["user_present"] = True
                    result["presence_confidence"] = 0.95
            except Exception:
                pass

        if self._recognizer is None:
            return result

        # 2. INFERÊNCIA MEDIAPIPE GESTURE RECOGNIZER
        try:
            rgb_frame = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
            recognition_res = self._recognizer.recognize(mp_image)

            if recognition_res.gestures and len(recognition_res.gestures) > 0:
                top_gesture = recognition_res.gestures[0][0]
                category_name = top_gesture.category_name
                score = float(top_gesture.score)

                # Mão detectada (Right / Left)
                hand_label = "right"
                if recognition_res.handedness and len(recognition_res.handedness) > 0:
                    hand_label = recognition_res.handedness[0][0].display_name.lower()

                # Landmarks normalizados (21 nós)
                landmarks = []
                if recognition_res.hand_landmarks and len(recognition_res.hand_landmarks) > 0:
                    for lm in recognition_res.hand_landmarks[0]:
                        landmarks.append({"x": lm.x, "y": lm.y, "z": lm.z})

                # Mapeamento do resultado MediaPipe padrão
                parsed_gesture = self._normalize_mediapipe_gesture(category_name)
                
                # Se o classificador padrão retornar "none" ou "Pointing_Up", refinamos geometricamente
                geometric_gesture, geo_conf = self._analyze_finger_geometry(landmarks, w, h)
                if geometric_gesture and geometric_gesture != "none":
                    parsed_gesture = geometric_gesture
                    score = max(score, geo_conf)

                result["gesture"] = parsed_gesture
                result["confidence"] = round(score, 2)
                result["hand"] = hand_label
                result["landmarks"] = landmarks

                # Se a mão está visível, o usuário também está presente
                if not result["user_present"]:
                    result["user_present"] = True
                    result["presence_confidence"] = 0.88

                # 3. GESTOS DINÂMICOS: SWIPES E APROXIMAÇÃO (TEMPORAL BUFFER)
                if landmarks:
                    wrist = landmarks[0]
                    middle_mcp = landmarks[9]
                    
                    # Distância do pulso ao nó médio (medida de profundidade / tamanho da mão)
                    hand_size = math.sqrt((wrist["x"] - middle_mcp["x"])**2 + (wrist["y"] - middle_mcp["y"])**2)
                    
                    self._wrist_history.append((wrist["x"] * w, wrist["y"] * h, now))
                    self._hand_size_history.append((hand_size, now))

                    dynamic_ev = self._detect_motion_swipes(w, h, now)
                    if dynamic_ev:
                        result["dynamic_gesture"] = dynamic_ev
            else:
                self._wrist_history.clear()
                self._hand_size_history.clear()

        except Exception as e:
            # print(f"[GestureDetector] Erro no processamento: {e}")
            pass

        return result

    def _normalize_mediapipe_gesture(self, category: str) -> str:
        """Converte nomes padrão do MediaPipe para a nomenclatura Jarvis."""
        cat_lower = category.lower()
        if "thumb_up" in cat_lower:
            return "thumbs_up"
        elif "thumb_down" in cat_lower:
            return "thumbs_down"
        elif "closed_fist" in cat_lower or "fist" in cat_lower:
            return "fist"
        elif "open_palm" in cat_lower:
            return "open_hand"
        elif "pointing_up" in cat_lower:
            return "point_up"
        elif "victory" in cat_lower:
            return "peace_sign"
        elif "iloveyou" in cat_lower:
            return "three_fingers"
        return "none"

    def _analyze_finger_geometry(self, landmarks: List[Dict[str, float]], width: int, height: int) -> Tuple[str, float]:
        """
        Análise geométrica precisa de cada um dos 5 dedos:
        - Pontaria para baixo (point_down)
        - Pontaria para direita (point_right)
        - Pontaria para esquerda (point_left)
        - Três dedos estendidos (three_fingers)
        """
        if len(landmarks) < 21:
            return "none", 0.0

        # Nós das pontas (tips) e nós das articulações médias (pips)
        # Polegar: 4, Indicador: 8, Médio: 12, Anelar: 16, Mínimo: 20
        # Pips: Polegar: 2, Indicador: 6, Médio: 10, Anelar: 14, Mínimo: 18
        wrist = landmarks[0]
        thumb_tip, thumb_ip = landmarks[4], landmarks[3]
        index_tip, index_pip = landmarks[8], landmarks[6]
        middle_tip, middle_pip = landmarks[12], landmarks[10]
        ring_tip, ring_pip = landmarks[16], landmarks[14]
        pinky_tip, pinky_pip = landmarks[20], landmarks[18]

        # Verifica se cada dedo está estendido ou recolhido (relativo à distância do pulso)
        def is_finger_extended(tip, pip):
            d_tip = math.sqrt((tip["x"] - wrist["x"])**2 + (tip["y"] - wrist["y"])**2)
            d_pip = math.sqrt((pip["x"] - wrist["x"])**2 + (pip["y"] - wrist["y"])**2)
            return d_tip > (d_pip * 1.25)

        index_ext = is_finger_extended(index_tip, index_pip)
        middle_ext = is_finger_extended(middle_tip, middle_pip)
        ring_ext = is_finger_extended(ring_tip, ring_pip)
        pinky_ext = is_finger_extended(pinky_tip, pinky_pip)

        # Três dedos estendidos (Indicador, Médio e Anelar estendidos, Mínimo recolhido)
        if index_ext and middle_ext and ring_ext and not pinky_ext:
            return "three_fingers", 0.90

        # Dois dedos estendidos (Indicador e Médio, outros recolhidos) -> peace_sign
        if index_ext and middle_ext and not ring_ext and not pinky_ext:
            return "peace_sign", 0.92

        # Apenas Indicador estendido -> Analisa direção do vetor
        if index_ext and not middle_ext and not ring_ext and not pinky_ext:
            dx = (index_tip["x"] - index_pip["x"]) * width
            dy = (index_tip["y"] - index_pip["y"]) * height

            angle_deg = math.degrees(math.atan2(dy, dx))
            # 0 deg = direita, 90 deg = baixo, -90 deg = cima, 180/-180 deg = esquerda
            if 45 <= angle_deg <= 135:
                return "point_down", 0.92
            elif -45 <= angle_deg <= 45:
                return "point_right", 0.90
            elif angle_deg >= 135 or angle_deg <= -135:
                return "point_left", 0.90
            elif -135 <= angle_deg <= -45:
                return "point_up", 0.92

        return "none", 0.0

    def _detect_motion_swipes(self, width: int, height: int, now: float) -> Optional[Dict[str, Any]]:
        """
        Detecta movimentos dinâmicos rápidos (swipes e aproximação) através do buffer temporal.
        """
        if now - self._last_swipe_time < 1.2:
            return None

        if len(self._wrist_history) < 10:
            return None

        p_old = self._wrist_history[0]
        p_now = self._wrist_history[-1]
        dt = p_now[2] - p_old[2]
        if dt <= 0.05 or dt > 0.6:
            return None

        dx = p_now[0] - p_old[0]
        dy = p_now[1] - p_old[1]

        # Velocidade em pixels por segundo
        vx = dx / dt
        vy = dy / dt

        # Swipe Horizontal (mínimo 350 px/s e 70px deslocamento)
        if abs(dx) > 75 and abs(vx) > 320 and abs(dx) > abs(dy) * 1.5:
            self._last_swipe_time = now
            self._wrist_history.clear()
            if dx > 0:
                return {"gesture": "swipe_right", "confidence": 0.91, "delta_px": round(dx, 1)}
            else:
                return {"gesture": "swipe_left", "confidence": 0.91, "delta_px": round(dx, 1)}

        # Swipe Vertical
        if abs(dy) > 70 and abs(vy) > 300 and abs(dy) > abs(dx) * 1.5:
            self._last_swipe_time = now
            self._wrist_history.clear()
            if dy < 0:
                return {"gesture": "swipe_up", "confidence": 0.88, "delta_px": round(dy, 1)}
            else:
                return {"gesture": "swipe_down", "confidence": 0.88, "delta_px": round(dy, 1)}

        # Zoom In / Zoom Out (Aproximação ou Afastamento da mão)
        if len(self._hand_size_history) >= 12 and (now - self._last_zoom_time > 1.8):
            old_size = self._hand_size_history[0][0]
            new_size = self._hand_size_history[-1][0]
            ratio = new_size / (old_size + 1e-5)
            
            if ratio > 1.45:
                self._last_zoom_time = now
                self._hand_size_history.clear()
                return {"gesture": "zoom_in", "confidence": 0.87, "ratio": round(ratio, 2)}
            elif ratio < 0.65:
                self._last_zoom_time = now
                self._hand_size_history.clear()
                return {"gesture": "zoom_out", "confidence": 0.87, "ratio": round(ratio, 2)}

        return None
