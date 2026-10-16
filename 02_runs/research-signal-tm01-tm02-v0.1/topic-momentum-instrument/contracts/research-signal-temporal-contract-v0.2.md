# Research Signal — extension temporelle 0.2

| Champ | Valeur |
|---|---|
| Statut | Contrat d'implémentation TM-07 |
| Version | `research-signal-temporal/0.2` |
| Contrat structurel hérité | `research-signal-common/0.1` |
| Enveloppe étendue | `signal-envelope/0.2` |

## Décision

Un replay rétrospectif ne doit pas antidater un snapshot actuel. L'enveloppe 0.2
conserve donc `detected_at` comme date réelle d'émission ou de reconstruction et
ajoute un `temporal_context` distinct.

```json
{
  "detected_at": "2026-08-31T14:00:00Z",
  "temporal_context": {
    "mode": "retrospective_reconstruction",
    "emitted_at": "2026-08-31T14:00:00Z",
    "information_cutoff": "2023-06-30T23:59:59Z",
    "observation_vintage": "2026-08-29T10:45:42Z",
    "cutoff_basis": "publication_date"
  }
}
```

## Sémantique des temps

| Champ | Signification |
|---|---|
| `emitted_at` | Instant réel auquel l'instrument produit le signal |
| `information_cutoff` | Dernière date de publication admise dans le replay |
| `observation_vintage` | Date du snapshot de la source effectivement interrogée |
| `cutoff_basis` | Champ utilisé pour exclure les éléments postérieurs au cutoff |

`detected_at` est un alias structurel de `emitted_at` conservé pour la
compatibilité avec le contrat commun 0.1. Il ne prétend jamais être la date
historique à laquelle le signal aurait réellement été observé.

## Invariants

1. `detected_at == temporal_context.emitted_at`.
2. `provenance.observation_vintage == temporal_context.observation_vintage`.
3. `provenance.backtest_data_mode == temporal_context.mode`.
4. La fenêtre courante se termine à la date de `information_cutoff`.
5. Aucune œuvre utilisée comme preuve ne possède une `publication_date`
   postérieure à `information_cutoff`.
6. En mode `retrospective_reconstruction`, `observed_at` peut être postérieur au
   cutoff, mais ne peut être postérieur à `emitted_at`.
7. En mode `observed_vintage`, aucune preuve ne peut être postérieure au cutoff.
8. Les résultats futurs restent hors du signal et appartiennent à TM-08.

## Portée de TM-07

TM-07 rejoue les assessments TM-05 éligibles à chaque cutoff, recalcule le rang
et le niveau éditorial dans la population disponible au même cutoff, puis émet
des enveloppes 0.2 et leurs preuves. Il ne qualifie pas encore la persistance ou
l'utilité future du signal.

TM-08 reliera ultérieurement ces signaux à des horizons +6 et +12 mois sans
modifier les enveloppes historiques.
