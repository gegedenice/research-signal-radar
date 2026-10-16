# kb_emitter.py — Claim Delta Mini-Radar :: per-topic Markdown KB emitter
#
# Emits one Markdown file per claim-cluster, with QMD/YAML front-matter, so a
# radar run becomes a browsable, Quarto-searchable knowledge base (the "all
# metadata in .md files + QMD search" pattern). One file per topic; an index
# file links them and records the run's delta summary.
#
# Consumes the cluster dicts produced by cluster_delta():
#   {label, status (NEW|PERSISTING|DISAPPEARING), n, n_papers, members:[...]}
# where each member is a claim dict {text, work_id, title, date, window, ...}
# (member shape is tolerant — missing keys degrade gracefully).

import os, re, json, datetime

_STATUS_TAG = {"NEW": "emerging", "PERSISTING": "persisting", "DISAPPEARING": "receding"}


def _slug(s, maxlen=60):
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return (s[:maxlen].rstrip("-")) or "topic"


def _yaml_scalar(s):
    s = str(s or "").replace('"', "'").replace("\n", " ").strip()
    return f'"{s}"'


def _yaml_list(items):
    if not items:
        return "[]"
    return "[" + ", ".join(_yaml_scalar(x) for x in items) + "]"


def _member_fields(m):
    """Tolerant accessor for a claim member across pipeline variants."""
    text = m.get("text") or m.get("claim") or ""
    wid = m.get("work_id") or m.get("paper_id") or m.get("id") or ""
    title = m.get("title") or m.get("paper_title") or ""
    date = m.get("date") or m.get("paper_date") or ""
    window = m.get("window") or m.get("win") or ""
    return text, wid, title, date, window


def cluster_to_markdown(cluster, meta=None, rank=None):
    """Render one cluster dict to a QMD-front-matter Markdown string."""
    meta = meta or {}
    label = cluster.get("label") or "Untitled topic"
    status = (cluster.get("status") or "").upper()
    tag = _STATUS_TAG.get(status, "topic")
    members = cluster.get("members") or []
    n = cluster.get("n", len(members))
    n_papers = cluster.get("n_papers")

    categories = [tag]
    if meta.get("source"):
        categories.append(meta["source"])
    if meta.get("field"):
        categories.append(meta["field"])

    fm = ["---",
          f"title: {_yaml_scalar(label)}",
          f"status: {_yaml_scalar(status.lower())}",
          f"signal: {_yaml_scalar(tag)}",
          f"claim_count: {n}",
          f"paper_count: {n_papers if n_papers is not None else 'null'}",
          f"categories: {_yaml_list(categories)}"]
    if meta.get("source"):
        fm.append(f"source: {_yaml_scalar(meta['source'])}")
    if meta.get("institution"):
        fm.append(f"institution: {_yaml_scalar(meta['institution'])}")
    if meta.get("window_from") or meta.get("window_to"):
        fm.append(f"window_from: {_yaml_scalar(meta.get('window_from',''))}")
        fm.append(f"window_to: {_yaml_scalar(meta.get('window_to',''))}")
    if rank is not None:
        fm.append(f"rank: {rank}")
    fm.append(f"generated: {_yaml_scalar(datetime.date.today().isoformat())}")
    fm.append("---")

    body = ["", f"# {label}", "",
            f"**Signal:** {tag} ({status.lower() or 'n/a'}) · "
            f"**{n} claim{'s' if n != 1 else ''}**"
            + (f" across {n_papers} paper{'s' if n_papers != 1 else ''}" if n_papers is not None else ""),
            ""]

    if status == "NEW":
        body.append("> This topic appears in the recent window with no semantic "
                    "match in the prior window — a candidate emerging line.")
    elif status == "DISAPPEARING":
        body.append("> This topic was present in the prior window but has no "
                    "match in the recent window — a receding or completed line.")
    elif status == "PERSISTING":
        body.append("> This topic carries across both windows — an established, "
                    "continuing line.")
    body.append("")

    body.append("## Claims")
    body.append("")
    for m in members:
        text, wid, title, date, window = _member_fields(m)
        prefix = f"[{window}] " if window else ""
        src = f" — *{title}*" if title else ""
        ref = f" (`{wid}`)" if wid else ""
        dt = f" · {date}" if date else ""
        body.append(f"- {prefix}{text}{src}{ref}{dt}")
    body.append("")

    return "\n".join(fm + body)


def emit_kb(clusters, out_dir, meta=None, top=None, statuses=None, write_index=True):
    """Write one .md per cluster into out_dir, plus an index.md. Returns list of
    written paths. `top` caps the number of files (clusters sorted by size);
    `statuses` optionally filters to e.g. {"NEW","PERSISTING"}."""
    os.makedirs(out_dir, exist_ok=True)
    meta = meta or {}
    sel = [c for c in clusters if (statuses is None or (c.get("status") or "").upper() in statuses)]
    sel = sorted(sel, key=lambda c: c.get("n", len(c.get("members") or [])), reverse=True)
    if top:
        sel = sel[:top]

    written = []
    seen = {}
    for i, c in enumerate(sel, 1):
        base = _slug(c.get("label"))
        seen[base] = seen.get(base, 0) + 1
        fname = f"{i:03d}-{base}.md" if seen[base] == 1 else f"{i:03d}-{base}-{seen[base]}.md"
        path = os.path.join(out_dir, fname)
        with open(path, "w") as f:
            f.write(cluster_to_markdown(c, meta=meta, rank=i))
        written.append(path)

    if write_index:
        idx = _index_markdown(sel, meta, written, out_dir)
        ipath = os.path.join(out_dir, "index.md")
        with open(ipath, "w") as f:
            f.write(idx)
        written.insert(0, ipath)
    return written


def _index_markdown(clusters, meta, written_paths, out_dir):
    from collections import Counter
    counts = Counter((c.get("status") or "").upper() for c in clusters)
    title = meta.get("title") or "Claim Delta Radar — Topic KB"
    fm = ["---",
          f"title: {_yaml_scalar(title)}",
          f"generated: {_yaml_scalar(datetime.date.today().isoformat())}",
          f"new_count: {counts.get('NEW', 0)}",
          f"persisting_count: {counts.get('PERSISTING', 0)}",
          f"disappearing_count: {counts.get('DISAPPEARING', 0)}",
          "---", ""]
    body = [f"# {title}", ""]
    if meta.get("source") or meta.get("window_from"):
        body.append(f"**Source:** {meta.get('source','—')} · "
                    f"**Window:** {meta.get('window_from','?')} → {meta.get('window_to','?')} · "
                    f"**Institution:** {meta.get('institution','—')}")
        body.append("")
    body.append(f"**{counts.get('NEW',0)} emerging · {counts.get('PERSISTING',0)} persisting · "
                f"{counts.get('DISAPPEARING',0)} receding** topics.")
    body.append("")
    body.append("| # | Signal | Topic | Claims |")
    body.append("|---|---|---|---|")
    # written_paths excludes index at this point (index inserted after)
    md_files = [p for p in written_paths if os.path.basename(p) != "index.md"]
    for i, (c, p) in enumerate(zip(clusters, md_files), 1):
        tag = _STATUS_TAG.get((c.get("status") or "").upper(), "topic")
        link = os.path.basename(p)
        n = c.get("n", len(c.get("members") or []))
        label = (c.get("label") or "").replace("|", "\\|")
        body.append(f"| {i} | {tag} | [{label}]({link}) | {n} |")
    body.append("")
    return "\n".join(fm + body)
