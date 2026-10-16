# TM-03 / TM-04 — sketch d'implémentation de l'agrégation multi-échelle

| Champ | Valeur |
|---|---|
| Statut | Sketch d'implémentation (non implémenté) |
| Cible | `topic-momentum/0.2` |
| Date | 11 septembre 2026 |
| Fichiers concernés | `src/research_signal/tm03.py`, `tm04.py`, `config.py`, `tests/` |
| Décision fondatrice | `06_topic-granularity-diagnostic.md`, `03.01_…-contract.md` §6.6 |

---

## 0. Principe directeur

**Une série de subfield est structurellement identique à une série de topic.** Le
classificateur TM-04 (`classify_windows`) est déjà agnostique au niveau : il ne
consomme que des dictionnaires portant `topic_count`, `topic_share`,
`classified_works_count`, `topic_coverage`, `is_complete`, `active_months`. On
réutilise donc **le même code de série et le même classificateur à chaque niveau**,
puis on joint les directions pour annoter le signal topic.

Conséquence : blast radius minimal.

- Le chemin topic reste la source canonique — mêmes fichiers, mêmes schémas, TM-05/06 inchangés.
- Les niveaux subfield/field sont **additifs** : nouveaux fichiers parallèles + un seul bloc `scale_corroboration` ajouté à la classification topic.
- Aucun nouveau seuil : la corroboration est dérivée des directions déjà calculées.

Les dénominateurs (`classified_works_count`, `included_works_count`,
`topic_coverage`) sont des grandeurs **de portefeuille**, donc identiques à tous les
niveaux. Seul le numérateur (`count`) change : au niveau subfield/field il est la
**somme des counts des topics enfants**. Comme chaque œuvre classifiée a exactement
un `primary_topic`, donc exactement un subfield et un field, on a l'invariant fort :

```
∀ mois m :  Σ_subfields count(sf, m) == classified_works_count(m)
            Σ_fields    count(f,  m) == classified_works_count(m)
```

à utiliser comme contrôle automatique (voir §5).

---

## 1. Config — `config.py`

Ajouter au dataclass `TopicMomentumConfig` (après `min_supporting_evaluations`) :

```python
    # v0.2 — agrégation multi-échelle
    multi_scale: bool = True
    scale_levels: tuple[str, ...] = ("subfield", "field")
    # v0.2 — garde de petits effectifs (Poisson), différée mais réservée ici
    use_poisson_lower_bound: bool = False
```

`multi_scale=True` par défaut ; `scale_levels` liste les niveaux **parents** calculés
en plus du topic. Les seuils de détection restent **partagés** avec le niveau topic
en 0.2 (le diagnostic montre que la garde de part `rise_share_ratio` fait déjà le
tri aux niveaux agrégés). Un profil de seuils par niveau pourra être ajouté en 0.3
sans changer la forme de sortie.

Rétro-compatibilité : les deux champs ont des valeurs par défaut, donc les
`configs/*.json` existants restent valides. `min_supporting_evaluations` étant déjà
présent, insérer les nouveaux champs **après** lui pour ne pas casser un éventuel
positional-init.

---

## 2. TM-03 — généraliser le constructeur de séries

`build_topic_series` reste tel quel et devient un cas particulier d'un constructeur
générique. La seule donnée nouvelle à préparer est, pour chaque niveau parent, la
table `count[(unit_id, month_start)]` obtenue en **sommant les snapshots topic** par
subfield / field, plus une table d'identité par unité.

### 2.1 Nouvelle fonction générique

```python
def _unit_identity(level: str, topic: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Retourne (unit_id, bloc identité 'topic-shaped') pour un niveau parent."""
    node = topic[level]  # topic["subfield"] ou topic["field"]
    identity = {
        "id": node["id"],
        "display_name": node["display_name"],
        "level": level,
        # pas de created_date -> _taxonomy_change() renverra False (cf. tm04.py:253)
    }
    if level == "subfield":
        identity["field"] = topic["field"]
        identity["domain"] = topic["domain"]
    elif level == "field":
        identity["domain"] = topic["domain"]
    return node["id"], identity


def build_unit_series(
    level: str,
    manifest: dict[str, Any],
    snapshot_by_key: dict[tuple[str, str], dict[str, Any]],
    summaries: list[dict[str, Any]],
    catalog_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Série mensuelle + fenêtres glissantes agrégées au niveau `level`.
    Réutilise _window() et la même mécanique d'endpoints que build_topic_series."""
    summaries = _validated_month_axis(summaries)

    # 1) counts agrégés: (unit_id, month_start) -> somme des counts topic
    counts: dict[tuple[str, str], int] = {}
    identities: dict[str, dict[str, Any]] = {}
    for (topic_id, start), snap in snapshot_by_key.items():
        topic = catalog_by_id[topic_id]
        if level not in topic or not topic[level].get("id"):
            raise InvariantError(f"topic {topic_id} lacks a {level} for multi-scale")
        unit_id, identity = _unit_identity(level, topic)
        identities.setdefault(unit_id, identity)
        counts[(unit_id, start)] = counts.get((unit_id, start), 0) + snap["topic_count"]

    # 2) mêmes endpoints/fenêtres que le niveau topic
    window_months = ...  # config.topic_momentum.analysis_window_months
    step_months = ...     # evaluation_step_months
    # (réutiliser le bloc endpoints de build_topic_series tel quel)

    series: list[dict[str, Any]] = []
    for unit_id, identity in sorted(identities.items()):
        month_points = []
        for summary in summaries:
            start = summary["bucket"]["start"]
            count = counts.get((unit_id, start), 0)
            classified_total = summary["classified_works_count"]
            included_total = summary["included_works_count"]
            month_points.append({
                "start": start, "end": summary["bucket"]["end"],
                "is_complete": summary["bucket"]["is_complete"],
                "count": count,
                "share": round(count / classified_total, 12) if classified_total else 0.0,
                "coverage": summary["topic_coverage"],
                "classified_total": classified_total,
                "included_total": included_total,
                "zero_filled": (unit_id, start) not in counts,
            })
        rolling = [ {**_window(month_points[e - window_months + 1 : e + 1]),
                     "evaluation_date": month_points[e]["end"]}
                    for e in endpoints ]
        series.append({
            "schema_version": "unit-series/0.2",
            "run_id": manifest["run_id"],
            "query_manifest_ref": manifest["manifest_id"],
            "universe_id": manifest["universe"]["id"],
            "universe_version": manifest["universe"]["version"],
            "scope_mode": manifest["universe"]["scope_mode"],
            "stream_id": manifest["stream"]["id"],
            "level": level,
            "topic": identity,   # bloc identité 'topic-shaped' -> TM-04 le lit tel quel
            "bucket_granularity": "month",
            "monthly": month_points,
            "rolling_windows": rolling,
        })
    return series
```

> Note DRY : `build_topic_series` et `build_unit_series` partagent ~90 % du corps
> (endpoints, month_points, rolling). En pratique on extrait un helper
> `_assemble_series(identity, month_points_fn, endpoints)` et les deux appellent
> dessus. Le sketch les garde séparés pour la lisibilité.

### 2.2 Câblage dans `run_tm03`

Après l'écriture de `series/topic-series.jsonl.gz` :

```python
    if config.topic_momentum.multi_scale:
        catalog_by_id = {t["id"]: t for t in catalog}
        for level in config.topic_momentum.scale_levels:
            unit_series = build_unit_series(level, manifest, snapshot_by_key,
                                            summaries, catalog_by_id)
            store.write_jsonl_gz(f"series/{level}-series.jsonl.gz", unit_series)
            _assert_level_mass(level, unit_series, summaries)  # invariant §5
```

(`snapshot_by_key` est déjà construit dans `build_topic_series` ; l'exposer via un
petit refactor ou le reconstruire une fois dans `run_tm03`.)

Sorties nouvelles : `series/subfield-series.jsonl.gz`, `series/field-series.jsonl.gz`.
Le rapport qualité TM-03 gagne `level_series_counts: {"subfield": N, "field": M}`.

---

## 3. TM-04 — classifier chaque niveau puis joindre

`classify_topic_series` est réutilisé **sans modification** sur les séries parentes
(le bloc `topic` identité est présent, `created_date` absent → `taxonomy_change`
False, ce qui est correct : les subfields/fields OpenAlex ont des IDs stables).

### 3.1 `run_tm04` — classifier les trois niveaux

```python
    series = store.read_jsonl_gz("series/topic-series.jsonl.gz")
    classifications = []
    for item in series:
        classifications.extend(classify_topic_series(item, cfg, parameters_hash, manifest))

    # niveaux parents (si présents)
    parent_dir: dict[tuple[str, str, str], str] = {}   # (level, unit_id, eval_date) -> direction
    parent_classifications: dict[str, list[dict]] = {}
    if config.topic_momentum.multi_scale:
        for level in config.topic_momentum.scale_levels:
            path = f"series/{level}-series.jsonl.gz"
            if not store.path(path).exists():
                continue
            rows = []
            for item in store.read_jsonl_gz(path):
                for c in classify_topic_series(item, cfg, parameters_hash, manifest):
                    rows.append(c)
                    parent_dir[(level, item["topic"]["id"], c["evaluation_date"])] = \
                        c["classification"]["momentum_direction"]
            parent_classifications[level] = rows

    # jointure : annoter chaque classification topic
    for c in classifications:
        _attach_scale_corroboration(c, series_lookup, parent_dir)
```

`series_lookup` mappe `topic_id -> series["topic"]` pour retrouver `subfield.id` /
`field.id` du topic (déjà présents dans le bloc identité topic).

### 3.2 La fonction de concordance

```python
_OPPOSITE = {"RISING": "FALLING", "FALLING": "RISING"}

def _attach_scale_corroboration(classification, series_lookup, parent_dir):
    topic_id = classification["topic"]["id"]
    eval_date = classification["evaluation_date"]
    dt = classification["classification"]["momentum_direction"]
    ident = series_lookup[topic_id]
    sf_id = ident.get("subfield", {}).get("id")
    fld_id = ident.get("field", {}).get("id")
    ds = parent_dir.get(("subfield", sf_id, eval_date))
    df = parent_dir.get(("field", fld_id, eval_date))

    concordance, note = "NEUTRAL", None
    if dt in ("RISING", "FALLING"):
        if ds == dt:
            concordance = "CORROBORATED"
        elif ds == _OPPOSITE[dt]:
            concordance, note = "CONTRADICTED", "opposite_subfield_direction"
        elif ds in ("STABLE", "UNDETERMINED", None):
            concordance, note = "ISOLATED_WITHIN_SUBFIELD", "focused_emergence"

    classification["classification"]["scale_corroboration"] = {
        "subfield_direction": ds,
        "field_direction": df,
        "concordance": concordance,   # CORROBORATED | ISOLATED_WITHIN_SUBFIELD | CONTRADICTED | NEUTRAL
        "note": note,
    }
```

- `CORROBORATED` : topic et subfield bougent dans le même sens → preuve convergente.
- `ISOLATED_WITHIN_SUBFIELD` : subfield plat → émergence focalisée réelle, conservée.
- `CONTRADICTED` : sens opposés → artefact de petit effectif probable, revue requise.
- `NEUTRAL` : topic non directionnel (STABLE/UNDETERMINED) → pas d'annotation forte.

`scale_corroboration` s'insère dans le bloc `classification` déjà défini au contrat
(§16 du contrat, champ ajouté). Aucun champ au sommet de l'enveloppe → conforme au
contrat commun.

### 3.3 Sorties

- `classifications/topic-momentum-classifications.jsonl.gz` — **inchangé de nom**, enrichi de `scale_corroboration` (rétro-compatible : champ additif).
- `classifications/subfield-momentum-classifications.jsonl.gz`, `field-…` — nouveaux, mêmes schémas, pour permettre plus tard à TM-06 d'émettre une carte « déplacement diffus de subfield ».
- Rapport qualité TM-04 : ajouter `scale_concordance_counts` (Counter sur les topics `latest`) — un indicateur immédiat de la part de signaux corroborés vs contredits.

---

## 4. La carte « déplacement diffus » (subfield RISING sans topic dominant)

Utile mais **hors TM-04** : c'est une décision d'émission qui appartient à TM-06.
La donnée est déjà disponible après §3 (on a la direction subfield et toutes les
directions topics au même `evaluation_date`). Règle à implémenter côté TM-06 en 0.2 :

```
subfield sf est RISING à eval_date
ET aucun topic enfant de sf n'est RISING à eval_date
   (ou aucun ne porte > X% du delta de sf)
=> émettre un signal de niveau subfield, note = DIFFUSE_SUBFIELD_SHIFT
```

À réserver à un ticket TM-06 séparé pour ne pas élargir ce sketch.

---

## 5. Invariants et contrôles à ajouter

```python
def _assert_level_mass(level, unit_series, summaries):
    # Σ_units count(unit, m) == classified_works_count(m), pour chaque mois complet
    by_month_expected = {s["bucket"]["start"]: s["classified_works_count"] for s in summaries}
    got = defaultdict(int)
    for item in unit_series:
        for mp in item["monthly"]:
            got[mp["start"]] += mp["count"]
    for start, expected in by_month_expected.items():
        if got.get(start, 0) != expected:
            raise InvariantError(
                f"{level} mass mismatch at {start}: {got.get(start,0)} != {expected}")
```

Autres garde-fous :

- chaque topic du catalogue possède `subfield.id` et `field.id` (sinon `InvariantError`) ;
- les endpoints/fenêtres des séries parentes sont identiques à ceux du topic (mêmes `evaluation_date`), sinon la jointure §3.2 rate silencieusement — à asserter ;
- `scale_corroboration.concordance == "CONTRADICTED"` force `review_status = REQUIRED` en aval (hook TM-06, cf. §7).

---

## 6. Tests à ajouter (`tests/test_tm03_tm04.py`)

1. **Masse conservée** : sur un mini-catalogue à 2 subfields / 3 topics, `Σ count subfield == classified_total` à chaque mois.
2. **Fenêtres alignées** : les `evaluation_date` des séries subfield == celles du topic.
3. **Concordance CORROBORATED** : topic RISING + subfield RISING → `CORROBORATED`.
4. **Concordance ISOLATED** : topic RISING + subfield STABLE → `ISOLATED_WITHIN_SUBFIELD`.
5. **Concordance CONTRADICTED** : topic RISING + subfield FALLING → `CONTRADICTED` + note.
6. **Rétro-compat** : `multi_scale=False` reproduit exactement la sortie topic 0.1 (aucun fichier parent, pas de bloc `scale_corroboration`).
7. **Taxonomy** : une série subfield sans `created_date` → `taxonomy_change` False (pas d'exception).

---

## 7. Ce que ce sketch NE fait pas (dépendances explicites)

- **TM-05 (confiance)** : ajouter une composante `scale_corroboration` au guard —
  `CORROBORATED` relève d'un cran la cohérence, `CONTRADICTED` plafonne à `LOW` et
  pose un flag. Hook seulement, non spécifié ici.
- **TM-06 (émission/éditorial)** : (a) `CONTRADICTED` → `review_status = REQUIRED` ;
  (b) carte `DIFFUSE_SUBFIELD_SHIFT` (§4) ; (c) exposer `scale_corroboration` dans le
  bundle POC pour l'UI.
- **Borne de Poisson** (`use_poisson_lower_bound`) : réservée dans la config, calcul
  laissé à un ticket 0.2 dédié (déclencher sur la borne inférieure de l'IC du rate
  ratio, pas sur le point estimé).
- **UI** : le champ `scale_corroboration` n'apparaîtra dans l'interface qu'une fois le
  détecteur rejoué et `build_poc_bundle.py` mis à jour pour le porter. Ne rien inventer
  côté front avant.

---

## 8. Séquencement et effort

| Étape | Portée | Effort | Risque |
|---|---|---|---|
| TM-03 séries parentes + invariant de masse | `tm03.py`, `config.py` | ~½ j | faible (additif) |
| TM-04 classification multi-niveaux + jointure concordance | `tm04.py` | ~½ j | faible (classifieur réutilisé) |
| Tests 1–7 | `tests/` | ~½ j | — |
| TM-05 hook confiance | `tm05.py` | ~¼ j | moyen (touche le guard) |
| TM-06 diffuse-shift + bundle + UI | `tm06.py`, `scripts/`, `ui/` | ~1 j | moyen |

Chemin critique pour la valeur : les deux premières lignes suffisent à produire
`scale_corroboration` sur chaque signal topic et à démoter automatiquement les
artefacts de petit effectif. Le reste est incrémental.
