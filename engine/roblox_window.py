"""Utility: check if Roblox window is focused."""

from __future__ import annotations

from loguru import logger


def is_roblox_focused() -> bool:
    """Check if Roblox window is the active window."""
    try:
        import pywinctl as pwc
        win = pwc.getActiveWindow()
        return win and "roblox" in win.title.lower()
    except Exception:
        return False


def focus_roblox() -> bool:
    """Try to bring Roblox window to focus."""
    try:
        import pywinctl as pwc
        wins = pwc.getWindowsWithTitle("Roblox")
        if wins:
            wins[0].activate()
            logger.info("Roblox window focused")
            return True
        logger.warning("Roblox window not found")
        return False
    except Exception as e:
        logger.error(f"Failed to focus Roblox: {e}")
        return False
