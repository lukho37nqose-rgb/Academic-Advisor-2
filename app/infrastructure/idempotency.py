import redis.asyncio as redis
from fastapi import Header, HTTPException
import hashlib
import json
import os
import time
from typing import Any

# Create a mock for local sandbox execution when redis is not available
class MockRedis:
    def __init__(self):
        self._cache: dict[str, tuple[object, float | None]] = {}

    def _get_entry(self, key: str) -> tuple[object, float | None] | None:
        entry = self._cache.get(key)
        if entry is None:
            return None
        _value, expires_at = entry
        if expires_at is not None and expires_at <= time.monotonic():
            del self._cache[key]
            return None
        return entry
        
    async def get(self, key):
        entry = self._get_entry(key)
        return entry[0] if entry else None
        
    async def set(self, key, value, nx=False, ex=None):
        if nx and self._get_entry(key) is not None:
            return False
        expires_at = time.monotonic() + ex if ex else None
        self._cache[key] = (value, expires_at)
        return True
        
    async def delete(self, key):
        if key in self._cache:
            del self._cache[key]

    async def incr(self, key):
        entry = self._get_entry(key)
        value = int(entry[0]) + 1 if entry else 1
        expires_at = entry[1] if entry else None
        self._cache[key] = (value, expires_at)
        return value

    async def expire(self, key, seconds):
        entry = self._get_entry(key)
        if entry is None:
            return False
        self._cache[key] = (entry[0], time.monotonic() + seconds)
        return True

    async def ttl(self, key):
        entry = self._get_entry(key)
        if entry is None:
            return -2
        if entry[1] is None:
            return -1
        return max(0, int(entry[1] - time.monotonic()))

# Use the real redis if configured, otherwise use the mock
redis_url = os.environ.get("REDIS_URL")
if redis_url:
    redis_client: Any = redis.from_url(redis_url)
else:
    redis_client = MockRedis()

async def verify_idempotency_key(idempotency_key: str = Header(None)) -> str:
    if not idempotency_key or not idempotency_key.strip():
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required for this operation.")
    normalized = idempotency_key.strip()
    if len(normalized) > 255:
        raise HTTPException(status_code=400, detail="Idempotency-Key must be at most 255 characters.")
    return normalized


def scoped_idempotency_key(
    *,
    operation: str,
    client_key: str,
    tenant_id: str,
    user_id: str,
    subject_id: str | None,
    request_payload: dict[str, Any],
) -> str:
    """Return an opaque, principal- and request-bound Redis key.

    A client idempotency header is neither a tenant boundary nor a secret.  The
    cache namespace therefore binds it to the authorised actor, the subject
    scope, and canonical request content before any cached result is read.
    """

    canonical = json.dumps(
        {
            "operation": operation,
            "client_key": client_key,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "subject_id": subject_id,
            "request": request_payload,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

async def check_idempotency_cache(key: str) -> dict | None:
    """
    Checks if a response is already cached for the given key.
    """
    cached = await redis_client.get(f"idemp:{key}")
    if cached:
        return json.loads(cached)
    return None

async def set_idempotency_cache(key: str, data: dict, expire_seconds: int = 86400):
    """
    Caches the final response.
    """
    await redis_client.set(f"idemp:{key}", json.dumps(data), ex=expire_seconds)

async def acquire_idempotency_lock(key: str, expire_seconds: int = 300) -> bool:
    """
    Acquires an atomic lock using SET NX to prevent race conditions.
    Returns True if the lock was acquired, False if another process is already handling the request.
    """
    # SET NX atomically sets the key only if it does not already exist
    # NX = Only set if not exists, EX = Expire in X seconds
    acquired = await redis_client.set(f"idemp_lock:{key}", "locked", nx=True, ex=expire_seconds)
    return bool(acquired)

async def release_idempotency_lock(key: str):
    """
    Releases the idempotency lock.
    """
    await redis_client.delete(f"idemp_lock:{key}")
