"""PRIV-04: application-level field encryption for high-sensitivity columns.

Fernet (AES-128-CBC + HMAC) via ``cryptography``. Keys come ONLY from the
environment — never hardcoded, never committed.

Env:
  FERNET_KEY   single base64 Fernet key (urlsafe, 44 chars), OR
  FERNET_KEYS  comma-separated keys, NEWEST FIRST (for rotation)

Payload format: ``"v<index>:<fernet-token>"`` where index selects the key in
FERNET_KEYS order (index 0 = newest). Single-key deployments produce
``"v0:<token>"``.

Wiring (REPORTED, not applied — models are owned by another workstream):

    from studybuddy.field_encryption import encrypt_field, decrypt_field

    class ResumeVersion(db.Model):
        # keep the column as-is; encrypt on write, decrypt on read:
        _resume_text = db.Column("resume_text", db.Text)

        @property
        def resume_text(self):
            return decrypt_field(self._resume_text) if self._resume_text else None

        @resume_text.setter
        def resume_text(self, value):
            self._resume_text = encrypt_field(value) if value else None

Same pattern for interview answers / LinkedIn text columns.
"""

from __future__ import annotations

import os

from cryptography.fernet import Fernet, InvalidToken

__all__ = [
    "FieldCipher",
    "get_cipher",
    "encrypt_field",
    "decrypt_field",
    "rotate_field",
    "EncryptionError",
]


class EncryptionError(RuntimeError):
    """Raised when no key is configured or no key can decrypt a payload."""


def _load_keys() -> list[bytes]:
    """Read encryption keys from the environment, newest first."""
    raw_multi = os.environ.get("FERNET_KEYS", "").strip()
    raw_single = os.environ.get("FERNET_KEY", "").strip()
    keys: list[bytes] = []
    for chunk in raw_multi.split(","):
        chunk = chunk.strip()
        if chunk:
            keys.append(chunk.encode())
    if raw_single:
        keys.append(raw_single.encode())
    # Validate each key eagerly so a bad deploy fails fast, not on first read.
    for k in keys:
        Fernet(k)  # raises if not a valid urlsafe base64 Fernet key
    return keys


class FieldCipher:
    """Encrypt/decrypt individual field values with versioned keys."""

    def __init__(self, keys: list[bytes] | None = None):
        self._keys = keys if keys is not None else _load_keys()
        if not self._keys:
            raise EncryptionError(
                "No encryption key configured: set FERNET_KEY (or FERNET_KEYS, "
                "newest first) in the environment."
            )
        self._fernets = [Fernet(k) for k in self._keys]

    @property
    def key_count(self) -> int:
        return len(self._fernets)

    def encrypt(self, plaintext: str | None) -> str | None:
        """Encrypt with the newest key; returns ``"v0:<token>"``."""
        if plaintext is None:
            return None
        if not isinstance(plaintext, str):
            raise TypeError("encrypt() expects str or None")
        token = self._fernets[0].encrypt(plaintext.encode("utf-8")).decode()
        return f"v0:{token}"

    def decrypt(self, payload: str | None) -> str | None:
        """Decrypt ``"v<i>:<token>"``; tries the indexed key first, then all."""
        if payload is None:
            return None
        if not isinstance(payload, str) or not payload.startswith("v"):
            raise EncryptionError("Not an encrypted payload")
        try:
            version_part, token = payload.split(":", 1)
            index = int(version_part[1:])
        except (ValueError, IndexError) as exc:
            raise EncryptionError("Malformed encrypted payload") from exc
        order = ([index] if 0 <= index < len(self._fernets) else []
                 ) + [i for i in range(len(self._fernets)) if i != index]
        for i in order:
            try:
                return self._fernets[i].decrypt(
                    token.encode()).decode("utf-8")
            except InvalidToken:
                continue
        raise EncryptionError("No configured key could decrypt the payload")

    def rotate(self, payload: str | None) -> str | None:
        """Re-encrypt a payload with the newest key (post-rotation sweep)."""
        if payload is None:
            return None
        return self.encrypt(self.decrypt(payload))


# Lazy process-wide singleton — reads env on first use so tests can
# set FERNET_KEY before touching it.
_cipher: FieldCipher | None = None


def get_cipher() -> FieldCipher:
    global _cipher
    if _cipher is None:
        _cipher = FieldCipher()
    return _cipher


def reset_cipher() -> None:
    """Drop the cached singleton (tests only)."""
    global _cipher
    _cipher = None


def encrypt_field(value: str | None) -> str | None:
    return get_cipher().encrypt(value)


def decrypt_field(payload: str | None) -> str | None:
    return get_cipher().decrypt(payload)


def rotate_field(payload: str | None) -> str | None:
    return get_cipher().rotate(payload)
