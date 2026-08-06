"""Utility: check if Roblox window is focused."""

from __future__ import annotations

from loguru import logger


def is_roblox_focused() -> bool:
    """Check if Roblox window is the active window."""
    try:
        import pywinctl as pwc
        win = pwc.getActiveWindow()
        if not win:
            return False
        title = win.title.lower()
        return "roblox" in title or "mm2" in title
    except Exception:
        return False


def focus_roblox() -> bool:
    """Try to bring Roblox window to focus."""
    try:
        import pywinctl as pwc
        # Case-insensitive search
        wins = pwc.getWindowsWithTitle("Roblox") or pwc.getWindowsWithTitle("roblox")
        if not wins:
            logger.warning("Roblox window not found")
            return False
        wins[0].activate()
        logger.info("Roblox window focused")
        return True
    except Exception as e:
        logger.error(f"Failed to focus Roblox: {e}")
        return False
