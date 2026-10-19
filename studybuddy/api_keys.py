"""Hashed API keys with per-key rate limits (PROD-09).

Keys are stored as salted hashes (never plaintext). Verification is constant-
time. Per-key rate limits use a simple in-memory token bucket (dev default);
swap in Redis for multi-worker deploys via the RateLimiter protocol.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field


def _hash_key(raw: str, *, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", raw.encode(), salt.encode(), 210_000
    ).hex()


@dataclass
class ApiKeyRecord:
    name: str
    key_hash: str
    salt: str
    created_at: float
    rate_per_minute: int = 60
    revoked: bool = False
    last_used_at: float | None = None


class ApiKeyStore:
    """In-memory store. Production: persist records to the database."""

    def __init__(self) -> None:
        self._records: dict[str, ApiKeyRecord] = {}  # kid -> record

    def create(self, name: str, *, rate_per_minute: int = 60) -> tuple[str, str]:
        """Create a key. Returns (key_id, raw_key) — raw_key is shown ONCE."""
        raw = "sb_" + secrets.token_urlsafe(32)
        kid = "kid_" + secrets.token_hex(8)
        salt = secrets.token_hex(16)
        self._records[kid] = ApiKeyRecord(
            name=name,
            key_hash=_hash_key(raw, salt=salt),
            salt=salt,
            created_at=time.time(),
            rate_per_minute=rate_per_minute,
        )
        return kid, raw

    def verify(self, raw: str) -> ApiKeyRecord | None:
        for rec in self._records.values():
            if rec.revoked:
                continue
            if hmac.compare_digest(rec.key_hash, _hash_key(raw, salt=rec.salt)):
                rec.last_used_at = time.time()
                return rec
        return None

    def revoke(self, key_id: str) -> bool:
        rec = self._records.get(key_id)
        if rec is None:
            return False
        rec.revoked = True
        return True

    def list_meta(self) -> list[dict]:
        return [
            {
                "key_id": kid,
                "name": r.name,
                "rate_per_minute": r.rate_per_minute,
                "revoked": r.revoked,
                "created_at": r.created_at,
                "last_used_at": r.last_used_at,
            }
            for kid, r in self._records.items()
        ]


@dataclass
class TokenBucket:
    capacity: int
    tokens: float = field(init=False)
    last: float = field(init=False)

    def __post_init__(self) -> None:
        self.tokens = float(self.capacity)
        self.last = time.time()

    def allow(self) -> tuple[bool, float]:
        """Return (allowed, retry_after_seconds)."""
        now = time.time()
        self.tokens = min(
            self.capacity, self.tokens + (now - self.last) * (self.capacity / 60)
        )
        self.last = now
        if self.tokens >= 1:
            self.tokens -= 1
            return True, 0.0
        return False, (1 - self.tokens) / (self.capacity / 60)


class RateLimiter:
    """Per-key rate limiter keyed by key_id."""

    def __init__(self) -> None:
        self._buckets: dict[str, TokenBucket] = {}

    def check(self, key_id: str, rate_per_minute: int) -> tuple[bool, float]:
        bucket = self._buckets.get(key_id)
        if bucket is None or bucket.capacity != rate_per_minute:
            bucket = TokenBucket(capacity=rate_per_minute)
            self._buckets[key_id] = bucket
        return bucket.allow()


def api_keys_wiring_snippet() -> str:
    return (
        "from studybuddy.api_keys import ApiKeyStore, RateLimiter\n"
        "store, limiter = ApiKeyStore(), RateLimiter()\n"
        "# kid, raw = store.create('partner-x', rate_per_minute=30)  # show raw ONCE\n"
        "# rec = store.verify(request.headers['X-API-Key']); ok, wait = limiter.check(kid, rec.rate_per_minute)\n"
    )


__all__ = ["ApiKeyStore", "ApiKeyRecord", "RateLimiter", "api_keys_wiring_snippet"]
