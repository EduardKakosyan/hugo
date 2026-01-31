"""OpenCV camera capture – returns numpy frames and JPEG bytes."""

import logging

import cv2
import numpy as np

from src.config import settings

logger = logging.getLogger("hugo.vision.camera")


class Camera:
    def __init__(self, index: int = settings.camera_index) -> None:
        self.index = index
        self._cap: cv2.VideoCapture | None = None

    def open(self) -> None:
        self._cap = cv2.VideoCapture(self.index)
        if not self._cap.isOpened():
            raise RuntimeError(f"Cannot open camera {self.index}")
        logger.info("Camera %d opened", self.index)

    def capture_frame(self) -> np.ndarray:
        if self._cap is None:
            self.open()
        assert self._cap is not None
        ret, frame = self._cap.read()
        if not ret:
            raise RuntimeError("Failed to capture frame")
        return frame

    def capture_jpeg(self, quality: int = 85) -> bytes:
        frame = self.capture_frame()
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not ok:
            raise RuntimeError("Failed to encode JPEG")
        return buf.tobytes()

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
            logger.info("Camera %d closed", self.index)


camera = Camera()
