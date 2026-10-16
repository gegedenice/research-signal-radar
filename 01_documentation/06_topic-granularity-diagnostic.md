# Topic Momentum — diagnostic de granularité et décision multi-échelle

| Champ | Valeur |
|---|---|
| Statut | Diagnostic mesuré + décision de conception |
| Version | `topic-momentum/0.2` (granularité) |
| Date | 11 septembre 2026 |
| Univers | Mines Paris–PSL, scope `lineage`, corpus `published_core` |
| Run analysé | `tm-2026-06-30-mines-v1`, fenêtre courante 2025-07-01 → 2026-06-30 |
| Documents liés | `03.01_topic-momentum-detector-contract.md`, `05_tm08-qualitative-review.md` |
| Figure | `topic-granularity-diagnostic.png` |

---

## 1. Question

La taxonomie OpenAlex est hiérarchique : 4 domaines → 26 fields → 252 subfields →
4 516 topics. Le détecteur Topic Momentum compte les œuvres par `primary_topic.id`,
c'est-à-dire au grain le plus fin. Deux craintes concurrentes :

- au niveau **topic**, les effectifs par fenêtre de 12 mois seraient trop faibles
  (3–8 œuvres) pour porter un « signal » statistiquement crédible ;
- au niveau **subfield**, l'agrégation lisserait précisément les mouvements que l'on
  cherche à détecter.

Ce diagnostic tranche la question sur les données réelles plutôt que par argument.

## 2. Méthode

Calcul entièrement hors ligne à partir de `series/topic-series.jsonl.gz`
(1 893 topics, 78 buckets mensuels, 23 fenêtres glissantes de 12 mois évaluées
tous les 3 mois). Les mêmes séries sont réagrégées à trois niveaux — topic,
subfield, field — en sommant les comptes mensuels des topics enfants, puis la
règle POC `RISING` (`min_current=3`, `min_abs_delta=2`, `rise_count_ratio=1.5`,
`rise_share_ratio=1.25`, `min_active_months=2`) est appliquée à l'identique à
chaque niveau. La comparaison utilise deux fenêtres de 12 mois non chevauchantes
(courante vs. antérieure de 12 mois). Les parts sont calculées sur le même
dénominateur de portefeuille classifié à chaque fenêtre.

Les issues à +12 mois sont mesurées à partir de l'onset (première évaluation
`RISING` après une non-`RISING`), sur le flux d'onsets **brut et non filtré** —
distinct de l'échantillon mûr et curé de la revue TM-08.2, et à lire comme tel.

## 3. Résultats

### 3.1 Le grain topic est bien dans le régime des petits effectifs

Fenêtre courante 2025-07 → 2026-06, portefeuille classifié = 1 097 œuvres.

| Mesure | Topic | Subfield | Field |
|---|---:|---:|---:|
| Unités présentes | 1 893 | 217 | 26 |
| Unités atteignant ≥3 œuvres dans une fenêtre (au moins une fois) | 452 (24 %) | 147 (68 %) | 24 (92 %) |
| Unités déjà classées `RISING` | 393 | 128 | 14 |
| Onsets `RISING` (tous points d'évaluation) | 616 | 222 | 16 |
| Médiane d'œuvres par unité active, fenêtre courante | **1** | 3 | 19,5 |
| Moyenne d'œuvres par unité active, fenêtre courante | 1,83 | 7,57 | 45,7 |
| Unités actives sous 3 œuvres (fenêtre courante) | 493 / 600 (82 %) | 58 / 145 (40 %) | 3 / 24 |
| Médiane d'œuvres par unité sur 6,5 ans | 2 | 13 | 169,5 |

Deux faits saillants au niveau topic :

- **82 % des topics actifs dans la fenêtre courante portent moins de 3 œuvres** ;
  la médiane est de 1. Le seuil `min_current=3` place donc la barre au-dessus de
  la majorité de la population active.
- **L'alphabet réel de signalement est petit.** Sur 4 516 topics nominaux, 1 893
  apparaissent dans le corpus Mines, et seuls **452 franchissent une fois le seuil
  de 3 œuvres** sur 6,5 ans. Le détecteur travaille en pratique sur ~450 topics,
  pas 4 516.
- 1 492 topics sur 1 893 (79 %) totalisent moins de 6 œuvres sur toute la période.

### 3.2 La concentration de la masse

Toujours dans la fenêtre courante : **55,5 % des œuvres classifiées** appartiennent
à des topics portant moins de 3 œuvres, et **75,6 %** à des topics portant moins de
5 œuvres. L'essentiel du portefeuille vit donc dans la longue traîne fine, non dans
une tête dense de topics.

### 3.3 Les onsets fins sont volatils ; l'agrégation stabilise mais efface

Devenir des onsets `RISING` à +12 mois (fenêtre non chevauchante) :

| Devenir à +12 mois | Topic | Subfield | Field |
|---|---:|---:|---:|
| Volume maintenu ou supérieur | 20 % | 37 % | 36 % |
| Retourné en `FALLING` actif | **66 %** | 43 % | 21 % |
| Toujours en ré-accélération `RISING` | 3 % | 9 % | 0 % |

Passer du topic au subfield **divise presque par deux le taux de retournement**
(66 % → 43 %) et **double la rétention de volume** (20 % → 37 %) : l'agrégation
achète bien de la stabilité statistique.

Mais elle a un coût net : le nombre d'unités en mouvement **s'effondre de 393
topics à 128 subfields** jamais `RISING`, et **40 % des subfields actifs restent
sous 3 œuvres** — l'agrégation ne supprime donc pas le problème des petits
effectifs, elle le déplace, tout en noyant les pivots fins d'un laboratoire dans la
masse de son subfield. Le field est clairement trop grossier (14 unités en
mouvement seulement, 16 onsets sur toute la période).

> Le taux de retournement de 66 % au niveau topic porte sur le flux d'onsets brut,
> sans filtre de maturité ni de confiance. Il ne contredit pas la revue TM-08.2
> (qui, sur un sous-ensemble mûr et curé, mesurait ~67 % de non-retournement) : il
> mesure autre chose — la churn du flux non filtré — et c'est précisément ce que la
> couche de confiance, la logique d'épisodes et, désormais, la corroboration
> multi-échelle sont là pour maîtriser.

## 4. Décision de conception : détection multi-échelle

Ni « rester au topic » ni « monter au subfield » n'est le bon arbitrage. Le niveau
auquel une anomalie est la plus nette est lui-même une information. Le détecteur
`topic-momentum/0.2` évalue donc **le même classificateur déterministe à trois
niveaux simultanément** (topic, subfield, field — tous déjà présents dans le
payload de chaque œuvre, agrégation gratuite et hors ligne), puis croise les
résultats :

| Configuration observée | Lecture | Effet sur le signal |
|---|---|---|
| Topic `RISING` **et** subfield parent `RISING` de même sens | Preuve convergente entre échelles | Signal le plus fort ; confiance rehaussée |
| Subfield plat, un topic `RISING` isolé | Émergence focalisée réelle | Signal conservé, marqué `ISOLATED_WITHIN_SUBFIELD` |
| Subfield `RISING`, aucun topic dominant | Déplacement diffus de l'institution | Carte de niveau subfield (« Mines s'élargit vers X ») |
| Topic `RISING`, subfield en sens opposé | Bruit de petit effectif probable | Rétrogradé ; revue requise |

Le topic reste l'**unité de sens** et l'unité canonique de sortie ; le subfield et
le field deviennent une **couche de corroboration**, pas un remplacement. Cela
répond directement aux artefacts taxonomiques relevés par TM-08.2 : un pic 2→7 dans
un topic incohérent dont le subfield ne bouge pas est désormais démoté
automatiquement, sans nouveau seuil.

### Statistiques honnêtes pour les petits effectifs (complément)

Deux mesures, par effort croissant, à appliquer indépendamment du niveau :

1. **Borne de Poisson.** Déclencher et afficher sur la borne inférieure de
   l'intervalle de confiance du rate ratio, pas sur le point estimé ; afficher les
   comptes sous la forme `n (IC 95 %)`. Coût nul, supprime la moitié des onsets
   fragiles.
2. **Shrinkage empirique-bayésien** (B12 de la roadmap, non implémenté) : modéliser
   le taux de chaque topic comme tiré de la distribution de son subfield parent et
   signaler sur la déviation postérieure. Les petits comptes se contractent vers le
   parent ; les mouvements réels survivent. C'est la version principielle du point 1,
   et elle **utilise** la hiérarchie au lieu d'y monter.

La couche d'épisodes (ISOLATED / PERSISTENT / ESCALATED) reste le lieu où la
sparsité est absorbée à la confirmation : un onset sur 4 œuvres est un candidat de
veille, jamais un mouvement confirmé.

## 5. Portée et limites

- Le diagnostic porte sur un seul univers (Mines, taille moyenne : ~1 400
  œuvres/an en `published_core`). Une institution plus grande, ou le mode topic
  (surveillance mondiale d'un topic, où les comptes sont grands), sortent du régime
  des petits effectifs ; la conclusion sur la granularité y sera différente.
- Le backtest reconstruit le passé avec la taxonomie et le snapshot OpenAlex de
  2026 (`retrospective_reconstruction`).
- Le taux de retournement dépend de la définition d'onset retenue ici ; il illustre
  la volatilité relative entre niveaux, pas une mesure absolue d'utilité.

## 6. Suite recommandée

1. Implémenter l'agrégation subfield/field dans TM-03 (séries) et exposer la
   corroboration multi-échelle dans TM-04/TM-06 (champ `scale_corroboration` de
   l'enveloppe).
2. Ajouter la borne de Poisson à l'affichage et au guard de confiance (TM-05).
3. Réserver le shrinkage empirique-bayésien à une version 0.3, après mesure de
   l'apport de la corroboration multi-échelle seule.
