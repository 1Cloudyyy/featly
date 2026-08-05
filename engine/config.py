"""Windows Engine configuration — loaded from YAML + env vars."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from loguru import logger
from pydantic import BaseModel


class Regions(BaseModel):
    """Screen regions for template matching (x, y, width, height)."""

    trade_request: tuple[int, int, int, int] = (0, 0, 100, 100)
    accept_button: tuple[int, int, int, int] = (0, 0, 100, 100)
    search_box: tuple[int, int, int, int] = (0, 0, 100, 100)
    your_offer: tuple[int, int, int, int] = (0, 0, 100, 100)
    confirm_button: tuple[int, int, int, int] = (0, 0, 100, 100)
    reconnect_button: tuple[int, int, int, int] = (0, 0, 100, 100)
    mm2_hud: tuple[int, int, int, int] = (0, 0, 100, 100)
    you_have_accepted: tuple[int, int, int, int] = (0, 0, 100, 100)


class EngineConfig(BaseModel):
    """Full engine configuration."""

    # WebSocket
    ws_url: str = "ws://localhost:8000/ws/engine"
    ws_secret: str = "change-me-in-production"
    bot_id: str = "bot_main"
    ws_heartbeat_interval: int = 30

    # Screen capture
    scan_interval: float = 2.0  # seconds between screen scans
    template_threshold: float = 0.8  # OpenCV matchTemplate threshold

    # Anti-AFK
    anti_afk_interval: int = 300  # seconds between anti-AFK actions
    anti_afk_enabled: bool = True

    # Trade flow
    trade_confirm_delay: float = 6.0  # seconds to wait for green Accept
    ocr_enabled: bool = True

    # Regions (overridden by profile)
    regions: Regions = Regions()


CONFIG_DIR = Path(__file__).parent
PROFILES_DIR = CONFIG_DIR / "profiles"
TEMPLATES_DIR = CONFIG_DIR / "templates"


def load_config(profile: str = "mm2") -> EngineConfig:
    """Load engine config, optionally merging with a game profile."""
    config = EngineConfig()

    # Override from env vars
    if ws_url := os.getenv("FEATLY_WS_URL"):
        config.ws_url = ws_url
    if ws_secret := os.getenv("FEATLY_WS_SECRET"):
        config.ws_secret = ws_secret
    if bot_id := os.getenv("FEATLY_BOT_ID"):
        config.bot_id = bot_id

    # Try loading profile
    profile_path = PROFILES_DIR / f"{profile}.yaml"
    if profile_path.exists():
        try:
            data = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
            if data:
                if "regions" in data:
                    config.regions = Regions(**data["regions"])
                for key, value in data.items():
                    if key != "regions" and hasattr(config, key):
                        setattr(config, key, value)
            logger.info(f"Loaded profile: {profile}")
        except Exception as e:
            logger.error(f"Failed to load profile {profile}: {e}")

    return config
