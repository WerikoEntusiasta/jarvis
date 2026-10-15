import cv2
import time
import threading
from typing import Optional, Tuple, Dict, Any
import numpy as np

class CameraCapture:
    """
    High-performance thread-safe camera capture pipeline for Jarvis Vision.
    - Captures at target FPS (e.g. 30 FPS).
    - Releases hardware resources when disabled (0% CPU/GPU overhead in standby).
    - Measures real-time FPS and latency.
    """

    def __init__(self, device_index: int = 1, width: int = 640, height: int = 480, fps_target: int = 30):
        self.device_index = device_index
        self.width = width
        self.height = height
        self.fps_target = fps_target
        
        self._cap: Optional[cv2.VideoCapture] = None
        self._is_running = False
        self._is_enabled = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        
        self._latest_frame: Optional[np.ndarray] = None
        self._frame_timestamp: float = 0.0
        self._fps_real: float = 0.0
        self._frame_count: int = 0
        self._last_fps_calc_time: float = time.time()
        self._fps_window_count: int = 0
        self._camera_name = f"Camera #{device_index}"

    def start(self):
        """Starts the capture background thread."""
        if self._is_running:
            return
        self._is_running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True, name="JarvisCameraThread")
        self._thread.start()

    def enable(self):
        """Activates camera hardware capturing."""
        with self._lock:
            self._is_enabled = True

    def disable(self):
        """Puts camera in standby, releasing hardware handle to save 100% CPU."""
        with self._lock:
            self._is_enabled = False
            self._release_camera()
            self._latest_frame = None

    def toggle(self) -> bool:
        if self.is_enabled():
            self.disable()
            return False
        else:
            self.enable()
            return True

    def is_enabled(self) -> bool:
        with self._lock:
            return self._is_enabled

    def get_frame(self) -> Tuple[bool, Optional[np.ndarray], float]:
        """Returns (success, frame, timestamp)."""
        with self._lock:
            if not self._is_enabled or self._latest_frame is None:
                return False, None, 0.0
            return True, self._latest_frame.copy(), self._frame_timestamp

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "enabled": self._is_enabled,
                "fps": round(self._fps_real, 1),
                "device": self._camera_name,
                "device_index": self.device_index,
                "resolution": f"{self.width}x{self.height}",
                "timestamp": self._frame_timestamp
            }

    def _init_camera(self) -> bool:
        if self._cap is not None and self._cap.isOpened():
            return True
        
        # Ordem de tentativa: primeiro o configurado, depois fallbacks
        candidates = [self.device_index]
        for idx in [1, 0, 2]:
            if idx not in candidates:
                candidates.append(idx)

        for idx in candidates:
            try:
                cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
                if not cap.isOpened():
                    cap = cv2.VideoCapture(idx)
                
                if cap.isOpened():
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                    cap.set(cv2.CAP_PROP_FPS, self.fps_target)

                    # Testa se produz imagem real e não tela preta (brilho > 2.0)
                    ret, test_frame = cap.read()
                    if ret and test_frame is not None and test_frame.mean() > 2.0:
                        self.device_index = idx
                        self._cap = cap
                        self._camera_name = f"Webcam Device #{idx} (Ativa, Brilho {test_frame.mean():.1f})"
                        print(f"[CameraCapture] Câmera #{idx} conectada e verificada ({self.width}x{self.height}, Brilho {test_frame.mean():.1f}).")
                        return True
                    else:
                        cap.release()
            except Exception as e:
                print(f"[CameraCapture] Erro ao testar câmera #{idx}: {e}")

        # Se nenhum passou no teste de brilho, tenta abrir o padrão de qualquer forma
        try:
            cap = cv2.VideoCapture(self.device_index, cv2.CAP_DSHOW)
            if cap.isOpened():
                self._cap = cap
                print(f"[CameraCapture] Câmera #{self.device_index} aberta como fallback.")
                return True
        except Exception:
            pass

        return False

    def _release_camera(self):
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None

    def _capture_loop(self):
        desired_frame_time = 1.0 / max(1, self.fps_target)
        
        while self._is_running:
            if not self._is_enabled:
                time.sleep(0.1)
                continue

            if self._cap is None or not self._cap.isOpened():
                if not self._init_camera():
                    time.sleep(1.0)
                    continue

            t_start = time.time()
            ret, frame = self._cap.read()
            now = time.time()

            if ret and frame is not None:
                with self._lock:
                    self._latest_frame = frame
                    self._frame_timestamp = now
                    self._frame_count += 1
                    self._fps_window_count += 1
                
                # Cálculo de FPS real a cada 0.5s
                if now - self._last_fps_calc_time >= 0.5:
                    elapsed = now - self._last_fps_calc_time
                    with self._lock:
                        self._fps_real = self._fps_window_count / elapsed
                        self._fps_window_count = 0
                    self._last_fps_calc_time = now
            else:
                time.sleep(0.02)

            # Mantém cadência de FPS
            t_process = time.time() - t_start
            sleep_time = desired_frame_time - t_process
            if sleep_time > 0:
                time.sleep(sleep_time)

        self._release_camera()

    def stop(self):
        self._is_running = False
        self.disable()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
