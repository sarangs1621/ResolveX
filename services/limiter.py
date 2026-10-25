"""Token Bucket & Sliding Window Rate Limiting Service.

Protects /ask and /auth/login endpoints against Denial-of-Service and brute-force
attacks. Uses distributed Redis atomics when connected, with thread-safe in-memory
sliding window fallback.
"""

import logging
import os
import time
from typing import Dict, List, Optional, Tuple
from fastapi import HTTPException, Request

logger = logging.getLogger("support_agent.limiter")


class SlidingWindowRateLimiter:
    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.redis_client = None
        self.is_redis_connected = False
        # In-memory store: { key: [timestamp1, timestamp2, ...] }
        self._memory_store: Dict[str, List[float]] = {}

    async def initialize(self):
        """Attempts to connect to Redis; falls back to in-memory sliding window."""
        try:
            import redis.asyncio as aioredis
            client = aioredis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_timeout=1.5,
                socket_connect_timeout=1.5
            )
            await client.ping()
            self.redis_client = client
            self.is_redis_connected = True
            logger.info(f"Rate Limiter connected to distributed Redis at {self.redis_url}")
        except Exception as err:
            self.is_redis_connected = False
            logger.info(f"Rate Limiter running in in-memory mode ({err}).")

    async def is_allowed(
        self,
        identifier: str,
        limit: int = 30,
        window_seconds: int = 60
    ) -> Tuple[bool, int, int]:
        """Evaluates rate limit.

        Returns:
            (allowed: bool, remaining: int, retry_after: int)
        """
        now = time.time()
        bucket_key = f"ratelimit:{identifier}"

        if self.is_redis_connected and self.redis_client:
            try:
                # Use Redis atomic pipeline
                pipe = self.redis_client.pipeline()
                pipe.zremrangebyscore(bucket_key, 0, now - window_seconds)
                pipe.zcard(bucket_key)
                pipe.zadd(bucket_key, {str(now): now})
                pipe.expire(bucket_key, window_seconds)
                results = await pipe.execute()

                current_count = results[1]
                if current_count >= limit:
                    # Exceeded
                    return False, 0, int(window_seconds)
                remaining = max(0, limit - current_count - 1)
                return True, remaining, 0
            except Exception as err:
                logger.warning(f"Redis rate limit check failed: {err}. Using memory fallback.")

        # In-memory sliding window implementation
        timestamps = self._memory_store.get(bucket_key, [])
        cutoff = now - window_seconds
        # Filter expired timestamps
        valid_timestamps = [ts for ts in timestamps if ts > cutoff]

        if len(valid_timestamps) >= limit:
            oldest_ts = valid_timestamps[0]
            retry_after = max(1, int(window_seconds - (now - oldest_ts)))
            self._memory_store[bucket_key] = valid_timestamps
            return False, 0, retry_after

        valid_timestamps.append(now)
        self._memory_store[bucket_key] = valid_timestamps
        remaining = max(0, limit - len(valid_timestamps))
        return True, remaining, 0


# Global singleton instance
rate_limiter = SlidingWindowRateLimiter()


async def enforce_rate_limit(
    request: Request,
    key_prefix: str = "ask",
    limit: int = 30,
    window_seconds: int = 60
):
    """FastAPI Dependency to enforce endpoint rate limits."""
    # Determine client identifier (authenticated user or IP address)
    client_ip = request.headers.get("x-forwarded-for") or (request.client.host if request.client else "127.0.0.1")
    if "," in client_ip:
        client_ip = client_ip.split(",")[0].strip()

    # Check for authorization header to key by user if present
    auth_header = request.headers.get("authorization", "")
    identifier = f"{key_prefix}:{auth_header if auth_header else client_ip}"

    allowed, remaining, retry_after = await rate_limiter.is_allowed(
        identifier=identifier,
        limit=limit,
        window_seconds=window_seconds
    )

    # Attach remaining count to request state so middleware or response can read it
    request.state.ratelimit_limit = limit
    request.state.ratelimit_remaining = remaining

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Maximum {limit} requests per {window_seconds}s. Try again in {retry_after}s.",
            headers={
                "Retry-After": str(retry_after),
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0"
            }
        )
