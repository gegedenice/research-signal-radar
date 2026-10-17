import json
from datetime import datetime, timezone

import pandas as pd
import pytest

from openalex_api_client import OpenAlex
from radar.config import Citations, Collaborations, Topics
from radar.detectors import ASSESSMENT_COLUMNS, SIGNAL_EXTRA_COLUMNS, citations, collaborations, run_detect, topics
from radar.detectors.common import SweepTables
from radar.engine import cutoffs, windows, Cutoff
from radar.brief import write_brief
from radar.sweep import run_sweep

from conftest import FakeSession, authorship, inst, raw_work

CUT_2025 = cutoffs(2016, 2025, "year")[-1]


def work(wid, year, month=6, field="F1", domain="D1", n_authors=3, topic="T1", subfield="S1"):
    return {"work_id": wid, "title": f"Title {wid}", "publication_year": year,
            "pub_month": (year - 2016) * 12 + month - 1, "field_id": field, "field": f"Field {field}",
            "domain_id": domain, "domain": f"Domain {domain}", "n_authors": n_authors,
            "primary_topic_id": topic, "primary_topic": f"Topic {topic}", "subfield_id": subfield,
            "subfield": f"Subfield {subfield}", "cited_by_count": 0}


def tables(works, authorships=None, cby=None, coverage=(2012, 2026), topic_rows=None):
    auth_cols = ["work_id", "author_position_idx", "institution_id", "institution_name", "institution_country",
                 "institution_type", "institution_ror", "is_anchor"]
    return SweepTables(
        sweep_id="test", works=pd.DataFrame(works),
        authorships=pd.DataFrame(authorships or [], columns=auth_cols),
        counts_by_year=pd.DataFrame(cby or [], columns=["work_id", "year", "cited_by_count"]),
        first_year=2016, last_year=2025, citation_coverage=coverage,
        topics=pd.DataFrame(topic_rows or [], columns=["work_id", "rank", "topic_id", "topic", "score",
                                                       "subfield_id", "field_id", "domain_id"]),
    )


# 6. citations -------------------------------------------------------------------------


def test_citations_leave_one_out_and_baseline_from_publication_year():
    works = [work("W1", 2023), work("W2", 2023), work("W3", 2023), work("W4", 2020)]
    cby = [("W1", 2025, 10), ("W1", 2024, 2), ("W1", 2023, 1), ("W1", 2022, 50),  # 2022 < pub year: ignored
           ("W2", 2025, 4), ("W2", 2024, 6), ("W3", 2025, 1), ("W3", 2023, 3),
           ("W4", 2025, 7), ("W4", 2022, 5), ("W4", 2021, 9)]
    t = tables(works, cby=[dict(zip(["work_id", "year", "cited_by_count"], r)) for r in cby])
    out = citations.build(t, Citations(min_cohort_size=1), CUT_2025).set_index("entity_id")
    w1 = out.loc["W1"]
    assert (w1.c, w1.b, w1.history_before) == (10, 3, 0)  # baseline 2023–2024 only
    assert (w1.C, w1.B) == (4 + 1, 6 + 3)                   # cohort minus W1 itself
    w4 = out.loc["W4"]
    assert (w4.c, w4.b, w4.history_before) == (7, 5, 9)     # baseline 2022–2024, history 2021
    assert w1.extra["cohort_level"] == "field" and w1.extra["cohort"] == "2023 · Field F1"


def test_citations_min_age_excludes_recent_works():
    t = tables([work("W1", 2024), work("W2", 2023)])
    out = citations.build(t, Citations(min_cohort_size=1), CUT_2025)
    assert list(out.entity_id) == ["W2"]


def test_cohort_fallback_order():
    works = ([work(f"A{i}", 2022, field="F1", domain="D1") for i in range(3)]
             + [work(f"B{i}", 2022, field="F2", domain="D1") for i in range(2)]
             + [work(f"C{i}", 2022, field="F3", domain="D2") for i in range(1)])
    cohorts = citations.assign_cohorts(pd.DataFrame(works), min_size=3).set_index("work_id")
    assert cohorts.loc["A0", "cohort_level"] == "field"      # 3 works in 2022 × F1
    assert cohorts.loc["B0", "cohort_level"] == "domain"     # F2 too small, D1 has 5
    assert cohorts.loc["C0", "cohort_level"] == "year"       # F3 and D2 too small
    assert cohorts.loc["C0", "cohort_label"] == "2022 · all fields"


# 7. collaborations --------------------------------------------------------------------


def auth_row(wid, pos, iid, country, anchor):
    return {"work_id": wid, "author_position_idx": pos, "institution_id": iid, "institution_name": f"Inst {iid}",
            "institution_country": country, "institution_type": "education", "institution_ror": None,
            "is_anchor": anchor}


def test_copublication_rule_and_consortium_guard():
    works = [work("W1", 2025), work("W2", 2025), work("W3", 2025, n_authors=80), work("W4", 2025)]
    auth = [
        auth_row("W1", 0, "IRD", "FR", True), auth_row("W1", 0, "E1", "SN", False),   # dual affiliation only
        auth_row("W2", 0, "IRD", "FR", True), auth_row("W2", 1, "E1", "SN", False),   # two distinct authors
        auth_row("W3", 0, "IRD", "FR", True), auth_row("W3", 1, "E1", "SN", False),   # consortium
        auth_row("W4", 0, "IRD", "FR", True), auth_row("W4", 0, "E2", "SN", False),
        auth_row("W4", 1, "IRD2", "FR", True),                                         # anchor from another author
    ]
    cfg = Collaborations(max_authors=50, min_support=1)
    t = tables(works, auth)
    inst_level = collaborations.build(t, cfg, CUT_2025, "institution").set_index("entity_id")
    assert inst_level.loc["E1", "work_ids_current"] == ["W2"]
    assert inst_level.loc["E2", "work_ids_current"] == ["W4"]
    assert set(inst_level["C"]) == {3}  # W3 excluded from the denominator too
    country = collaborations.build(t, cfg, CUT_2025, "country").set_index("entity_id")
    assert country.loc["SN", "c"] == 2  # E1 (W2) + E2 (W4) aggregated, distinct works
    units = inst_level.loc["E2", "extra"]["anchor_units"]
    assert {u["institution_id"] for u in units} == {"IRD", "IRD2"}


def test_exclude_countries():
    works = [work("W1", 2025)]
    auth = [auth_row("W1", 0, "IRD", "FR", True), auth_row("W1", 1, "E1", "FR", False),
            auth_row("W1", 2, "E2", "SN", False)]
    out = collaborations.build(tables(works, auth), Collaborations(exclude_countries=["FR"]), CUT_2025, "institution")
    assert list(out.entity_id) == ["E2"]


# topics -------------------------------------------------------------------------------


def test_topics_counts_denominator_and_history():
    works = ([work(f"A{i}", 2025, topic="T1") for i in range(3)] + [work("B0", 2023, topic="T1")]
             + [work("C0", 2017, topic="T2"), work("D0", 2025, topic="T3", subfield="S2")]
             + [{**work("E0", 2025), "primary_topic_id": None, "subfield_id": None}])
    out = topics.build(tables(works), Topics(counting="primary"), CUT_2025, "topic").set_index("entity_id")
    assert (out.loc["T1", "c"], out.loc["T1", "b"], out.loc["T1", "C"], out.loc["T1", "B"]) == (3, 1, 4, 1)
    assert out.loc["T2", "history_before"] == 1 and out.loc["T1", "parent_id"] == "S1"
    series = {p["period"]: (p["n"], p["den"]) for p in out.loc["T1", "series"]}
    assert series[2025] == (3, 4) and series[2016] == (0, 0)
    sub = topics.build(tables(works), Topics(counting="primary"), CUT_2025, "subfield").set_index("entity_id")
    assert sub.loc["S1", "c"] == 3 and sub.loc["S2", "c"] == 1


# 9. citation cutoffs ------------------------------------------------------------------


def test_citations_only_at_year_end_and_within_coverage():
    t = tables([work("W1", 2018)], coverage=(2017, 2026))
    semester = cutoffs(2016, 2025, "semester")
    h1 = next(c for c in semester if c.label == "2021-H1")
    assert "latest available: 2020-H2" in citations.skip_reason(t, h1, Citations())
    year_cuts = {c.label: c for c in cutoffs(2016, 2025, "year")}
    assert "outside" in citations.skip_reason(t, year_cuts["2019"], Citations())  # needs 2016
    assert citations.skip_reason(t, year_cuts["2020"], Citations()) is None


# 10. detect on a fixture sweep ---------------------------------------------------------


def fixture_works():
    """Steady topic T1, a topic T2 that takes off in 2025, partners with a new one in 2025."""
    works, n = [], 0
    for year in range(2016, 2026):
        for i in range(40):
            n += 1
            partner = "I88" if i % 2 else "I99"
            if year == 2025 and i < 15:
                partner = "I55"
            works.append(raw_work(n, date=f"{year}-{(i % 12) + 1:02d}-15",
                                  topic_id="T2" if (year == 2025 and i < 20) or i == 0 else "T1",
                                  authorships=[authorship("A1", [inst("I77", "FR", anchor=True)]),
                                               authorship("A2", [inst(partner, "KH" if partner == "I55" else "SN")])]))
    return works


def test_detect_writes_documented_outputs(config):
    session = FakeSession(fixture_works(), page_size=100)
    oa = OpenAlex(session=session, cache_dir=config.data_dir / "cache" / "openalex", max_rps=None, api_key=None)
    sweep = run_sweep(config, oa=oa, now=datetime(2026, 10, 20, tzinfo=timezone.utc))
    summary = run_detect(sweep, config)

    derived = sweep / "derived"
    assessments = pd.read_parquet(derived / "assessments.parquet")
    signals = pd.read_parquet(derived / "signals.parquet")
    assert list(assessments.columns) == ASSESSMENT_COLUMNS
    assert list(signals.columns) == ASSESSMENT_COLUMNS + SIGNAL_EXTRA_COLUMNS
    assert summary["cutoffs"] == [str(y) for y in range(2019, 2026)]
    assert {r["detector"] for r in summary["runs"]} >= {"topics", "collaborations"}
    assert json.loads((derived / "detect_summary.json").read_text())["config_hash"] == config.config_hash

    t2 = signals[(signals.signal_id == "topics:topic:T2:2025")]
    assert len(t2) == 1 and t2.label.iloc[0] == "RISING"
    assert t2.why.iloc[0].startswith("Topic T2: 20 of 40 works in 2025 (50.0%) vs 3 of 120 in 2022–2024")
    assert len(t2.work_ids_current.iloc[0]) == 20
    new_partner = signals[signals.signal_id == "collaborations:institution:I55:2025"]
    assert new_partner.label.iloc[0] == "NEW"
    assert json.loads(new_partner.extra.iloc[0])["anchor_units"][0]["institution_id"] == "I77"

    brief = write_brief(sweep, config).read_text()
    assert "cutoff **2025**" in brief and "Topic T2: 20 of 40" in brief
    assert "https://openalex.org/I55" in brief and "## Method" in brief


def test_citation_rows_without_cohort_reference_are_not_tested(config):
    from radar.detectors import plan
    supported = dict((name, f) for name, _, _, _, _, f in plan(config))["citations"]
    frame = pd.DataFrame({"c": [10, 10, 10, 2], "C": [5, 0, 5, 5], "B": [5, 5, 0, 5]})
    assert list(supported(frame)) == [True, False, False, False]


# 11. topics counting amendment ----------------------------------------------------------


def test_topics_all_counting_counts_each_topic_once_per_work():
    works = [work("W1", 2025, topic="T1", subfield="S1"), work("W2", 2025, topic="T2", subfield="S2"),
             work("W3", 2023, topic="T1", subfield="S1")]
    topic_rows = [
        ("W1", 1, "T1", "Topic T1", 0.9, "S1", "F1", "D1"), ("W1", 2, "T2", "Topic T2", 0.5, "S2", "F1", "D1"),
        ("W1", 3, "T3", "Topic T3", 0.2, "S2", "F1", "D1"),  # T3 never primary; S2 twice for W1
        ("W2", 1, "T2", "Topic T2", 0.8, "S2", "F1", "D1"),
        ("W3", 1, "T1", "Topic T1", 0.9, "S1", "F1", "D1"), ("W3", 2, "T3", "Topic T3", 0.4, "S2", "F1", "D1"),
    ]
    rows = [dict(zip(["work_id", "rank", "topic_id", "topic", "score", "subfield_id", "field_id", "domain_id"], r))
            for r in topic_rows]
    t = tables(works, topic_rows=rows)
    out = topics.build(t, Topics(counting="all"), CUT_2025, "topic").set_index("entity_id")
    assert out.loc["T2", "c"] == 2 and out.loc["T2", "work_ids_current"] == ["W1", "W2"]
    assert (out.loc["T3", "c"], out.loc["T3", "b"]) == (1, 1)
    assert out.loc["T3", "entity_label"] == "Topic T3" and out.loc["T3", "parent_id"] == "S2"
    assert set(out["C"]) == {2} and set(out["B"]) == {1}  # works, not topic assignments
    assert out.loc["T2", "extra"] == {"counting": "all", "primary_share": 0.5}
    assert out.loc["T3", "extra"]["primary_share"] == 0.0

    sub = topics.build(t, Topics(counting="all"), CUT_2025, "subfield").set_index("entity_id")
    assert sub.loc["S2", "c"] == 2  # W1 counted once although two of its topics are in S2
    assert sub.loc["S1", "c"] == 1

    primary = topics.build(t, Topics(counting="primary"), CUT_2025, "topic").set_index("entity_id")
    assert "T3" not in primary.index and primary.loc["T2", "c"] == 1


def test_counting_must_be_valid(config_table):
    from radar.config import ConfigError, parse_config
    config_table["detectors"]["topics"]["counting"] = "weighted"
    with pytest.raises(ConfigError, match="counting"):
        parse_config(config_table)
