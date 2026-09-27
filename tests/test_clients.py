"""Source clients, against recorded responses."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from pipeline.ingest import pvlive
from pipeline.ingest.carbon_intensity import CarbonIntensityClient, max_days, range_path
from pipeline.ingest.pvlive import PVLiveClient
from tests.conftest import load_fixture

UTC = timezone.utc
START = datetime(2023, 1, 1, tzinfo=UTC)


def test_ci_range_path_format_and_limit() -> None:
    assert range_path("ci_generation", START, datetime(2023, 1, 15, tzinfo=UTC)) == (
        "generation/2023-01-01T00:00Z/2023-01-15T00:00Z"
    )
    with pytest.raises(ValueError):
        range_path("ci_national", START, datetime(2023, 1, 15, 0, 30, tzinfo=UTC))


def test_ci_regional_limit_is_13_days() -> None:
    # The live API answers HTTP 400 to an exact 14-day regional window.
    assert max_days("ci_regional") == 13
    with pytest.raises(ValueError):
        range_path("ci_regional", START, datetime(2023, 1, 15, tzinfo=UTC))
    assert range_path("ci_regional", START, datetime(2023, 1, 14, tzinfo=UTC))


@pytest.mark.parametrize(
    ("endpoint", "fixture", "path_part"),
    [
        ("ci_national", "ci_national.json", "/intensity/2023-01-01T00:00Z/"),
        ("ci_generation", "ci_generation.json", "/generation/"),
        ("ci_regional", "ci_regional.json", "/regional/intensity/"),
    ],
)
def test_ci_fetch_range(make_api, endpoint: str, fixture: str, path_part: str) -> None:
    body = load_fixture(fixture)
    api, seen = make_api("https://api.carbonintensity.org.uk", lambda r: httpx.Response(200, json=body))
    payload = CarbonIntensityClient(api).fetch_range(endpoint, START, datetime(2023, 1, 2, tzinfo=UTC))
    assert payload["data"]
    assert path_part in seen[0].url.path


def test_ci_regional_fixture_has_expected_shape() -> None:
    period = load_fixture("ci_regional.json")["data"][0]
    ids = {r["regionid"] for r in period["regions"]}
    assert set(range(1, 15)) <= ids
    nw = next(r for r in period["regions"] if r["regionid"] == 3)
    assert nw["shortname"] == "North West England"


def test_ci_fw48h(make_api) -> None:
    body = load_fixture("ci_fw48h_national.json")
    api, seen = make_api("https://api.carbonintensity.org.uk", lambda r: httpx.Response(200, json=body))
    payload = CarbonIntensityClient(api).fetch_fw48h("national", datetime(2026, 9, 27, 18, tzinfo=UTC))
    assert seen[0].url.path.endswith("/intensity/2026-09-27T18:00Z/fw48h")
    assert len(payload["data"]) >= 96


def test_pvlive_fetch_range_sends_params(make_api) -> None:
    body = load_fixture("pvlive_gsp0.json")
    api, seen = make_api("https://api.pvlive.uk/pvlive/api/v4", lambda r: httpx.Response(200, json=body))
    PVLiveClient(api).fetch_range("gsp", 0, START, datetime(2023, 1, 2, tzinfo=UTC))
    req = seen[0]
    assert req.url.path == "/pvlive/api/v4/gsp/0"
    assert req.url.params["start"] == "2023-01-01T00:00:00Z"
    assert "updated_gmt" in req.url.params["extra_fields"]


def test_pvlive_rows_use_meta_not_position() -> None:
    body = load_fixture("pvlive_gsp0.json")
    shuffled = {"meta": list(reversed(body["meta"])), "data": [list(reversed(r)) for r in body["data"]]}
    assert pvlive.rows_as_dicts(shuffled) == pvlive.rows_as_dicts(body)
    assert all(r["generation_mw"] >= 0 for r in pvlive.rows_as_dicts(body))


def test_pvlive_pes_ids_come_from_list() -> None:
    ids = pvlive.pes_ids(load_fixture("pvlive_pes_list.json"))
    assert len(ids) == 14 and 0 not in ids


def test_pvlive_rejects_oversize_range(make_api) -> None:
    api, _ = make_api("https://x.test", lambda r: httpx.Response(200, json={}))
    with pytest.raises(ValueError):
        PVLiveClient(api).fetch_range("pes", 16, START, datetime(2023, 2, 1, tzinfo=UTC))
