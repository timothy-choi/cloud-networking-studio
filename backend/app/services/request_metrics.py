"""In-process API request counters (Step 53C)."""

from __future__ import annotations

import threading
from collections import defaultdict

_lock = threading.Lock()
_total_requests = 0
_by_status: dict[int, int] = defaultdict(int)


def record_api_request(*, status_code: int) -> None:
    global _total_requests
    with _lock:
        _total_requests += 1
        _by_status[int(status_code)] += 1


def api_request_metrics() -> dict[str, int | dict[str, int]]:
    with _lock:
        return {
            "total_requests": _total_requests,
            "by_status": {str(k): v for k, v in _by_status.items()},
        }


def reset_api_request_metrics_for_tests() -> None:
    global _total_requests
    with _lock:
        _total_requests = 0
        _by_status.clear()
