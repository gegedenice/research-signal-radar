# 02 — `openalex-api-client` v1

Repository: `https://github.com/gegedenice/openalex-api-client` (rewrite in place, new major version).

## 1. Goal

A small, generic, dependable Python client for the OpenAlex REST API, plus helpers that turn
work records into tidy tables. It must serve two projects without project-specific code:

- **Delta Radar**: harvest ≈ 50k works with full authorships, abstracts and `counts_by_year`.
- **IRD OpenAlex study**: counts and breakdowns, e.g. South co-publications for SDG 14,
  Cambodia co-publications, open-access status by field.

## 2. Problems in v0 that v1 must fix

| v0 behaviour | Consequence | v1 |
|---|---|---|
| Page-number pagination computed from `meta.count` | Fails past 10,000 results (OpenAlex basic paging limit) | Cursor paging |
| No retry; any error stops `list_all_*` silently (`break`) | Partial harvests without warning | Retry with backoff; raise on final failure |
| `logging.info(f"... api_key: {self.api_key}")` | API key written to logs | Key never logged; masked in `repr` |
| `logging.basicConfig` called at import | Overrides the caller's logging setup | Module logger only (`logging.getLogger(__name__)`) |
| No `group_by`, `select`, `sample`, `search` helpers | Every caller rebuilds query strings | First-class parameters |
| "Digest" = flat dict with `|`-joined strings, 10-value truncation | Lossy, cannot be joined or counted reliably | Tidy tables (§6) |
| Hard dependency on pandas/numpy though unused by core | Heavy install | Core depends on `requests` only; `[tables]` extra adds pandas + pyarrow |
| Endpoint-specific methods duplicated per entity (`list_all_funders`, …) | Boilerplate, missing entities (sources, subfields, fields, domains, keywords…) | One generic API taking an `entity` name |

## 3. OpenAlex facts the client relies on

From the official docs (developers.openalex.org, checked October 2026):

- The API key is passed as the `api_key` query parameter. A free key gives a daily budget; usage is metered per call type (list+filter calls cost $0.10 per 1,000, singleton gets are free).
- `per_page` maximum is **100**.
- Basic paging stops at 10,000 results; cursor paging (`cursor=*`, then `meta.next_cursor`) is required beyond that.
- More than 100 requests per second, or exhausting the daily budget, returns **HTTP 429**.
- Each response carries `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Credits-Used`, `X-RateLimit-Reset`.
- At most 100 OR values per filter. `sample` maximum is 10,000.
- **Verify:** `select` accepts root-level fields only; `group_by` supports cursor paging; the name of the flag for truncated author lists in list results (believed to be `is_authors_truncated`).

## 4. Public API

```python
from openalex_api_client import OpenAlex

oa = OpenAlex(
    api_key=None,            # default: env OPENALEX_API_KEY; None → anonymous
    base_url="https://api.openalex.org",
    timeout=30,
    max_retries=6,
    user_agent="openalex-api-client/1.0",
    cache_dir=None,          # optional: enables page cache + resume (§5)
)

oa.get("works", "W2741809807", select=None) -> dict
oa.get("works", "https://doi.org/10.1234/x")   # DOI, ROR, ORCID etc. accepted as IDs
oa.count("works", filter=...) -> int
oa.iter("works", filter=..., search=None, select=None, sort=None,
        per_page=100, max_results=None, checkpoint=None) -> Iterator[dict]
oa.list(...same as iter...) -> list[dict]
oa.group_by("works", "authorships.countries", filter=...) -> list[dict]   # all groups, paged
oa.sample("works", n=500, seed=42, filter=...) -> list[dict]
oa.usage -> Usage(limit, remaining, credits_used_total, reset_seconds)   # from last headers
```

- `entity` is any OpenAlex entity path (`works`, `authors`, `sources`, `institutions`, `topics`, `subfields`, `fields`, `domains`, `publishers`, `funders`, `keywords`, …). No per-entity methods.
- `filter` accepts a string or a dict (§4.1).
- `iter` always uses cursor paging. It stops at `next_cursor is None` or at `max_results`. It raises `PaginationError` on cursor loops or if `meta.count` changes during iteration *and* `strict=True` (default `False`: log a warning).
- `group_by` returns `[{"key": ..., "key_display_name": ..., "count": ...}]` and follows cursors until exhausted. The unknown/null group is kept with `key=None`.
- All methods return plain dicts/lists (no custom result classes).

### 4.1 Three ways to ask — no query builder

There is no filter-building class. A user writes queries the way OpenAlex documents them, and
the client accepts them in whichever form the user already has.

**(a) Paste a URL** — the easiest for manual use: build the query on openalex.org or in the
browser, copy the API URL, paste it.

```python
url = ("https://api.openalex.org/works?filter=authorships.institutions.lineage:I4210166444,"
       "type:article,publication_year:2020-2025,is_retracted:false&select=id,title")
oa.list_url(url)          # all results (cursor paging added automatically)
oa.count_url(url)         # meta.count only
oa.iter_url(url, max_results=500)
```
The client parses the URL. It accepts `api.openalex.org` and `openalex.org` web URLs, removes any
`api_key`/`page`/`cursor`/`mailto` parameter, and keeps the rest unchanged.

**(b) A classic filter, as a string or a dict.** Values are written exactly as in the OpenAlex
docs (`2020-2025`, `!FR`, `>10`, `KH|VN`).

```python
IRD = "authorships.institutions.lineage:I4210166444,type:article,publication_year:2020-2025,is_retracted:false"
oa.count("works", filter=IRD)

ird = {"authorships.institutions.lineage": "I4210166444", "type": "article",
       "publication_year": "2020-2025", "is_retracted": "false"}
oa.group_by("works", "authorships.countries", filter={**ird, "publication_year": "2021-2025"})
```
The dict form has only two conveniences: a list becomes an OR (`["KH", "VN"]` → `KH|VN`) and
Python `True/False/int` become `true/false/"10"`. Changing a query is plain Python
(`{**ird, "key": "value"}`). A list longer than 100 values raises `ValueError`, because OpenAlex
limits OR to 100 values per filter.

**(c) OQL** — OpenAlex's text query language ([help.openalex.org/api/oql](https://help.openalex.org/api/oql/)).

```python
oa.oql("works where institution is (I4210166444) and type is (article) "
       "and year >= (2020) and year <= (2025)", select="id,title", max_results=None)
oa.oql("works where year is (2020) group by type")   # returns the group_by list
oa.translate(IRD_URL_or_OQL)   # → {"oql", "oqo", "classic_url", "valid", "errors"} via /query, no execution
```
- Sent as `POST /` with the body `{"oql": ..., "per_page": 100, "cursor": ..., "select": ...}`. Sorting, selection and paging are sibling keys, never inside the OQL text. GET `/?oql=` is limited to 8,190 bytes, so POST is always used.
- `oa.oql` iterates with cursors like `iter`. If the query contains `group by`, it returns the groups.
- `oa.translate` is the learning tool. Given a classic URL it shows the OQL equivalent, given OQL it shows the classic URL when one exists, and it validates without spending a list call.
- **Status:** OpenAlex states that OQL "is in active development". The client supports it for manual and exploratory use, and pins nothing on it. Delta Radar's universe stays a classic filter string, which is stable and documented. **Verify** with `oa.translate` whether `authorships.institutions.lineage` (IRD and its child units) has an OQL equivalent: the documented `institution is (…)` may match the exact institution only.

## 5. Reliability

- **Retry** on 429, 500, 502, 503, 504 and connection/timeouts. Delay: `Retry-After` if present, else exponential backoff with jitter (`min(60, 1.5**attempt) + uniform(0, 1)`). On a 429 with `X-RateLimit-Remaining: 0`, raise `BudgetExhausted` immediately (retrying is pointless until reset) with the reset time in the message.
- **Throttle**: at most `max_rps=10` requests per second by default (well under the 100/s limit).
- **Errors**: `OpenAlexError` base; `HTTPError(status, url_without_key, body_excerpt)`; `BudgetExhausted`; `PaginationError`. URLs in messages and logs MUST have `api_key` removed.
- **Page cache and resume** (only when `cache_dir` is set and `checkpoint="name"` is passed to `iter`):
  - each page is written to `cache_dir/name/page-00001.json.gz` with the request params (minus key) and the cursor that produced it;
  - re-running the same `iter` with the same checkpoint replays cached pages, then continues from the last `next_cursor`;
  - if the params differ from those stored in `cache_dir/name/params.json`, raise instead of mixing harvests.
- **Session**: one `requests.Session`, gzip accepted, no Brotli.

## 6. Tidy tables (`openalex_api_client.tidy`, extra `[tables]`)

Pure functions, no network. They take an iterable of raw work dicts and return pandas DataFrames.

```python
from openalex_api_client.tidy import works_tables, reconstruct_abstract, short_id
tables = works_tables(works, root_institution="I4210166444")   # root optional
tables["works"], tables["authorships"], tables["topics"], tables["counts_by_year"],
tables["sdgs"], tables["funders"]
```

| Table | One row per | Columns (minimum) |
|---|---|---|
| `works` | work | `work_id`, `doi`, `title`, `abstract`, `has_abstract`, `publication_date`, `publication_year`, `type`, `language`, `cited_by_count`, `fwci`, `is_retracted`, `oa_status`, `is_oa`, `source_id`, `source_name`, `primary_topic_id`, `primary_topic`, `subfield_id`, `subfield`, `field_id`, `field`, `domain_id`, `domain`, `n_authors`, `authors_truncated`, `updated_date` |
| `authorships` | work × author position × institution (an author with no institution gets one row with null institution) | `work_id`, `author_position_idx` (0-based), `author_id`, `author_name`, `is_corresponding`, `institution_id`, `institution_name`, `institution_ror`, `institution_country`, `institution_type`, `institution_lineage` (list), `is_anchor` (only if `root_institution` given: root ∈ lineage) |
| `topics` | work × topic (up to 3) | `work_id`, `rank` (1 = primary), `topic_id`, `topic`, `score`, `subfield_id`, `field_id`, `domain_id` |
| `counts_by_year` | work × year with ≥ 1 citation | `work_id`, `year`, `cited_by_count` |
| `sdgs` | work × SDG | `work_id`, `sdg_id`, `sdg`, `score` |
| `funders` | work × funder/award | `work_id`, `funder_id`, `funder`, `award_id` |

Rules:
- All IDs are short form (`W123`, `I456`, `T789`, `A…`). `short_id()` is public.
- `reconstruct_abstract(inverted_index) -> str | None` returns `None` (not a placeholder string) when absent.
- Missing nested objects produce nulls, never exceptions. A malformed record is skipped with a warning that includes its ID.
- `works_tables` also accepts a path to cached pages (`*.json.gz`) so a harvest can be re-tidied offline.
- `write_parquet(tables, directory)` helper.

## 7. Small CLI (optional, low priority)

```
openalex dump works --filter "..." --select "..." --out works.parquet [--checkpoint name]
openalex count works --filter "..." [--group-by authorships.countries]
```

## 8. Backwards compatibility

- Keep `OpenAlexClient` as a thin deprecated wrapper for one version (`get_work`, `list_works`, `list_all_works` …) that calls the new API and emits `DeprecationWarning`. `digest=True` is kept in the wrapper only.
- Bump to `1.0.0`. Move packaging to `pyproject.toml` (hatchling), Python ≥ 3.10.

## 9. Tests (pytest, no network)

Inject a fake transport (`OpenAlex(..., session=FakeSession(pages))`):

1. Cursor iteration over 3 pages stops at `next_cursor=None`; total = sum of results.
2. `max_results` truncates exactly.
3. Retry: 429 with `Retry-After: 1` then 200 succeeds; 5 × 503 then raises `HTTPError`; 429 with remaining 0 raises `BudgetExhausted` without retry.
4. API key never appears in exception messages, log records or `repr(oa)`.
5. Filters: string passed unchanged; dict → string with list-as-OR and booleans; > 100 OR values raises. URL parsing: an API URL and an openalex.org web URL give the same request; `api_key`, `page`, `cursor` and `mailto` are removed. OQL: POST body has the query and the paging keys as siblings; a `group by` query returns groups; a 400 response surfaces the `validation` message.
6. `group_by` follows cursors and keeps the null group.
7. Resume: interrupt after page 2, rerun with the same checkpoint → pages 1–2 read from cache, 3 fetched; different params → raises.
8. `works_tables` on 3 fixture works (one without abstract, one author without institution, one with 3 topics) gives the expected row counts and nulls; `is_anchor` true only where the lineage contains the root.
9. `reconstruct_abstract` round-trips a known abstract.

## 10. Acceptance examples (to put in the README)

```python
from openalex_api_client import OpenAlex
oa = OpenAlex()                                   # key read from OPENALEX_API_KEY

# Delta Radar universe — pasted URL
oa.count_url("https://api.openalex.org/works?filter=authorships.institutions.lineage:I4210166444,"
             "type:article,publication_year:2020-2025,is_retracted:false")   # ≈ 47,851 in Oct 2026

# IRD study — partner countries of IRD articles linked to SDG 14, 2021–2025 (dict form)
ird = {"authorships.institutions.lineage": "I4210166444", "type": "article", "is_retracted": "false"}
oa.group_by("works", "authorships.countries",
            filter={**ird, "publication_year": "2021-2025", "sustainable_development_goals.id": "sdgs/14"})

# IRD study — OA status by field
for field in oa.list("fields"):
    oa.group_by("works", "open_access.oa_status",
                filter={**ird, "publication_year": "2021-2025", "primary_topic.field.id": short_id(field["id"])})

# The same kind of question in OQL, and the translation tool
oa.oql("works where year is (2023) group by type")
oa.translate("https://api.openalex.org/works?filter=authorships.institutions.lineage:I4210166444")
```

Exact filter values such as the SDG ID format are **verify** items (`oa.translate` helps check them).
