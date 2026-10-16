# client.py — Claim Delta Mini-Radar :: connector bridge
#
# Lets the radar CONSUME the generalist agentic-stack source connectors
# (search-records-hal, search-theses-fr, search-works-openalex — as CLIs or
# MCP tools) instead of its own built-in fetch_* helpers. Each connector emits
# an OpenAlex-compatible normalized record; this bridge maps those records into
# the radar pipeline work-dict {id, title, date, abstract, lang, ...} consumed
# by extract_claims / embed_claims / cluster_delta.
#
# Two layers:
#   1. Pure mappers  — map_hal_record / map_theses_record / map_openalex_record.
#      No I/O; use these when records already come from an MCP tool call.
#   2. CLI runners   — fetch_hal / fetch_theses via the agentic-stack skill CLIs
#      (subprocess). Point AGENTIC_STACK_ROOT (env or arg) at the repo clone.
#
# The radar never re-implements source quirks (HAL Solr fields, theses.fr
# hydration, OpenAlex abstract inversion) — the connectors own those.

import os, json, subprocess

DEFAULT_MIN_ABSTRACT = 200


# ---- Pure mappers: normalized connector record -> radar work-dict ------------

def map_hal_record(rec):
    """HAL normalized record (search-records-hal / mcp hal) -> radar work-dict."""
    return {
        "id": rec.get("hal_id") or rec.get("id"),
        "title": (rec.get("title") or "").strip(),
        "date": rec.get("date") or "",
        "abstract": (rec.get("abstract") or "").strip(),
        "lang": rec.get("language") or "",
        "doctype": rec.get("doc_type") or "",
        "source": "hal",
    }


def map_theses_record(rec):
    """theses.fr normalized record (search-theses-fr / mcp theses-fr) -> work-dict.
    Requires a hydrated record (abstract present); search hits without --hydrate
    carry abstract=None and are dropped by the min_abstract filter downstream."""
    nnt = rec.get("nnt") or rec.get("id")
    langs = rec.get("languages") or []
    return {
        "id": f"these-{nnt}" if nnt and not str(nnt).startswith("these-") else nnt,
        "title": (rec.get("title") or "").strip(),
        "date": rec.get("date") or "",
        "abstract": (rec.get("abstract") or "").strip(),
        "lang": ",".join(langs) if isinstance(langs, list) else (langs or ""),
        "discipline": rec.get("discipline") or "",
        "source": "theses-fr",
    }


def map_openalex_record(rec):
    """OpenAlex normalized record (search-works-openalex) -> radar work-dict."""
    oid = rec.get("id") or ""
    return {
        "id": oid.split("/")[-1] if oid else oid,
        "title": (rec.get("title") or "").strip(),
        "date": rec.get("date") or rec.get("publication_date") or "",
        "abstract": (rec.get("abstract") or "").strip(),
        "lang": rec.get("language") or "",
        "cited": rec.get("cited_by_count") or rec.get("cited") or 0,
        "source": "openalex",
    }


_MAPPERS = {"hal": map_hal_record, "theses-fr": map_theses_record,
            "theses": map_theses_record, "openalex": map_openalex_record}


def map_records(records, source, min_abstract=DEFAULT_MIN_ABSTRACT):
    """Map a list of normalized records from `source` to work-dicts, keeping
    only those whose abstract meets min_abstract."""
    fn = _MAPPERS[source]
    out = [fn(r) for r in records]
    return [w for w in out if len(w.get("abstract") or "") >= min_abstract]


# ---- CLI runners: invoke the agentic-stack skill CLIs ------------------------

def _repo_root(root=None):
    root = root or os.environ.get("AGENTIC_STACK_ROOT")
    if not root:
        raise RuntimeError(
            "Set AGENTIC_STACK_ROOT (env or arg) to the agentic-stack repo clone, "
            "or use the pure map_* functions on records you already fetched.")
    return root


def _run_cli(root, skill, argv):
    script = os.path.join(root, "skills", skill, "scripts", "cli.py")
    if not os.path.exists(script):
        raise FileNotFoundError(script)
    # Prefer `uv run` (PEP-723 header); fall back to python3.
    for launcher in (["uv", "run", script], ["python3", script]):
        try:
            p = subprocess.run(launcher + argv, capture_output=True, text=True, timeout=180)
        except FileNotFoundError:
            continue
        if p.returncode == 0 and p.stdout.strip():
            return json.loads(p.stdout)
        if launcher[0] == "python3":
            raise RuntimeError(f"{skill} CLI failed: {p.stderr[:400]}")
    raise RuntimeError(f"could not launch {skill} CLI")


def fetch_hal(collection, from_date, to_date, domain="0.info",
              rows=45, min_abstract=DEFAULT_MIN_ABSTRACT, root=None):
    """HAL via search-records-hal CLI -> radar work-dicts (abstracts only)."""
    root = _repo_root(root)
    # HAL CLI default fl omits the abstract — request it (and the fields the
    # radar work-dict maps) explicitly, else `abstract` comes back empty.
    fl = ("halId_s,title_s,uri_s,abstract_s,authFullName_s,doiId_s,"
          "publicationDate_s,producedDate_s,publicationDateY_i,docType_s,"
          "journalTitle_s,language_s,fileMain_s")
    argv = ["search", "--collection", collection, "--q", "*:*",
            "--fq", f"domain_s:{domain}", "--fq", "abstract_s:[* TO *]",
            "--fq", f"producedDate_s:[{from_date} TO {to_date}]",
            "--fl", fl, "--rows", str(rows), "--sort", "producedDate_s desc"]
    data = _run_cli(root, "search-records-hal", argv)
    return map_records(data.get("results", []), "hal", min_abstract)


def fetch_theses(from_date, to_date, code_etab="COAZ", discipline="informatique",
                 cap=60, min_abstract=DEFAULT_MIN_ABSTRACT, root=None):
    """theses.fr via search-theses-fr CLI (with --hydrate) -> radar work-dicts."""
    root = _repo_root(root)
    argv = ["search", "--etab", code_etab, "--discipline", discipline,
            "--date-from", from_date, "--date-to", to_date,
            "--rows", str(cap), "--hydrate"]
    data = _run_cli(root, "search-theses-fr", argv)
    return map_records(data.get("results", []), "theses-fr", min_abstract)
