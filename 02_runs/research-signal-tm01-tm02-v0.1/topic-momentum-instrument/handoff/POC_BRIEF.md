# Research Signal — brief du POC d'interface

## 1. Résultat attendu

Produire une « situation room » académique locale, démontrable en dix minutes,
pour le portefeuille institutionnel Mines Paris–PSL en scope `lineage`.

La démonstration doit rendre tangible la chaîne :

> baseline → sweep → delta → signal → drill-down → validation rétrospective

Le produit ne cherche pas à remplacer un moteur de recherche bibliographique.
Il montre comment une institution peut repérer, classer et expliquer des
changements inhabituels dans son écosystème de recherche.

## 2. Question à laquelle le POC doit répondre

> À partir d'un portefeuille OpenAlex versionné, peut-on détecter,
> hiérarchiser et expliquer des changements académiques qui auraient mérité une
> attention plus tôt ?

Le POC doit montrer trois familles complémentaires de signal :

| Détecteur | Sujet | Question opérationnelle |
|---|---|---|
| Topic Momentum | topic OpenAlex | Quels thèmes montent, reculent ou changent de rythme ? |
| Citation Acceleration | œuvre | Quels travaux reçoivent des citations anormalement vite par rapport à une cohorte comparable ? |
| Actor/Collaboration Novelty | institution ou arête | Quels partenaires ou liens institutionnels apparaissent ou reviennent dans le portefeuille ? |

## 3. Public et scénario de démonstration

Public principal du POC : direction de la recherche, bibliothèque, cellule de
veille, responsable de laboratoire ou financeur.

Scénario nominal :

1. ouvrir une synthèse du portefeuille au cutoff courant ;
2. voir immédiatement les trois types de changements détectés ;
3. filtrer le flux de signaux par détecteur, tier et confiance ;
4. ouvrir un signal ;
5. comprendre pourquoi il est inhabituel ;
6. consulter ses métriques, son contexte temporel et ses preuves ;
7. revenir à la synthèse sans perdre les filtres ;
8. lire le résultat minimal du backtest pour juger la valeur du détecteur.

## 4. Périmètre fonctionnel

### 4.1 Vue « Situation »

Une page principale comprenant :

- nom du portefeuille et scope ;
- cutoff d'information, vintage et mode temporel ;
- trois cartes détecteur avec nombre de signaux, nombre de headlines et une
  phrase expliquant ce que le détecteur observe ;
- un court bandeau « validation rétrospective » présentant seulement les
  chiffres disponibles dans les résumés de backtest ;
- un flux unifié des signaux courants, trié par priorité décroissante ;
- filtres : détecteur, tier éditorial, confiance et recherche textuelle ;
- distinction visuelle claire entre `HEADLINE_CANDIDATE`, `WATCH` et
  `EXPLORATION`.

Le flux unifié ne crée pas de score inter-détecteurs. Il juxtapose les scores
de priorité déjà calculés et rappelle qu'ils sont propres à chaque détecteur.

### 4.2 Fiche de signal

Un panneau latéral ou une vue détail affiche :

- headline et sujet ;
- détecteur et label ;
- « pourquoi c'est inhabituel » ;
- priorité, confiance et limitations ;
- fenêtre courante et référence/baseline ;
- métriques spécifiques au détecteur ;
- éléments de preuve représentatifs avec IDs et dates ;
- scope, cutoff, vintage, version du détecteur et version du code ;
- avertissements de qualité ;
- lien interne vers le bundle de preuve complet lorsqu'il est présent dans le
  bundle préparé.

La fiche ne génère aucune interprétation nouvelle. Elle reformate les champs
des enveloppes et preuves existantes.

### 4.3 Vue « Validation » minimale

Une section ou un onglet, sans outil de calibration, affiche :

- Topic Momentum : résumé de calibration/backtest déjà calculé ;
- Citation Acceleration : `SUSTAINED`, `FADED`, `RIGHT_CENSORED` ;
- Actor/Collaboration Novelty : `CONTINUED`, `ONE_OFF`, `RIGHT_CENSORED` ;
- nombre de cutoffs et limites temporelles ;
- avertissement constant sur la reconstruction rétrospective.

Pour ACN, formuler correctement : « 814 occurrences de signal concernant 673
sujets distincts », et non « 814 découvertes ». Pour les 514 issues observées,
le taux de continuation fourni est 38,9 % ; ne pas le présenter comme une
mesure d'importance scientifique.

## 5. Hors périmètre

- recherche globale dans OpenAlex ;
- choix d'une autre institution ou d'un topic à surveiller ;
- ingestion ou rafraîchissement en temps réel ;
- modification des seuils et recalcul des détecteurs ;
- fusion ou score global des trois détecteurs ;
- recommandations générées par LLM ;
- prédictions ;
- gestion de comptes, droits ou favoris ;
- export PDF, alertes, emails ou notifications ;
- carte géographique et graphes réseau interactifs ;
- interface mobile complète ;
- déploiement de production.

Ces éléments appartiennent au produit futur, pas à ce POC ni à la proposition
de talk de dix minutes.

## 6. Direction visuelle

Le POC doit évoquer une console de veille stratégique, sans imiter la surcharge
d'un terminal financier :

- fond bleu nuit ou ardoise ;
- surfaces sobres et contrastées ;
- vert pour les mouvements positifs/continués ;
- ambre pour les éléments à surveiller ou à revoir ;
- rouge réservé aux reculs et avertissements réels ;
- typographie compacte mais lisible ;
- chiffres alignés et hiérarchie nette ;
- densité adaptée à un écran d'ordinateur portable ;
- animations très discrètes, uniquement pour les transitions utiles.

Éviter les gradients décoratifs, les cartes surdimensionnées, le jargon de
startup et les visualisations sans information.

## 7. Architecture attendue

```text
run OpenAlex existant
        │
        ▼
scripts/build_poc_bundle.py
        │
        ▼
ui/public/data/research-signal-poc.json
        │
        ▼
React + TypeScript + Vite
```

Le script Python :

- reçoit `--run-root`, `--scope` et éventuellement `--output` ;
- lit les fichiers JSON et JSONL gzip existants ;
- vérifie les versions de schéma minimales attendues ;
- joint les signaux à leurs preuves par ID ;
- produit un seul bundle déterministe, compact et documenté ;
- n'altère jamais le run source ;
- échoue avec un message précis si un artefact indispensable manque ;
- signale les artefacts de backtest optionnels absents sans empêcher l'accès
  aux signaux courants.

Commande cible :

```bash
uv run python scripts/build_poc_bundle.py \
  --run-root runs/tm-2026-06-30-mines-v1 \
  --scope lineage \
  --output ui/public/data/research-signal-poc.json
```

Le front doit ensuite pouvoir fonctionner hors ligne :

```bash
cd ui
npm install
npm run dev
```

## 8. Artefacts sources

Le chemin de base est `<run-root>/<scope>/`.

### Obligatoires pour les signaux courants

```text
query-manifest.json
signals/topic-momentum-signals.jsonl.gz
evidence/topic-momentum-evidence.jsonl.gz
signals/citation-acceleration-signals.jsonl.gz
evidence/citation-acceleration-evidence.jsonl.gz
signals/actor-collaboration-novelty-signals.jsonl.gz
evidence/actor-collaboration-novelty-evidence.jsonl.gz
```

Les index JSON peuvent être utilisés pour accélérer ou vérifier l'ordre, mais
les enveloppes de signal restent la source canonique.

### Optionnels pour la vue Validation

```text
backtest/outcomes/topic-momentum-calibration-summary.json
backtest/citation-acceleration-backtest-summary.json
backtest/actor-collaboration-novelty-backtest-summary.json
backtest/actor-collaboration-novelty-cutoff-summaries.json
```

Le chemin Topic Momentum peut différer selon la version du run. L'adaptateur
doit résoudre en priorité les chemins déclarés dans `tm08-result.json`, puis
utiliser les chemins documentés comme repli. Il doit appliquer la même logique
aux résultats CA-04 et ACN-04 lorsque leurs fichiers `*-result.json` sont
présents.

### Artefacts utiles au contrôle

```text
tm06-result.json
tm08-result.json
ca03-result.json
ca04-result.json
acn03-result.json
acn04-result.json
quality/*-quality-report.json
```

## 9. Contrat du bundle d'interface

Le schéma peut être précisé lors de l'implémentation, mais doit au minimum
fournir :

```json
{
  "schema_version": "research-signal-poc/0.1",
  "generated_at": "...",
  "source": {
    "run_id": "...",
    "scope_mode": "lineage",
    "information_cutoff": "2026-06-30",
    "observation_vintage": "...",
    "temporal_mode": "retrospective_reconstruction"
  },
  "detectors": [],
  "signals": [],
  "evidence_by_id": {},
  "backtests": {},
  "warnings": []
}
```

Chaque signal normalisé pour l'UI conserve obligatoirement :

- `signal_id` source ;
- type et version du détecteur ;
- sujet et label source ;
- priorité et confiance sans recalcul ;
- tier éditorial lorsqu'il existe ;
- contexte temporel ;
- résumé et métriques du payload ;
- `evidence_bundle_id` ;
- quality flags et provenance.

Les champs spécifiques restent dans un sous-objet `metrics` ou `payload`. Ne
pas forcer artificiellement les trois détecteurs dans un modèle métrique unique.

## 10. Critères d'acceptation

### Données

- Les nombres de signaux par détecteur sont identiques aux fichiers résultat.
- Chaque signal affiché conserve son `signal_id` et son cutoff exacts.
- Chaque preuve affichée est reliée par un ID existant.
- Aucun score, label, confidence ou outcome n'est recalculé dans le front.
- Le script produit deux fois exactement le même contenu pour les mêmes
  entrées, à l'exception éventuelle de `generated_at` si ce champ est activé.
- Les données futures de backtest ne figurent jamais dans la fiche d'un signal
  courant comme si elles étaient connues au moment de la détection.

### Interface

- La page principale présente les trois détecteurs sans scroll horizontal à
  1440 px.
- Les filtres fonctionnent conjointement et peuvent être réinitialisés.
- L'ouverture et la fermeture d'une fiche ne perdent pas les filtres.
- Les trois types de signal ont une fiche lisible malgré leurs métriques
  différentes.
- Les états chargement, erreur, absence de résultat et backtest indisponible
  sont traités.
- Les limitations et le mode rétrospectif restent visibles.
- Aucun lien, bouton ou contrôle factice n'est présenté comme fonctionnel.

### Qualité technique

- tests Python ciblés pour l'adaptateur ;
- tests front ciblés sur filtres et fiche de signal ;
- `npm run build` réussi ;
- aucune erreur ou warning applicatif dans la console au parcours nominal ;
- README du POC limité aux commandes d'installation, préparation des données,
  lancement et build.

## 11. Déroulé conseillé

1. Inventorier les champs réellement présents dans un échantillon de chaque
   signal et preuve.
2. Implémenter et tester le bundle statique.
3. Construire la vue Situation avec données réelles.
4. Ajouter la fiche de signal pour les trois détecteurs.
5. Ajouter la vue Validation depuis les résumés existants.
6. Soigner les états dégradés et la lisibilité.
7. Exécuter tests et build, puis documenter les commandes.

Ne pas créer une maquette alimentée par des données fictives si les artefacts
réels sont disponibles.

## 12. Prompt de démarrage pour Codex

```text
Lis AGENTS.md puis handoff/POC_BRIEF.md intégralement. Inspecte ensuite le dépôt,
les contrats et un petit échantillon des artefacts du run lineage disponible.

Implémente le POC d'interface décrit dans le brief en respectant strictement son
périmètre. Commence par scripts/build_poc_bundle.py et ses tests, puis construis
l'application React/TypeScript/Vite dans ui/. Utilise les sorties réelles des
trois détecteurs ; ne modifie ni leur code, ni leurs contrats, ni leurs seuils,
et ne recalcule aucun signal dans l'interface.

Travaille jusqu'à satisfaire la définition de terminé et les critères
d'acceptation. Vérifie les tests Python, les tests front et npm run build. À la
fin, donne-moi les commandes exactes pour préparer le bundle, lancer le POC et
faire le build, ainsi qu'une liste courte des choix et limites restantes.
```

## 13. Retour d’usage et évolution de lisibilité

### 13.1 Remarques recueillies

La première version de l’interface rendait correctement les contrats, mais des
termes de transport et des codes de détecteurs étaient exposés sans explication
suffisante. Les retours portent sur :

- une en-tête difficile à comprendre (`scope`, `cutoff`, `vintage`,
  `retrospective_reconstruction`) ;
- des libellés de cartes, de filtres et de validation opaques (`headlines`,
  `watch`, `exploration`, `observed outcomes`, `continued`, `sustained`,
  `warnings source`) ;
- l’absence d’un filtre par qualification de signal, alors que la direction ou
  le type de changement (`RISING`, `FALLING`, `ACCELERATING`, etc.) est une
  information de lecture essentielle ;
- le souhait ultérieur d’une vue de contexte et de graphiques utiles.

### 13.2 Résolution retenue pour cette itération

La modification reste dans le périmètre de la vue Situation. Elle :

- reformule le contexte temporel en français courant : périmètre institutionnel
  élargi, date d’arrêt des publications, date de collecte des données et
  analyse reconstituée après coup ;
- explique en continu que les résultats à douze mois décrivent le devenir des
  signaux, ne participent pas à leur classement et ne mesurent pas une
  probabilité ;
- remplace les codes éditoriaux par « À examiner en priorité », « À surveiller »
  et « À explorer », tout en conservant les valeurs contractuelles dans le
  bundle ;
- reformule les métriques de validation avec leur horizon et leur sens métier ;
- ajoute un filtre « Qualification du signal » dont les options dépendent du
  détecteur sélectionné et filtrent les valeurs source sans les recalculer ;
- affiche la qualification sous une forme lisible et conserve le code source
  entre parenthèses pour la traçabilité.

La vue de contexte (trajectoire ou réseau) et les graphiques sont consignés
comme pistes de la prochaine tranche. Ils ne sont pas ajoutés ici : ils étaient
explicitement hors périmètre du POC initial et demandent de définir les séries
ou structures de réseau à exposer sans interprétation supplémentaire.

### 13.3 Point de restauration avant l’évolution

Un instantané du code et de la configuration de l’interface, antérieur à cette
évolution, est conservé dans
`handoff/backups/poc-ui-before-clarity-pass.zip`.

SHA-256 :
`245B0C4BCE66363B4929A0AC1C0B949FC0C2009EA6DD1AE0A2549BCE23294B42`

Pour revenir à cet état, depuis la racine du dépôt :

```powershell
Expand-Archive -LiteralPath handoff/backups/poc-ui-before-clarity-pass.zip -DestinationPath ui -Force
```

L’archive couvre `ui/src/` et les fichiers de configuration du front. Elle ne
contient ni `node_modules/` ni le bundle de données dérivé.
