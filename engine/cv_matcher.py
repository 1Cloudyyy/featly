"""Computer vision matcher — OpenCV template matching."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from loguru import logger

TEMPLATES_DIR = Path(__file__).parent / "templates"

# Cache loaded templates
_template_cache: dict[str, np.ndarray] = {}


def _load_template(name: str) -> np.ndarray | None:
    """Load and cache a template image."""
    if name in _template_cache:
        return _template_cache[name]

    path = TEMPLATES_DIR / name
    if not path.exists():
        logger.warning(f"Template not found: {path}")
        return None

    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        logger.error(f"Failed to load template: {path}")
        return None

    _template_cache[name] = img
    return img


def detect_template(
    screenshot: np.ndarray,
    template_name: str,
    threshold: float = 0.8,
    region: tuple[int, int, int, int] | None = None,
) -> tuple[bool, tuple[int, int] | None]:
    """Detect a template in screenshot.

    Args:
        screenshot: BGR numpy array (full screen or region)
        template_name: filename in templates/ dir
        threshold: match confidence (0.0 - 1.0)
        optional region to search within (x, y, w, h)

    Returns:
        (found, center_x, center_y) or (False, None)
    """
    template = _load_template(template_name)
    if template is None:
        return False, None

    # Crop to region if specified
    if region:
        x, y, w, h = region
        search_area = screenshot[y : y + h, x : x + w]
    else:
        search_area = screenshot
        x, y = 0, 0

    # Convert to grayscale for matching
    gray_screen = cv2.cvtColor(search_area, cv2.COLOR_BGR2GRAY)
    gray_template = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)

    # Template matching
    result = cv2.matchTemplate(gray_screen, gray_template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)

    if max_val >= threshold:
        # Calculate center of matched region
        th, tw = gray_template.shape[:2]
        center_x = x + max_loc[0] + tw // 2
        center_y = y + max_loc[1] + th // 2
        logger.debug(f"Template '{template_name}' found at ({center_x}, {center_y}) conf={max_val:.3f}")
        return True, (center_x, center_y)

    return False, None


def wait_for_template(
    screenshot_fn,
    template_name: str,
    threshold: float = 0.8,
    timeout: float = 30.0,
    interval: float = 0.5,
    region: tuple[int, int, int, int] | None = None,
) -> tuple[bool, tuple[int, int] | None]:
    """Synchronously wait for a template to appear.

    Args:
        screenshot_fn: callable that returns BGR numpy array
        template_name: filename in templates/
        threshold: match confidence
        timeout: max wait time in seconds
        interval: time between attempts
        region: optional region to search

    Returns:
        (found, center) or (False, None) after timeout
    """
    import time

    start = time.monotonic()
    while time.monotonic() - start < timeout:
        screenshot = screenshot_fn()
        found, center = detect_template(screenshot, template_name, threshold, region)
        if found:
            return True, center
        time.sleep(interval)

    logger.warning(f"Template '{template_name}' not found after {timeout}s")
    return False, None


def clear_template_cache() -> None:
    """Clear the template cache."""
    _template_cache.clear()
