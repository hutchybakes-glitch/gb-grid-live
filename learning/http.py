# The module description.
"""Shared HTTP client: polite rate limiting plus retries with exponential backoff."""
# Allows modern type-hint syntax everywhere in this file.
from __future__ import annotations

# The standard way to print progress and warning messages with timestamps.
import logging
# Gives us a clock and the ability to pause (sleep).
import time
# Any = "any type"; Callable = "a function".
from typing import Any, Callable

# httpx is the library that actually sends web requests.
import httpx

# Our shared settings (timeouts, rate limit, number of retries).
from pipeline import config

# Create a logger named after this module, so log lines show where they came from.
log = logging.getLogger(__name__)

# HTTP status codes worth trying again: 429 = "too many requests", 5xx = the server had a temporary problem.
RETRYABLE_STATUS: frozenset[int] = frozenset({429, 500, 502, 503, 504})


# A class whose only job is to stop us sending requests too quickly.
class RateLimiter:
    # The docstring.
    """Ensures a minimum gap between consecutive requests."""

    # The set-up method, run when a RateLimiter is created.
    def __init__(
        # "self" is the limiter being created.
        self,
        # Minimum seconds between requests (1 second by default).
        min_interval: float = config.MIN_SECONDS_BETWEEN_REQUESTS,
        # Which clock to read; tests swap in a fake clock so they don't really wait.
        clock: Callable[[], float] = time.monotonic,
        # Which "pause" function to use; tests swap this out too.
        sleep: Callable[[float], None] = time.sleep,
    # This method returns nothing.
    ) -> None:
        # The docstring.
        """Create a limiter; ``clock``/``sleep`` are injectable so tests run instantly."""
        # Remember the minimum gap.
        self.min_interval = min_interval
        # Remember which clock to use.
        self._clock = clock
        # Remember which pause function to use.
        self._sleep = sleep
        # When the last request went out; None means "no request yet".
        self._last: float | None = None

    # Call this just before every request.
    def wait(self) -> None:
        # The docstring.
        """Block until at least ``min_interval`` has passed since the last call."""
        # Read the current time.
        now = self._clock()
        # Only need to wait if there was an earlier request.
        if self._last is not None:
            # How much of the minimum gap is still left?
            remaining = self.min_interval - (now - self._last)
            # If some is left, pause for exactly that long.
            if remaining > 0:
                # Pause.
                self._sleep(remaining)
                # Re-read the clock after pausing.
                now = self._clock()
        # Record this moment as the time of the latest request.
        self._last = now


# A custom error type, so callers can catch "the API failed" separately from other bugs.
class ApiError(RuntimeError):
    # The docstring.
    """Raised when a request still fails after all retries."""


# The client every data source uses to talk to its API.
class ApiClient:
    # The docstring.
    """Thin wrapper over httpx that every source module uses."""

    # The set-up method.
    def __init__(
        # The client being created.
        self,
        # The start of every URL, e.g. https://api.carbonintensity.org.uk
        base_url: str,
        # Normally None (use the real internet); tests pass a fake one.
        transport: httpx.BaseTransport | None = None,
        # Optionally share a rate limiter; otherwise make a new one.
        limiter: RateLimiter | None = None,
        # How many attempts before giving up.
        max_retries: int = config.MAX_RETRIES,
        # Which pause function to use between retries (tests use a no-op).
        sleep: Callable[[float], None] = time.sleep,
    # Returns nothing.
    ) -> None:
        # The docstring.
        """Build a client; pass ``transport`` in tests to avoid the network."""
        # Store the base URL without a trailing slash, so joining paths is predictable.
        self.base_url = base_url.rstrip("/")
        # Use the given limiter, or make a default one.
        self.limiter = limiter or RateLimiter()
        # Remember the retry limit.
        self.max_retries = max_retries
        # Remember the pause function.
        self._sleep = sleep
        # Create the underlying httpx client, which re-uses connections for speed.
        self._client = httpx.Client(
            # Real network, or a fake one in tests.
            transport=transport,
            # Give up on a single request after this many seconds.
            timeout=config.REQUEST_TIMEOUT_SECONDS,
            # Identify ourselves politely and ask for JSON.
            headers={"User-Agent": config.USER_AGENT, "Accept": "application/json"},
        )

    # Build a full URL from a path.
    def url(self, path: str) -> str:
        # The docstring.
        """Join a path onto the base URL."""
        # Glue base URL and path with exactly one slash between them.
        return f"{self.base_url}/{path.lstrip('/')}"

    # The main method: fetch a URL and return its JSON.
    def get_json(self, path: str, params: dict[str, str] | None = None) -> Any:
        # The docstring.
        """GET a JSON document, retrying transient failures with backoff."""
        # Work out the full URL once.
        url = self.url(path)
        # Try up to max_retries times, counting attempts from 1.
        for attempt in range(1, self.max_retries + 1):
            # Respect the rate limit before every single attempt, including retries.
            self.limiter.wait()
            # Try the request; network problems raise an exception, which we catch.
            try:
                # Send the GET request.
                response = self._client.get(url, params=params)
            # The connection failed (DNS, timeout, reset, and so on).
            except httpx.TransportError as exc:
                # Note why, for the log message.
                reason = f"network error: {exc!r}"
            # The request got a reply of some kind.
            else:
                # 200 means OK: decode the JSON and we're done.
                if response.status_code == 200:
                    # Return the decoded JSON to the caller.
                    return response.json()
                # Errors like 400 (bad request) won't fix themselves, so fail immediately.
                if response.status_code not in RETRYABLE_STATUS:
                    # Include the start of the error body to help debugging.
                    raise ApiError(f"GET {url} -> HTTP {response.status_code}: {response.text[:200]}")
                # A retryable status: note it for the log.
                reason = f"HTTP {response.status_code}"
            # If this was the last allowed attempt, give up with a clear message.
            if attempt == self.max_retries:
                # Raise our custom error.
                raise ApiError(f"GET {url} failed after {attempt} attempts ({reason})")
            # Exponential backoff: wait 2, 4, 8, 16 seconds, giving the server time to recover.
            backoff = 2**attempt
            # Log a warning so a human can see what happened.
            log.warning(
                # The message template.
                "GET %s attempt %d/%d failed (%s); retrying in %ds",
                # The values that fill the template.
                url, attempt, self.max_retries, reason, backoff,
            )
            # Pause before the next attempt.
            self._sleep(backoff)
        # Python can't tell the loop always returns or raises, so this line should never run.
        raise AssertionError("unreachable")

    # Tidy up network connections when finished.
    def close(self) -> None:
        # The docstring.
        """Close the underlying connection pool."""
        # Close the httpx client.
        self._client.close()
