import json
import tomllib
from pathlib import Path

import pytest

from radar.config import parse_config

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "ird.toml"
ROOT = "https://openalex.org/I4210166444"


@pytest.fixture
def config_table():
    with open(CONFIG_PATH, "rb") as fh:
        return tomllib.load(fh)


@pytest.fixture
def config(config_table, tmp_path):
    config_table["sweep"]["data_dir"] = str(tmp_path / "data")
    return parse_config(config_table)


class FakeResponse:
    def __init__(self, body, status=200, headers=None):
        self.status_code = status
        self._body = body
        self.headers = headers or {}
        self.text = json.dumps(body)

    def json(self):
        return self._body


class FakeSession:
    """Answers OpenAlex calls offline: count, cursor pages of `works`, singleton gets."""

    def __init__(self, works, page_size=2, full_authors=None):
        self.works = works
        self.page_size = page_size
        self.full_authors = full_authors or {}
        self.calls = []

    def request(self, method, url, params=None, json=None, headers=None, timeout=None):
        params = dict(params or {})
        self.calls.append((url, params))
        if "/works/" in url:
            work_id = url.rsplit("/", 1)[1]
            return FakeResponse({"id": f"https://openalex.org/{work_id}",
                                 "authorships": self.full_authors[work_id]})
        if params.get("per_page") == 1:
            return FakeResponse({"meta": {"count": len(self.works)}, "results": self.works[:1]})
        cursor = params["cursor"]
        start = 0 if cursor == "*" else int(cursor)
        end = start + self.page_size
        next_cursor = str(end) if end < len(self.works) else None
        return FakeResponse({"meta": {"count": len(self.works), "next_cursor": next_cursor},
                             "results": self.works[start:end]},
                            headers={"X-RateLimit-Credits-Used": "1"})


def authorship(author, institutions):
    return {"author": {"id": f"https://openalex.org/{author}", "display_name": author},
            "institutions": institutions}


def inst(iid, country, anchor=False):
    lineage = [f"https://openalex.org/{iid}"] + ([ROOT] if anchor else [])
    return {"id": f"https://openalex.org/{iid}", "display_name": f"Inst {iid}", "country_code": country,
            "lineage": lineage}


def topic(tid, field="Environmental Science"):
    return {"id": f"https://openalex.org/{tid}", "display_name": f"Topic {tid}", "score": 0.9,
            "subfield": {"id": "https://openalex.org/subfields/2303", "display_name": "Ecology"},
            "field": {"id": "https://openalex.org/fields/23", "display_name": field},
            "domain": {"id": "https://openalex.org/domains/3", "display_name": "Physical Sciences"}}


def raw_work(n, date="2021-05-10", authorships=None, abstract=True, topic_id="T1", cited=3):
    return {
        "id": f"https://openalex.org/W{n}",
        "title": f"<i>Work</i> {n}",
        "publication_date": date,
        "publication_year": int(date[:4]),
        "type": "article",
        "abstract_inverted_index": {"Rice": [0], "grows": [1]} if abstract else None,
        "primary_topic": topic(topic_id),
        "topics": [topic(topic_id)],
        "authorships": authorships if authorships is not None else [
            authorship("A1", [inst("I77", "FR", anchor=True)]),
            authorship("A2", [inst("I88", "SN")]),
        ],
        "cited_by_count": cited,
        "counts_by_year": [{"year": 2023, "cited_by_count": 2}, {"year": 2022, "cited_by_count": 1}],
        "is_retracted": False,
    }
