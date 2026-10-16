"""Sweep-to-sweep diff, descriptive only (specs/03 §6)."""

import json
from pathlib import Path

import pandas as pd

MAX_IDS = 50
TOP_CITATION_JUMPS = 20


def _read(sweep_dir: Path) -> dict:
    return {
        name: pd.read_parquet(sweep_dir / f"{name}.parquet")
        for name in ("works", "authorships")
    }


def _external(auth: pd.DataFrame) -> pd.DataFrame:
    return auth[(~auth["is_anchor"].fillna(False).astype(bool)) & auth["institution_id"].notna()]


def previous_sweep(root: Path, sweep_id: str) -> Path | None:
    """Most recent other complete sweep, by `observed_at` in its manifest."""
    candidates = []
    for path in Path(root).iterdir():
        manifest = path / "manifest.json"
        if path.name != sweep_id and path.is_dir() and manifest.exists():
            observed = json.loads(manifest.read_text(encoding="utf-8"))["observed_at"]
            candidates.append((observed, path.name, path))
    return max(candidates)[2] if candidates else None


def _totals(tables: dict) -> dict:
    works, auth = tables["works"], tables["authorships"]
    anchors = auth[auth["is_anchor"].fillna(False).astype(bool)]
    return {
        "works": int(len(works)),
        "anchors": int(anchors["institution_id"].nunique()),
        "topics": int(works["primary_topic_id"].nunique()),
        "partners": int(_external(auth)["institution_id"].nunique()),
    }


def diff_tables(old: dict, new: dict, old_id: str, new_id: str) -> dict:
    ow, nw = old["works"].set_index("work_id"), new["works"].set_index("work_id")
    added = nw.index.difference(ow.index)
    removed = ow.index.difference(nw.index)
    both = nw.index.intersection(ow.index)

    by_year = {}
    added_works = nw.loc[added].sort_index()
    for year, group in added_works.groupby("publication_year", dropna=False):
        key = "unknown" if pd.isna(year) else str(int(year))
        by_year[key] = {"count": int(len(group)), "ids": list(group.index[:MAX_IDS])}

    old_topic = ow.loc[both, "primary_topic_id"]
    new_topic = nw.loc[both, "primary_topic_id"]
    changed = both[(old_topic.astype("string").fillna("") != new_topic.astype("string").fillna("")).to_numpy()]
    changed = changed.sort_values()
    reassigned = [
        {
            "work_id": wid,
            "old_topic_id": ow.at[wid, "primary_topic_id"], "old_topic": ow.at[wid, "primary_topic"],
            "new_topic_id": nw.at[wid, "primary_topic_id"], "new_topic": nw.at[wid, "primary_topic"],
        }
        for wid in changed[:MAX_IDS]
    ]

    old_auth, new_ext = old["authorships"], _external(new["authorships"])
    seen_institutions = set(old_auth["institution_id"].dropna())
    seen_countries = set(old_auth["institution_country"].dropna())
    first_inst = new_ext[~new_ext["institution_id"].isin(seen_institutions)]
    institutions = [
        {
            "institution_id": inst_id,
            "institution_name": group["institution_name"].iloc[0],
            "country": group["institution_country"].iloc[0],
            "work_ids": sorted(group["work_id"].unique()),
        }
        for inst_id, group in first_inst.groupby("institution_id", sort=True)
    ]
    first_country = new_ext[
        new_ext["institution_country"].notna() & ~new_ext["institution_country"].isin(seen_countries)
    ]
    countries = [
        {"country": country, "work_ids": sorted(group["work_id"].unique())}
        for country, group in first_country.groupby("institution_country", sort=True)
    ]

    cites = pd.DataFrame({
        "old": ow.loc[both, "cited_by_count"].astype("Int64"),
        "new": nw.loc[both, "cited_by_count"].astype("Int64"),
    }).fillna(0)
    cites["delta"] = cites["new"] - cites["old"]
    cites = cites[cites["delta"] > 0].reset_index(names="work_id")
    cites = cites.sort_values(["delta", "work_id"], ascending=[False, True]).head(TOP_CITATION_JUMPS)
    jumps = [
        {"work_id": r.work_id, "title": nw.at[r.work_id, "title"],
         "old": int(r.old), "new": int(r.new), "delta": int(r.delta)}
        for r in cites.itertuples()
    ]

    return {
        "old_sweep": old_id,
        "new_sweep": new_id,
        "works_added": {"count": int(len(added)), "by_publication_year": by_year},
        "works_removed": {"count": int(len(removed)), "ids": list(removed.sort_values()[:MAX_IDS])},
        "topic_reassigned": {"count": int(len(changed)), "examples": reassigned},
        "partners_first_seen": {"institutions": institutions, "countries": countries},
        "citation_jumps": jumps,
        "totals": {old_id: _totals(old), new_id: _totals(new)},
    }


def diff_sweeps(old_dir: Path, new_dir: Path) -> dict:
    old_dir, new_dir = Path(old_dir), Path(new_dir)
    return diff_tables(_read(old_dir), _read(new_dir), old_dir.name, new_dir.name)
