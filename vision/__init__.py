"""
J.A.R.V.I.S. Computer Vision Subsystem
Multimodal Edge Vision Engine with MediaPipe, OpenCV, Real-time Gesture Detection and Windows Control.
"""

from .config import VisionConfig
from .camera import CameraCapture
from .gestures import GestureDetector
from .events import VisionEventBus, VisionEvent
from .actions import WindowsActions
from .engine import VisionEngine

__all__ = [
    "VisionConfig",
    "CameraCapture",
    "GestureDetector",
    "VisionEventBus",
    "VisionEvent",
    "WindowsActions",
    "VisionEngine"
]
