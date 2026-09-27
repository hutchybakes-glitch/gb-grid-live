"""Resumable backfill, snapshots and the summary, all offline."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx

from pipeline import backfill, summary
from pipeline.backfill import BackfillStats, backfill_source
from pipeline.chunks import iter_chunks
from pipeline.http import ApiError
from pipeline.ingest.carbon_intensity import CarbonIntensityClient
from pipeline.raw_paths import chunk_path
from pipeline.snapshot import take_snapshots
from pipeline.storage import read_json
from tests.conftest import load_fixture

UTC = timezone.utc
CHUNKS = list(iter_chunks(datetime(2023, 1, 1, tzinfo=UTC), datetime(2023, 2, 12, tzinfo=UTC)))


def test_resume_skips_completed_chunks(tmp_path) -> None:
    calls: list[str] = []

    def flaky(chunk):
        calls.append(chunk.start.isoformat())
        if len(calls) == 2:
            raise ApiError("simulated outage")
        return load_fixture("ci_national.json")

    first = BackfillStats()
    backfill_source("ci_national", flaky, CHUNKS, tmp_path, first)
    assert (first.fetched, len(first.failed)) == (2, 1)

    calls.clear()
    second = BackfillStats()
    backfill_source("ci_national", lambda c: calls.append(c.start.isoformat()) or load_fixture("ci_national.json"), CHUNKS, tmp_path, second)
    assert second.skipped == 2 and second.fetched == 1
    assert calls == [CHUNKS[1].start.isoformat()]  # only the failed chunk is refetched


def test_longer_chunk_replaces_short_trailing_chunk(tmp_path) -> None:
    start = datetime(2023, 1, 1, tzinfo=UTC)
    short = next(iter_chunks(start, datetime(2023, 1, 5, tzinfo=UTC)))
    full = next(iter_chunks(start, datetime(2023, 1, 20, tzinfo=UTC)))
    body = load_fixture("ci_national.json")
    backfill_source("ci_national", lambda c: body, [short], tmp_path, BackfillStats())
    backfill_source("ci_national", lambda c: body, [full], tmp_path, BackfillStats())
    files = list((tmp_path / "ci_national").rglob("*.json"))
    assert files == [chunk_path("ci_national", full, tmp_path)]


def test_empty_response_is_not_written(tmp_path) -> None:
    stats = BackfillStats()
    backfill_source("ci_national", lambda c: {"data": []}, CHUNKS[:1], tmp_path, stats)
    assert stats.empty == 1
    assert not list(tmp_path.rglob("*.json"))


def test_file_names_are_windows_safe() -> None:
    assert ":" not in chunk_path("ci_national", CHUNKS[0]).name


def test_snapshot_saves_both_scopes_with_captured_at(tmp_path, make_api) -> None:
    national, regional = load_fixture("ci_fw48h_national.json"), load_fixture("ci_regional.json")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=regional if "/regional/" in request.url.path else national)

    api, seen = make_api("https://api.carbonintensity.org.uk", handler)
    captured = datetime(2026, 9, 27, 18, 47, 5, tzinfo=UTC)
    written = take_snapshots(CarbonIntensityClient(api), captured, tmp_path)
    assert set(written) == {"national", "regional"}
    for path in written.values():
        assert path.name.endswith(".json.gz")
        saved = read_json(path)
        assert saved["captured_at"] == "2026-09-27T18:47:05Z"
        assert saved["data"]
    assert all("2026-09-27T18:30Z" in r.url.path for r in seen)


def test_summary_counts_both_formats(tmp_path) -> None:
    (tmp_path / "ci_national" / "d").mkdir(parents=True)
    (tmp_path / "pvlive_gsp0" / "d").mkdir(parents=True)
    (tmp_path / "ci_national" / "d" / "a.json").write_text(json.dumps(load_fixture("ci_national.json")))
    (tmp_path / "pvlive_gsp0" / "d" / "a.json").write_text(json.dumps(load_fixture("pvlive_gsp0.json")))
    result = summary.summarise(tmp_path)
    assert result["ci_national"].rows == len(load_fixture("ci_national.json")["data"])
    assert result["pvlive_gsp0"].first is not None


def test_cli_parses_dates() -> None:
    assert backfill.parse_date("2023-01-01") == datetime(2023, 1, 1, tzinfo=UTC)


def test_recent_chunks_are_refetched_old_ones_are_not(tmp_path) -> None:
    body = load_fixture("ci_national.json")
    backfill_source("ci_national", lambda c: body, CHUNKS, tmp_path, BackfillStats())
    calls: list[datetime] = []
    stats = BackfillStats()
    refresh_after = CHUNKS[-1].end - timedelta(days=2)
    backfill_source(
        "ci_national", lambda c: calls.append(c.start) or body, CHUNKS, tmp_path, stats, refresh_after
    )
    assert calls == [CHUNKS[-1].start]
    assert (stats.fetched, stats.skipped) == (1, len(CHUNKS) - 1)


def test_refetch_with_empty_response_keeps_existing_file(tmp_path) -> None:
    body = load_fixture("ci_national.json")
    backfill_source("ci_national", lambda c: body, CHUNKS[:1], tmp_path, BackfillStats())
    stats = BackfillStats()
    backfill_source("ci_national", lambda c: {"data": []}, CHUNKS[:1], tmp_path, stats, CHUNKS[0].start)
    assert stats.empty == 1
    assert json.loads(chunk_path("ci_national", CHUNKS[0], tmp_path).read_text()) == body
