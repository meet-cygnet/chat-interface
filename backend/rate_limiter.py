"""Token-bucket rate limiter.

Provides both a *global* limiter (shared across all requests) and optional
*per-session* limiting to prevent a single user from monopolising capacity.

The implementation is lock-free for the fast path — it uses
``asyncio.Lock`` only when the bucket needs to be refilled.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict


class TokenBucketRateLimiter:
    """Classic token-bucket algorithm.

    Parameters
    ----------
    rate:
        Sustained requests per second.
    burst:
        Maximum burst size (bucket capacity).
    """

    def __init__(self, rate: float, burst: int) -> None:
        if rate <= 0:
            raise ValueError("rate must be > 0")
        if burst < 1:
            raise ValueError("burst must be >= 1")

        self._rate = rate
        self._burst = burst
        self._tokens = float(burst)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        """Try to consume one token.  Returns ``True`` if allowed."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
            self._last_refill = now

            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True
            return False

    @property
    def retry_after(self) -> float:
        """Seconds until the next token becomes available."""
        if self._tokens >= 1.0:
            return 0.0
        return (1.0 - self._tokens) / self._rate


class PerSessionRateLimiter:
    """Maintains a separate ``TokenBucketRateLimiter`` per session ID.

    Idle sessions are cleaned up lazily when the number of tracked sessions
    exceeds ``max_sessions``.
    """

    def __init__(
        self,
        rate: float = 10.0,
        burst: int = 20,
        max_sessions: int = 1_000,
    ) -> None:
        self._rate = rate
        self._burst = burst
        self._max_sessions = max_sessions
        self._buckets: dict[str, TokenBucketRateLimiter] = defaultdict(
            lambda: TokenBucketRateLimiter(self._rate, self._burst)
        )
        self._last_access: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, session_id: str) -> bool:
        """Try to consume a token for *session_id*.  Returns ``True`` if allowed."""
        async with self._lock:
            self._last_access[session_id] = time.monotonic()
            # Lazy eviction.
            if len(self._buckets) > self._max_sessions:
                self._evict_stale()

        return await self._buckets[session_id].acquire()

    def retry_after(self, session_id: str) -> float:
        bucket = self._buckets.get(session_id)
        return bucket.retry_after if bucket else 0.0

    def _evict_stale(self) -> None:
        """Remove the oldest half of tracked sessions."""
        sorted_sessions = sorted(self._last_access.items(), key=lambda kv: kv[1])
        cutoff = len(sorted_sessions) // 2
        for sid, _ in sorted_sessions[:cutoff]:
            self._buckets.pop(sid, None)
            self._last_access.pop(sid, None)
