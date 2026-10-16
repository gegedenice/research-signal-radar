"""persist.py - signal persistence & trajectory for the claim-delta radar.

The delta engine (kernel.cluster_delta) compares TWO windows. This module lifts
that to a running series of >=3 sweeps so a topic's *trajectory* -- not just its
direction in one pair -- becomes observable (acceleration, sustained rise, a
signal that flips receding->emerging).

Model
-----
- A **sweep** is one delta run over a window. `record_sweep` writes a JSON record
  into a store directory: window bounds, a run timestamp, and per-topic
  {label, exemplar, status, n_claims, n_papers, recent_share, centroid}. The
  centroid is the L2-normalized mean of the topic's claim embeddings -- the key
  used to thread topics across sweeps.
- `thread_topics` loads every sweep in window order and greedily chains each
  sweep's topics onto **lineages** by centroid cosine similarity (>= sim_threshold).
  A topic that matches no open lineage starts a new one.
- `trajectories` turns each lineage into a per-window count series with a
  direction (RISING/FALLING/STABLE/INTERMITTENT) and an acceleration sign from
  the second difference of the paper counts.

All pure-Python + numpy; no network. Tolerant of member-key variants
(claim/text, paper_id/work_id, paper_date/date) like the KB emitter.
"""
import os
import re
import json
import glob
import datetime

import numpy as np

CENTROID_KEY = "centroid"
DEFAULT_SIM = 0.60          # topic-to-lineage match threshold (cosine)
_STATUS_SIGNAL = {"NEW": "emerging", "PERSISTING": "persisting", "DISAPPEARING": "receding"}


# ----------------------------------------------------------------------------- helpers
def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def _slug(s, n=60):
    s = re.sub(r"[^a-z0-9]+", "-", (s or "topic").lower()).strip("-")
    return (s or "topic")[:n]


def _member_claim(m):
    return m.get("claim") or m.get("text") or ""


def _l2(v):
    v = np.asarray(v, dtype="float32")
    return v / max(float(np.linalg.norm(v)), 1e-9)


def topic_centroids(clusters, emb, claims):
    """Recompute an L2-normalized centroid per cluster from the run's embeddings.

    Must be called with the SAME `emb` (N,1024) and `claims` list that
    `cluster_delta` consumed -- cluster members ARE the claim dicts, so we map
    them back to embedding rows by object identity (robust to duplicate text).
    Returns a list of topic dicts (centroid as a plain list), ordered as `clusters`.
    """
    idx = {id(c): i for i, c in enumerate(claims)}
    topics = []
    for c in clusters:
        rows = [idx[id(m)] for m in c.get("members", []) if id(m) in idx]
        if not rows:
            continue
        cen = _l2(emb[rows].mean(axis=0))
        topics.append({
            "label": c.get("label", ""),
            "exemplar": c.get("exemplar", ""),
            "status": c.get("status", ""),
            "n_claims": int(c.get("n", len(rows))),
            "n_papers": int(c.get("n_papers", 0)),
            "recent_share": float(c.get("recent_share", 0.0)),
            CENTROID_KEY: [round(float(x), 6) for x in cen.tolist()],
        })
    return topics


# ----------------------------------------------------------------------------- record
def record_sweep(clusters, emb, claims, window, store_dir, meta=None, run_id=None):
    """Persist one sweep's topics (with centroids) as a JSON record in `store_dir`.

    `window` = {"label": "H1-2026", "from": "2026-01-01", "to": "2026-06-30"}.
    Returns the written path. Sweeps are keyed by window.from so `thread_topics`
    can order them; re-recording the same window overwrites its file.
    """
    os.makedirs(store_dir, exist_ok=True)
    w = dict(window)
    start = w.get("from") or w.get("start") or ""
    label = w.get("label") or start or "sweep"
    rec = {
        "run_id": run_id or _now_iso(),
        "recorded": _now_iso(),
        "window": w,
        "meta": dict(meta or {}),
        "topics": topic_centroids(clusters, emb, claims),
    }
    fn = "sweep-%s-%s.json" % (_slug(start or label, 24), _slug(label, 24))
    path = os.path.join(store_dir, fn)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, ensure_ascii=False, indent=2)
    return path


def load_sweeps(store_dir):
    """Load all sweep records, ordered by window start (then label)."""
    sweeps = []
    for p in glob.glob(os.path.join(store_dir, "sweep-*.json")):
        with open(p, encoding="utf-8") as fh:
            rec = json.load(fh)
        rec["_path"] = p
        sweeps.append(rec)
    def key(r):
        w = r.get("window", {})
        return (w.get("from") or w.get("start") or "", w.get("label") or "")
    sweeps.sort(key=key)
    return sweeps


# ----------------------------------------------------------------------------- thread
def thread_topics(store_dir_or_sweeps, sim_threshold=DEFAULT_SIM):
    """Chain topics across sweeps into lineages by centroid cosine similarity.

    Greedy, order-preserving: sweeps are processed oldest->newest; each topic
    matches the open lineage with the highest cosine >= sim_threshold (each
    lineage claims at most one topic per sweep), else opens a new lineage. A
    lineage's running centroid is the mean of its matched topic centroids.

    Returns a list of lineage dicts:
      {lineage_id, label, windows:[...], entries:[{window, ...topic}], centroid}
    ordered by span (n sweeps present) then peak paper count, descending.
    """
    sweeps = store_dir_or_sweeps if isinstance(store_dir_or_sweeps, list) else load_sweeps(store_dir_or_sweeps)
    lineages = []   # each: {vecs:[np], centroid:np, entries:[], windows:set}

    for si, sw in enumerate(sweeps):
        wlabel = (sw.get("window") or {}).get("label") or (sw.get("window") or {}).get("from") or "w%d" % si
        topics = sw.get("topics", [])
        if not topics:
            continue
        T = np.vstack([_l2(t[CENTROID_KEY]) for t in topics])            # (nt,1024)
        if lineages:
            L = np.vstack([lg["centroid"] for lg in lineages])           # (nl,1024)
            S = T @ L.T                                                   # (nt,nl)
        else:
            S = np.zeros((len(topics), 0))
        # greedy best-first matching over all (topic,lineage) pairs this sweep
        taken_t, taken_l = set(), set()
        pairs = []
        for ti in range(S.shape[0]):
            for li in range(S.shape[1]):
                if S[ti, li] >= sim_threshold:
                    pairs.append((S[ti, li], ti, li))
        pairs.sort(reverse=True)
        matched = {}
        for score, ti, li in pairs:
            if ti in taken_t or li in taken_l:
                continue
            taken_t.add(ti); taken_l.add(li); matched[ti] = (li, score)
        for ti, t in enumerate(topics):
            entry = {"window": wlabel, "sweep_index": si, **{k: v for k, v in t.items() if k != CENTROID_KEY}}
            vec = T[ti]
            if ti in matched:
                li, score = matched[ti]
                lg = lineages[li]
                entry["match_sim"] = round(float(score), 4)
                lg["entries"].append(entry)
                lg["windows"].append(wlabel)
                lg["vecs"].append(vec)
                lg["centroid"] = _l2(np.mean(lg["vecs"], axis=0))
                if t["n_papers"] >= max(e["n_papers"] for e in lg["entries"]):
                    lg["label"] = t["label"]
            else:
                lineages.append({"vecs": [vec], "centroid": vec,
                                 "entries": [entry], "windows": [wlabel], "label": t["label"]})

    out = []
    for i, lg in enumerate(sorted(lineages, key=lambda g: (-len(g["entries"]),
                                                           -max(e["n_papers"] for e in g["entries"])))):
        out.append({
            "lineage_id": i + 1,
            "label": lg["label"],
            "windows": lg["windows"],
            "n_sweeps": len(lg["entries"]),
            "entries": lg["entries"],
            CENTROID_KEY: [round(float(x), 6) for x in lg["centroid"].tolist()],
        })
    return out


# ----------------------------------------------------------------------------- trajectory
def _global_windows(lineages):
    """Ordered union of window labels across all lineages, first-seen order.

    Lineages already carry windows in sweep order (thread_topics processes
    sweeps oldest->newest), so first-seen concatenation preserves chronology.
    """
    order = []
    for lg in lineages:
        for w in lg["windows"]:
            if w not in order:
                order.append(w)
    return order


def _direction(span):
    """Classify a gap-filled count series over a lineage's present span.

    `span` is trimmed to first..last present window, so internal zeros are real
    gaps. Uses OLS slope + presence pattern. Needs >=2 points."""
    if len(span) < 2:
        return "NEW"
    present = [c > 0 for c in span]
    if any(not p for p in present):          # a real gap inside the span
        return "INTERMITTENT"
    xs = np.arange(len(span), dtype="float64")
    ys = np.asarray(span, dtype="float64")
    slope = float(np.polyfit(xs, ys, 1)[0]) if np.ptp(ys) > 0 else 0.0
    if slope > 0.25:
        return "RISING"
    if slope < -0.25:
        return "FALLING"
    return "STABLE"


def _acceleration(span, direction):
    """Direction-aware acceleration from the 2nd difference of the count span.

    Positive 2nd-diff on a RISING series = accelerating; on a FALLING series it
    means the decline is slowing. Returns accelerating/slowing/steady or n/a."""
    if len(span) < 3 or direction in ("NEW", "INTERMITTENT", "STABLE"):
        return "n/a"
    d2 = float(np.diff(span, 2).mean())
    if abs(d2) <= 0.1:
        return "steady"
    if direction == "RISING":
        return "accelerating" if d2 > 0 else "slowing"
    if direction == "FALLING":
        return "accelerating" if d2 < 0 else "slowing"
    return "steady"


def trajectories(lineages, min_sweeps=1):
    """Per-lineage time series + direction + acceleration.

    Aligns each lineage's paper/claim counts to the GLOBAL ordered window axis
    (0 where the topic is absent), trims to the topic's present span, then fits
    a direction (RISING/FALLING/STABLE/INTERMITTENT/NEW) and a direction-aware
    acceleration. Series returned to the caller are the gap-filled present span,
    so a mid-series 0 is a genuine disappearance-then-return.
    Returns rows sorted by signal strength (span * peak papers) descending.
    """
    gw = _global_windows(lineages)
    gidx = {w: i for i, w in enumerate(gw)}
    rows = []
    for lg in lineages:
        if lg["n_sweeps"] < min_sweeps:
            continue
        ent = lg["entries"]
        papers_by = {e["window"]: int(e["n_papers"]) for e in ent}
        claims_by = {e["window"]: int(e["n_claims"]) for e in ent}
        stat_by = {e["window"]: e.get("status", "") for e in ent}
        present_pos = sorted(gidx[e["window"]] for e in ent)
        lo, hi = present_pos[0], present_pos[-1]
        span_windows = gw[lo:hi + 1]
        papers = [papers_by.get(w, 0) for w in span_windows]
        claims = [claims_by.get(w, 0) for w in span_windows]
        statuses = [stat_by.get(w, "-") for w in span_windows]
        direction = _direction(papers)
        accel = _acceleration(papers, direction)
        last_present = ent[-1].get("status", "")
        rows.append({
            "lineage_id": lg["lineage_id"],
            "label": lg["label"],
            "n_sweeps": lg["n_sweeps"],
            "windows": span_windows,
            "papers_series": papers,
            "claims_series": claims,
            "status_series": statuses,
            "current_status": last_present,
            "current_signal": _STATUS_SIGNAL.get(last_present, "") if last_present else "",
            "direction": direction,
            "acceleration": accel,
            "peak_papers": max(papers) if papers else 0,
            "strength": lg["n_sweeps"] * (max(papers) if papers else 0),
        })
    rows.sort(key=lambda r: (-r["strength"], -r["peak_papers"]))
    return rows


# ----------------------------------------------------------------------------- report
def trajectory_markdown(rows, meta=None, top=40):
    """Render a trajectory table + emerging/receding/persistent groupings to Markdown."""
    meta = meta or {}
    L = []
    L.append("# Signal Trajectory Report")
    if meta.get("title"):
        L.append("\n*%s*" % meta["title"])
    scope = " · ".join(str(meta[k]) for k in ("institution", "source", "field") if meta.get(k))
    if scope:
        L.append("\n%s" % scope)
    L.append("\nWindows tracked: **%d** · lineages: **%d**\n" %
             (len({w for r in rows for w in r["windows"]}), len(rows)))
    L.append("| # | Topic | Sweeps | Papers/window | Direction | Accel | Now |")
    L.append("|---|---|---|---|---|---|---|")
    for r in rows[:top]:
        series = "→".join(str(p) for p in r["papers_series"])
        L.append("| %d | %s | %d | %s | %s | %s | %s |" % (
            r["lineage_id"], (r["label"] or "")[:48], r["n_sweeps"], series,
            r["direction"], r["acceleration"], r["current_signal"]))
    for tag, keep in (("Rising / accelerating", lambda r: r["direction"] == "RISING"),
                      ("Falling / receding", lambda r: r["direction"] == "FALLING"),
                      ("Intermittent (flickering signals)", lambda r: r["direction"] == "INTERMITTENT")):
        grp = [r for r in rows if keep(r)]
        if grp:
            L.append("\n## %s (%d)" % (tag, len(grp)))
            for r in grp[:top]:
                L.append("- **%s** — %s papers across %s (%s)" % (
                    (r["label"] or "")[:60], "→".join(map(str, r["papers_series"])),
                    ", ".join(r["windows"]), r["acceleration"]))
    return "\n".join(L) + "\n"


def emit_trajectory(rows, out_dir, meta=None, top=40, plot=True):
    """Write trajectory.md (+ trajectory.json, + trajectory.png if plot) into out_dir."""
    os.makedirs(out_dir, exist_ok=True)
    paths = {}
    md = os.path.join(out_dir, "trajectory.md")
    with open(md, "w", encoding="utf-8") as fh:
        fh.write(trajectory_markdown(rows, meta=meta, top=top))
    paths["markdown"] = md
    js = os.path.join(out_dir, "trajectory.json")
    with open(js, "w", encoding="utf-8") as fh:
        json.dump({"meta": meta or {}, "trajectories": rows}, fh, ensure_ascii=False, indent=2)
    paths["json"] = js
    if plot:
        try:
            paths["plot"] = _plot_trajectories(rows, os.path.join(out_dir, "trajectory.png"), meta=meta)
        except Exception as e:
            paths["plot_error"] = str(e)
    return paths


_DIR_COLOR = {"RISING": "#2a9d5c", "FALLING": "#c1442e",
              "INTERMITTENT": "#c99a2e", "STABLE": "#58a6ff", "NEW": "#8b949e"}


def trajectory_html(rows, fig_src=None, meta=None, top=24, min_sweeps=2):
    """Return an HTML fragment (dark-theme dashboard section) for a trajectory run.

    `fig_src` is an <img src> value (a path, URL, or an artifact marker string)
    for the trajectory plot; omit to skip the figure. `rows` come from
    `trajectories()`. Renders a headline stat line, an optional figure, grouped
    RISING/FALLING/INTERMITTENT/persistent lists, and a compact lineage table.
    Self-contained fragment (uses classes from the dashboard stylesheet, with a
    small scoped <style> for the trajectory-specific bits)."""
    import html as _h
    meta = meta or {}
    multi = [r for r in rows if r["n_sweeps"] >= min_sweeps]
    n_windows = len({w for r in rows for w in r["windows"]})
    by_dir = {}
    for r in multi:
        by_dir.setdefault(r["direction"], []).append(r)

    def esc(s):
        return _h.escape(str(s))

    def series_spark(r):
        return "\u2192".join(str(p) for p in r["papers_series"])

    L = []
    L.append('<div class="traj">')
    L.append('<style>'
             '.traj .tmeta{color:var(--mut);font-size:12px;margin-bottom:10px;font-variant-numeric:tabular-nums}'
             '.traj .tgrp{margin:10px 0}'
             '.traj .tgrp h3{font-size:11px;text-transform:uppercase;letter-spacing:.6px;color:var(--mut);margin:0 0 6px}'
             '.traj .trow{border-top:1px solid var(--edge);padding:6px 0;display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}'
             '.traj .tdir{color:#fff;font-size:10px;font-weight:700;border-radius:4px;padding:1px 6px;letter-spacing:.3px}'
             '.traj .tname{font-weight:600;font-size:13px}'
             '.traj .tser{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;color:var(--acc);font-variant-numeric:tabular-nums}'
             '.traj .taccel{font-size:11px;color:var(--mut)}'
             '.traj table{width:100%;border-collapse:collapse;margin-top:12px;font-size:12px}'
             '.traj th,.traj td{text-align:left;padding:4px 8px;border-bottom:1px solid var(--edge)}'
             '.traj th{color:var(--mut);font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.4px}'
             '.traj td.num{font-variant-numeric:tabular-nums;font-family:ui-monospace,Menlo,monospace}'
             '</style>')

    title = meta.get("title") or "Signal trajectory across sweeps"
    L.append('<h2>%s <span class="tag">&ge;%d sweeps</span></h2>' % (esc(title), min_sweeps))
    scope = " \u00b7 ".join(esc(meta[k]) for k in ("institution", "source", "field") if meta.get(k))
    win = " \u2192 ".join(esc(w) for w in (meta.get("windows") or []))
    L.append('<div class="tmeta">%s%s \u00b7 %d windows tracked \u00b7 %d lineages \u00b7 %d span &ge;%d windows</div>'
             % (scope, (" \u00b7 " + win) if win else "", n_windows, len(rows), len(multi), min_sweeps))

    if fig_src:
        L.append('<div class="figbox"><img src="%s" alt="Topic trajectories across sweeps"></div>' % esc(fig_src))

    def group_block(direction, label, note):
        grp = sorted(by_dir.get(direction, []), key=lambda r: -r["strength"])[:top]
        if not grp:
            return
        L.append('<div class="tgrp"><h3>%s (%d) \u2014 %s</h3>' % (esc(label), len(grp), esc(note)))
        for r in grp:
            accel = ("" if r["acceleration"] in ("n/a", "") else
                     ' \u00b7 <span class="taccel">%s</span>' % esc(r["acceleration"]))
            L.append('<div class="trow"><span class="tdir" style="background:%s">%s</span>'
                     '<span class="tname">%s</span>'
                     '<span class="tser">%s</span>%s</div>'
                     % (_DIR_COLOR.get(direction, "#8b949e"), esc(direction),
                        esc(r["label"]), series_spark(r), accel))
        L.append('</div>')

    group_block("RISING", "Rising / accelerating", "gaining papers window-over-window")
    group_block("FALLING", "Falling / receding", "losing papers window-over-window")
    group_block("INTERMITTENT", "Intermittent", "disappear then return \u2014 a two-window diff misreads these as new")
    group_block("STABLE", "Persistent spine", "present every window \u2014 durable institutional signature")

    L.append('<table><thead><tr><th>#</th><th>Topic</th><th>Sweeps</th>'
             '<th>Papers / window</th><th>Direction</th><th>Accel</th><th>Now</th></tr></thead><tbody>')
    for r in sorted(multi, key=lambda r: -r["strength"])[:top]:
        L.append('<tr><td class="num">%d</td><td>%s</td><td class="num">%d</td>'
                 '<td class="num tser">%s</td><td>%s</td><td>%s</td><td>%s</td></tr>'
                 % (r["lineage_id"], esc(r["label"]), r["n_sweeps"], series_spark(r),
                    esc(r["direction"]), esc(r["acceleration"]), esc(r["current_signal"])))
    L.append('</tbody></table>')
    L.append('</div>')
    return "\n".join(L)


def _plot_trajectories(rows, path, meta=None, top=12):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    multi = [r for r in rows if r["n_sweeps"] >= 2][:top]
    if not multi:
        multi = rows[:top]
    # common window axis from the longest-spanning lineages
    all_windows = []
    for r in rows:
        for w in r["windows"]:
            if w not in all_windows:
                all_windows.append(w)
    xpos = {w: i for i, w in enumerate(all_windows)}
    fig, ax = plt.subplots(figsize=(9, 5.2))
    for r in multi:
        xs = [xpos[w] for w in r["windows"]]
        ys = r["papers_series"]
        ax.plot(xs, ys, marker="o", linewidth=1.8, markersize=5,
                label=(r["label"] or "")[:34])
    ax.set_xticks(range(len(all_windows)))
    ax.set_xticklabels(all_windows, rotation=20, ha="right")
    ax.set_ylabel("papers in topic")
    ax.set_xlabel("sweep window")
    ax.set_title((meta or {}).get("title", "Topic trajectories across sweeps"))
    ax.legend(fontsize=7, ncol=2, loc="upper left", frameon=False)
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path
