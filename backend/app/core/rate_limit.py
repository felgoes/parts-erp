from collections import defaultdict, deque
from threading import Lock
from time import monotonic

from starlette.datastructures import Headers


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._windows: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def hit(self, key: str, limit: int, window_seconds: int) -> bool:
        now = monotonic()
        with self._lock:
            window = self._windows[key]
            while window and window[0] <= now - window_seconds:
                window.popleft()
            if len(window) >= limit:
                return False
            window.append(now)
            return True

    def clear(self, key: str) -> None:
        with self._lock:
            self._windows.pop(key, None)


def client_ip(headers: Headers, fallback: str) -> str:
    forwarded = headers.get("cf-connecting-ip") or headers.get("x-forwarded-for")
    return str(forwarded or fallback).split(",", maxsplit=1)[0].strip()
