
# kernel.py — Claim Delta Mini-Radar helpers
# Pipeline: OpenAlex works -> LLM atomic-claim extraction -> Albert(bge-m3) embeddings
#           -> average-linkage cosine clustering -> new/persisting/disappearing delta.

import os, json, re, time

OPENALEX = "https://api.openalex.org"
ALBERT_EMBED = "https://albert.api.etalab.gouv.fr/v1/embeddings"
ALBERT_MODEL = "BAAI/bge-m3"

def load_env(path=".env"):
    """Read simple KEY=VALUE lines from a .env into a dict (no export)."""
    env = {}
    if not os.path.exists(path):
        return env
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env

def oa_get(session, path, params, email=None, tries=4):
    if email:
        params.setdefault("mailto", email)
    import urllib.parse
    url = OPENALEX + path + "?" + urllib.parse.urlencode(params)
    last = None
    for a in range(tries):
        r = session.get(url, timeout=45)
        if r.status_code in (429, 500, 503):
            last = r; time.sleep(1.5 * (a + 1)); continue
        r.raise_for_status(); return r.json()
    if last is not None:
        last.raise_for_status()

def resolve_institution(ror, email=None):
    """ROR id (bare or full URL) -> {'id','name','works_count'}."""
    import requests
    s = requests.Session(); s.headers.update({"User-Agent": "claim-radar/1.0"})
    ror_full = ror if ror.startswith("http") else f"https://ror.org/{ror}"
    j = oa_get(s, "/institutions", {"filter": f"ror:{ror_full}"}, email)
    inst = j["results"][0]
    return {"id": inst["id"].split("/")[-1], "name": inst["display_name"],
            "works_count": inst["works_count"]}

def invert_abstract(inv):
    if not inv:
        return ""
    pos = [(i, w) for w, idxs in inv.items() for i in idxs]
    pos.sort()
    return " ".join(w for _, w in pos)

def fetch_works(inst_id, from_date, to_date, field_id=None, email=None,
                pages=3, per_page=100, min_abstract=200):
    """OpenAlex articles for an institution+window (optional field), with abstracts."""
    import requests
    s = requests.Session(); s.headers.update({"User-Agent": "claim-radar/1.0"})
    filt = (f"authorships.institutions.id:{inst_id},"
            f"from_publication_date:{from_date},to_publication_date:{to_date},"
            f"type:article,has_abstract:true")
    if field_id:
        filt += f",primary_topic.field.id:{field_id}"
    out = []; cur = "*"
    for _ in range(pages):
        j = oa_get(s, "/works", {"filter": filt, "per-page": per_page, "cursor": cur}, email)
        for w in j["results"]:
            pt = w.get("primary_topic") or {}
            out.append({"id": w["id"].split("/")[-1], "title": w.get("title") or "",
                        "date": w.get("publication_date"), "cited": w.get("cited_by_count", 0),
                        "topic": pt.get("display_name") if pt else None,
                        "abstract": invert_abstract(w.get("abstract_inverted_index"))})
        cur = j["meta"].get("next_cursor")
        if not cur or len(j["results"]) < per_page:
            break
        time.sleep(0.3)
    return [w for w in out if len(w["abstract"]) >= min_abstract]

# ---- Source adapters (all emit the pipeline work-dict: {id,title,date,abstract,...}) ----
import html as htmllib

def clean_txt(s):
    if isinstance(s, list):
        s = s[0] if s else ""
    return htmllib.unescape(re.sub(r"\s+", " ", str(s))).strip()

def fetch_hal(coll, from_date, to_date, domain="0.info", rows=45, min_abstract=200):
    """HAL (archives-ouvertes.fr) adapter. coll=collCode_s (e.g. UNIV-COTEDAZUR),
    domain=domain_s prefix (0.info = Computer Science). Windows on producedDate_s.
    Multilingual (French+English abstracts) — bge-m3 handles both."""
    import requests
    r = requests.get("https://api.archives-ouvertes.fr/search/", params={
        "q": "*:*",
        "fq": [f"collCode_s:{coll}", f"domain_s:{domain}", "abstract_s:[* TO *]",
               f"producedDate_s:[{from_date} TO {to_date}]"],
        "fl": "docid,title_s,abstract_s,producedDate_s,language_s,docType_s",
        "rows": rows, "sort": "producedDate_s desc", "wt": "json"}, timeout=45)
    out = []
    for d in r.json()["response"]["docs"]:
        ab = clean_txt(d.get("abstract_s", ""))
        if len(ab) < min_abstract:
            continue
        out.append({"id": f"hal-{d['docid']}", "title": clean_txt(d.get("title_s", "")),
                    "date": clean_txt(d.get("producedDate_s", "")), "abstract": ab,
                    "lang": clean_txt(d.get("language_s", "")), "doctype": d.get("docType_s", "")})
    return out

def fetch_theses(from_date, to_date, code_etab="COAZ", discipline="informatique",
                 cap=60, min_abstract=200):
    """theses.fr adapter. Search by NNT establishment code (COAZ = Universite Cote d'Azur)
    + discipline + dateSoutenance range via Lucene q syntax; abstracts (resumes, bilingual)
    live on the /these/{nnt} detail endpoint, so each hit is hydrated individually.
    Theses are annual — use full-year windows, not half-years."""
    import requests
    api = "https://theses.fr/api/v1/theses"
    q = (f"nnt:*{code_etab}* AND discipline:{discipline} "
         f"AND dateSoutenance:[{from_date} TO {to_date}]")
    hits = requests.get(f"{api}/recherche/", params={"q": q, "nombre": cap}, timeout=45).json().get("theses", [])
    out = []
    for h in hits:
        nnt = h.get("nnt")
        if not nnt:
            continue
        try:
            d = requests.get(f"{api}/these/{nnt}", timeout=30).json()
        except Exception:
            continue
        res = d.get("resumes") or {}
        ab = clean_txt(res.get("en") or res.get("fr") or "")
        if len(ab) < min_abstract:
            continue
        titres = d.get("titres") or {}
        title = clean_txt(titres.get("en") or titres.get("fr") or h.get("titrePrincipal", ""))
        out.append({"id": f"these-{nnt}", "title": title, "date": clean_txt(d.get("dateSoutenance", "")),
                    "abstract": ab, "lang": ",".join(d.get("langues") or []),
                    "discipline": clean_txt(d.get("discipline", ""))})
    return out


EXTRACT_SYS = (
    "You extract atomic scientific claims from a paper abstract. An atomic claim is a single, "
    "self-contained, verifiable proposition the authors assert (a finding, capability, causal link, "
    "or quantitative result) - NOT background, motivation, or method description. "
    "Return ONLY a JSON array of 2-5 objects, each: "
    '{"claim":"one declarative sentence <=25 words, self-contained (no we/our/this paper)",'
    '"topic":"2-4 word noun phrase naming what the claim is about",'
    '"type":"finding|capability|method-result|comparison|resource"}. '
    "No prose, no markdown fences, JSON array only.")

def parse_json(txt):
    t = (txt or "").strip()
    t = re.sub(r"^```(?:json)?", "", t).strip(); t = re.sub(r"```$", "", t).strip()
    m = re.search(r"[\[{].*[\]}]", t, re.S)
    if m: t = m.group(0)
    try: return json.loads(t)
    except Exception: return None

def extract_claims(host, works, window, max_concurrency=8):
    """LLM fan-out: attach a .claims list to every work; tag each claim with window/paper."""
    reqs = [{"messages": [{"role": "user",
             "content": f"TITLE: {w['title']}\nABSTRACT: {w['abstract'][:1600]}"}],
             "system": EXTRACT_SYS, "max_tokens": 900} for w in works]
    res = host.llm(reqs, max_concurrency=max_concurrency)
    for w, r in zip(works, res):
        claims = [] if r.get("error") else (parse_json(r.get("text", "")) or [])
        w["claims"] = claims
        for c in claims:
            c["paper_id"] = w["id"]; c["paper_date"] = w["date"]; c["window"] = window
    return [c for w in works for c in w["claims"]]

def embed_claims(texts, api_key, batch=32):
    """Albert bge-m3 embeddings -> L2-normalized numpy array (len(texts), 1024)."""
    import requests, numpy as np
    vecs = []
    for i in range(0, len(texts), batch):
        chunk = texts[i:i+batch]
        r = requests.post(ALBERT_EMBED,
                          headers={"Authorization": f"Bearer {api_key}",
                                   "Content-Type": "application/json"},
                          json={"model": ALBERT_MODEL, "input": chunk}, timeout=60)
        r.raise_for_status()
        data = sorted(r.json()["data"], key=lambda x: x["index"])
        vecs.extend(row["embedding"] for row in data)
        time.sleep(0.2)
    emb = np.asarray(vecs, dtype="float32")
    emb /= np.clip(np.linalg.norm(emb, axis=1, keepdims=True), 1e-9, None)
    return emb

def cluster_delta(claims, emb, threshold=0.62):
    """Average-linkage cosine clustering -> per-cluster NEW/PERSISTING/DISAPPEARING delta."""
    import numpy as np
    n = len(claims); sim = emb @ emb.T
    groups = {i: [i] for i in range(n)}; active = set(range(n))
    def avg(a, b):
        return sim[np.ix_(groups[a], groups[b])].mean()
    merged = True
    while merged and len(active) > 1:
        merged = False; best = (-1.0, None, None); al = list(active)
        for x in range(len(al)):
            for y in range(x+1, len(al)):
                s = avg(al[x], al[y])
                if s > best[0]: best = (s, al[x], al[y])
        if best[0] >= threshold:
            _, a, b = best
            groups[a] = groups[a] + groups[b]; del groups[b]; active.discard(b); merged = True
    out = []
    for idxs in groups.values():
        win = [claims[i]["window"] for i in idxs]
        nr = win.count("recent"); npv = win.count("prior")
        sub = emb[idxs]; med = idxs[int((sub @ sub.T).mean(1).argmax())]
        status = "NEW" if (nr and not npv) else "DISAPPEARING" if (npv and not nr) else "PERSISTING"
        out.append({"status": status, "n": len(idxs), "n_recent": nr, "n_prior": npv,
                    "n_papers": len({claims[i]["paper_id"] for i in idxs}),
                    "label": claims[med]["topic"], "exemplar": claims[med]["claim"],
                    "recent_share": round(nr/len(idxs), 2),
                    "members": [claims[i] for i in idxs]})
    out.sort(key=lambda c: (-c["n"], c["status"]))
    return out

BRIEF_SYS = (
    "You are a research-intelligence analyst for an academic library monitoring an institution's "
    "scholarly output. You receive a CLAIM DELTA between two time windows: emerging claim-topics "
    "(recent window only) and receding ones (prior window only), extracted from abstracts. Produce "
    "a concise monitoring brief. Be precise and grounded - cite the topic labels and claim counts "
    "you are given, never invent papers or numbers. Output ONLY valid JSON:\n"
    '{"headline":"one sentence naming the dominant shift",'
    '"signals":[{"signal":"short title","direction":"EMERGING|RECEDING|WATCH",'
    '"evidence":"1-2 sentences citing specific topics/counts","library_action":"one concrete '
    'monitoring/collection action","confidence":"HIGH|MEDIUM|LOW"}],'
    '"caveats":["methodological caveats a librarian should know"]}'
    " Give 5-7 signals. Ground every claim in the provided data.")

def make_brief(host, clusters, meta, top=12):
    """LLM analyst layer: turn the delta into a grounded monitoring brief (dict)."""
    def ctx(status):
        lst = sorted([c for c in clusters if c["status"] == status],
                     key=lambda c: (-c["n_papers"], -c["n"]))[:top]
        return [{"topic": c["label"], "exemplar": c["exemplar"],
                 "n_claims": c["n"], "n_papers": c["n_papers"]} for c in lst]
    payload = dict(meta); payload["emerging"] = ctx("NEW"); payload["receding"] = ctx("DISAPPEARING")
    r = host.llm({"messages": [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
                  "system": BRIEF_SYS, "max_tokens": 3000, "model": host.current_model()})
    return parse_json(r.get("text", "")) or {"headline": "", "signals": [], "caveats": ["brief parse failed"]}

# ============================================================================
# TWO-TIER PIPELINE (the primary path)
#   Tier 1 = topic-count headline from OpenAlex metadata (NO language model):
#            which topics are moving. Cheap, exact, reproducible, at full scale.
#   Tier 2 = atomic-claim drill-down, run ONLY inside topics Tier 1 flags as
#            moving: what is being claimed, and whether it is new.
# Language-model cost scales with the number of live signals, not the size of
# the institution. Tier 1 uses OpenAlex primary_topic directly; §Robustness in
# SKILL.md shows the count headline matches a far more expensive claim headline
# (trajectory Spearman 0.99, delta 0.93 on the Mines pilot).
# ============================================================================

def fetch_topic_meta(inst_id, from_date, to_date, field_id=None, email=None,
                     pages=12, per_page=200):
    """TIER 1 ingestion — lightweight OpenAlex metadata for institution+window.
    No abstract requirement, so it sees the FULL paper population. Returns
    work-dicts {id, date, topic, topic_id, field}."""
    import requests
    s = requests.Session(); s.headers.update({"User-Agent": "claim-radar/1.0"})
    filt = (f"authorships.institutions.id:{inst_id},"
            f"from_publication_date:{from_date},to_publication_date:{to_date},"
            f"type:article")
    if field_id:
        filt += f",primary_topic.field.id:{field_id}"
    out = []; cur = "*"
    for _ in range(pages):
        j = oa_get(s, "/works", {"filter": filt, "per-page": per_page, "cursor": cur,
                                 "select": "id,publication_date,primary_topic"}, email)
        for w in j["results"]:
            pt = w.get("primary_topic") or {}
            fld = (pt.get("field") or {}) if pt else {}
            out.append({"id": w["id"].split("/")[-1], "date": w.get("publication_date"),
                        "topic": pt.get("display_name") if pt else None,
                        "topic_id": (pt.get("id") or "").split("/")[-1] if pt else None,
                        "field": fld.get("display_name")})
        cur = j["meta"].get("next_cursor")
        if not cur or len(j["results"]) < per_page:
            break
        time.sleep(0.3)
    return out


def build_headline(windows, win_order, prior=None, recent=None, min_total=4):
    """TIER 1 — per-topic paper-count matrix -> trajectory + delta (no LLM).
    windows: {window_label: [work-dicts with 'topic' (+optional 'field')]};
    win_order: ordered window labels. prior/recent: the two labels for the delta
    (default: last two in win_order). Returns
    {win_order, prior, recent, topics:[...], strong:[...], delta_counts:{...}}.
    Each topic dict: {topic, field, series, total, slope, delta_status,
    prior, recent}; 'strong' (total>=min_total) also carries 'direction'
    (RISING/FALLING/STABLE)."""
    from collections import defaultdict
    if prior is None:  prior  = win_order[-2]
    if recent is None: recent = win_order[-1]
    mat = defaultdict(lambda: {w: 0 for w in win_order}); field_of = {}
    for w in win_order:
        for rec in windows.get(w, []):
            t = rec.get("topic")
            if not t:
                continue
            mat[t][w] += 1
            field_of.setdefault(t, rec.get("field"))
    topics = []; dc = {"NEW": 0, "PERSISTING": 0, "DISAPPEARING": 0}
    for t, counts in mat.items():
        series = [counts[w] for w in win_order]; total = sum(series)
        n = len(series); xs = list(range(n)); mx = sum(xs)/n; my = total/n
        den = sum((x-mx)**2 for x in xs) or 1.0
        slope = sum((xs[i]-mx)*(series[i]-my) for i in range(n))/den
        p, r = counts[prior], counts[recent]
        status = ("PERSISTING" if p and r else
                  ("NEW" if r and not p else
                   ("DISAPPEARING" if p and not r else "none")))
        if status in dc:
            dc[status] += 1
        topics.append({"topic": t, "field": field_of.get(t), "series": series,
                       "total": total, "slope": round(slope, 3),
                       "delta_status": status, "prior": p, "recent": r})
    topics.sort(key=lambda d: -d["total"])
    strong = [d for d in topics if d["total"] >= min_total]
    for d in strong:
        d["direction"] = ("RISING" if d["slope"] > 0.15 else
                          ("FALLING" if d["slope"] < -0.15 else "STABLE"))
    return {"win_order": win_order, "prior": prior, "recent": recent,
            "min_total": min_total, "topics": topics, "strong": strong,
            "delta_counts": dc}


def flag_moving(headline, kinds=("RISING", "FALLING", "NEW"), min_recent=1, top=None):
    """Select topics worth a Tier-2 drill-down. `kinds` mixes trajectory
    directions (RISING/FALLING/STABLE, from headline['strong']) and delta
    statuses (NEW/PERSISTING/DISAPPEARING). Returns
    [{topic, reason, recent, slope}] ranked by recent activity then |slope|."""
    picked = {}
    for d in headline.get("strong", []):
        if d.get("direction") in kinds:
            picked.setdefault(d["topic"], {"topic": d["topic"], "reason": d["direction"],
                                           "recent": d["recent"], "slope": d["slope"]})
    for d in headline["topics"]:
        if d["delta_status"] in kinds and d["recent"] >= min_recent:
            picked.setdefault(d["topic"], {"topic": d["topic"], "reason": d["delta_status"],
                                           "recent": d["recent"], "slope": d.get("slope", 0)})
    rows = sorted(picked.values(), key=lambda r: (-r["recent"], -abs(r["slope"])))
    return rows[:top] if top else rows


def drilldown_claims(flagged, works_with_abstracts, host, window, max_concurrency=3):
    """TIER 2 — extract claims ONLY inside flagged topics. `flagged` is a list
    of topic names or the dicts from flag_moving; `works_with_abstracts` are
    work-dicts that carry 'abstract' and 'topic' (fetch via fetch_works for the
    flagged window). Reuses extract_claims. Returns {topic: [claim-dicts]}."""
    names = {(f["topic"] if isinstance(f, dict) else f) for f in flagged}
    subset = [w for w in works_with_abstracts
              if w.get("topic") in names and w.get("abstract")]
    by_topic = {}
    for t in names:
        tw = [w for w in subset if w.get("topic") == t]
        if not tw:
            continue
        by_topic[t] = extract_claims(host, tw, window, max_concurrency=max_concurrency)
    return by_topic

# ============================================================================
# TIER 3 — GLOBAL POSITIONING (leading / following / niche-owner, per topic)
#   For a topic Tier 1 flags as persistent/moving: where does the institution
#   sit vs the rest of the world working on that SAME OpenAlex topic —
#   leading, following, niche-owner, wave-rider, or diverging?
#
# Design (POSITIONING.md "auditable core", Proposal A) re-keyed onto the topic
# axis. Because Tier 1 already identifies topics by their exact OpenAlex
# primary_topic.id, the global reference set and the institution subset are
# EXACT taxonomy filters (primary_topic.id[+authorships.institutions.id]) — no
# fuzzy label search, so the retrieval gap the original prototype fought
# (POSITIONING.md §7-§8) is gone by construction. Every number is a
# recomputable OpenAlex count; verdicts never collapse to a black-box arrow.
#
# Three sub-signals, three confidence levels:
#   1. Timing     — median-date lead/lag + citation-flow direction  [HIGH, free]
#   2. Prominence — institution share of global papers + trend      [HIGH, free]
#   3. Stance     — LLM read of the institution claim vs global      [LOW, opt.]
# ============================================================================

def position_topic(topic_id, from_date, to_date, inst_openalex_id,
                   topic_label=None, email=None, pages=4, per_page=100):
    """TIER 3 — positioning card for ONE OpenAlex topic (exact-membership).

    topic_id: OpenAlex primary_topic id (e.g. 'T10402'), as carried on the
    Tier-1 work-dicts (fetch_topic_meta sets 'topic_id'). inst_openalex_id:
    resolve_institution(ror). Returns a card dict with n_global / n_inst,
    prominence + timing sub-signals, a verdict, and a confidence tier — all
    recomputable from the raw OpenAlex response.
    """
    import requests
    from datetime import date as _date

    def median_date(dates):
        ds = sorted(d for d in dates if d)
        return ds[len(ds) // 2] if ds else None

    def days_between(d1, d2):
        a = _date(*[int(x) for x in d1.split("-")])
        b = _date(*[int(x) for x in d2.split("-")])
        return (b - a).days

    s = requests.Session(); s.headers.update({"User-Agent": "claim-radar/1.0"})
    sel = ("id,publication_date,publication_year,cited_by_count,"
           "referenced_works,authorships,primary_topic")
    span = f"from_publication_date:{from_date},to_publication_date:{to_date},type:article"
    gfilt = f"primary_topic.id:{topic_id},{span}"
    ifilt = f"primary_topic.id:{topic_id},authorships.institutions.id:{inst_openalex_id},{span}"

    def _true_count(filt):
        j = oa_get(s, "/works", {"filter": filt, "per-page": 1, "select": "id"}, email)
        return j.get("meta", {}).get("count", 0)

    def _page(filt, npages):
        out, cur = [], "*"
        for _ in range(npages):
            j = oa_get(s, "/works", {"filter": filt, "per-page": per_page,
                                     "cursor": cur, "select": sel}, email)
            for w in j.get("results", []):
                rors = {(inst.get("ror") or "").rstrip("/").split("/")[-1]
                        for a in (w.get("authorships") or [])
                        for inst in (a.get("institutions") or [])}
                out.append({"id": w["id"].split("/")[-1], "date": w.get("publication_date"),
                            "year": w.get("publication_year"), "cited": w.get("cited_by_count", 0),
                            "refs": [r.split("/")[-1] for r in (w.get("referenced_works") or [])],
                            "rors": rors})
            cur = j.get("meta", {}).get("next_cursor")
            if not cur or len(j.get("results", [])) < per_page:
                break
            time.sleep(0.3)
        return out

    n_global = _true_count(gfilt)
    n_inst = _true_count(ifilt)
    card = {"topic_id": topic_id, "topic": topic_label,
            "window": {"from": from_date, "to": to_date},
            "n_global": n_global, "n_inst": n_inst, "subsignals": {}}
    if n_global == 0:
        card["verdict"], card["confidence"] = "NO-GLOBAL-MATCH", "none"
        return card

    gset = _page(gfilt, pages)
    inst = _page(ifilt, 2)
    n_sampled = len(gset)
    fired = 1  # prominence always fires when n_global>0

    share = n_inst / n_global if n_global else 0.0
    card["subsignals"]["prominence"] = {
        "inst_share": round(share, 4),
        "reading": ("niche-owner" if share >= 0.15 else
                    "co-leader" if share >= 0.05 else
                    "wave-rider" if n_inst > 0 else "absent"),
        "global_by_year": {y: sum(1 for w in gset if w.get("year") == y)
                           for y in sorted({w["year"] for w in gset if w.get("year")})},
    }

    if n_inst:
        gmed = median_date([w["date"] for w in gset])
        imed = median_date([w["date"] for w in inst])
        lead_days = days_between(imed, gmed) if (gmed and imed) else None
        inst_ids = {w["id"] for w in inst}
        global_ids = {w["id"] for w in gset}
        out_refs = sum(len([r for r in w["refs"] if r in global_ids]) for w in inst)
        in_cites = sum(1 for w in gset if w["id"] not in inst_ids
                       and inst_ids & set(w["refs"]))
        flow = in_cites - out_refs
        card["subsignals"]["timing"] = {
            "inst_median_date": imed, "global_median_date": gmed, "lead_days": lead_days,
            "flow_in_cites": in_cites, "flow_out_refs": out_refs, "flow_net": flow,
            "flow_basis": f"sampled {n_sampled} of {n_global} global",
            "reading": ("leads" if (lead_days or 0) > 30 or flow > 0 else
                        "lags" if (lead_days or 0) < -30 or flow < 0 else "concurrent"),
        }
        fired += 1

    prom = card["subsignals"]["prominence"]["reading"]
    tim = card["subsignals"].get("timing", {}).get("reading")
    if n_inst == 0:
        verdict = "DIVERGING/ABSENT"
    elif prom == "niche-owner" and tim == "leads":
        verdict = "LEADING"
    elif tim == "leads":
        verdict = "EARLY-MOVER"
    elif tim == "lags":
        verdict = "FOLLOWING"
    elif prom == "wave-rider":
        verdict = "WAVE-RIDER"
    else:
        verdict = "CONCURRENT"
    card["verdict"] = verdict

    if n_inst >= 4 and n_global >= 30 and fired >= 2:
        conf = "high"
    elif n_inst >= 2 and n_global >= 12 and fired >= 2:
        conf = "medium"
    elif n_global >= 8:
        conf = "low"
    else:
        conf = "very-low"
    card["confidence"] = conf
    card["_fired"] = fired
    return card


def position_flagged(flagged, from_date, to_date, inst_openalex_id, topics=None,
                     email=None, top=None):
    """TIER 3 batch — position each flagged topic that carries a topic_id.

    flagged: rows from flag_moving. Each needs a 'topic_id'; if flag_moving rows
    lack it, pass `topics` = the headline['topics'] list (or any list of dicts
    with 'topic' + 'topic_id') to join on the topic name. Returns a list of
    positioning cards, most confident first.
    """
    id_of = {}
    if topics:
        id_of = {t["topic"]: t.get("topic_id") for t in topics if t.get("topic")}
    rows = flagged[:top] if top else flagged
    cards = []
    for r in rows:
        tid = r.get("topic_id") or id_of.get(r.get("topic"))
        if not tid:
            cards.append({"topic": r.get("topic"), "verdict": "NO-TOPIC-ID",
                          "confidence": "none"})
            continue
        cards.append(position_topic(tid, from_date, to_date, inst_openalex_id,
                                    topic_label=r.get("topic"), email=email))
    order = {"high": 0, "medium": 1, "low": 2, "very-low": 3, "none": 4}
    cards.sort(key=lambda c: order.get(c.get("confidence"), 5))
    return cards

# ============================================================================
# SECONDARY SIGNAL — claim-level exploration (taxonomy-independent)
#   Runs ALONGSIDE the Tier-1 topic headline wherever claims have been
#   extracted at corpus scale. Reads structure directly from what is asserted
#   rather than from which OpenAlex bucket a paper is filed in — surfacing
#   (a) cross-cutting themes that span many topics, and (b) a claim-theme delta
#   between two windows. Heavier and noisier than Tier 1 (needs corpus-wide
#   claims; a large method-generic "boilerplate" cluster is reported and
#   excluded from the delta), so it is a secondary lens, not a replacement.
# ============================================================================

def explore_claims(claims, emb, topic_key="oa_topic", window_key="window",
                   prior=None, recent=None, threshold=0.55,
                   min_theme=8, min_delta=6, cross_min_topics=3):
    """Cluster ALL claims independent of the topic taxonomy and derive two
    readings the per-topic count is structurally blind to.

    claims : list of dicts; each needs claims[i][topic_key] (OpenAlex topic
             label/id) and claims[i][window_key] (the window bucket).
    emb    : (n, d) float array of L2-normalisable claim embeddings, row-aligned
             to `claims`.
    prior, recent : the two window values to diff for the claim-theme delta
             (e.g. "2024","2025"). If None, the delta is skipped.

    Returns {"n_claims", "n_themes", "boilerplate", "cross_cutting", "delta"}.
    The largest cluster is treated as method-generic boilerplate: reported
    separately and excluded from the delta.
    """
    import numpy as np
    try:
        from sklearn.preprocessing import normalize
        from sklearn.cluster import AgglomerativeClustering
    except ImportError as e:
        raise ImportError("explore_claims needs scikit-learn: pip install scikit-learn") from e
    from collections import Counter, defaultdict

    X = normalize(np.asarray(emb, dtype=np.float32))
    lab = AgglomerativeClustering(n_clusters=None, distance_threshold=threshold,
                                  metric="cosine", linkage="average").fit_predict(X)
    members = defaultdict(list)
    for i, l in enumerate(lab):
        members[int(l)].append(i)

    def medoid_exemplar(idx):
        sub = X[idx]
        cen = sub.mean(0, keepdims=True)
        cen = cen / (np.linalg.norm(cen) + 1e-9)
        return claims[idx[int((sub @ cen.T).ravel().argmax())]]["claim"]

    def topics(idx):
        return Counter(claims[i].get(topic_key) for i in idx if claims[i].get(topic_key))

    boiler_l = max(members, key=lambda l: len(members[l]))
    big = [l for l, v in members.items() if len(v) >= min_theme]

    # (a) cross-cutting themes: clusters spanning many distinct topics
    cross = []
    for l in big:
        if l == boiler_l:
            continue
        tc = topics(members[l])
        if len(tc) >= cross_min_topics:
            cross.append({"n_claims": len(members[l]), "spans_topics": len(tc),
                          "top_topics": [t for t, _ in tc.most_common(4)],
                          "exemplar": medoid_exemplar(members[l])})
    cross.sort(key=lambda c: -c["spans_topics"])

    # (b) claim-theme delta between two windows
    delta = None
    if prior is not None and recent is not None:
        rows = []
        for l in members:
            if l == boiler_l:
                continue
            wc = Counter(claims[i].get(window_key) for i in members[l])
            npv, nr = wc.get(prior, 0), wc.get(recent, 0)
            if npv + nr < min_delta:
                continue
            status = ("PERSISTING" if npv and nr else "NEW" if nr else "DISAPPEARING")
            rows.append({"status": status, "prior": npv, "recent": nr, "delta": nr - npv,
                         "spans_topics": len(topics(members[l])),
                         "top_topics": [t for t, _ in topics(members[l]).most_common(2)],
                         "exemplar": medoid_exemplar(members[l])})
        counts = Counter(r["status"] for r in rows)
        delta = {"prior_window": prior, "recent_window": recent,
                 "counts": dict(counts),
                 "emerging": sorted([r for r in rows if r["delta"] > 0],
                                    key=lambda r: -r["delta"]),
                 "receding": sorted([r for r in rows if r["delta"] < 0],
                                    key=lambda r: r["delta"])}

    return {"n_claims": len(claims), "n_themes": len(members),
            "boilerplate": {"n_claims": len(members[boiler_l]),
                            "spans_topics": len(topics(members[boiler_l])),
                            "exemplar": medoid_exemplar(members[boiler_l])},
            "cross_cutting": cross, "delta": delta}



