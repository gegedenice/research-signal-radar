# Research Signal Common Contract

## Mini-contrat partagé par les détecteurs

| Champ | Valeur |
|---|---|
| Statut | Candidat validé par fixtures dummy |
| Version | `research-signal-common/0.1` |
| Date | 28 août 2026 |
| Premier détecteur | `topic_momentum` |
| Détecteurs testés en anticipation | `citation_acceleration`, `actor_collaboration_novelty` |
| Contrat détaillé associé | `topic-momentum-detector-contract.md` |

## 1. Décision d'architecture

Le pipeline est un **instrument composé d'un socle commun et de détecteurs indépendants**. Le socle collecte et normalise les observations, décrit les runs et transporte les signaux. Chaque détecteur reste propriétaire de sa baseline, de ses métriques, de ses règles et de son `payload`.

Le mini-contrat ne cherche pas à anticiper les formules des futurs détecteurs. Il garantit seulement que :

1. une observation est datée, sourcée et rejouable ;
2. un signal est interprétable sans connaître son implémentation ;
3. les preuves renvoient à des observations ou artefacts identifiables ;
4. les données du futur sont séparées du signal produit à une date de cutoff ;
5. les champs propres à un détecteur restent dans son `payload` ;
6. le backtest utilise la même enveloppe de signal que l'exécution normale.

## 2. Frontière entre socle et détecteur

| Responsabilité | Socle commun | Détecteur |
|---|---:|---:|
| Définition et version du périmètre | Oui | Non |
| Query manifest et vintage | Oui | Non |
| Conservation des réponses brutes | Oui | Non |
| Normalisation des œuvres et authorships | Oui | Non |
| Historique des snapshots citationnels | Oui | Non |
| Construction de la baseline | Orchestration | Méthode |
| Calcul des métriques | Non | Oui |
| Seuils et abstentions | Non | Oui |
| Enveloppe du signal | Oui | Payload spécifique |
| Dossier de preuves | Format | Sélection |
| Validation prospective du backtest | Format | Critères |

## 3. Objets canoniques

### 3.1 `QueryManifest`

Identifie une collecte sans réinterpréter sa requête : source, date d'observation, univers, paramètres et empreinte de requête. Le manifeste OpenAlex complet demeure celui défini dans le contrat Topic Momentum ; le socle n'en retient que les champs transversaux.

### 3.2 `WorkObservation`

Une observation n'est pas « un article » : c'est **l'état observé d'une œuvre à un instant donné**.

Identité logique :

```text
(source, work_id, observed_at, universe_id)
```

Le même `work_id` peut donc apparaître plusieurs fois. C'est indispensable pour reconstruire une accélération citationnelle sans utiliser la valeur actuelle comme si elle avait été connue dans le passé.

Champs conservés dès le premier sweep :

- identifiants OpenAlex et DOI ;
- titre, date et type de publication ;
- topic primaire avec ID et label ;
- auteurs, positions et institutions ;
- snapshot du nombre de citations ;
- références, lorsqu'elles sont demandées ou disponibles ;
- motif d'inclusion dans l'univers ;
- source, manifeste et vintage.

Un abstract n'est pas obligatoire. Une œuvre sans topic reste une observation valide avec `primary_topic: null` et participe aux métriques de couverture.

### 3.3 `SignalEnvelope`

Tous les détecteurs exposent les mêmes rubriques :

- identité et version du détecteur ;
- univers observé ;
- sujet du signal ;
- fenêtre courante et référence ;
- score de priorité, sans prétention probabiliste ;
- confiance et limites ;
- explication courte ;
- preuves ;
- provenance du run ;
- indicateurs qualité ;
- `payload` spécifique au détecteur.

Le `priority_score` est borné entre 0 et 1 pour le tri. Il ne signifie ni probabilité de vérité ni probabilité de succès futur.

### 3.4 `EvidenceItem`

Une preuve possède :

- un identifiant stable dans le signal ;
- un type (`observation`, `metric`, `graph_edge`, `query_manifest`, `external_artifact`) ;
- un rôle explicite dans l'argument ;
- une date d'observation ;
- un locator structuré ;
- une phrase précisant ce qu'elle soutient.

Une preuve utilisée pour détecter un signal ne peut pas être postérieure à `detected_at`.

### 3.5 `BacktestResult`

Le résultat futur ne modifie jamais le signal historique. Il est stocké séparément et relie :

- le `signal_id` produit au cutoff ;
- l'horizon d'évaluation ;
- des métriques prospectives ;
- une qualification automatique ;
- éventuellement une revue humaine.

Cette séparation empêche la fuite du futur dans le dossier de preuves originel.

## 4. Interface logique du détecteur

```python
class Detector:
    detector_type: str
    detector_version: str

    def build_baseline(self, observations, analysis_context, parameters): ...
    def detect(self, observations, baseline, parameters): ...
    def build_evidence(self, signal, observations): ...
    def backtest(self, observations, cutoffs, parameters): ...
```

Ce contrat n'impose ni classe Python réelle, ni framework de plugins. Il définit les entrées et sorties attendues de chaque étape.

## 5. Sémantique temporelle

Le socle distingue trois temps :

| Temps | Signification |
|---|---|
| `publication_date` | Date attribuée à l'œuvre |
| `observed_at` | Date à laquelle la source a été interrogée ou figée |
| `detected_at` | Cutoff informationnel du signal |

Règles :

1. toute observation utilisée par le signal vérifie `observed_at <= detected_at` ;
2. la fenêtre courante se termine au plus tard à `detected_at` ;
3. une validation à +6 ou +12 mois appartient uniquement à `BacktestResult` ;
4. un snapshot actuel ne peut pas être antidaté pour simuler un état historique ;
5. un backtest rétrospectif indique si les données utilisées sont un vrai vintage ou une reconstruction.

## 6. Extension par détecteur

Le champ `payload` est un espace de noms contrôlé par `detector.type` et `detector.version`.

### `topic_momentum`

Contient notamment les volumes, parts, ratios, présence, direction, accélération et anomalie historique. Son contrat complet reste `topic-momentum/0.1`.

### `citation_acceleration`

Le dummy vérifie que le socle peut exprimer :

- une œuvre comme sujet ;
- plusieurs snapshots citationnels ;
- une référence de type `cohort` ;
- un gain observé, un gain attendu et un ratio normalisé ;
- une couverture OpenCitations/OpenAlex documentée.

Les règles de normalisation par âge, type et topic ne sont pas contractualisées ici.

### `actor_collaboration_novelty`

Le dummy vérifie que le socle peut exprimer :

- un auteur, une institution ou une collaboration comme sujet ;
- deux membres dans une collaboration ;
- une référence de type `network_history` ;
- une arête nouvelle ou réactivée ;
- les œuvres qui matérialisent la relation.

Les règles de désambiguïsation, de nouveauté et de centralité ne sont pas contractualisées ici.

## 7. Test dummy de compatibilité

Le bundle `dummy-detector-compatibility-fixtures.json` contient :

- deux query manifests correspondant aux deux vintages simulés ;
- cinq observations, dont deux snapshots de la même œuvre ;
- trois signaux partageant exactement la même enveloppe ;
- trois résultats de backtest séparés.

Le validateur exécute :

### Tests positifs

1. validation JSON Schema du bundle ;
2. identité des clés d'enveloppe entre les trois détecteurs ;
3. correspondance `payload.payload_schema == detector.type` ;
4. résolution des preuves vers les observations ;
5. correspondance entre chaque observation, son manifeste et son univers ;
6. absence de fuite temporelle ;
7. présence d'un topic observable pour Topic Momentum ;
8. présence de deux snapshots citationnels ordonnés ;
9. présence des deux membres de la collaboration dans une authorship observée ;
10. séparation entre signal au cutoff et résultat futur.

### Tests négatifs

1. un score de confiance supérieur à 1 doit être rejeté ;
2. un champ propre au détecteur placé au sommet de l'enveloppe doit être rejeté ;
3. une preuve postérieure au cutoff doit être rejetée ;
4. une observation reliée au mauvais manifeste de vintage doit être rejetée ;
5. la suppression du topic supportant le signal Topic Momentum doit être détectée.

Commande :

```bash
uv run validate_dummy_compatibility.py \
  research-signal-contract.schema.json \
  dummy-detector-compatibility-fixtures.json
```

## 8. Critère de compatibilité

Le test est concluant si les trois détecteurs peuvent être représentés sans :

- ajouter un champ spécifique au sommet de `SignalEnvelope` ;
- détourner la sémantique d'un champ commun ;
- utiliser une donnée postérieure au cutoff ;
- écraser un snapshot antérieur ;
- placer les résultats du backtest dans le signal d'origine.

## 9. Résultat

**Compatibilité structurelle : PASS.**

**Compatibilité temporelle : PASS.**

**Compatibilité des preuves : PASS.**

**Tests négatifs : PASS — les cinq corruptions simulées sont rejetées.**

Le test révèle une contrainte importante pour l'implémentation : le sweep du premier détecteur doit déjà conserver les authorships et un snapshot citationnel daté, même si Topic Momentum ne les utilise pas encore dans son calcul. Le coût marginal est faible et évite une incompatibilité ou une recollecte future.

## 10. Ce que ce contrat ne fige pas

- stockage fichiers, DuckDB ou base relationnelle ;
- format des réponses brutes compressées ;
- cadence du sweep ;
- formules de normalisation citationnelle ;
- règles de résolution des auteurs et affiliations ;
- score commun multi-détecteurs ;
- fusion ou déduplication de signaux ;
- texte final du dossier de preuves.

Ces décisions doivent être prises à partir du premier instrument et de son backtest.

## 11. Décision de passage à l'implémentation

Le socle est suffisamment compatible pour engager la tranche verticale Topic Momentum :

```text
sweep OpenAlex
→ observations normalisées
→ baseline historique
→ Topic Momentum
→ signal.json
→ dossier-de-preuves.md
→ backtest walk-forward
```

Les deux autres contrats détaillés peuvent rester différés. Aucun élément détecté par le test dummy n'exige de les spécifier avant l'implémentation de cette première tranche.
