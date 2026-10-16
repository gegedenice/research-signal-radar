import pandas as pd

from radar.diff import diff_sweeps, previous_sweep


def works(rows):
    return pd.DataFrame(rows, columns=["work_id", "title", "publication_year", "primary_topic_id",
                                       "primary_topic", "cited_by_count"])


def auth(rows):
    return pd.DataFrame(rows, columns=["work_id", "author_position_idx", "institution_id", "institution_name",
                                       "institution_country", "is_anchor"])


def write(path, w, a, observed):
    path.mkdir(parents=True)
    w.to_parquet(path / "works.parquet")
    a.to_parquet(path / "authorships.parquet")
    (path / "manifest.json").write_text(f'{{"observed_at": "{observed}"}}')


def test_diff_sections(tmp_path):
    old_w = works([
        ("W1", "One", 2020, "T1", "Topic 1", 10),
        ("W2", "Two", 2021, "T2", "Topic 2", 5),
        ("W3", "Three", 2022, "T3", "Topic 3", 0),
    ])
    old_a = auth([
        ("W1", 0, "I1", "IRD", "FR", True), ("W1", 1, "I10", "Univ A", "SN", False),
        ("W2", 0, "I1", "IRD", "FR", True), ("W3", 0, "I1", "IRD", "FR", True),
    ])
    new_w = works([
        ("W1", "One", 2020, "T1", "Topic 1", 30),
        ("W2", "Two", 2021, "T9", "Topic 9", 6),
        ("W4", "Four", 2025, "T1", "Topic 1", 0),
        ("W5", "Five", 2019, "T2", "Topic 2", 1),
    ])
    new_a = auth([
        ("W1", 0, "I1", "IRD", "FR", True), ("W1", 1, "I10", "Univ A", "SN", False),
        ("W2", 0, "I1", "IRD", "FR", True),
        ("W4", 0, "I1", "IRD", "FR", True), ("W4", 1, "I20", "Univ B", "KH", False),
        ("W5", 0, "I1", "IRD", "FR", True), ("W5", 1, "I20", "Univ B", "KH", False),
        ("W5", 2, "I10", "Univ A", "SN", False), ("W5", 3, None, None, None, None),
    ])
    root = tmp_path / "sweeps"
    write(root / "2026-10-01", old_w, old_a, "2026-10-01T08:00:00Z")
    write(root / "2026-10-20", new_w, new_a, "2026-10-20T08:00:00Z")

    assert previous_sweep(root, "2026-10-20").name == "2026-10-01"
    assert previous_sweep(root, "2026-10-01").name == "2026-10-20"

    d = diff_sweeps(root / "2026-10-01", root / "2026-10-20")
    assert d["works_added"] == {"count": 2, "by_publication_year": {
        "2019": {"count": 1, "ids": ["W5"]}, "2025": {"count": 1, "ids": ["W4"]}}}
    assert d["works_removed"] == {"count": 1, "ids": ["W3"]}
    assert d["topic_reassigned"]["count"] == 1
    assert d["topic_reassigned"]["examples"][0] == {
        "work_id": "W2", "old_topic_id": "T2", "old_topic": "Topic 2", "new_topic_id": "T9", "new_topic": "Topic 9"}
    assert d["partners_first_seen"]["institutions"] == [
        {"institution_id": "I20", "institution_name": "Univ B", "country": "KH", "work_ids": ["W4", "W5"]}]
    assert d["partners_first_seen"]["countries"] == [{"country": "KH", "work_ids": ["W4", "W5"]}]
    assert [(j["work_id"], j["delta"]) for j in d["citation_jumps"]] == [("W1", 20), ("W2", 1)]
    assert d["totals"] == {
        "2026-10-01": {"works": 3, "anchors": 1, "topics": 3, "partners": 1},
        "2026-10-20": {"works": 4, "anchors": 1, "topics": 3, "partners": 2},
    }
