# 03 — Universe and sweep

## 1. Universe configuration

All parameters live in one TOML file. The detection and semantic sections are specified in 04 and 05; they are shown here so the file is complete.

```toml
# config/ird.toml
[universe]
id = "ird-articles-2016-2025"
label = "IRD — articles 2016–2025"
root_institution = "I4210166444"          # IRD; anchors = institutions whose lineage contains it
filter = "authorships.institutions.lineage:I4210166444,type:article,publication_year:2016-2025,is_retracted:false"
first_year = 2016                         # 2016–2018 = baseline only; first cutoff 2019
last_year = 2025

[sweep]
data_dir = "data"
select = [
  "id", "doi", "title", "publication_date", "publication_year", "type", "language",
  "primary_topic", "topics", "authorships", "cited_by_count", "counts_by_year", "fwci",
  "abstract_inverted_index", "open_access", "primary_location", "sustainable_development_goals",
  "is_retracted", "updated_date",
]
refetch_truncated_authors = true          # singleton gets are free

[periods]
mode = "year"                             # "year" | "semester" — see 04 §2; decided at build step 2
window_months = 12                        # current window, both modes
baseline_months = 36

[engine]
alpha = 0.05                              # BH false discovery rate
min_log2_ratio = 0.585                    # |share ratio| ≥ 1.5

[detectors.topics]
levels = ["topic", "subfield"]
counting = "all"                          # "all" (up to 3 topics per work) | "primary" — see 04 §4.1
min_support = 10                          # current + baseline works

[detectors.citations]
min_age_years = 2
min_current = 5
min_cohort_size = 20
directions = ["up"]

[detectors.collaborations]
levels = ["institution", "country"]
min_support = 5
max_authors = 50
exclude_countries = []                    # e.g. ["FR"] to hide domestic partners

[semantic]
base_url = "https://albert.api.etalab.gouv.fr/v1"
model = "BAAI/bge-m3"
api_key_env = "ALBERT_API_KEY"
batch_size = 64
max_chars = 4000
min_cluster_size = 60
n_regions = 20
extra_stopwords = ["study", "results", "using", "based", "analysis", "data", "paper", "approach", "effect", "effects"]
random_state = 42
```

Rules:
- `universe.filter` is the single source of truth for membership. The config loader MUST check that `first_year`/`last_year` match the `publication_year` range in the filter.
- Secrets come only from environment variables (`OPENALEX_API_KEY`, `ALBERT_API_KEY`), loaded from a git-ignored `.env`. A config file containing a key-like value MUST be rejected.
- `config_hash` = SHA-256 of the canonical JSON of the parsed config, stored with every output.

## 2. The sweep

`radar sweep --config config/ird.toml` performs one complete harvest:

1. `sweep_id = YYYY-MM-DD` of `observed_at` (UTC). If the directory already exists, append `-2`, `-3`, … (a sweep is never overwritten).
2. `expected = oa.count("works", filter=universe.filter)`.
3. `oa.iter("works", filter=…, select=…, per_page=100, checkpoint=f"sweep-{sweep_id}")` with `cache_dir=data/cache/openalex`. About 700–800 list calls for 70–80k works (under $0.10).
4. If `refetch_truncated_authors`: for every work whose author list is flagged as truncated, `oa.get("works", id, select="id,authorships")` and replace its authorships.
5. `tables = works_tables(works, root_institution=universe.root_institution)` (client spec §6).
6. Add radar-specific columns (§3), write Parquet files and `manifest.json` (§4), then the quality report (§5).
7. If a previous sweep exists, compute the diff (§6).

The harvest can be resumed after interruption by re-running the command on the same day (the client's checkpoint replays cached pages).

## 3. Radar-specific columns

Added to `works`:
- `pub_month` = months since `first_year`-01 (0-based int), from `publication_date`. This is the only time column detection and the UI use. Windows in both period modes are ranges of `pub_month` (04 §2).
- `date_is_jan1` = `publication_date` ends in `-01-01` (bool). Used by the quality report and the semester-mode decision.
- `has_abstract` and `text_for_embedding` = `title` + `"\n\n"` + `abstract` (or the title alone), whitespace-normalized, HTML/JATS tags stripped, cut at `semantic.max_chars`.
- `n_anchor_authors` = number of distinct author positions with at least one anchor institution.

Added to `authorships`:
- `is_anchor` (from the client, root ∈ `institution_lineage`).

## 4. Snapshot layout

```
data/sweeps/<sweep_id>/
├── manifest.json
├── works.parquet
├── authorships.parquet
├── topics.parquet
├── counts_by_year.parquet
├── sdgs.parquet
├── quality.json
├── diff.json                  # if a previous sweep exists
└── derived/                   # written by later commands, safe to delete
    ├── assessments.parquet    # spec 04
    ├── signals.parquet        # spec 04
    ├── brief.md               # spec 04
    ├── embeddings.parquet     # spec 05 (symlink/copy from the cache)
    ├── map_points.parquet     # spec 05
    └── clusters.parquet       # spec 05
```

`manifest.json`:

```json
{
  "sweep_id": "2026-10-20",
  "observed_at": "2026-10-20T08:14:03Z",
  "universe": {"id": "...", "label": "...", "filter": "...", "root_institution": "I4210166444"},
  "expected_count": 75000,
  "harvested_count": 75000,
  "select": ["..."],
  "client_version": "1.0.0",
  "radar_version": "0.1.0",
  "config_hash": "sha256:...",
  "openalex_credits_used": 0.05
}
```

Counts in this example are illustrative.

If `harvested_count != expected_count`, log a warning and record both. The live API can change during a harvest; that is not an error.

## 5. Quality report (`quality.json`)

Computed, never used to block anything. Shown in the UI "About the data" panel.

- Works per year; share with abstract per year; share with a primary topic per year.
- Share of `publication_date` values ending in `-01-01` (`date_is_jan1`), overall, per year and per field, plus the expected share if dates were spread evenly (≈ 1/365). This feeds the **semester-mode decision** (04 §2.3).
- `counts_by_year` coverage: earliest and latest citation year present across works (expected: the last ten years only).
- Share of works with ≥ 1 anchor author position materialized (`n_anchor_authors > 0`). Works matched by the server filter but without a materialized anchor are kept and counted here.
- Distribution of `n_authors` and count of works above `collaborations.max_authors`.
- Share of authorships with null `author_id`; with null institution.
- Number of distinct topics, subfields, external institutions and countries.

## 6. Sweep-to-sweep diff (`diff.json`)

Computed by `radar diff <old_sweep_id> <new_sweep_id>` and automatically at the end of a sweep against the most recent previous sweep. It is the "since last sweep" panel of the UI.

| Section | Definition |
|---|---|
| `works_added` | IDs in new, not in old. Split by `publication_year` so late-indexed old works are distinguishable from genuinely recent ones. |
| `works_removed` | IDs in old, not in new (retractions, re-typing, affiliation changes, merges). Count + up to 50 IDs. |
| `topic_reassigned` | Works present in both whose `primary_topic_id` changed. Count + up to 50 examples. |
| `partners_first_seen` | External institutions (and countries) that appear in the new sweep's co-publications and in no work of the old sweep. With the works that bring them. |
| `citation_jumps` | Works present in both, ranked by `cited_by_count` increase; top 20 with old, new and delta. |
| `totals` | Counts of works, anchors, topics, partners in each sweep. |

The diff compares snapshots; it does not run statistics. It is descriptive by design.

## 7. Tests

- Config loader: rejects inline secrets; rejects a year range that disagrees with the filter.
- `sweep` against a fake client with 3 pages: writes all tables and a manifest; second run on the same day creates `<date>-2`.
- Radar columns: `text_for_embedding` uses title only when abstract is null; HTML tags removed; length ≤ `max_chars`.
- Diff on two hand-built snapshots: each section returns the expected items.
