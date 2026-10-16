"""Radar columns on top of the client's tidy tables, and the quality report (specs/03 §3, §5)."""

import html
import re

import pandas as pd

from .config import Config

_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")

# Bucket edges for the n_authors distribution in quality.json.
AUTHOR_BUCKETS = [(1, 1), (2, 5), (6, 10), (11, 20), (21, 50), (51, 100), (101, None)]


def clean_text(text) -> str:
    """Strip HTML/JATS tags, unescape entities, normalize whitespace."""
    if text is None or (isinstance(text, float) and pd.isna(text)) or text is pd.NA:
        return ""
    text = html.unescape(_TAG.sub(" ", str(text)))
    return _SPACE.sub(" ", text).strip()


def text_for_embedding(title, abstract, max_chars: int) -> str:
    title, abstract = clean_text(title), clean_text(abstract)
    text = f"{title}\n\n{abstract}" if title and abstract else (title or abstract)
    return text[:max_chars]


def pub_month(dates: pd.Series, years: pd.Series, first_year: int) -> pd.Series:
    """Months since January of first_year, from publication_date (publication_year if no date)."""
    parsed = pd.to_datetime(dates, format="%Y-%m-%d", errors="coerce")
    year = parsed.dt.year.astype("Int64").fillna(years.astype("Int64"))
    month = parsed.dt.month.astype("Int64").fillna(1)
    return ((year - first_year) * 12 + month - 1).astype("Int64")


def add_radar_columns(tables: dict, config: Config) -> dict:
    works = tables["works"].copy()
    auth = tables["authorships"]

    works["pub_month"] = pub_month(works["publication_date"], works["publication_year"], config.universe.first_year)
    dates = works["publication_date"].astype("string")
    works["date_is_jan1"] = dates.str.endswith("-01-01").astype("boolean")
    works["text_for_embedding"] = [
        text_for_embedding(t, a, config.semantic.max_chars) for t, a in zip(works["title"], works["abstract"])
    ]
    anchors = auth[auth["is_anchor"].fillna(False).astype(bool)]
    per_work = anchors.groupby("work_id")["author_position_idx"].nunique()
    works["n_anchor_authors"] = works["work_id"].map(per_work).fillna(0).astype("Int64")
    return {**tables, "works": works}


def _share(mask: pd.Series) -> float | None:
    return round(float(mask.mean()), 4) if len(mask) else None


def _by(frame: pd.DataFrame, key: str, column: str) -> dict:
    grouped = frame.groupby(key, dropna=True)[column]
    return {str(k): round(float(v), 4) for k, v in grouped.mean().items()}


def quality_report(tables: dict, config: Config, authors_refetched: int = 0) -> dict:
    works, auth = tables["works"], tables["authorships"]
    cby, topics = tables["counts_by_year"], tables["topics"]
    w = works.assign(
        _abstract=works["has_abstract"].fillna(False).astype(bool),
        _topic=works["primary_topic_id"].notna(),
        _jan1=works["date_is_jan1"].fillna(False).astype(bool),
    )

    # January-1 dates: feeds the semester-mode decision (04 §2.3).
    per_field = {}
    for field_name, group in w.groupby("field", dropna=True):
        per_field[str(field_name)] = {"works": int(len(group)), "share": round(float(group["_jan1"].mean()), 4)}
    overall = _share(w["_jan1"])
    big_fields_over = sorted(f for f, v in per_field.items() if v["works"] >= 500 and v["share"] > 0.15)
    semester_allowed = overall is not None and overall <= 0.05 and not big_fields_over

    n_authors = works["n_authors"].dropna().astype(int)
    buckets = {}
    for low, high in AUTHOR_BUCKETS:
        label = f"{low}+" if high is None else (str(low) if low == high else f"{low}-{high}")
        mask = n_authors >= low if high is None else n_authors.between(low, high)
        buckets[label] = int(mask.sum())
    max_authors = config.detectors.collaborations.max_authors

    external = auth[(~auth["is_anchor"].fillna(False).astype(bool)) & auth["institution_id"].notna()]
    years = cby["year"].dropna()

    return {
        "works": int(len(works)),
        "works_per_year": {str(k): int(v) for k, v in works.groupby("publication_year").size().items()},
        "abstract_share_per_year": _by(w, "publication_year", "_abstract"),
        "abstract_share": _share(w["_abstract"]),
        "primary_topic_share_per_year": _by(w, "publication_year", "_topic"),
        "publication_date_missing": int(works["publication_date"].isna().sum()),
        "jan1": {
            "share": overall,
            "expected_if_even": round(1 / 365, 4),
            "per_year": _by(w, "publication_year", "_jan1"),
            "per_field": per_field,
            "semester_rule": {
                "overall_le_5pct": overall is not None and overall <= 0.05,
                "fields_ge_500_works_over_15pct": big_fields_over,
                "semester_allowed": semester_allowed,
            },
        },
        "counts_by_year_coverage": {
            "earliest_year": int(years.min()) if len(years) else None,
            "latest_year": int(years.max()) if len(years) else None,
            "works_with_citations": int(cby["work_id"].nunique()),
        },
        "anchor_materialized_share": _share(works["n_anchor_authors"].fillna(0) > 0),
        "n_authors": {
            "quantiles": {
                q: int(n_authors.quantile(p)) for q, p in
                [("min", 0), ("p25", .25), ("median", .5), ("p75", .75), ("p90", .9), ("p99", .99), ("max", 1)]
            } if len(n_authors) else {},
            "buckets": buckets,
            "above_max_authors": int((n_authors > max_authors).sum()),
            "max_authors": max_authors,
            "refetched_truncated": authors_refetched,
        },
        "authorships_null_author_share": _share(auth["author_id"].isna()),
        "authorships_null_institution_share": _share(auth["institution_id"].isna()),
        "distinct": {
            "topics": int(topics["topic_id"].nunique()),
            "subfields": int(topics["subfield_id"].nunique()),
            "external_institutions": int(external["institution_id"].nunique()),
            "countries": int(external["institution_country"].dropna().nunique()),
        },
    }
