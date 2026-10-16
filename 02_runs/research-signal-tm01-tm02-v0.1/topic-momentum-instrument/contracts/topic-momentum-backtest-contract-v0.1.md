# Topic Momentum — contrat de backtest TM-08

| Champ | Valeur |
|---|---|
| Statut | Contrat d'implémentation TM-08 |
| Version | `topic-momentum-backtest/0.1` |
| Entrée temporelle | `signal-envelope/0.2` |
| Politique de résultat | `topic-momentum-outcome/0.1` |
| Horizons | +6 et +12 mois |

## Objet

TM-08 mesure le devenir des signaux rejoués par TM-07. Il ne modifie ni les
signaux historiques, ni leurs scores, ni les seuils du détecteur. Un résultat
décrit la persistance d'un déplacement bibliométrique dans le même snapshot ;
il ne constitue ni une validation scientifique du topic ni une preuve causale.

## Unités d'analyse

### Événement-signal

Chaque enveloppe TM-07 reçoit un résultat indépendant à +6 et +12 mois. Ce
niveau sert à calibrer les tiers, la confiance et les deux directions.

### Épisode

Un épisode regroupe, pour un topic et une direction donnés, des signaux présents
à des cutoffs consécutifs. Un cutoff absent ou un changement de direction ouvre
un nouvel épisode. L'épisode conserve deux ancres :

1. son premier signal, qui mesure l'early warning ;
2. son premier `HEADLINE_CANDIDATE`, s'il existe, qui mesure la confirmation
   éditoriale.

## Mesure du résultat

Pour une direction de signe `s` (`+1` pour `RISING`, `NEW` ou `REACTIVATED` ;
`-1` pour `FALLING` ou `DORMANT`) :

```text
déplacement détection = s × (valeur détection − valeur référence)
déplacement horizon   = s × (valeur horizon − valeur référence)
rétention             = déplacement horizon / déplacement détection
```

Le calcul est réalisé séparément sur le nombre d'œuvres et la part de
portefeuille. Le déplacement de détection doit être strictement positif sur les
deux axes, conformément au contrat Topic Momentum.

| Résultat | Règle conjointe volume / part |
|---|---|
| `STRENGTHENED` | les deux rétentions sont supérieures ou égales à 1 |
| `RETAINED` | les deux rétentions sont supérieures ou égales à 0,5 |
| `FADED` | les deux restent positives, mais au moins une est inférieure à 0,5 |
| `REVERSED` | les deux sont inférieures ou égales à 0 |
| `MIXED` | les deux axes se trouvent de part et d'autre de 0 |

`confirmed = true` uniquement pour `STRENGTHENED` et `RETAINED`. Le seuil de
rétention 0,5 est un paramètre versionné de lecture du backtest, pas un nouveau
seuil du détecteur. Les ratios continus sont toujours conservés.

## Horizons et censure

- La cible est la fin du mois obtenue exactement 6 ou 12 mois après le cutoff.
- Une cible disponible dans les séries TM-03 produit `status = OBSERVED`.
- Une cible postérieure à la dernière évaluation disponible produit
  `status = RIGHT_CENSORED`.
- Un cutoff qui devrait être disponible mais manque dans la série est une erreur
  d'invariant, pas une censure.
- Les résultats censurés sont exclus des taux de confirmation et de retournement.

Les résultats utilisent les mêmes fenêtres roulantes de douze mois que le
détecteur. La fenêtre à +6 mois chevauche donc la fenêtre de détection sur six
mois : elle mesure une persistance précoce, mais n'est pas indépendante. La
fenêtre à +12 mois ne la chevauche pas. Le nombre de mois communs est sérialisé
dans chaque résultat et rappelé dans la synthèse.

## Invariants anti-fuite

1. Le signal source reste inchangé et conserve son `information_cutoff` TM-07.
2. Le cutoff cible est strictement postérieur au cutoff du signal.
3. La fenêtre cible provient des séries TM-03 du même run, scope et topic.
4. Les valeurs courantes du signal concordent avec sa fenêtre TM-03 au cutoff.
5. La classification future, lorsqu'elle est jointe, provient du cutoff cible.
6. `retrospective_reconstruction` reste visible dans toute sortie et ne devient
   jamais un historique prétendument observé.

## Sorties

- résultats à +6/+12 pour chaque événement-signal ;
- épisodes et résultats depuis leur onset et leur première escalade headline ;
- index compact des épisodes ;
- synthèse de calibration globale et stratifiée ;
- rapport qualité et résultat d'étape.

Toutes les sorties TM-08 sont JSON ou JSONL compressé. Aucun appel OpenAlex ni
aucune production Markdown ne sont effectués.

## Extension de calibration TM-08.1

TM-08.1 ne modifie ni les résultats événementiels 0.1 ni leur seuil de
rétention. La synthèse, étendue en `topic-momentum-calibration/0.3` par
TM-08.2, expose trois lectures :

| Métrique | Interprétation |
|---|---|
| `strict_retention_rate` | `STRENGTHENED` ou `RETAINED` sur les deux axes |
| `directional_survival_rate` | volume et part restent du côté détecté, `FADED` inclus |
| `non_reversal_rate` | absence de retournement complet, `MIXED` inclus |

La priorité reste une mesure de saillance actuelle et de force probatoire. Elle
n'est jamais interprétée comme une probabilité de persistance future.

La version `topic-momentum-episode/0.2` qualifie la maturité :

- `ISOLATED` : un seul signal, puis clôture ;
- `PERSISTENT` : au moins deux cutoffs sans headline ;
- `ESCALATED` : l'épisode atteint `HEADLINE_CANDIDATE` ;
- `OPEN_ONSET` : un premier signal au dernier cutoff, encore impossible à
  qualifier d'isolé.

Une cohorte récente réservée regroupe les quatre derniers cutoffs trimestriels
d'onset observables à +12 mois. Elle est publiée séparément de la référence
historique et ne doit pas servir à ajuster puis évaluer les mêmes seuils.

Enfin, un échantillon déterministe vise six épisodes `RISING` pour chacun des
cinq résultats à +12 mois. La sélection effectue un round-robin entre classes
de maturité et tiers initiaux. Elle prépare une revue humaine ; elle ne produit
aucun jugement automatique.

## Contrôle de consolidation TM-08.2

TM-08.2 conserve les outcomes et les seuils du détecteur. Il compare la
calibration des onsets à +12 mois en excluant les cibles trop proches du vintage
OpenAlex selon trois délais simples : 3, 6 et 9 mois. Le profil 6 mois sert par
défaut à constituer l'échantillon qualitatif mature. Ces délais sont des tests
de sensibilité, pas une modélisation publication par publication de
l'indexation OpenAlex.
