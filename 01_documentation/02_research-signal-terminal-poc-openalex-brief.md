# Research Signal Terminal

## Brief produit — POC institutionnel et OpenAlex Users Meeting

| Champ | Valeur |
|---|---|
| Statut | Feuille de route opérationnelle |
| Version | 0.1 |
| Date | 28 août 2026 |
| Horizon | 28 août–22 octobre 2026 |
| Univers du POC | Mines Paris–PSL — ROR `04y8cs423` |
| Échéance proposition | 14 septembre 2026 |
| Meeting | Paris, 20–22 octobre 2026 |
| Document directeur | `research-intelligence-platform-product-reference.md` |

---

## 1. Décision produit

Le premier POC démontrera une seule tranche verticale :

> Surveiller la trajectoire scientifique d'une institution, détecter un changement inhabituel, l'afficher comme signal et permettre d'en vérifier immédiatement les preuves.

Il ne cherchera pas à représenter toute la future plateforme. Le document directeur conserve le périmètre global et l'ordre des extensions ultérieures.

### Pourquoi commencer par le mode institution

- le pilote Mines Paris–PSL existe déjà ;
- le corpus, les figures et les résultats méthodologiques sont disponibles ;
- le filtre institutionnel et les topics OpenAlex rendent le périmètre auditable ;
- le positionnement par rapport au monde est déjà expérimenté ;
- le meeting OpenAlex fournit un public directement pertinent ;
- ce mode permet de tester le contrat générique d'un signal avant le mode topic.

---

## 2. Utilisateur principal et décision assistée

### Persona du POC

Professionnel de l'information scientifique, bibliothécaire chargé de la bibliométrie, cellule de stratégie ou direction de la recherche devant préparer une veille ou une lecture de la trajectoire d'une institution.

### Job-to-be-done

> Quand je surveille la production scientifique de mon institution, je veux savoir quels changements méritent réellement mon attention, comprendre pourquoi ils sont inhabituels et vérifier les documents concernés, afin de préparer une analyse stratégique traçable sans inspecter manuellement des centaines de publications.

### Résultat recherché

L'utilisateur doit pouvoir, en moins de 30 secondes :

1. identifier le changement ;
2. comprendre son caractère inhabituel ;
3. estimer la confiance ;
4. accéder aux œuvres et acteurs qui le fondent.

---

## 3. Hypothèses à tester

| ID | Hypothèse | Validation attendue |
|---|---|---|
| H1 | Les trajectoires de topics produisent un headline suffisamment robuste | Résultat stable aux fenêtres et seuils raisonnables |
| H2 | Un signal contextualisé apporte plus de valeur qu'un indicateur bibliométrique isolé | Utilisateurs capables d'expliquer pourquoi il mérite l'attention |
| H3 | Le dossier de preuves crée la confiance | Les utilisateurs vérifient documents, calcul et limites sans aide |
| H4 | Une baseline explicite réduit les faux signaux | Backtest et analyse des faux positifs |
| H5 | Le résumé LLM n'est utile qu'après constitution du signal | Le signal reste compréhensible sans résumé génératif |
| H6 | Le contrat `Signal` peut accueillir plusieurs détecteurs | Trois détecteurs ou sorties compatibles sans schémas ad hoc |

---

## 4. Périmètre obligatoire du POC

### 4.1 Acquisition et périmètre

- univers institutionnel Mines Paris–PSL ;
- collecte OpenAlex initiale ;
- historique 2020–2026-H1, complété si nécessaire par la fenêtre disponible la plus récente ;
- requêtes, paramètres et date de collecte conservés ;
- périmètre mondial par exact `primary_topic.id` pour le positionnement ;
- métriques de couverture et fraîcheur affichées.

### 4.2 Observation store minimal

Chaque observation doit conserver :

- OpenAlex Work ID et DOI si disponible ;
- date de publication ;
- topic principal ;
- auteurs et institutions nécessaires aux détecteurs ;
- citations ou relations utilisées ;
- première date de détection et date du sweep ;
- provenance et empreinte/version de collecte.

Le stockage doit être rejouable. Le choix DuckDB/Parquet ou SQLite est pris par un spike de deux heures maximum, selon le mode de requête et de mise à jour le plus simple.

### 4.3 Trois sorties de détecteurs

#### Détecteur 1 — Topic momentum — obligatoire

Produit :

- matrice de volumes par fenêtre ;
- trajectoire `RISING/FALLING/STABLE/NEW/INTERMITTENT` ;
- pente et accélération ;
- delta récent ;
- taille d'échantillon ;
- confiance et avertissements.

Ce détecteur réutilise et consolide le Tier 1 du claim-delta-radar.

#### Détecteur 2 — Positionnement institution vs monde — obligatoire

Produit :

- retard/avance médiane ;
- part institutionnelle du topic mondial ;
- évolution de cette part ;
- éléments de flux citationnel lorsqu'ils sont robustes ;
- verdict prudent et confiance ;
- indicateur d'échantillonnage.

Ce détecteur réutilise le Tier 3 existant. Il ne doit pas produire de verdict `LEADING` ou `FOLLOWING` sans afficher les mesures sous-jacentes.

#### Détecteur 3 — Accélération citationnelle ou collaboration inhabituelle — stretch

Le choix final dépendra du spike de données :

- choisir l'accélération citationnelle si une cohorte normalisée par âge et champ peut être calculée proprement ;
- choisir la collaboration inhabituelle si les données d'affiliation et le graphe historique sont plus immédiatement exploitables.

La valeur méthodologique prime sur la variété visuelle. Si aucun des deux n'est assez robuste, le POC reste à deux détecteurs et approfondit le backtest.

### 4.4 Contrat commun d'un signal

Champs minimaux :

```yaml
id: stable-id
universe_id: mines-paris-psl
universe_version: 1
detector_id: topic-momentum
detector_version: 0.1
detected_at: 2026-09-30
effective_window: 2026-H1
signal_type: topic_acceleration
title: factual-title
entities: []
observation:
  value: null
  expected: null
  delta: null
  anomaly: null
dynamics:
  direction: rising
  velocity: null
  acceleration: null
confidence:
  level: high
  reasons: []
  limitations: []
evidence: []
provenance: {}
```

### 4.5 Dossier de preuves

Chaque signal montré doit posséder :

- un titre factuel ;
- une phrase « pourquoi c'est inhabituel » ;
- observé versus attendu ;
- historique ou chronologie ;
- documents et acteurs principaux ;
- qualité, couverture et fraîcheur ;
- confiance et limites ;
- identifiant et version du détecteur ;
- liens OpenAlex/DOI.

### 4.6 Interface minimale

#### Écran 1 — Situation Room

- liste de 5 à 10 signaux maximum ;
- statut, date, type, confiance ;
- une mesure principale et sa référence ;
- sélection d'un signal.

#### Écran 2 — Signal Dossier

- pourquoi le signal existe ;
- observé versus baseline ;
- trajectoire ou chronologie ;
- documents et acteurs ;
- preuves, limites et provenance.

#### Écran 3 — Contexte

Une seule vue adaptée au signal : trajectoire thématique ou positionnement mondial. Elle peut être intégrée au dossier si un troisième écran n'apporte rien.

---

## 5. Périmètre stretch

À développer uniquement si les critères obligatoires sont atteints :

- troisième détecteur ;
- enrichissement OpenCitations ;
- résumé grounded d'un signal ;
- drill-down de claims dans un topic déjà signalé ;
- mini brief hebdomadaire Markdown ;
- graphe citationnel simplifié ;
- bouton `watch` ou `dismiss` ;
- second univers préconfiguré de type topic ;
- test utilisateur avec trois à cinq personnes.

Chaque stretch doit pouvoir être abandonné sans fragiliser la démonstration.

---

## 6. Hors POC, mais conservé dans la roadmap

Ne pas implémenter avant le meeting :

- constructeur visuel d'univers ;
- multi-utilisateur et authentification ;
- workspaces persistants multiples ;
- portfolio ;
- alertes e-mail/Slack ;
- brevets, financements et essais cliniques ;
- HAL, DataCite et preprints comme sources actives ;
- migration méthode–domaine ;
- contribution frames à grande échelle ;
- terminal de panneaux composables ;
- scores stratégiques personnalisés ;
- prédictions de développements futurs ;
- offre commerciale intégrée et facturation.

Ces éléments ne sont pas abandonnés. Leur ordre est défini dans le Product Reference.

---

## 7. Backtest et protocole d'évaluation

### 7.1 Backtest principal

1. choisir une date de coupure historique ;
2. n'utiliser que les données qui auraient été disponibles à cette date, autant que le permettent les snapshots ;
3. produire les signaux sans regarder la période suivante ;
4. observer l'évolution ultérieure ;
5. classer les résultats : utile, plausible mais faible, faux positif, artefact de données ;
6. documenter les échecs aussi précisément que les réussites.

### 7.2 Tests de sensibilité

Pour le topic momentum :

- plusieurs seuils de taille minimale ;
- fenêtres annuelles versus semestrielles ;
- pente avec et sans fenêtre 2026-H1 ;
- volumes bruts versus parts relatives ;
- stabilité du top des signaux.

### 7.3 Critères d'acceptation

Le POC est prêt pour démonstration si :

- une commande reconstruit les données et signaux ;
- au moins trois signaux possèdent un dossier de preuves complet ;
- au moins un cas de faux positif ou de signal faible est expliqué ;
- chaque graphique correspond aux valeurs du signal JSON ;
- la confiance diminue effectivement sur les petits échantillons ;
- la source et les limites sont visibles ;
- le parcours feed → dossier fonctionne sans explication orale ;
- une version de secours de la démonstration fonctionne hors réseau.

---

## 8. Angle du talk OpenAlex

### Titre recommandé

**Baseline, Delta, Signal: Building an Explainable Research Radar with OpenAlex**

### Promesse

Montrer comment OpenAlex peut servir non seulement à décrire un paysage scientifique, mais à détecter des changements institutionnels, tout en expliquant pourquoi une approche plus complexe fondée sur l'extraction massive de claims n'améliore pas nécessairement le headline.

### Fil narratif en dix minutes

| Temps | Contenu |
|---:|---|
| 0:00–0:50 | Problème : les dashboards décrivent un état, pas un changement |
| 0:50–1:40 | Baseline → sweep → delta → signal → drill-down |
| 1:40–3:10 | Pilote Mines et Tier 1 par topics OpenAlex |
| 3:10–4:20 | Trajectoires et positionnement mondial |
| 4:20–5:50 | Expérience claims : coût, boilerplate et limites |
| 5:50–6:40 | Résultat central : counts vs claims, Spearman 0,99/0,93 |
| 6:40–8:20 | Démonstration signal → dossier de preuves |
| 8:20–9:15 | Rough edges : fenêtres, petits échantillons, couverture, claims |
| 9:15–10:00 | Vers un Research Signal Terminal et questions à OpenAlex |

### Ce que le talk doit montrer

- une figure de trajectoire ;
- une figure ou carte de positionnement ;
- le résultat comparatif counts/claims ;
- un exemple de boilerplate ou de cluster cross-cutting ambigu ;
- un signal dans la mini situation room ;
- le dossier de preuves associé ;
- une slide de limites ;
- une seule slide de vision future.

### Ce que le talk ne doit pas prétendre

- que le POC prédit la prochaine rupture scientifique ;
- que les topics OpenAlex suffisent à toute analyse sémantique ;
- que les claims extraits sont des vérités scientifiques ;
- que Mines Paris–PSL valide la méthode pour toutes les institutions ;
- que « real-time » signifie instantané ;
- que la plateforme complète existe déjà.

### Questions utiles à adresser à la communauté OpenAlex

- comment distinguer au mieux nouveaux enregistrements et modifications tardives ?
- quel historique des changements est disponible ou souhaitable ?
- comment suivre l'évolution de la taxonomie et des affectations de topics ?
- quelles pratiques sont recommandées pour les analyses longitudinales après les évolutions de données ?
- quelles briques manquent aux utilisateurs construisant des systèmes de veille continue ?

---

## 9. Plan de travail et portes de sortie

### Séquence 1 — Cadrage et soumission — 28 août au 14 septembre

Livrables :

- Product Reference ;
- présent brief ;
- abstract de 250 mots ;
- contrat final du signal ;
- choix du troisième détecteur ou décision de le différer ;
- inventaire du code existant réutilisable.

**Gate A :** l'abstract peut être soumis sur la base des résultats déjà acquis, sans dépendre du futur POC.

### Séquence 2 — Instrument et backtest — 15 au 27 septembre

Livrables :

- observation store ;
- pipeline reproductible ;
- topic momentum et positionnement convertis au contrat `Signal` ;
- backtest ;
- trois dossiers de preuves Markdown ;
- analyse de sensibilité et faux positifs.

**Gate B :** aucun travail UI substantiel tant qu'au moins trois dossiers ne sont pas convaincants en Markdown.

### Séquence 3 — Tranche verticale — 28 septembre au 7 octobre

Livrables :

- feed de signaux ;
- dossier de signal ;
- visualisation contextuelle ;
- provenance et limites ;
- données de démonstration figées.

**Gate C :** l'interface doit expliquer le signal sans résumé génératif.

### Séquence 4 — Validation et simplification — 8 au 15 octobre

Livrables :

- tests de compréhension ;
- correction des ambiguïtés ;
- suppression des éléments décoratifs ;
- capture ou vidéo de secours ;
- figures finales.

**Gate D :** toute fonctionnalité instable ou non nécessaire au récit est retirée de la démo.

### Séquence 5 — Talk — 16 au 22 octobre

Livrables :

- slides ;
- script ;
- répétitions chronométrées ;
- démonstration inférieure à deux minutes ;
- liste de questions et retours à collecter.

---

## 10. Backlog priorisé du POC

### P0 — indispensable

- [ ] figer le schéma `Signal` ;
- [ ] inventorier les modules existants du claim-delta-radar ;
- [ ] choisir le stockage local ;
- [ ] construire le journal d'observations ;
- [ ] adapter topic momentum au schéma `Signal` ;
- [ ] adapter le positionnement au schéma `Signal` ;
- [ ] constituer trois dossiers de preuves ;
- [ ] effectuer le backtest ;
- [ ] analyser seuils et faux positifs ;
- [ ] construire le feed ;
- [ ] construire le signal dossier ;
- [ ] figer les données de démonstration ;
- [ ] produire une démonstration hors réseau.

### P1 — utile si P0 stable

- [ ] choisir et tester le troisième détecteur ;
- [ ] produire un résumé grounded ;
- [ ] ajouter OpenCitations ;
- [ ] intégrer un drill-down claims ciblé ;
- [ ] générer un brief hebdomadaire ;
- [ ] mener trois à cinq tests utilisateurs.

### P2 — après octobre

- [ ] persister plusieurs sweeps réels ;
- [ ] ajouter cycle de vie et feedback ;
- [ ] améliorer les baselines ;
- [ ] développer les contribution frames ;
- [ ] ouvrir le mode topic ;
- [ ] connecter d'autres sources.

---

## 11. Risques immédiats et parades

| Risque | Signal d'alerte | Parade |
|---|---|---|
| Trop de temps sur la documentation | Aucun résultat exécutable mi-septembre | Aucun nouveau document avant les signal contracts nécessaires |
| Reconstruction excessive du radar | Réécriture du pipeline sans besoin démontré | Adapter les sorties existantes au contrat commun |
| Troisième détecteur fragile | Baseline improvisée | Le différer et renforcer le backtest |
| UI trop ambitieuse | Multiplication des écrans/contrôles | Limite feed + dossier + contexte |
| Démo dépendante du réseau | API lente ou quota | Données figées et vidéo/captures |
| Signal narratif mais non mesurable | Explication sans observé/attendu | Rejeter le signal du POC |
| Claims reprennent trop de place | Clustering corpus-wide relancé | Claims uniquement dans le récit méthodologique ou le drill-down ciblé |
| Demi-année 2026 trompeuse | Trop de NEW/DISAPPEARING | Trajectoire multi-fenêtres et avertissement visible |
| Talk surchargé | Plus de trois idées centrales | Un problème, un résultat, une leçon, une démo |

---

## 12. Définition de « terminé »

### POC terminé

- le pipeline est rejouable ;
- les résultats sont sérialisés dans un format versionné ;
- les signaux possèdent preuves et limites ;
- le backtest est documenté ;
- l'interface montre le parcours complet ;
- le fonctionnement ne dépend pas d'un LLM ;
- les fonctions différées restent répertoriées dans le Product Reference.

### Talk terminé

- l'abstract est accepté ou, à défaut, le support reste réutilisable ;
- le script tient en moins de dix minutes ;
- les résultats déjà établis sont clairement distingués des travaux en cours ;
- la démonstration possède un mode de secours ;
- les limites occupent une place explicite ;
- la vision future tient sur une seule slide.

---

## 13. Prochaine action immédiate

Rédiger et soumettre l'abstract OpenAlex à partir du récit déjà démontré :

1. OpenAlex topics comme headline robuste ;
2. claims utiles au drill-down mais faibles comme unité de comptage ;
3. positionnement prudent institution–monde ;
4. évolution vers un système explicable de signaux.

La soumission ne doit pas attendre la fin du POC.

