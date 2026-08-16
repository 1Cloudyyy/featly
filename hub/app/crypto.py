"""Шифрование секретов hub (roblox_cookie и т.п.).

Ключ: FEATLY_COOKIE_KEY (env). Если не задан — генерируется один раз и сохраняется
в файл `.env` рядом с hub (чтобы при рестарте ключ не менялся). Fernet-ключ
нормализуется (urlsafe base64 с padding), поэтому подходят и токены token_urlsafe.
"""

from __future__ import annotations

import base64
import logging
import os
import secrets
from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

log = logging.getLogger("featly.crypto")

ENV_KEY_NAME = "FEATLY_COOKIE_KEY"


def _env_file() -> Path:
    """Файл .env в корне репозитория (gitignored)."""
    here = Path(__file__).resolve()
    # hub/app/crypto.py → корень репо / .env
    return here.parent.parent.parent / ".env"


def _normalize_key(key: str) -> bytes:
    """Привести ключ к 32-байтному urlsafe base64 с padding (формат Fernet)."""
    raw = key.encode("utf-8")
    try:
        decoded = base64.urlsafe_b64decode(raw + b"=" * (-len(raw) % 4))
    except Exception:
        raise ValueError("FEATLY_COOKIE_KEY не похож на base64 — сгенерируй новый")
    if len(decoded) != 32:
        raise ValueError("FEATLY_COOKIE_KEY должен быть 32 байта (base64url)")
    return base64.urlsafe_b64encode(decoded).decode("utf-8")


def _load_or_create_key() -> str:
    key = os.getenv(ENV_KEY_NAME, "").strip()
    if key:
        return _normalize_key(key)

    # Персистентный файл .env
    env_path = _env_file()
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith(f"{ENV_KEY_NAME}="):
                return _normalize_key(line.split("=", 1)[1].strip())

    # Генерация и сохранение один раз
    new_key = Fernet.generate_key().decode("utf-8")
    line = f"{ENV_KEY_NAME}={new_key}\n"
    try:
        env_path.parent.mkdir(parents=True, exist_ok=True)
        with env_path.open("a", encoding="utf-8") as fh:
            fh.write(line)
        log.warning("%s не задан — сгенерирован и сохранён в %s", ENV_KEY_NAME, env_path)
    except Exception as e:
        log.error("Не удалось сохранить ключ в %s: %s", env_path, e)
        log.critical("FEATLY_COOKIE_KEY не задан и не персистентен — ключ будет новым после рестарта!")
    return _normalize_key(new_key)


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    return Fernet(_load_or_create_key())


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as e:
        log.error("Не удалось расшифровать (ключ сменился?)")
        raise ValueError("cookie decrypt failed") from e