import json
from datetime import datetime, timezone

import pandas as pd

from openalex_api_client import OpenAlex
from radar.sweep import run_sweep

from conftest import FakeSession, authorship, inst, raw_work

NOW = datetime(2026, 10, 20, 8, 14, 3, tzinfo=timezone.utc)


def client(session, config):
    oa = OpenAlex(session=session, cache_dir=config.data_dir / "cache" / "openalex", max_rps=None, api_key=None)
    oa._sleep = lambda s: None
    return oa


def works_fixture():
    big = [authorship(f"A{i}", [inst("I88", "SN")]) for i in range(100)]  # cut at 100 in list results
    return [
        raw_work(1),
        raw_work(2, date="2020-01-01", abstract=False),
        raw_work(3, authorships=big),
        raw_work(4, date="2019-12-31"),
        raw_work(5, date="2025-07-01", authorships=[authorship("A9", [])]),
    ]


def test_sweep_writes_snapshot_and_second_run_gets_suffix(config):
    full = [authorship(f"A{i}", [inst("I88", "SN")]) for i in range(250)]
    session = FakeSession(works_fixture(), page_size=2, full_authors={"W3": full})
    path = run_sweep(config, oa=client(session, config), now=NOW)

    assert path.name == "2026-10-20"
    for name in ["works", "authorships", "topics", "counts_by_year", "sdgs"]:
        assert (path / f"{name}.parquet").exists()
    assert not (path / "diff.json").exists()

    manifest = json.loads((path / "manifest.json").read_text())
    assert manifest["expected_count"] == manifest["harvested_count"] == 5
    assert manifest["observed_at"] == "2026-10-20T08:14:03Z"
    assert manifest["client_version"] == "1.0.0" and manifest["radar_version"] == "0.1.0"
    assert manifest["config_hash"] == config.config_hash
    assert manifest["openalex_credits_used"] == 3  # three list pages
    assert manifest["universe"]["root_institution"] == "I4210166444"

    page_calls = [p for _, p in session.calls if "cursor" in p]
    assert len(page_calls) == 3
    gets = [url for url, _ in session.calls if "/works/" in url]
    assert gets == ["https://api.openalex.org/works/W3"]

    works = pd.read_parquet(path / "works.parquet").set_index("work_id")
    assert works.loc["W3", "n_authors"] == 250 and not works.loc["W3", "authors_truncated"]
    assert works.loc["W1", "pub_month"] == (2021 - 2016) * 12 + 4
    assert works.loc["W2", "date_is_jan1"] and not works.loc["W1", "date_is_jan1"]
    assert works.loc["W1", "n_anchor_authors"] == 1 and works.loc["W3", "n_anchor_authors"] == 0

    quality = json.loads((path / "quality.json").read_text())
    assert quality["works"] == 5
    assert quality["jan1"]["share"] == 0.2
    assert quality["n_authors"]["refetched_truncated"] == 1
    assert quality["n_authors"]["above_max_authors"] == 1
    assert quality["anchor_materialized_share"] == 0.6
    assert quality["counts_by_year_coverage"] == {"earliest_year": 2022, "latest_year": 2023,
                                                  "works_with_citations": 5}

    # Same day again: a new sweep id, a fresh harvest, and a diff against the first sweep.
    session2 = FakeSession(works_fixture()[:4] + [raw_work(6, date="2025-09-01")], full_authors={"W3": full})
    path2 = run_sweep(config, oa=client(session2, config), now=NOW)
    assert path2.name == "2026-10-20-2"
    diff = json.loads((path2 / "diff.json").read_text())
    assert diff["old_sweep"] == "2026-10-20"
    assert diff["works_added"]["count"] == 1 and diff["works_removed"]["ids"] == ["W5"]


def test_interrupted_sweep_resumes_same_id(config):
    class Boom(FakeSession):
        def request(self, method, url, params=None, **kw):
            if params and params.get("cursor") == "4":
                raise RuntimeError("network down")
            return super().request(method, url, params=params, **kw)

    full = [authorship(f"A{i}", [inst("I88", "SN")]) for i in range(250)]
    try:
        run_sweep(config, oa=client(Boom(works_fixture(), full_authors={"W3": full}), config), now=NOW)
    except RuntimeError:
        pass
    assert not (config.data_dir / "sweeps" / "2026-10-20").exists()

    session = FakeSession(works_fixture(), full_authors={"W3": full})
    path = run_sweep(config, oa=client(session, config), now=NOW)
    assert path.name == "2026-10-20"
    assert [p["cursor"] for _, p in session.calls if "cursor" in p] == ["4"]  # pages 1–2 replayed
    assert len(pd.read_parquet(path / "works.parquet")) == 5
