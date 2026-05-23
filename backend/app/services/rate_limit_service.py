"""In-memory sliding-window rate limiter (Step 53B)."""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, status

from app.core.config import settings

_lock = threading.Lock()
_buckets: dict[str, deque[float]] = defaultdict(deque)


def _rate_limits_enabled() -> bool:
    return os.environ.get("CNS_DISABLE_RATE_LIMITS", "").lower() not in ("1", "true", "yes")


def _prune(bucket: deque[float], now: float, window: float) -> None:
    cutoff = now - window
    while bucket and bucket[0] <= cutoff:
        bucket.popleft()


def check_rate_limit(*, key: str, limit: int, action: str, window_seconds: int | None = None) -> None:
    """Raise HTTP 429 when ``limit`` requests in ``window_seconds`` exceeded for ``key``."""
    if not _rate_limits_enabled() or limit <= 0:
        return
    window = float(window_seconds or settings.rate_limit_window_seconds)
    now = time.monotonic()
    with _lock:
        bucket = _buckets[key]
        _prune(bucket, now, window)
        if len(bucket) >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "code": "RATE_LIMITED",
                    "message": f"Rate limit exceeded for {action}. Try again shortly.",
                    "action": action,
                    "limit": limit,
                    "window_seconds": int(window),
                },
            )
        bucket.append(now)


def reset_rate_limits_for_tests() -> None:
    """Clear in-memory buckets (pytest only)."""
    with _lock:
        _buckets.clear()
