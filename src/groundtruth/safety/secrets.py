"""Fernet-based encryption for stored credentials.

The encryption key is read from GT_SECRET_KEY or from a local key file.
Tokens are encrypted individually so the connection store keeps metadata
(debuggable) separate from secrets (opaque).
"""

from __future__ import annotations

import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from groundtruth.config import PROJECT_ROOT


class DecryptError(Exception):
    """Raised when a stored secret cannot be decrypted."""


KEY_ENV = "GT_SECRET_KEY"
KEY_PATH = PROJECT_ROOT / ".groundtruth" / "secret.key"


def _load_or_create_key() -> bytes:
    env_key = os.getenv(KEY_ENV, "").strip()
    if env_key:
        return env_key.encode("utf-8")

    if KEY_PATH.exists():
        return KEY_PATH.read_bytes()

    key = Fernet.generate_key()
    KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = KEY_PATH.with_suffix(".key.tmp")
    tmp.write_bytes(key)
    os.replace(tmp, KEY_PATH)
    try:
        os.chmod(KEY_PATH, 0o600)
    except OSError:
        pass  # Windows does not enforce Unix file modes.
    return key


def _fernet() -> Fernet:
    return Fernet(_load_or_create_key())


def encrypt(plaintext: str) -> str:
    """Return a Fernet token string for the plaintext."""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(ciphertext: str) -> str:
    """Decrypt a Fernet token string, raising DecryptError on failure."""
    try:
        return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise DecryptError(
            "Stored connection cannot be decrypted — the encryption key changed. "
            "Reconnect your accounts in Settings."
        ) from exc
