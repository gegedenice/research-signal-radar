# Citation Acceleration — mini-contrat du détecteur

| Champ | Valeur |
|---|---|
| Statut | CA-01 à CA-04 implémentés ; détecteur v0.1 complet |
| Version | `citation-acceleration/0.1` |
| Enveloppe commune | `research-signal-common/0.1` + `signal-envelope/0.2` |
| Sujet | Une œuvre académique |
| Question | Cette œuvre reçoit-elle des citations beaucoup plus vite que précédemment et que des œuvres comparables ? |

## 1. Finalité

Le détecteur repère une **rupture de vitesse citationnelle**, et non les œuvres
les plus citées. Une œuvre ancienne et déjà très citée ne devient pas un signal
si son rythme reste normal. Une œuvre encore peu citée peut devenir un signal
si son rythme récent accélère anormalement dans sa cohorte.

Le détecteur produit une alerte explicable : métriques, cohorte de référence,
chronologie des citations, sources et limites de couverture.

## 2. Sources et décision OpenCitations

### OpenAlex

OpenAlex reste la source de référence pour l'identité de l'œuvre, le DOI, la
date, le type, le topic, les auteurs, les institutions et le snapshot
`cited_by_count` déjà présent dans `WorkObservation`.

### OpenCitations Index v2

Le chemin critique utilise seulement :

- `GET /index/v2/citations/{id}` : citations entrantes, avec DOI du document
  citant, date `creation` et indicateurs de self-citation ;
- `GET /index/v2/citation-count/{id}` : contrôle de complétude de la réponse.

L'identifiant privilégié est `doi:<doi-normalisé>`. Le token éventuel passe par
`OPENCITATIONS_API_KEY` et n'est jamais sérialisé.

Les routes `references` et `reference-count` sont supportables par le futur
client, mais **hors calcul v0.1** : elles décrivent les références sortantes et
ne sont pas nécessaires pour mesurer la vitesse des citations entrantes. Elles
pourront enrichir plus tard les analyses de transfert conceptuel.

Les réponses brutes sont mises en cache et la collecte est reprenable. Le
pipeline respecte la limite publiée par OpenCitations et reste en dessous de
celle-ci par défaut.

## 3. Population éligible et abstentions

Une œuvre est éligible si :

- elle appartient au `QueryManifest` et à l'univers versionné ;
- elle possède un DOI normalisable ;
- elle est publiée depuis au moins douze mois au cutoff ;
- OpenCitations renvoie une réponse exploitable ;
- une cohorte de référence suffisante peut être construite.

Le détecteur s'abstient explicitement avec l'un des motifs suivants :

- `NO_DOI` ;
- `TOO_RECENT` ;
- `OPENCITATIONS_UNAVAILABLE` ;
- `INSUFFICIENT_CITATION_HISTORY` ;
- `INSUFFICIENT_COHORT_SUPPORT`.

La part du corpus exclue pour absence de DOI ou de couverture OpenCitations est
toujours publiée dans le rapport qualité.

## 4. Observation citationnelle normalisée

Chaque ligne OpenCitations devient un `CitationEventObservation` :

```json
{
  "schema_version": "citation-event-observation/0.1",
  "event_id": "oc:oci:...",
  "cited_work_id": "W...",
  "cited_doi": "10....",
  "citing_pid": "doi:10....",
  "creation_date": "2025-03-14",
  "creation_month": "2025-03",
  "creation_year": "2025",
  "creation_precision": "DAY",
  "observed_at": "2026-08-29T10:45:42Z",
  "author_self_citation": "no",
  "journal_self_citation": "no",
  "source": {"provider": "OpenCitations", "oci": "..."}
}
```

`creation_date` est la date de publication de l'œuvre citante, pas la date à
laquelle OpenCitations a indexé la citation. CA-01 conserve aussi les précisions
partielles réellement fournies : `creation_precision` vaut `DAY`, `MONTH`,
`YEAR`, `MISSING` ou `CONFLICTING`. Une date au mois alimente les séries
mensuelles via `creation_month`; une année seule est conservée mais exclue du
calcul principal CA-02. Aucun jour ou mois fictif n'est imputé.

## 5. Fenêtres et baseline

À chaque cutoff :

- fenêtre courante : douze derniers mois ;
- fenêtre précédente : les douze mois antérieurs ;
- événements postérieurs au cutoff : interdits ;
- citations marquées `author_sc = yes` : exclues de la métrique principale,
  mais conservées pour un test de sensibilité.

Métriques élémentaires :

```text
recent_count       = citations dans la fenêtre courante
previous_count     = citations dans la fenêtre précédente
absolute_delta     = recent_count - previous_count
acceleration_ratio = (recent_count + 1) / (previous_count + 1)
raw_acceleration   = log(1 + recent_count) - log(1 + previous_count)
```

La normalisation compare `raw_acceleration` à une cohorte du même univers,
construite selon :

1. type de publication ;
2. âge de publication au cutoff ;
3. primary topic lorsque l'effectif le permet ;
4. repli vers le subfield, puis vers le portefeuille institutionnel.

La métrique normalisée principale est le percentile empirique dans cette
cohorte. Chaque signal expose le niveau de repli effectivement utilisé.

CA-02 réalise ce calcul au cutoff courant du corpus. Il publie les assessments,
les cohortes et les abstentions, mais n'applique pas encore la règle candidate
ci-dessous et n'émet aucun signal. La même logique sera rejouée aux cutoffs
historiques par CA-04.

## 6. Règle candidate v0.1

Une œuvre devient candidate si toutes les conditions sont satisfaites :

```text
recent_count >= 3
absolute_delta >= 2
acceleration_ratio >= 1.5
cohort_percentile >= 0.90
cohort_size >= 20
```

Ces seuils sont des paramètres versionnés à backtester, pas des vérités métier.

Deux labels sont distingués :

- `BREAKOUT` : zéro ou une citation dans la fenêtre précédente ;
- `ACCELERATING` : vitesse antérieure déjà établie puis en hausse.

## 7. Confiance et priorité

La confiance dépend de :

- la taille et la précision de la cohorte ;
- la couverture DOI/OpenCitations ;
- la concordance diagnostique entre le compte OpenCitations et le snapshot
  OpenAlex, sans exiger leur égalité ;
- la robustesse du signal après exclusion des self-citations connues ;
- la complétude des dates `creation`.

La priorité combine le percentile de cohorte, le ratio d'accélération, le
volume récent et la robustesse. Comme dans le contrat commun, elle ne représente
pas une probabilité de persistance ou d'importance scientifique.

## 8. Payload dans `SignalEnvelope`

```json
{
  "payload_schema": "citation_acceleration",
  "signal_label": "BREAKOUT",
  "recent_citation_count": 8,
  "previous_citation_count": 2,
  "absolute_delta": 6,
  "acceleration_ratio": 3.0,
  "raw_acceleration": 1.0986,
  "cohort": {
    "kind": "primary_topic_age_type",
    "size": 37,
    "percentile": 0.97,
    "fallback_level": 0
  },
  "coverage": {
    "opencitations_count": 19,
    "openalex_count_at_vintage": 24,
    "cross_source_ratio": 0.7917
  },
  "self_citation_sensitivity": {
    "known_author_self_citations": 1,
    "candidate_without_known_self_citations": true
  }
}
```

Tous les champs propres au détecteur restent dans `payload`.

## 9. Dossier de preuves

Pour chaque signal :

- identité et métadonnées de l'œuvre ;
- histogramme mensuel ou trimestriel des citations entrantes ;
- comparaison des deux fenêtres ;
- définition et distribution résumée de la cohorte ;
- citations récentes représentatives avec DOI, date et self-citation connue ;
- comparaison diagnostique OpenCitations/OpenAlex ;
- explication « pourquoi c'est inhabituel » ;
- limites et niveau de confiance.

L'enrichissement des quelques œuvres citantes représentatives peut être fait
après détection via OpenAlex, puis archivé avec son propre vintage.

## 10. Backtest minimal CA-04

Le replay semestriel utilise uniquement les événements dont le mois de création
est exploitable et antérieur ou égal à `information_cutoff`. Il reconstruit à
chaque cutoff la population éligible, les fenêtres, les cohortes et la règle
candidate CA-03.

Dans un snapshot OpenCitations courant, il porte obligatoirement le mode
`retrospective_reconstruction` : il reconstruit les dates de publication des
citations, mais ne prétend pas que ces relations étaient déjà indexées au
cutoff historique. Pour éviter une fuite du futur, le cross-check entre les
comptes OpenAlex et OpenCitations du vintage actuel ne participe pas au score
historique.

À +12 mois, une politique volontairement descriptive distingue seulement :

- `SUSTAINED` : le nombre de citations des douze mois suivants égale ou dépasse
  celui de la fenêtre de détection ;
- `FADED` : le nombre des douze mois suivants est inférieur ;
- `RIGHT_CENSORED` : l'horizon complet n'est pas encore disponible.

Le résultat futur reste séparé du `SignalEnvelope`. Un échantillon équilibré
des issues observées est publié pour revue humaine.

## 11. Tranche d'implémentation

```text
CA-01  collecte OpenCitations reprenable + CitationEventObservation
CA-02  séries 12m/12m + cohortes + abstentions
CA-03  détection + SignalEnvelope + dossier de preuves
CA-04  replay historique + outcomes + revue qualitative
```

Le test dummy du contrat commun couvre déjà la forme de l'enveloppe, le sujet
`work`, la référence `cohort` et la séparation du backtest. Aucun changement du
contrat commun n'est requis.

## 12. Critère de sortie

Le détecteur est retenu pour le POC si le backtest montre que :

1. les signaux sont rares par rapport aux œuvres éligibles ;
2. ils restent explicables par des événements citationnels identifiables ;
3. une part suffisante demeure anormale à +12 mois ;
4. la revue humaine trouve des cas qui auraient justifié une lecture anticipée ;
5. le résultat ne dépend pas principalement des self-citations ou d'une cohorte
   trop petite.

## Référence API

- [OpenCitations Index REST API v2](https://api.opencitations.net/index/v2)
