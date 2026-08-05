"""OCR module — text recognition via pytesseract."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytesseract
from loguru import logger


class OCRReader:
    """Text recognition from screenshots."""

    def __init__(self) -> None:
        # Try common Tesseract paths on Windows
        default_paths = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ]
        for path in default_paths:
            if Path(path).exists():
                pytesseract.pytesseract.tesseract_cmd = path
                break

    def read_text(
        self,
        image: np.ndarray,
        region: tuple[int, int, int, int] | None = None,
        preprocess: str = "thresh",
    ) -> str:
        """Read text from image/region.

        Args:
            image: BGR numpy array
            region: optional (x, y, w, h) to crop
            preprocess: preprocessing type ('thresh', 'blur', 'none')

        Returns:
            Extracted text string
        """
        if region:
            x, y, w, h = region
            image = image[y : y + h, x : x + w]

        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Preprocessing
        if preprocess == "thresh":
            gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
        elif preprocess == "blur":
            gray = cv2.medianBlur(gray, 3)

        # OCR
        text = pytesseract.image_to_string(gray, config="--psm 7").strip()
        return text

    def read_text_region(
        self,
        screenshot_fn,
        region: tuple[int, int, int, int],
        preprocess: str = "thresh",
    ) -> str:
        """Capture region and read text."""
        screenshot = screenshot_fn()
        return self.read_text(screenshot, region, preprocess)

    def find_text(
        self,
        image: np.ndarray,
        text: str,
        region: tuple[int, int, int, int] | None = None,
    ) -> bool:
        """Check if text exists in image."""
        found_text = self.read_text(image, region)
        return text.lower() in found_text.lower()

    def read_nickname_from_trade(
        self, screenshot: np.ndarray, region: tuple[int, int, int, int] | None = None
    ) -> str | None:
        """Read buyer's nickname from trade window.

        Tries to extract the nickname from the trade request popup.
        Returns None if no valid nickname found.
        """
        text = self.read_text(screenshot, region, preprocess="thresh")
        # Clean up common OCR errors
        text = text.strip()
        if not text or len(text) < 2:
            return None
        # Remove non-alphanumeric chars except underscore
        cleaned = "".join(c for c in text if c.isalnum() or c == "_")
        return cleaned if cleaned else None


# Singleton
ocr = OCRReader()
