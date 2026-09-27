"""Chunking, rate limiting, retries and safe storage."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from pipeline.chunks import floor_half_hour, iter_chunks
from pipeline.http import ApiError, RateLimiter
from pipeline.storage import EmptyResponseError, save_records, write_json_atomic

UTC = timezone.utc


def test_chunks_never_exceed_14_days_and_cover_range() -> None:
    start, end = datetime(2023, 1, 1, tzinfo=UTC), datetime(2026, 9, 27, tzinfo=UTC)
    chunks = list(iter_chunks(start, end))
    assert all(c.end - c.start <= timedelta(days=14) for c in chunks)
    assert chunks[0].start == start and chunks[-1].end == end
    assert all(a.end == b.start for a, b in zip(chunks, chunks[1:]))


def test_chunks_are_stable_so_resume_finds_same_files() -> None:
    start = datetime(2023, 1, 1, tzinfo=UTC)
    a = list(iter_chunks(start, datetime(2024, 1, 1, tzinfo=UTC)))
    b = list(iter_chunks(start, datetime(2024, 6, 1, tzinfo=UTC)))
    assert a[:-1] == b[: len(a) - 1]


def test_chunks_reject_naive_datetimes_and_oversize() -> None:
    with pytest.raises(ValueError):
        list(iter_chunks(datetime(2023, 1, 1), datetime(2023, 2, 1)))
    with pytest.raises(ValueError):
        list(iter_chunks(datetime(2023, 1, 1, tzinfo=UTC), datetime(2023, 2, 1, tzinfo=UTC), days=15))


def test_floor_half_hour() -> None:
    assert floor_half_hour(datetime(2026, 9, 27, 18, 47, 12, tzinfo=UTC)) == datetime(2026, 9, 27, 18, 30, tzinfo=UTC)


def test_rate_limiter_spaces_calls() -> None:
    clock = [0.0]
    sleeps: list[float] = []

    def sleep(s: float) -> None:
        sleeps.append(s)
        clock[0] += s

    limiter = RateLimiter(min_interval=1.0, clock=lambda: clock[0], sleep=sleep)
    limiter.wait()
    clock[0] += 0.25
    limiter.wait()
    limiter.wait()
    assert sleeps == [0.75, 1.0]


def test_retries_on_429_then_succeeds(make_api) -> None:
    responses = iter([httpx.Response(429), httpx.Response(503), httpx.Response(200, json={"data": [1]})])
    api, seen = make_api("https://x.test", lambda r: next(responses))
    assert api.get_json("a") == {"data": [1]}
    assert len(seen) == 3


def test_gives_up_after_max_retries(make_api) -> None:
    api, seen = make_api("https://x.test", lambda r: httpx.Response(500))
    with pytest.raises(ApiError):
        api.get_json("a")
    assert len(seen) == api.max_retries


def test_client_error_is_not_retried(make_api) -> None:
    api, seen = make_api("https://x.test", lambda r: httpx.Response(400, text="bad range"))
    with pytest.raises(ApiError, match="400"):
        api.get_json("a")
    assert len(seen) == 1


def test_empty_response_never_overwrites_good_file(tmp_path) -> None:
    path = tmp_path / "f.json"
    write_json_atomic(path, {"data": [1, 2]})
    with pytest.raises(EmptyResponseError):
        save_records(path, {"data": []})
    assert path.read_text() == '{"data": [1, 2]}'
