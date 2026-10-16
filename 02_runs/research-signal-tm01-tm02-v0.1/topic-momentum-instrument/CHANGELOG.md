# Changelog

## 0.19.0 — 2026-09-12

- abaisse le support minimal du détecteur pour Mines : `min_current` / `min_previous` repassent de 10 à **5** dans `configs/mines-poc.json` — un topic doit porter au moins 5 œuvres sur la fenêtre de 12 mois pour émettre un signal (46 signaux de thème au lieu de 7, sur 50 candidats à la dernière fenêtre) ;
- UI (situation room) :
  - **internationalisation français / anglais** : toutes les chaînes d'interface passent par un dictionnaire FR/EN (`src/i18n.tsx`, contexte React, sans dépendance) ; sélecteur de langue FR/EN dans l'en-tête ; les libellés de données (noms de topics, titres d'œuvres) restent en langue source OpenAlex ; les nombres et dates suivent la locale choisie ;
  - retire le drapeau « priorité de lecture » (À examiner en priorité / À surveiller / À explorer) : « à surveiller » impliquait une action peu claire. Les cartes détecteur affichent désormais une barre de composition par **niveau de confiance** (élevée / moyenne / faible) ;
  - enrichit l'encart « Comment lire les indicateurs » : définitions et **mode de calcul** du signal saillant (deux fenêtres de 12 mois, ≥ 5 publications, variation ≥ 50 % du volume et ≥ 25 % de la part) et de la priorité, plus confiance et corroboration ;
- bundle régénéré au seuil de 5 (46 thèmes + 236 œuvres + 142 acteurs = 424 signaux ; 200 plus gros thèmes en vue stock) ; le replay rétrospectif (TM-07/08) n'a pas été relancé et reste optionnel (non affiché dans l'UI) ;
- tests front adaptés (suppression du filtre de priorité de lecture, ajout de la bascule de langue).

## 0.18.0 — 2026-09-11

- relève le support minimal du détecteur pour Mines : `min_current` / `min_previous` passent de 3 à 10 dans `configs/mines-poc.json` — un topic doit porter au moins 10 œuvres sur la fenêtre de 12 mois pour émettre un signal (7 candidats au lieu de 121 à la dernière fenêtre) ; le bruit des tout petits topics disparaît du flux ;
- `build_poc_bundle.py` : ajoute une section `top_topics` (vue « stock ») — les plus gros thèmes par volume total sur la période, avec leur direction courante, lus depuis les classifications TM-04 ; relie stock et flux par `topic_id` ;
- UI :
  - en-tête explicite : ventilation « Thèmes en mouvement / Œuvres qui accélèrent / Nouveaux acteurs » au lieu d'un total opaque « Signaux détectés » ;
  - bascule **Flux** (signaux de mouvement) / **Stock** (plus gros thèmes) : la vue stock liste les thèmes par volume, avec barre et pastille de tendance ; un thème doté d'un signal renvoie d'un clic vers son dossier dans le flux ;
- tests Python et front étendus ; suite verte.

## 0.17.0 — 2026-09-11

- `CONTRADICTED` ne masque plus le signal : TM-05 retire le plafonnement de confiance (garde la limitation `SCALE_CONTRADICTED`), TM-06 exige la revue et interdit seulement le rang « À examiner en priorité » (rétrogradé en « À surveiller »). Le signal reste donc visible et filtrable dans le flux ;
- UI (situation room) :
  - retire les trois cartes « Ce que sont devenus les signaux » (validation rétrospective), peu lisibles ;
  - remplace les compteurs de chaque détecteur par une barre de composition (À examiner / À surveiller / À explorer) plus lisible, dans l'esprit d'une console de veille ;
  - ajoute un encart dépliable « Comment lire les indicateurs » (priorité, confiance, priorité de lecture, corroboration) ;
  - rend le filtre « Corroboration » dynamique : options limitées aux valeurs réellement présentes, filtre masqué quand aucun signal ne porte de corroboration (correctif du filtre inopérant) ;
- tests Python et front étendus ; suite verte.

## 0.16.0 — 2026-09-11

- exploite `scale_corroboration` en aval du détecteur :
  - TM-05 : `CONTRADICTED` (topic en mouvement, subfield parent en sens opposé) plafonne la confiance à `LOW` et pose la limitation `SCALE_CONTRADICTED` — le signal sort donc des alertes par défaut ; `CORROBORATED` ajoute la raison `SCALE_CORROBORATED` ; `latest_scale_concordance_counts` au rapport qualité ;
  - TM-06 : `CONTRADICTED` force `review_status = REQUIRED` (`SCALE_CONTRADICTED`) ; la corroboration figure dans le dossier Markdown et le payload du signal ; `scale_concordance_counts` au rapport qualité ;
  - `build_poc_bundle.py` : expose `scale_corroboration` en champ de premier niveau de chaque signal normalisé (hors métriques brutes) ;
  - UI : badge « Confirmé / Isolé / Contredit », filtre « Corroboration » et phrase explicative dans le dossier, en français clair ;
- ajoute `tm05 --rebuild` (mutuellement exclusif de `--resume`) pour régénérer en place la confiance d'un run existant, par cohérence avec TM-03/04/06/07/08 ;
- aucune de ces règles n'introduit de seuil de détection ; suite de tests étendue (Python + front) et verte.

## 0.15.0 — 2026-09-11

- ajoute l'agrégation multi-échelle du détecteur `topic_momentum` (topic + subfield + field) ;
- TM-03 produit `series/subfield-series.jsonl.gz` et `series/field-series.jsonl.gz` en sommant les counts des topics enfants, avec un invariant de conservation de masse (Σ counts identique à tous les niveaux) ;
- TM-04 réutilise le classificateur déterministe à chaque niveau et annote chaque classification topic d'un bloc `scale_corroboration` (CORROBORATED / ISOLATED_WITHIN_PARENT / CONTRADICTED / NEUTRAL) dérivé des directions parentes, sans nouveau seuil ;
- écrit les classifications parentes (`{level}-momentum-classifications.jsonl.gz`) et publie `scale_concordance_counts` au rapport qualité TM-04 ;
- pilotable par `topic_momentum.multi_scale` (défaut vrai) et `topic_momentum.scale_levels` ; `multi_scale=false` reproduit la sortie topic 0.1 ;
- ajoute `tm03 --rebuild` et `tm04 --rebuild` (mutuellement exclusifs de `--resume`) pour régénérer en place les artefacts d'un run existant sans re-collecter TM-02 ;
- les topics sans niveau parent résolu sont regroupés sous une unité sentinelle plutôt que d'interrompre le run ;
- validé sur le run Mines `lineage` (217 subfields, 26 fields, masse conservée) ; suite de tests étendue et intégralement verte.

## 0.14.0 — 2026-09-02

- ajoute ACN-04, replay semestriel entièrement hors ligne du détecteur acteur/collaboration ;
- reconstruit les candidats ACN-02 à chaque cutoff avec les seules œuvres alors publiées ;
- exclut explicitement les cutoffs qui ne disposent pas des 36 mois de baseline requis ;
- évalue une seule issue à +12 mois : `CONTINUED`, `ONE_OFF` ou `RIGHT_CENSORED` ;
- produit signaux et preuves rejoués, résumés par cutoff, outcomes, échantillon de revue et bref rapport Markdown ;
- clôt le troisième détecteur sans calibration ni métrique réseau supplémentaire.

## 0.13.0 — 2026-09-02

- ajoute ACN-03 et émet tous les candidats ACN-02 dans le `SignalEnvelope/0.2` commun ;
- sépare confiance de la preuve, priorité de tri et politique éditoriale ;
- résout chaque signal vers ses œuvres, authorships, événements et historique institutionnel ;
- regroupe les signaux reposant exactement sur les mêmes œuvres sans les supprimer du JSONL ;
- limite le dossier Markdown à deux représentants par groupe de preuves et demande une revue humaine pour les groupes d'au moins trois signaux ;
- produit signaux, index, preuves exhaustives, paramètres, rapport qualité et dossier compact entièrement hors ligne.

## 0.8.0 — 2026-09-01

- ajoute CA-02, étape entièrement hors ligne du détecteur `citation_acceleration` ;
- construit les fenêtres courante et précédente de douze mois au cutoff du corpus ;
- calcule delta, ratio et accélération logarithmique hors self-citations auteur connues, avec mesure de sensibilité incluant celles-ci ;
- exclut les événements postérieurs au cutoff et exige un cutoff de fin de mois ;
- normalise par cohortes type + âge + topic, avec replis subfield puis portefeuille et taille minimale versionnée ;
- publie toutes les abstentions de couverture, de DOI, d'âge, de cohérence des comptes et de support de cohorte ;
- produit assessments, vue éligible, cohortes, paramètres et rapport qualité sans émettre de signal.

## 0.7.1 — 2026-09-01

- ajoute CA-01.1 et la commande `ca01 --rebuild`, strictement hors ligne ;
- reconnaît les dates OpenCitations aux précisions jour, mois et année, y compris les valeurs préfixées ou multi-index ;
- conserve `creation_date`, `creation_month`, `creation_year`, la précision et les valeurs sources sans imputation artificielle ;
- mesure séparément les événements utilisables pour des fenêtres mensuelles, les années seules, les valeurs absentes et les conflits ;
- refuse un rebuild si l'une des réponses OpenCitations brutes attendues n'est pas disponible.

## 0.7.0 — 2026-09-01

- ajoute CA-01, première étape du détecteur `citation_acceleration`, sans logique de scoring ;
- collecte les routes OpenCitations Index v2 `citations` et `citation-count` pour les œuvres TM-02 éligibles ;
- normalise les relations entrantes en `CitationEventObservation` et publie une couverture par œuvre ;
- archive les réponses brutes par DOI, permet une reprise fine après interruption et limite le débit sous le plafond public ;
- configure le token par `OPENCITATIONS_API_KEY`, sans jamais sérialiser sa valeur ;
- ajoute les contrôles DOI, âge minimal, collisions, dates manquantes, doublons d'événements et divergence entre compte et lignes.

## 0.6.2 — 2026-08-31

- ajoute à TM-08 une sensibilité minimale au délai de consolidation OpenAlex à 3, 6 et 9 mois ;
- conserve les outcomes existants et recalcule uniquement la calibration des onsets à +12 mois ;
- adopte 6 mois comme profil de lecture par défaut, sans modifier le détecteur ni ses seuils ;
- réserve l'échantillon qualitatif aux outcomes considérés comme matures sous ce profil.

## 0.6.1 — 2026-08-31

- conserve intacts les outcomes TM-08 et enrichit uniquement leur calibration ;
- distingue rétention stricte, survie directionnelle sur les deux axes et absence de retournement complet ;
- explicite que la priorité mesure la saillance actuelle et non une probabilité de persistance ;
- classe les épisodes en `ISOLATED`, `PERSISTENT`, `ESCALATED` et `OPEN_ONSET` sans considérer prématurément un onset récent comme isolé ;
- publie les résultats à +6/+12 par classe de maturité ;
- réserve comme cohorte temporelle les quatre derniers cutoffs trimestriels évaluables à +12 mois ;
- produit un échantillon déterministe de 30 épisodes `RISING`, équilibré entre les cinq outcomes, pour revue qualitative humaine ;
- versionne la calibration en `topic-momentum-calibration/0.2` et les épisodes en `topic-momentum-episode/0.2`.

## 0.6.0 — 2026-08-31

- ajoute le contrat de backtest `topic-momentum-backtest/0.1` et la politique de résultat `topic-momentum-outcome/0.1` ;
- évalue séparément chaque signal TM-07 à +6 et +12 mois sans modifier les enveloppes historiques ;
- distingue `STRENGTHENED`, `RETAINED`, `FADED`, `REVERSED`, `MIXED` et `RIGHT_CENSORED` à partir du volume et de la part de portefeuille ;
- conserve les ratios continus de rétention et la classification future pour rendre chaque résultat explicable ;
- regroupe les événements trimestriels en épisodes séparés par un gap ou un changement de direction ;
- mesure le devenir depuis l'onset et depuis la première escalade `HEADLINE_CANDIDATE` ;
- rend explicite le chevauchement de six mois de la fenêtre +6 et réserve au +12 la validation sans chevauchement ;
- produit les calibrations globales et stratifiées par direction, tier éditorial et confiance ;
- ajoute `tm08 --resume` et `tm08 --rebuild`, entièrement hors ligne.

## 0.5.0 — 2026-08-31

- ajoute le contrat temporel `research-signal-temporal/0.2` et l'enveloppe `signal-envelope/0.2` ;
- distingue explicitement l'instant réel d'émission, le cutoff d'information simulé et le vintage du snapshot ;
- ajoute TM-07 : replay hors ligne de tous les assessments TM-05 éligibles à leurs cutoffs historiques ;
- recalcule la priorité, le rang et le niveau éditorial dans la population propre à chaque cutoff ;
- produit les signaux, preuves, index et synthèses par cutoff exclusivement en JSON/JSONL compressé ;
- interdit par invariant toute œuvre publiée après le cutoff et signale le snapshot rétrospectif sans le présenter comme un historique observé ;
- réserve l'évaluation des devenirs à +6/+12 mois à TM-08 ;
- ajoute `tm07 --resume` et `tm07 --rebuild`, sans recollecte OpenAlex.

## 0.4.1 — 2026-08-31

- ajoute au bundle TM-06 la couverture complète du rattachement institutionnel pour les deux fenêtres ;
- distingue les œuvres `verified_local` des inclusions `asserted_by_source_filter` et affiche les institutions effectivement appariées ;
- marque les signaux à preuve institutionnelle partielle pour revue humaine sans altérer leur score statistique ;
- répartit les signaux entre `HEADLINE_CANDIDATE`, `WATCH` et `EXPLORATION` avec une politique versionnée ;
- rend explicites les formulations « hausse accélérée » et « recul accéléré » dans les dossiers ;
- ajoute `tm06 --rebuild`, limité à la régénération des artefacts dérivés TM-06 ;
- corrige l'index manquant du dossier consolidé et sérialise les chemins de sortie au format POSIX.

## 0.4.0 — 2026-08-29

- ajoute TM-06 et l'émission du `SignalEnvelope` commun `signal-envelope/0.1` ;
- classe les signaux par une priorité déterministe et décomposable ;
- sélectionne des œuvres représentatives par citation, récence et diversité d'acteurs ;
- produit les bundles de preuves complets, l'index JSON et les dossiers Markdown individuels et consolidés ;
- compare les comptes des deux fenêtres aux `WorkObservation` archivées et rend les écarts visibles ;
- valide les enveloppes Topic Momentum contre le contrat commun des trois futurs détecteurs ;
- conserve TM-06 hors ligne et sans recollecte OpenAlex.

## 0.3.0 — 2026-08-29

- ajoute TM-05 et ses composantes de confiance explicables ;
- applique le guard à toutes les évaluations historiques pour préparer TM-08 ;
- compare chaque candidat sous trois profils versionnés `lenient`, `default` et `strict` ;
- rend `HIGH` exigeant sur support, couverture, persistance et stabilité des paramètres ;
- réserve les alertes par défaut aux niveaux `HIGH` et `MEDIUM` ;
- traite la date de création commune des topics comme projection taxonomique globale dans un snapshot rétrospectif, et non comme invalidation individuelle ;
- produit les assessments complets, la dernière évaluation, la sélection éligible et un rapport qualité.

## 0.2.1 — 2026-08-29

- accepte les `created_date` de topics OpenAlex sous forme de date ou de datetime ISO ;
- transforme les valeurs invalides en erreur contextualisée avec l'identifiant du topic ;
- ajoute une régression reproduisant exactement `2024-01-23T15:27:04`.

## 0.2.0 — 2026-08-29

- ajoute TM-03 : axe mensuel dense, zéros explicites, fenêtres glissantes de douze mois et pas trimestriel ;
- calcule ensemble counts, parts de portefeuille, couverture et mois actifs ;
- ajoute un diagnostic de concentration calendaire des dates de publication ;
- ajoute TM-04 : présence, direction, growth mode, accélération et baseline descriptive ;
- versionne et empreinte tous les paramètres du classificateur ;
- distingue les classifications historiques, la dernière évaluation et les candidats à TM-05 ;
- exécute TM-03/TM-04 hors ligne, à partir des artefacts TM-02 existants ;
- ajoute les tests contractuels `NEW`, `REACTIVATED`, `DORMANT`, `RISING`, `ACCELERATING` et `ABSOLUTE_ONLY`.

## 0.1.2 — 2026-08-29

- conserve les œuvres incluses par le filtre serveur OpenAlex lorsque l'institution n'est pas matérialisée dans les authorships retournées ;
- distingue `verified_local` de `asserted_by_source_filter` dans la preuve d'inclusion ;
- ajoute le flag `INSTITUTION_MATCH_NOT_MATERIALIZED` et son compteur au rapport qualité ;
- étend le contrat commun et son test dummy à ce cas de provenance partielle.

## 0.1.1 — 2026-08-29

- conserve les authorships OpenAlex sans ID auteur avec `author_id: null` et `identity_status: unresolved` ;
- ajoute les flags qualité et les compteurs d'identités non résolues ;
- ajoute `tm02 --resume` pour reprendre un sweep depuis les pages brutes archivées ;
- conserve le vintage du manifeste initial pendant une reprise ;
- refuse une reprise si les dates, types ou corpus diffèrent du manifeste ;
- retire le paramètre OpenAlex `mailto` devenu obsolète ;
- ajoute `.env` au `.gitignore` et documente `uv run --env-file`.

## 0.1.0 — 2026-08-29

- première implémentation de TM-01 et TM-02.
