"""Roblox API client — validate usernames, send friend requests.

Логирование на каждом этапе: получение CSRF, резолв ника, отправка заявки.
RobloxAuthError — единственное исключение, которое должно всплывать (протухший cookie).
"""

from __future__ import annotations

import logging
import time

import aiohttp

from ..meta import NAME
from ..settings import load_settings

log = logging.getLogger(f"{NAME}.roblox")

ROBLOX_USERS_URL = "https://users.roblox.com/v1/usernames/users"
ROBLOX_FRIENDS_URL = "https://friends.roblox.com/v1/users/{user_id}/request-friendship"
ROBLOX_CSRF_URL = "https://auth.roblox.com/v2/logout"


class RobloxAuthError(Exception):
    """Cookie (.ROBLOSECURITY) некорректен или протух."""


async def _get_csrf_token(session: aiohttp.ClientSession, cookie: str) -> str:
    """Получить X-CSRF-TOKEN через pre-flight запрос."""
    headers = {"Cookie": f".ROBLOSECURITY={cookie}"}
    started = time.perf_counter()
    try:
        async with session.post(ROBLOX_CSRF_URL, headers=headers) as resp:
            token = resp.headers.get("x-csrf-token", "")
            ms = (time.perf_counter() - started) * 1000
            if not token:
                raise RobloxAuthError(
                    f"CSRF не получен (status={resp.status}) — cookie может быть невалиден"
                )
            log.debug("CSRF-токен получен (%.1f ms)", ms)
            return token
    except aiohttp.ClientError as e:
        ms = (time.perf_counter() - started) * 1000
        log.error("CSRF-запрос упал (%.1f ms): %r", ms, e)
        raise RobloxAuthError(f"CSRF-запрос упал: {e!r}") from e


async def validate_username(username: str) -> int | None:
    """Резолв ника в userId. None — не найден/ошибка."""
    payload = {"usernames": [username], "excludeBannedUsers": False}
    started = time.perf_counter()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(ROBLOX_USERS_URL, json=payload) as resp:
                ms = (time.perf_counter() - started) * 1000
                if resp.status != 200:
                    log.warning("validate_username('%s') → %s (%.1f ms)", username, resp.status, ms)
                    return None
                data = await resp.json()
                users = data.get("data", [])
                if not users:
                    log.info("validate_username('%s'): пользователь не найден (%.1f ms)", username, ms)
                    return None
                uid = users[0].get("id")
                log.info("validate_username('%s') → userId=%s (%.1f ms)", username, uid, ms)
                return uid
    except Exception as e:
        log.error("validate_username('%s') → исключение: %r", username, e)
        return None


async def request_friendship(user_id: int) -> bool:
    """Отправить заявку в друзья. RobloxAuthError — cookie протух."""
    settings = load_settings()
    cookie = settings.get("roblox_cookie", "")
    if not cookie:
        raise RobloxAuthError("Файл настроек: roblox_cookie не задан")

    started = time.perf_counter()
    try:
        async with aiohttp.ClientSession() as session:
            csrf_token = await _get_csrf_token(session, cookie)
            url = ROBLOX_FRIENDS_URL.format(user_id=user_id)
            headers = {
                "Cookie": f".ROBLOSECURITY={cookie}",
                "X-CSRF-TOKEN": csrf_token,
                "Content-Type": "application/json",
            }
            async with session.post(url, headers=headers, json={}) as resp:
                ms = (time.perf_counter() - started) * 1000
                if resp.status == 401:
                    raise RobloxAuthError("Roblox cookie протух — /roblox_cookie")
                if resp.status == 200:
                    log.info("Заявка в друзья отправлена userId=%s (%.1f ms)", user_id, ms)
                    return True
                body = await resp.text()
                log.warning("Заявка в друзья userId=%s → %s (%.1f ms): %s", user_id, resp.status, ms, body[:200])
                return False
    except RobloxAuthError:
        raise
    except Exception as e:
        log.error("request_friendship(userId=%s) → исключение: %r", user_id, e)
        raise RobloxAuthError(f"Ошибка сети при заявке в друзья: {e!r}") from e