# Actor & Collaboration Novelty — mini-contrat du détecteur

| Champ | Valeur |
|---|---|
| Statut | ACN-01 à ACN-04 implémentés ; détecteur et backtest minimal complets |
| Version | `actor-collaboration-novelty/0.1` |
| Identifiant | `actor_collaboration_novelty` |
| Enveloppe commune | `research-signal-common/0.1` + `signal-envelope/0.2` |
| Sujets v0.1 | Institution externe ou collaboration institutionnelle |
| Source | `WorkObservation` OpenAlex déjà collectées |
| Nouvelle API | Aucune |

## 1. Finalité

Le détecteur repère l'entrée ou le retour d'une institution externe dans le
portefeuille observé, ainsi que l'apparition ou la réactivation d'une relation
de co-publication entre cette institution et une institution du périmètre.

Il répond à deux questions :

1. quelle institution externe devient nouvellement visible dans l'activité de
   recherche du périmètre ?
2. quelle relation institutionnelle absente de la période récente devient
   suffisamment matérialisée pour mériter une veille ?

Le détecteur ne prétend jamais qu'un acteur ou une relation est nouveau dans le
monde académique. Il affirme seulement une nouveauté **dans l'historique
observable du portefeuille versionné**.

## 2. Portée volontairement limitée

La v0.1 traite uniquement les institutions identifiées par un ID OpenAlex.

Sont hors v0.1 :

- détection d'auteurs émergents ;
- prestige ou réputation globale d'un acteur ;
- graph embeddings, community detection et prédiction de liens ;
- inférence d'une collaboration à partir du texte seul ;
- enrichissement pays, secteur, ROR ou géopolitique ;
- collaborations entre deux institutions externes sans lien direct avec le
  périmètre ;
- interface utilisateur et fusion automatique avec les autres détecteurs.

Ces exclusions empêchent de transformer une première brique produit en projet
de scientométrie générale.

## 3. Vocabulaire et périmètre

### Institution ancre

Institution dont l'ID appartient à `QueryManifest.universe.included_institution_ids`.
Dans un scope `exact`, il s'agit normalement de l'institution racine. Dans un
scope `lineage`, plusieurs unités peuvent être ancres.

### Institution externe

Institution présente dans une authorship mais absente de l'ensemble des
institutions ancres.

### Collaboration institutionnelle

Une œuvre matérialise une collaboration entre une ancre et une institution
externe si :

- au moins un auteur est affilié à l'ancre ;
- au moins un autre auteur est affilié à l'institution externe ;
- les deux auteurs possèdent des IDs OpenAlex distincts.

Une double affiliation portée uniquement par la même personne ne suffit pas à
créer une arête de collaboration. Elle est conservée comme diagnostic de
co-affiliation.

### Comptage

Une œuvre compte au maximum une fois pour un acteur ou une arête, quel que soit
le nombre d'auteurs concernés. Les IDs d'institution et d'œuvre sont les clés de
déduplication.

## 4. Observation normalisée

ACN-01 dérive des `WorkObservation` un `CollaborationEventObservation` sans
nouvel appel réseau :

```json
{
  "schema_version": "collaboration-event-observation/0.1",
  "event_id": "acn-event:W123:Ianchor:Iexternal",
  "work_id": "W123",
  "publication_date": "2025-09-12",
  "publication_month": "2025-09",
  "anchor_institution": {"id": "Ianchor", "label": "Unité interne"},
  "external_institution": {"id": "Iexternal", "label": "Partenaire externe"},
  "author_pairs": [
    {"anchor_author_id": "A1", "external_author_id": "A2"}
  ],
  "author_pair_count": 1,
  "author_pairs_truncated": false,
  "primary_topic": {"id": "T1", "label": "Topic"},
  "observed_at": "2026-08-29T10:45:42Z",
  "source": {"provider": "OpenAlex", "work_observation_id": "obs-..."}
}
```

Pour éviter une explosion combinatoire sur les publications de consortium, le
compte exact des paires est conservé mais seules vingt paires représentatives
au maximum sont sérialisées par arête. Cette borne ne change ni l'existence de
la collaboration ni les métriques de diversité.

Les œuvres dont le rattachement à une institution ancre n'est pas matérialisé
localement ne produisent pas d'arête. Elles sont comptées dans le rapport de
couverture sous `ANCHOR_NOT_MATERIALIZED`.

## 5. Fenêtres et baseline

Au cutoff courant :

- fenêtre courante : douze derniers mois ;
- baseline récente : trente-six mois immédiatement précédents ;
- historique antérieur : depuis le début du corpus jusqu'au début de la
  baseline récente ;
- œuvres postérieures au cutoff : interdites.

Le corpus doit offrir au moins trente-six mois complets avant la fenêtre
courante. La date de début du corpus est toujours exposée, car elle limite la
portée du mot « nouveau ».

Pour chaque institution externe et chaque arête ancre–externe, la baseline
conserve :

- nombre d'œuvres par mois ;
- première et dernière apparition observées ;
- institutions ancres reliées ;
- auteurs et paires d'auteurs distincts ;
- topics distincts ;
- proportion d'œuvres dont le rattachement à l'ancre est vérifié localement.

## 6. Labels

### Acteurs

- `NEW_EXTERNAL_ACTOR` : aucune apparition avant la fenêtre courante ;
- `REACTIVATED_EXTERNAL_ACTOR` : présence dans l'historique ancien, absence
  pendant les trente-six mois de baseline, puis retour dans la fenêtre courante.

### Collaborations

- `NEW_COLLABORATION` : l'institution externe est visible avec une autre ancre
  pendant la baseline récente, mais cette arête ancre–externe n'avait jamais
  été observée ;
- `REACTIVATED_COLLABORATION` : l'institution externe reste visible avec une
  autre ancre pendant la baseline récente, tandis que l'arête considérée
  existait seulement dans l'historique ancien puis réapparaît.

Lorsqu'une institution externe est nouvelle ou réactivée à l'échelle du
portefeuille, le détecteur émet un seul signal acteur. Ses arêtes sont décrites
dans le payload et les preuves, sans créer d'alertes collaboration redondantes.

Dans un scope `exact` à ancre unique, cette règle implique normalement que la
nouveauté d'une arête est absorbée par la nouveauté de l'acteur. Les signaux
`NEW_COLLABORATION` distincts prennent surtout leur sens dans le scope
`lineage`, lorsqu'un partenaire déjà actif commence à publier avec une autre
unité interne. Ce comportement est attendu, pas une absence de couverture.

## 7. Règle candidate v0.1

Un acteur ou une arête devient candidat si toutes les conditions suivantes sont
réunies :

```text
current_work_count >= 2
current_active_months >= 2
recent_baseline_work_count == 0
locally_verified_supporting_works >= 2
```

À ces conditions s'ajoute la condition historique propre à chaque label :

- aucune occurrence antérieure pour `NEW_*` ;
- au moins une occurrence antérieure à la baseline pour `REACTIVATED_*` ;
- acteur externe présent avec une autre ancre dans la baseline récente pour les
  deux labels collaboration.

Ces seuils privilégient une relation matérialisée plusieurs fois et écartent la
grande majorité des co-publications ponctuelles. Ils sont versionnés et devront
être backtestés, mais ne seront pas multipliés en profils de sensibilité dans le
POC.

## 8. Abstentions et couverture

Le rapport qualité distingue au minimum :

- `INSUFFICIENT_HISTORY` ;
- `ANCHOR_NOT_MATERIALIZED` ;
- `UNRESOLVED_AUTHOR_ID` ;
- `UNRESOLVED_INSTITUTION_ID` ;
- `NO_EXTERNAL_INSTITUTION` ;
- `DUAL_AFFILIATION_ONLY` ;
- `INSUFFICIENT_CURRENT_SUPPORT` ;
- `SINGLE_ACTIVE_MONTH`.

Les motifs liés à une authorship ou une œuvre n'invalident pas les autres
relations correctement observées sur la même œuvre. Le rapport publie le nombre
d'œuvres utilisables, exclues et partiellement utilisables.

## 9. Confiance et priorité

### Confiance

La confiance dépend uniquement de la qualité de la preuve :

- matérialisation locale de l'institution ancre ;
- nombre d'œuvres distinctes ;
- diversité des auteurs ou paires d'auteurs ;
- dispersion sur plusieurs mois ;
- stabilité des IDs d'institution.

Une proposition simple pour la v0.1 :

```text
confidence =
  0.35 * anchor_materialization
  + 0.25 * work_support
  + 0.20 * author_pair_diversity
  + 0.20 * temporal_spread
```

Chaque composante est bornée entre 0 et 1. La confiance ne mesure ni
l'importance stratégique ni la probabilité de continuation.

### Priorité

La priorité sert seulement au classement :

```text
priority =
  0.35 * current_support_rank
  + 0.25 * internal_reach_rank
  + 0.20 * topic_diversity_rank
  + 0.20 * confidence
```

`internal_reach` désigne le nombre d'institutions ancres distinctes reliées à
l'acteur. Pour une arête unique, cette composante vaut le rang de la portée
actuelle de l'acteur externe dans le portefeuille.

Le score reste une saillance éditoriale, jamais une probabilité.

## 10. Payload dans `SignalEnvelope`

### Exemple acteur

```json
{
  "payload_schema": "actor_collaboration_novelty",
  "signal_label": "NEW_EXTERNAL_ACTOR",
  "subject_type": "institution",
  "current_work_count": 3,
  "current_active_months": 3,
  "recent_baseline_work_count": 0,
  "older_history_work_count": 0,
  "first_observed_date": "2025-08-14",
  "anchor_institutions": ["I1", "I2"],
  "distinct_author_pair_count": 4,
  "distinct_topic_count": 2,
  "supporting_work_ids": ["W1", "W2", "W3"],
  "editorial": {
    "tier": "HEADLINE_CANDIDATE",
    "review_status": "OPTIONAL"
  }
}
```

### Sujet collaboration

Pour une collaboration, `subject.kind` vaut `collaboration`, `subject.id` est
un identifiant stable dérivé des deux institutions et `subject.member_ids`
contient `[anchor_institution_id, external_institution_id]`.

Le `payload` reprend les mêmes compteurs et ajoute `anchor_institution`,
`external_institution`, `edge_first_observed_date` et l'historique de l'arête.

## 11. Dossier de preuves

Chaque signal expose :

- chronologie mensuelle de l'acteur ou de l'arête ;
- toutes les œuvres soutenant la règle candidate sous forme d'IDs ;
- au plus cinq œuvres représentatives détaillées ;
- auteurs et affiliations matérialisant chaque relation ;
- topics concernés ;
- première et dernière apparition avant le cutoff ;
- raison exacte du label `NEW` ou `REACTIVATED` ;
- limites de couverture et date de début de l'historique observable ;
- manifeste et vintage.

Comme pour Citation Acceleration, un seul dossier Markdown présente les signaux
prioritaires ; les preuves exhaustives restent en JSONL compressé.

## 12. Backtest minimal

Le replay utilise les mêmes cutoffs semestriels que CA-04 et reconstruit les
nœuds et arêtes avec les seules œuvres publiées avant chaque cutoff. Le mode est
`retrospective_reconstruction` tant que les données proviennent d'un snapshot
OpenAlex actuel.

À +12 mois :

- `CONTINUED` : au moins une nouvelle œuvre matérialise le même acteur ou la
  même arête ;
- `ONE_OFF` : aucune nouvelle œuvre ;
- `RIGHT_CENSORED` : horizon incomplet.

Le taux de continuation n'est pas une mesure d'importance scientifique. La
revue humaine vérifie surtout si la relation aurait justifié une veille ou une
prise de contact au moment de sa première détection.

## 13. Tranches d'implémentation

```text
ACN-01  CollaborationEventObservation + rapport de couverture
ACN-02  historiques acteurs/arêtes + candidates + abstentions
ACN-03  SignalEnvelope + classement + preuves + dossier Markdown
ACN-04  replay semestriel + outcomes à 12 mois + échantillon de revue
```

ACN-01 à ACN-03 constituent le détecteur courant. ACN-04 clôt le détecteur par
un unique micro-cycle de validation, sans calibration supplémentaire prévue
dans le POC.

## 14. Critères de sortie

Le détecteur est retenu si :

1. la couverture des affiliations matérialisées est publiée et exploitable ;
2. les candidats restent rares par rapport aux acteurs et arêtes observés ;
3. chaque signal se résout vers au moins deux œuvres et leurs authorships ;
4. les doubles affiliations seules ne créent pas de fausses collaborations ;
5. le replay ne contient aucune œuvre postérieure au cutoff ;
6. la revue humaine identifie des relations qui auraient mérité une attention
   anticipée.

## 15. Décision avant implémentation

Les `WorkObservation` actuelles contiennent déjà les IDs d'auteurs, les
institutions, les dates, les topics, le manifeste et le vintage nécessaires.
Le détecteur peut donc être implémenté entièrement hors ligne sans modifier le
sweep OpenAlex ni le contrat commun.
