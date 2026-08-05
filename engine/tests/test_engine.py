"""Engine tests — placeholder for unit tests."""

import pytest


def test_config_loads():
    """Test that config loads with default values."""
    from engine.config import EngineConfig

    config = EngineConfig()
    assert config.ws_url == "ws://localhost:8000/ws/engine"
    assert config.scan_interval == 2.0


def test_waitlist_manager():
    """Test waitlist add/remove."""
    from engine.waitlist_manager import WaitlistManager

    wl = WaitlistManager()
    assert len(wl.waitlist) == 0

    wl.add({"buyer_nickname": "test_user", "order_id": 1, "items": ["Batwing"]})
    assert len(wl.waitlist) == 1
    assert wl.is_in_waitlist("test_user")

    wl.remove_by_buyer("test_user")
    assert len(wl.waitlist) == 0
