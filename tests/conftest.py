"""Shared fixtures. Real network access is blocked for every test."""
from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Any, Callable

import httpx
import pytest

from pipeline.http import ApiClient, RateLimiter

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail loudly if any test tries to open a real socket."""

    def guard(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("network access attempted during tests")

    monkeypatch.setattr(socket.socket, "connect", guard)
    monkeypatch.setattr(socket, "create_connection", guard)


def load_fixture(name: str) -> Any:
    """Load a recorded API response from tests/fixtures."""
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def make_api() -> Callable[..., tuple[ApiClient, list[httpx.Request]]]:
    """Build an ApiClient backed by a handler function; returns it with a request log."""

    def factory(base_url: str, handler: Callable[[httpx.Request], httpx.Response]) -> tuple[ApiClient, list[httpx.Request]]:
        seen: list[httpx.Request] = []

        def recording(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return handler(request)

        api = ApiClient(
            base_url,
            transport=httpx.MockTransport(recording),
            limiter=RateLimiter(min_interval=0),
            sleep=lambda _s: None,
        )
        return api, seen

    return factory
