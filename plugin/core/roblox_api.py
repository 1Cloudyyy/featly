"""Roblox API client — validate usernames, send friend requests.

Логирование на каждом этапе: получение CSRF, резолв ника, отправка заявки.
RobloxAuthError — единственное исключение, которое должно всплывать (протухший cookie).

Все запросы выполняются в отдельном потоке через стандартный urllib
(asyncio.to_thread) — не привязаны к event loop funpay-universal
(см. backend_client: «Event loop is closed»).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import urllib.error
import urllib.request

from ..meta import NAME
from ..settings import load_settings

log = logging.getLogger(f"{NAME}.roblox")

ROBLOX_USERS_URL = "https://users.roblox.com/v1/usernames/users"
ROBLOX_FRIENDS_URL = "https://friends.roblox.com/v1/users/{user_id}/request-friendship"
ROBLOX_CSRF_URL = "https://auth.roblox.com/v2/logout"

REQUEST_TIMEOUT = 15  # сек


class RobloxAuthError(Exception):
    """Cookie (.ROBLOSECURITY) некорректен или протух."""


def _sync_request(
    url: str, method: str = "POST", headers: dict[str, str] | None = None, payload: bytes | None = None
) -> tuple[int, bytes]:
    """Синхронный HTTP-запрос (выполняется в потоке через to_thread)."""
    req = urllib.request.Request(url, data=payload, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        raise RuntimeError(f"HTTP {method} {url}: {e!r}") from e


async def _request(url: str, method: str = "POST", headers: dict[str, str] | None = None, payload: bytes | None = None) -> tuple[int, bytes]:
    return await asyncio.to_thread(_sync_request, url, method, headers, payload)


def _sync_csrf(cookie: str) -> str:
    """Синхронный pre-flight к auth.roblox.com — с доступом к заголовкам ответа."""
    import http.client
    from urllib.parse import urlparse

    parsed = urlparse(ROBLOX_CSRF_URL)
    conn = http.client.HTTPSConnection(parsed.hostname, timeout=REQUEST_TIMEOUT)
    try:
        conn.request("POST", parsed.path, headers={"Cookie": f".ROBLOSECURITY={cookie}"})
        resp = conn.getresponse()
        resp.read()
        return resp.getheader("x-csrf-token", "")
    finally:
        conn.close()


async def _get_csrf_token(cookie: str) -> str:
    """Получить X-CSRF-TOKEN через pre-flight запрос."""
    started = time.perf_counter()
    try:
        token = await asyncio.to_thread(_sync_csrf, cookie)
        if not token:
            raise RobloxAuthError("CSRF не получен — cookie может быть невалиден")
        log.debug("CSRF-токен получен (%.1f ms)", (time.perf_counter() - started) * 1000)
        return token
    except RobloxAuthError:
        raise
    except Exception as e:
        ms = (time.perf_counter() - started) * 1000
        log.error("CSRF-запрос упал (%.1f ms): %r", ms, e)
        raise RobloxAuthError(f"CSRF-запрос упал: {e!r}") from e


async def validate_username(username: str) -> int | None:
    """Резолв ника в userId. None — не найден/ошибка."""
    payload = json.dumps({"usernames": [username], "excludeBannedUsers": False}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    started = time.perf_counter()
    try:
        status, raw = await _request(ROBLOX_USERS_URL, "POST", headers, payload)
        ms = (time.perf_counter() - started) * 1000
        if status != 200:
            log.warning("validate_username('%s') → %s (%.1f ms)", username, status, ms)
            return None
        data = json.loads(raw.decode("utf-8", errors="replace"))
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
        csrf_token = await _get_csrf_token(cookie)
        url = ROBLOX_FRIENDS_URL.format(user_id=user_id)
        headers = {
            "Cookie": f".ROBLOSECURITY={cookie}",
            "X-CSRF-TOKEN": csrf_token,
            "Content-Type": "application/json",
        }
        status, raw = await _request(url, "POST", headers, b"{}")
        ms = (time.perf_counter() - started) * 1000
        if status == 401:
            raise RobloxAuthError("Roblox cookie протух — /roblox_cookie")
        if status == 200:
            log.info("Заявка в друзья отправлена userId=%s (%.1f ms)", user_id, ms)
            return True
        body = raw.decode("utf-8", errors="replace")
        log.warning("Заявка в друзья userId=%s → HTTP %s (%.1f ms): %s", user_id, status, ms, body[:200])
        return False
    except RobloxAuthError:
        raise
    except Exception as e:
        log.error("request_friendship(userId=%s) → исключение: %r", user_id, e)
        raise RobloxAuthError(f"Ошибка сети при заявке в друзья: {e!r}") from e