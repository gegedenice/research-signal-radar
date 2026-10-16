import pandas as pd

from openalex_api_client.tidy import works_tables
from radar.tables import add_radar_columns, pub_month, text_for_embedding

from conftest import ROOT, raw_work


def test_text_for_embedding_title_only_when_no_abstract():
    assert text_for_embedding("A <i>title</i>", None, 4000) == "A title"
    assert text_for_embedding("A title", pd.NA, 4000) == "A title"
    assert text_for_embedding("T", "Some <jats:p>abstract</jats:p> &amp; more", 4000) == "T\n\nSome abstract & more"


def test_text_for_embedding_strips_tags_and_is_bounded():
    text = text_for_embedding("Title", "<p>" + "word " * 2000 + "</p>", 100)
    assert len(text) <= 100 and "<" not in text
    assert text.startswith("Title\n\nword word")


def test_pub_month_from_date_or_year():
    months = pub_month(pd.Series(["2016-01-15", "2025-12-01", None, "bad"]),
                       pd.Series([2016, 2025, 2018, 2019]), 2016)
    assert list(months) == [0, 119, 24, 36]


def test_radar_columns(config):
    tables = add_radar_columns(works_tables([raw_work(1), raw_work(2, date="2018-01-01", abstract=False)],
                                            root_institution=ROOT), config)
    works = tables["works"].set_index("work_id")
    assert works.loc["W1", "text_for_embedding"] == "Work 1\n\nRice grows"
    assert works.loc["W2", "text_for_embedding"] == "Work 2"
    assert bool(works.loc["W2", "date_is_jan1"]) and works.loc["W2", "pub_month"] == 24
    assert list(works["n_anchor_authors"]) == [1, 1]
