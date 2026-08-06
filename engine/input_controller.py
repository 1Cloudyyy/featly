"""Input controller — keyboard/mouse via pydirectinput-rgx."""

from __future__ import annotations

import asyncio
import random

import pydirectinput as pdi
from loguru import logger

# Enable FAILSAFE (move mouse to corner to abort)
pdi.FAILSAFE = True
pdi.PAUSE = 0.05

_emergency_stop = False


def set_emergency_stop(value: bool) -> None:
    global _emergency_stop
    _emergency_stop = value
    logger.warning(f"Emergency stop: {value}")


def is_emergency_stop() -> bool:
    return _emergency_stop


def _check_stop() -> None:
    if _emergency_stop:
        raise RuntimeError("Emergency stop activated")


def click(x: int, y: int, button: str = "left") -> None:
    _check_stop()
    logger.debug(f"Click ({x}, {y}) button={button}")
    pdi.click(x, y, button=button)


def double_click(x: int, y: int) -> None:
    _check_stop()
    logger.debug(f"Double click ({x}, {y})")
    pdi.doubleClick(x, y)


def move_to(x: int, y: int, duration: float = 0.2) -> None:
    _check_stop()
    pdi.moveTo(x, y, duration=duration)


def move_relative(dx: int, dy: int, duration: float = 0.2) -> None:
    _check_stop()
    pdi.moveRel(dx, dy, duration=duration)


def type_text(text: str, interval: float = 0.02) -> None:
    _check_stop()
    logger.debug(f"Type: {text}")
    pdi.typewrite(text, interval=interval)


def press_key(key: str) -> None:
    _check_stop()
    logger.debug(f"Press: {key}")
    pdi.press(key)


def key_down(key: str) -> None:
    _check_stop()
    pdi.keyDown(key)


def key_up(key: str) -> None:
    _check_stop()
    pdi.keyUp(key)


async def async_click(x: int, y: int, button: str = "left") -> None:
    await asyncio.to_thread(click, x, y, button)


async def async_type(text: str, interval: float = 0.02) -> None:
    await asyncio.to_thread(type_text, text, interval)


async def async_press(key: str) -> None:
    await asyncio.to_thread(press_key, key)


# --- Anti-AFK ---

async def anti_afk_action() -> None:
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
