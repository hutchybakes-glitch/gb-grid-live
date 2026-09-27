"""Shared HTTP client: polite rate limiting plus retries with exponential backoff."""
from __future__ import annotations

import logging
import time
from typing import Any, Callable

import httpx

from pipeline import config

log = logging.getLogger(__name__)

RETRYABLE_STATUS: frozenset[int] = frozenset({429, 500, 502, 503, 504})


class RateLimiter:
    """Ensures a minimum gap between consecutive requests."""

    def __init__(
        self,
        min_interval: float = config.MIN_SECONDS_BETWEEN_REQUESTS,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Create a limiter; ``clock``/``sleep`` are injectable so tests run instantly."""
        self.min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._last: float | None = None

    def wait(self) -> None:
        """Block until at least ``min_interval`` has passed since the last call."""
        now = self._clock()
        if self._last is not None:
            remaining = self.min_interval - (now - self._last)
            if remaining > 0:
                self._sleep(remaining)
                now = self._clock()
        self._last = now


class ApiError(RuntimeError):
    """Raised when a request still fails after all retries."""


class ApiClient:
    """Thin wrapper over httpx that every source module uses."""

    def __init__(
        self,
        base_url: str,
        transport: httpx.BaseTransport | None = None,
        limiter: RateLimiter | None = None,
        max_retries: int = config.MAX_RETRIES,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Build a client; pass ``transport`` in tests to avoid the network."""
        self.base_url = base_url.rstrip("/")
        self.limiter = limiter or RateLimiter()
        self.max_retries = max_retries
        self._sleep = sleep
        self._client = httpx.Client(
            transport=transport,
            timeout=config.REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": config.USER_AGENT, "Accept": "application/json"},
        )

    def url(self, path: str) -> str:
        """Join a path onto the base URL."""
        return f"{self.base_url}/{path.lstrip('/')}"

    def get_json(self, path: str, params: dict[str, str] | None = None) -> Any:
        """GET a JSON document, retrying transient failures with backoff."""
        url = self.url(path)
        for attempt in range(1, self.max_retries + 1):
            self.limiter.wait()
            try:
                response = self._client.get(url, params=params)
            except httpx.TransportError as exc:
                reason = f"network error: {exc!r}"
            else:
                if response.status_code == 200:
                    return response.json()
                if response.status_code not in RETRYABLE_STATUS:
                    raise ApiError(f"GET {url} -> HTTP {response.status_code}: {response.text[:200]}")
                reason = f"HTTP {response.status_code}"
            if attempt == self.max_retries:
                raise ApiError(f"GET {url} failed after {attempt} attempts ({reason})")
            backoff = 2**attempt
            log.warning(
                "GET %s attempt %d/%d failed (%s); retrying in %ds",
                url, attempt, self.max_retries, reason, backoff,
            )
            self._sleep(backoff)
        raise AssertionError("unreachable")

    def close(self) -> None:
        """Close the underlying connection pool."""
        self._client.close()
