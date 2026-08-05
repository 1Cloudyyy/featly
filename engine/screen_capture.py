"""Screen capture — fast screenshots via mss."""

from __future__ import annotations

import numpy as np
import cv2
import mss
from loguru import logger


class ScreenCapture:
    """Fast screen capture using mss."""

    def __init__(self) -> None:
        self._sct = mss.mss()

    def capture_full(self) -> np.ndarray:
        """Capture full screen as BGR numpy array."""
        screenshot = self._sct.grab(self._sct.monitors[0])
        # mss returns BGRA, convert to BGR for OpenCV
        frame = np.array(screenshot)
        return cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

    def capture_region(self, region: tuple[int, int, int, int]) -> np.ndarray:
        """Capture specific region (x, y, width, height) as BGR numpy array."""
        x, y, w, h = region
        monitor = {"left": x, "top": y, "width": w, "height": h}
        screenshot = self._sct.grab(monitor)
        frame = np.array(screenshot)
        return cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

    def capture_region_gray(self, region: tuple[int, int, int, int]) -> np.ndarray:
        """Capture region and convert to grayscale."""
        bgr = self.capture_region(region)
        return cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    def close(self) -> None:
        self._sct.close()


# Singleton
screen = ScreenCapture()


def capture_screen() -> np.ndarray:
    """Convenience function — full screen capture."""
    return screen.capture_full()


def capture_region(region: tuple[int, int, int, int]) -> np.ndarray:
    """Convenience function — region capture."""
    return screen.capture_region(region)
