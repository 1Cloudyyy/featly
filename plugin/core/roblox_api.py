"""Roblox API client — validate usernames, send friend requests."""

from __future__ import annotations

import aiohttp
from loguru import logger

from plugin.settings import load_settings

ROBLOX_USERS_URL = "https://users.roblox.com/v1/usernames/users"
ROBLOX_FRIENDS_URL = "https://friends.roblox.com/v1/users/{user_id}/request-friendship"
ROBLOX_CSRF_URL = "https://auth.roblox.com/v2/logout"


class RobloxAuthError(Exception):
    """Cookie (.ROBLOSECURITY) is invalid or expired."""


async def _get_csrf_token(session: aiohttp.ClientSession, cookie: str) -> str:
    """Get X-CSRF-TOKEN via pre-flight request."""
    headers = {"Cookie": f".ROBLOSECURITY={cookie}"}
    async with session.post(ROBLOX_CSRF_URL, headers=headers) as resp:
        token = resp.headers.get("x-csrf-token", "")
        if not token:
            raise RobloxAuthError("Could not obtain CSRF token — cookie may be invalid")
        return token


async def validate_username(username: str) -> int | None:
    """Resolve Roblox username to userId. Returns None if not found."""
    payload = {"usernames": [username], "excludeBannedUsers": False}
    async with aiohttp.ClientSession() as session:
        async with session.post(ROBLOX_USERS_URL, json=payload) as resp:
            if resp.status != 200:
                logger.error(f"Roblox validate_username failed: {resp.status}")
                return None
            data = await resp.json()
            users = data.get("data", [])
            if not users:
                return None
            return users[0].get("id")


async def request_friendship(user_id: int) -> bool:
    """Send friend request via Roblox API. Raises RobloxAuthError on 401."""
    settings = load_settings()
    cookie = settings.get("roblox_cookie", "")
    if not cookie:
        raise RobloxAuthError("No .ROBLOSECURITY cookie configured")

    async with aiohttp.ClientSession() as session:
        csrf_token = await _get_csrf_token(session, cookie)
        url = ROBLOX_FRIENDS_URL.format(user_id=user_id)
        headers = {
            "Cookie": f".ROBLOSECURITY={cookie}",
            "X-CSRF-TOKEN": csrf_token,
            "Content-Type": "application/json",
        }
        async with session.post(url, headers=headers, json={}) as resp:
            if resp.status == 401:
                raise RobloxAuthError("Roblox cookie expired — run /roblox_cookie")
            if resp.status == 200:
                logger.info(f"Friend request sent to user {user_id}")
                return True
            body = await resp.text()
            logger.warning(f"Friend request failed ({resp.status}): {body}")
            return False
