"""Input controller — keyboard/mouse via pydirectinput-rgx."""

from __future__ import annotations

import asyncio
import random

import pydirectinput as pdi
from loguru import logger

# Disable failsafe (moving mouse to corner won't abort)
pdi.FAILSAFE = False


def click(x: int, y: int, button: str = "left") -> None:
    """Click at coordinates."""
    logger.debug(f"Click ({x}, {y}) button={button}")
    pdi.click(x, y, button=button)


def double_click(x: int, y: int) -> None:
    """Double-click at coordinates."""
    logger.debug(f"Double click ({x}, {y})")
    pdi.doubleClick(x, y)


def move_to(x: int, y: int, duration: float = 0.2) -> None:
    """Move mouse to coordinates."""
    pdi.moveTo(x, y, duration=duration)


def move_relative(dx: int, dy: int, duration: float = 0.2) -> None:
    """Move mouse relative to current position."""
    pdi.moveRel(dx, dy, duration=duration)


def type_text(text: str, interval: float = 0.02) -> None:
    """Type text using keyboard."""
    logger.debug(f"Type: {text}")
    pdi.typewrite(text, interval=interval)


def press_key(key: str) -> None:
    """Press a single key."""
    logger.debug(f"Press: {key}")
    pdi.press(key)


def key_down(key: str) -> None:
    """Hold a key down."""
    pdi.keyDown(key)


def key_up(key: str) -> None:
    """Release a key."""
    pdi.keyUp(key)


async def async_click(x: int, y: int, button: str = "left") -> None:
    """Async click."""
    await asyncio.to_thread(click, x, y, button)


async def async_type(text: str, interval: float = 0.02) -> None:
    """Async type text."""
    await asyncio.to_thread(type_text, text, interval)


async def async_press(key: str) -> None:
    """Async key press."""
    await asyncio.to_thread(press_key, key)


# --- Anti-AFK ---

async def anti_afk_action() -> None:
    """Perform a random anti-AFK action."""
    action = random.choice(["camera", "jump", "walk"])
    logger.debug(f"Anti-AFK: {action}")

    if action == "camera":
        dx = random.randint(-200, 200)
        dy = random.randint(-100, 100)
        await asyncio.to_thread(move_relative, dx, dy, 0.5)
    elif action == "jump":
        await async_press("space")
    elif action == "walk":
        key = random.choice(["w", "a", "s", "d"])
        await asyncio.to_thread(key_down, key)
        await asyncio.sleep(0.3)
        await asyncio.to_thread(key_up, key)
