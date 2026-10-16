# Research Signal Terminal

## Product Reference — vision, architecture et registre fonctionnel

| Champ | Valeur |
|---|---|
| Statut | Document directeur vivant |
| Version | 0.1 |
| Date | 28 août 2026 |
| Nom de travail | Research Signal Terminal (RST) |
| Positionnement court | Terminal explicable de détection des mouvements de la recherche |
| Premier jalon externe | OpenAlex Users Meeting, Paris, 20–22 octobre 2026 |
| Document opérationnel associé | `research-signal-terminal-poc-openalex-brief.md` |

---

## 1. Fonction de ce document

Ce document conserve la vision complète du produit afin que le développement d'un POC volontairement étroit ne fasse pas disparaître des briques importantes. Il sert à :

- stabiliser le vocabulaire et les principes du produit ;
- distinguer les décisions structurantes des choix encore réversibles ;
- maintenir un registre exhaustif des fonctionnalités envisagées ;
- ordonner le développement après le POC et le meeting OpenAlex ;
- éviter que les ajouts opportunistes ne déforment la promesse centrale ;
- servir de référence pour les futures spécifications, offres commerciales et arbitrages techniques.

Il ne doit pas devenir une spécification détaillée de chaque écran ou algorithme. Une fonctionnalité n'est détaillée davantage que lorsqu'elle entre dans la phase active de développement.

### Règle de maintenance

Après chaque décision importante :

1. mettre à jour le registre des fonctionnalités ;
2. ajouter la décision au journal de décisions ;
3. ne détailler que les éléments de la phase en cours ou de la phase suivante ;
4. préserver les éléments différés sans les transformer prématurément en backlog technique.

---

## 2. Résumé exécutif

Research Signal Terminal est une plateforme de veille stratégique appliquée à la recherche académique. Elle permet de définir un écosystème de recherche — institution, topic ou portefeuille —, d'apprendre ce qui y est normal, de détecter les changements inhabituels, de les hiérarchiser et de remonter immédiatement aux preuves.

La chaîne conceptuelle est :

> **Universe → Baseline → Sweep → Observation → Delta → Candidate signal → Confirmed signal → Drill-down → Insight/action**

Le produit n'est pas :

- un moteur supplémentaire de recherche d'articles ;
- un tableau de bord bibliométrique descriptif ;
- un générateur automatique de tendances fondé sur un LLM ;
- un outil de classement universel des institutions ou des chercheurs ;
- une plateforme de prédiction certaine de l'avenir scientifique.

Sa proposition de valeur réside dans un catalogue versionné de détecteurs, de baselines, de règles de confiance et de dossiers de preuves. OpenAlex constitue la base de métadonnées de référence ; OpenCitations peut enrichir et corroborer la structure citationnelle. D'autres sources interviennent ensuite comme connecteurs spécialisés.

---

## 3. Problème et opportunité

### 3.1 Limite des outils existants

La majorité des outils de découverte scientifique et de bibliométrie répondent à des questions statiques :

- quels documents existent ?
- qui publie le plus ?
- quels articles sont les plus cités ?
- comment se répartit la production ?

Ils décrivent principalement un état déjà installé. Ils répondent plus difficilement à :

- qu'est-ce qui vient de changer ?
- ce changement est-il normal ou inhabituel ?
- plusieurs indices indépendants convergent-ils ?
- pourquoi ce signal mérite-t-il une attention maintenant ?
- quelles preuves permettent de le vérifier ?

### 3.2 Opportunité produit

Le produit transpose à la recherche académique la logique des plateformes de situation awareness et d'OSINT : baseline, sweep, delta, signal, drill-down et briefing. L'inspiration Bloomberg/OpenBB porte sur la composition d'instruments et la possibilité d'enquêter, non sur la reproduction de leur interface ou de leur modèle financier.

### 3.3 Promesse

> Détecter et expliquer les mouvements de la recherche avant qu'ils ne deviennent évidents dans les bilans bibliométriques classiques.

---

## 4. Utilisateurs et décisions assistées

### 4.1 Utilisateurs prioritaires

1. **Directions de la recherche et cellules de stratégie scientifique**
   - repérer les domaines en accélération ou en retrait ;
   - comparer une institution à ses pairs et au front mondial ;
   - identifier des collaborations ou compétences émergentes.

2. **Laboratoires et responsables d'axes scientifiques**
   - surveiller un domaine ;
   - identifier des acteurs, méthodes ou croisements nouveaux ;
   - construire une lecture priorisée de la littérature récente.

3. **Bibliothèques, services d'appui à la recherche et professionnels de l'information**
   - produire une veille scientifique traçable ;
   - superviser et expliquer les résultats ;
   - construire des observatoires configurés pour leurs publics.

4. **Financeurs, agences et programmes de recherche**
   - suivre la dynamique d'un portefeuille ;
   - repérer des niches à fort momentum ou insuffisamment soutenues ;
   - observer les effets ultérieurs des financements.

5. **Entreprises et équipes de R&D**
   - surveiller des domaines technologiques et leurs acteurs académiques ;
   - suivre les passages vers logiciels, datasets, brevets ou essais ;
   - détecter des partenaires ou concurrents émergents.

### 4.2 Principe de prudence

Les vues individuelles sur les auteurs servent à comprendre un réseau ou un signal, pas à produire un score universel de valeur des chercheurs. Les profils d'auteurs, affiliations et homonymies doivent toujours afficher leur niveau de qualité et leurs limites.

---

## 5. Concepts fondamentaux

### 5.1 Universe

Périmètre surveillé et versionné. Il contient :

- un type : institution, topic ou portefeuille ;
- des identifiants de départ ;
- des règles d'inclusion et d'exclusion ;
- un intervalle historique ;
- une cadence de sweep ;
- un ou plusieurs groupes de référence ;
- les détecteurs activés ;
- les paramètres stratégiques propres à l'utilisateur.

### 5.2 Baseline

Modèle du comportement attendu. Il n'existe pas une baseline unique : chaque détecteur possède une normalité adaptée à la mesure observée.

Exemples :

- volume attendu d'un topic par trimestre ;
- vitesse de citation attendue selon l'âge et le champ d'un article ;
- densité et centralité habituelles d'un réseau de collaboration ;
- fréquence historique d'une association méthode–domaine ;
- part attendue d'une institution dans un corpus mondial.

### 5.3 Sweep

Collecte récurrente des nouveaux objets et des modifications. Le sweep ne se limite pas aux nouvelles publications : il observe aussi les nouvelles citations, changements d'affiliation, corrections, rétractations et enrichissements tardifs.

### 5.4 Observation

Fait sourcé et horodaté issu d'un connecteur. Une observation conserve :

- la source ;
- l'identifiant source ;
- la date de l'objet ;
- la date d'indexation ou de modification dans la source, si disponible ;
- la date de première détection ;
- la date du dernier sweep ;
- la version ou empreinte des données ;
- les champs bruts nécessaires à l'audit.

### 5.5 Delta

Différence mesurée entre une observation récente et une référence attendue. Un delta est une valeur ; ce n'est pas encore un signal.

### 5.6 Signal candidat

Delta qui satisfait les conditions d'un détecteur. Il possède une magnitude, une vélocité, une anomalie, une confiance et un dossier de preuves minimal.

### 5.7 Signal confirmé

Signal candidat suffisamment robuste pour être présenté ou alerté. La confirmation peut être algorithmique, humaine ou les deux. Elle ne signifie pas que l'interprétation proposée est certaine.

### 5.8 Dossier de preuves

Objet central de confiance comprenant :

- mesure observée et valeur attendue ;
- historique et comparaison ;
- documents, citations et acteurs concernés ;
- explication du déclenchement ;
- qualité et couverture des données ;
- détecteur et version ;
- limites et causes possibles de faux positif.

### 5.9 Insight

Interprétation synthétique d'un ou plusieurs signaux. Un insight doit toujours renvoyer aux signaux et aux preuves qui le fondent.

---

## 6. Les trois niveaux épistémiques

| Niveau | Exemples | Statut |
|---|---|---|
| Faits observés | œuvre, date, citation, affiliation, financement | Source de vérité sourcée |
| Mesures dérivées | pente, accélération, centralité, anomalie | Calcul reproductible et versionné |
| Interprétations | résumé, importance, scénario, recommandation | Jugement explicite, contestable |

### Principe non négociable

Un modèle génératif ne doit jamais être la seule raison pour laquelle un signal existe. Il peut :

- classifier la pertinence d'un document ;
- extraire une contribution structurée ;
- produire une explication à partir d'un dossier de preuves ;
- résumer plusieurs signaux ;
- suggérer des pistes de lecture.

Il ne doit pas inventer une mesure, masquer la provenance ni remplacer les règles de confiance.

---

## 7. Déclinaisons du produit

### 7.1 Mode Institution

Question : où l'institution accélère-t-elle, recule-t-elle, se singularise-t-elle ou rejoint-elle tardivement un mouvement global ?

Vues et signaux principaux :

- trajectoire thématique ;
- positionnement par rapport au monde et aux pairs ;
- nouveaux acteurs internes ;
- collaborations internes et externes inhabituelles ;
- niches de visibilité ;
- domaines en perte de centralité ;
- compétences et méthodes émergentes.

### 7.2 Mode Topic

Question : comment la frontière, les acteurs et les applications d'un domaine se recomposent-ils ?

Vues et signaux principaux :

- sous-topics en échauffement ou en retrait ;
- nouveaux acteurs ;
- méthodes migrantes ;
- articles-ponts entre communautés ;
- convergence de groupes indépendants ;
- passage vers logiciel, dataset, brevet, essai ou politique publique.

### 7.3 Mode Portfolio

Question : que se passe-t-il dans un ensemble d'univers stratégiques et où faut-il porter l'attention ?

Fonctions futures :

- synthèse inter-univers ;
- allocation de l'attention ;
- comparaison de signaux ;
- dépendances entre univers ;
- briefing transversal.

---

## 8. Modèle de données fonctionnel

### 8.1 Entités principales

- `Universe`
- `Artifact` : publication, preprint, dataset, logiciel, brevet, essai, financement ;
- `Person`
- `Organization`
- `Venue`
- `Topic`
- `Funder`
- `ConceptOrMethod`
- `Relation` : citation, collaboration, affiliation, financement, dérivation ;
- `Observation`
- `MetricSnapshot`
- `BaselineModel`
- `Delta`
- `Detector`
- `Signal`
- `EvidenceItem`
- `Insight`
- `WatchlistItem`
- `AnalystFeedback`.

### 8.2 Temporalités à conserver

1. date de l'objet scientifique ;
2. date d'apparition ou de modification dans la source ;
3. date de détection par la plateforme ;
4. date de dernière vérification.

Cette distinction évite de transformer un retard d'indexation en événement scientifique récent.

### 8.3 Identité et provenance

Chaque objet normalisé conserve tous ses identifiants connus : OpenAlex, DOI, ORCID, ROR, PMID, HAL, arXiv, DataCite, identifiants de brevets ou d'essais. Les fusions doivent être réversibles et les conflits visibles.

---

## 9. Sources et stratégie d'enrichissement

### 9.1 Socle

- **OpenAlex** : œuvres, topics, auteurs, institutions, sources, financeurs et première structure de citations ;
- **OpenCitations** : enrichissement, provenance indépendante et contrôle de relations citationnelles.

### 9.2 Connecteurs académiques ultérieurs

- Crossref ;
- DataCite ;
- HAL ;
- arXiv et serveurs de preprints disciplinaires ;
- PubMed/Crossref selon les domaines ;
- theses.fr ;
- ORCID/ROR pour contrôles ciblés.

### 9.3 Objets de translation

- Software Heritage et dépôts de code ;
- dépôts de datasets ;
- financements nationaux et internationaux ;
- brevets ;
- essais cliniques ;
- documents de politique publique.

### 9.4 Contrat des connecteurs

Chaque connecteur émet des objets normalisés et des observations. Les détecteurs ne doivent pas dépendre des particularités de l'API source.

---

## 10. Catalogue des familles de détecteurs

### 10.1 Momentum thématique

- hausse ou baisse de volume ;
- accélération ou décélération ;
- topic nouveau, persistant, intermittent ou disparu ;
- changement relatif par rapport au champ ou au monde.

### 10.2 Accélération citationnelle

- citations anormalement rapides pour l'âge du document ;
- diversité des domaines ou institutions citantes ;
- changement récent de pente ;
- résurgence d'un document ancien.

### 10.3 Acteurs et centralité

- nouvelle institution ou équipe entrant dans un domaine ;
- auteur ou laboratoire devenant central ;
- perte de centralité ;
- concentration ou dispersion géographique.

### 10.4 Collaborations et ponts

- collaboration entre clusters auparavant séparés ;
- article-pont ;
- nouvelle relation interdisciplinaire ;
- internationalisation ou régionalisation rapide.

### 10.5 Diffusion conceptuelle et transfert de méthodes

- apparition d'une méthode dans un nouveau domaine ;
- terme ou approche se diffusant entre communautés ;
- réactivation d'une idée dormante ;
- convergence de vocabulaires auparavant séparés.

### 10.6 Convergence indépendante

- plusieurs groupes sans collaboration directe travaillant soudain sur le même problème ;
- diversification rapide des équipes ;
- corroboration par plusieurs types d'objets.

### 10.7 Translation et commercialisation

- publication suivie d'un logiciel ou dataset ;
- financement précédant une croissance de publications ;
- brevet lié à une découverte ;
- transition vers essai clinique ou usage réglementaire.

### 10.8 Vigilance et intégrité

- correction ou rétractation touchant un cluster actif ;
- anomalie bibliographique ;
- changement important de couverture ou de source ;
- signal reposant excessivement sur un objet unique.

---

## 11. Signal scoring et confiance

### 11.1 Dimensions visibles

- **Magnitude** : taille du changement ;
- **Velocity** : vitesse et accélération ;
- **Anomaly** : rareté par rapport à la baseline ;
- **Convergence** : pluralité des acteurs, documents ou sources ;
- **Strategic relevance** : adéquation aux intérêts du workspace ;
- **Confidence** : solidité statistique et qualité des données.

### 11.2 Principe d'affichage

Un score composite peut ordonner le feed, mais les dimensions restent visibles. Le produit ne doit pas réduire un signal complexe à une note opaque.

### 11.3 Confiance

La confiance dépend au minimum de :

- taille de l'échantillon ;
- couverture et fraîcheur des données ;
- stabilité à plusieurs paramètres raisonnables ;
- nombre de sous-signaux concordants ;
- sensibilité aux retards d'indexation ;
- qualité de résolution des entités ;
- reproductibilité du calcul.

### 11.4 Crédibilité

Le prestige d'une institution ou d'une revue ne constitue pas à lui seul une mesure de crédibilité. Le produit privilégie la fiabilité des preuves, la convergence et la diversité plutôt qu'un score de réputation qui renforcerait mécaniquement les acteurs dominants.

---

## 12. Couche sémantique : topics, motifs et contribution frames

### 12.1 Topics OpenAlex

Ils fournissent une couche stable, économique, auditable et adaptée au headline. Le pilote Mines Paris–PSL a montré que le comptage par topic reproduit presque exactement les trajectoires calculées à partir des claims : Spearman 0,99 pour les trajectoires et 0,93 pour les deltas.

### 12.2 Limites du claim delta

Les claims extraits d'abstracts :

- contiennent beaucoup de boilerplate ;
- reflètent les conventions d'écriture disciplinaires ;
- peuvent confondre hypothèse, méthode et résultat ;
- regroupent parfois des assertions proches mais contradictoires ;
- ne constituent pas une unité bibliométrique stable.

Ils ne doivent donc pas être le capteur principal du produit.

### 12.3 Contribution frames

Structure sémantique recommandée pour le drill-down :

- type de contribution ;
- objet étudié ;
- méthode ;
- contexte, population ou matériau ;
- résultat et direction ;
- statut épistémique ;
- phrase justificative ;
- document source.

### 12.4 Motifs sémantiques

Pour détecter des transferts, le système observe des associations telles que `méthode × objet × domaine`, sans affirmer que tous les textes d'un cluster soutiennent une même proposition.

### 12.5 Rôle du SLM

Un SLM local ou peu coûteux peut :

- classifier la pertinence ;
- extraire les contribution frames ;
- normaliser certains termes ;
- produire un résumé contraint par les preuves ;
- transformer un dossier de signal en briefing.

La détection quantitative reste déterministe ou fondée sur des représentations vérifiables. Le choix du modèle demeure remplaçable.

---

## 13. Cycle de vie d'un signal

États envisagés :

1. `candidate` : seuil initial franchi ;
2. `confirmed` : garde de confiance satisfaite ;
3. `watch` : suivi demandé ;
4. `explained` : dossier enrichi et synthèse produite ;
5. `dismissed` : bruit, faux positif ou non pertinent ;
6. `resolved` : signal stabilisé, absorbé par la baseline ou devenu obsolète ;
7. `reopened` : reprise ou nouvelle accélération.

Le feedback humain alimente la pertinence stratégique et le réglage des alertes ; il ne réécrit jamais rétroactivement la mesure observée.

---

## 14. Expérience produit

### 14.1 Situation Room / Pulse

- feed des signaux ;
- tri par nouveauté, confiance et pertinence ;
- comparaison avec le dernier sweep ;
- statut et actions analyste ;
- indicateurs de fraîcheur et de couverture.

### 14.2 Signal Dossier

- titre factuel ;
- résumé du changement ;
- pourquoi c'est inhabituel ;
- observé versus attendu ;
- chronologie ;
- documents et acteurs clés ;
- graphe pertinent ;
- confiance et limites ;
- détecteur et version ;
- lecture recommandée ;
- annotations et décision de suivi.

### 14.3 Frontier Radar

- noyau stable ;
- bord émergent ;
- domaines en déclin ;
- niches négligées ;
- méthodes migrantes ;
- ponts entre clusters.

### 14.4 Actors & Networks

- nouveaux entrants ;
- institutions et laboratoires centraux ;
- collaborations nouvelles ;
- évolution de centralité ;
- distribution géographique.

### 14.5 Briefing Workspace

- sélection et regroupement de signaux ;
- annotations ;
- brief quotidien, hebdomadaire ou à la demande ;
- export avec preuves ;
- comparaison de périodes ou d'univers.

### 14.6 Terminal modulaire

À terme, l'utilisateur compose un espace de travail à partir d'instruments spécialisés : feed, trajectoire, réseau, carte, chronologie, documents et notes. Ce terminal ne doit pas devenir un tableau de bord surchargé.

---

## 15. Architecture fonctionnelle cible

1. **Connectors** : acquisition et normalisation ;
2. **Observation store** : journal temporel et provenance ;
3. **Entity resolution** : identités et relations ;
4. **Universe service** : définition et version des périmètres ;
5. **Baseline engine** : modèles attendus ;
6. **Detector registry** : détecteurs versionnés ;
7. **Signal engine** : calcul, confiance, déduplication et cycle de vie ;
8. **Evidence service** : constitution des dossiers ;
9. **Semantic enrichment** : frames, motifs, résumés ;
10. **Briefing service** : synthèses et exports ;
11. **Application/API** : situation room et drill-down ;
12. **Scheduler/monitoring** : sweeps, reprises et observabilité.

### Architecture initiale recommandée

Pour le POC :

- scripts Python réutilisant le claim-delta-radar ;
- stockage local structuré, probablement DuckDB/Parquet ou SQLite selon les accès ;
- sorties JSON et Markdown avant l'interface ;
- une application web légère pour la tranche verticale ;
- exécution manuelle ou planifiée simplement ;
- aucune infrastructure multi-tenant.

Le choix définitif de la base, du framework web et de l'orchestrateur doit suivre l'instrument validé, pas le précéder.

---

## 16. Évaluation et qualité

### 16.1 Backtest

Rejouer les détecteurs en se plaçant à une date passée et mesurer ce qu'ils auraient signalé avant que le mouvement soit évident.

### 16.2 Évaluation par détecteur

- précision des signaux candidats ;
- stabilité aux seuils ;
- délai de détection ;
- couverture ;
- faux positifs liés à l'indexation ;
- utilité évaluée par un analyste ;
- coût de calcul et de collecte.

### 16.3 Évaluation du produit

- l'utilisateur comprend-il le signal en moins de 30 secondes ?
- peut-il vérifier la preuve sans quitter le dossier ?
- sait-il pourquoi le signal a été déclenché ?
- peut-il distinguer mesure et interprétation ?
- le volume de signaux reste-t-il soutenable ?

### 16.4 Versioning

Chaque signal conserve la version :

- du détecteur ;
- de la baseline ;
- des paramètres ;
- de l'univers ;
- des données ou de leur date de collecte ;
- du modèle sémantique lorsque celui-ci intervient.

---

## 17. Exigences non fonctionnelles

### 17.1 Traçabilité

Tout résultat remonte à des observations et identifiants sources.

### 17.2 Reproductibilité

Un détecteur et sa version peuvent être rejoués sur un snapshot connu.

### 17.3 Fraîcheur explicite

Le produit affiche la date du dernier sweep et le retard potentiel des sources. Il emploie « near-real-time » lorsque la source ne permet pas un véritable temps réel.

### 17.4 Coût maîtrisé

Les calculs de headline privilégient les métadonnées et statistiques. Les embeddings et modèles génératifs interviennent de manière ciblée.

### 17.5 Portabilité

Le moteur doit pouvoir fonctionner dans une infrastructure légère et, lorsque nécessaire, avec inférence locale CPU.

### 17.6 Accessibilité

Les informations ne reposent pas uniquement sur la couleur ; les graphes possèdent des alternatives textuelles ; la navigation principale est utilisable au clavier.

### 17.7 Sécurité et confidentialité

Les données publiques restent distinguées des annotations, watchlists et priorités stratégiques privées. Les futures offres institutionnelles nécessiteront isolation, contrôle d'accès et politique de conservation.

---

## 18. Principaux risques

| Risque | Conséquence | Réponse prévue |
|---|---|---|
| Retard d'indexation pris pour un signal | Faux positif | Temporalités distinctes, confirmation multi-sweep |
| Petits échantillons | Churn et amplitudes trompeuses | Garde de confiance et shrinkage |
| Effet de croissance globale d'OpenAlex | Fausses tendances | Normalisation par champ et couverture |
| Topics trop grossiers | Transferts invisibles | Motifs sémantiques en couche secondaire |
| Claims bruités | Narrations trompeuses | Claims hors headline, frames avec preuve |
| Citations trop récentes | Instabilité | Normalisation par âge, signal faible au début |
| Homonymies/affiliations | Acteurs incorrects | Qualité de résolution affichée |
| Score opaque | Perte de confiance | Dimensions séparées et explication |
| Trop d'alertes | Abandon du produit | Budget d'attention, déduplication, feedback |
| Interface construite trop tôt | Itérations coûteuses | Instrument et backtest avant UI |
| Surpromesse de prédiction | Risque méthodologique | Scénarios qualifiés, jamais certitudes |

---

## 19. Positionnement et offres futures

### 19.1 Offres possibles

- observatoire d'une institution ;
- radar stratégique d'un domaine ;
- terminal multi-portefeuilles ;
- prestation d'installation et de configuration ;
- abonnement de maintenance des détecteurs et sources ;
- développement de détecteurs métier ;
- API ou exports intégrables dans un portail existant.

### 19.2 Actif différenciant

L'actif n'est pas l'accès aux données ouvertes ni le résumé LLM. Il réside dans :

- les baselines contextualisées ;
- les détecteurs versionnés ;
- les gardes de confiance ;
- la combinaison de signaux ;
- les dossiers de preuves ;
- la capacité à configurer un observatoire pour un usage réel.

---

## 20. Classes de développement

La colonne **Classe** du registre emploie les valeurs suivantes :

| Classe | Sens | Ordre |
|---|---|---:|
| `POC-C` | Cœur obligatoire de la tranche verticale | 0 |
| `POC-S` | Extension seulement si le cœur est stable | 0b |
| `TALK` | Livrable ou preuve utile au talk, sans obligation produit | 0t |
| `POST-1` | Consolidation immédiate après le meeting | 1 |
| `POST-2` | Extension des signaux et des sources | 2 |
| `POST-3` | Productisation et usages institutionnels | 3 |
| `POST-4` | Échelle, écosystème et fonctions avancées | 4 |
| `HOLD` | Hypothèse à explorer avant engagement | — |

La colonne **Talk** distingue :

- `Cœur` : indispensable au récit ou à la démonstration ;
- `Mention` : cité comme perspective ou leçon ;
- `Non` : absent du talk de dix minutes.

---

## 21. Registre exhaustif des fonctionnalités

### A. Univers, périmètres et workspaces

| ID | Fonctionnalité | Classe | POC | Talk | Dépendances / critère principal |
|---|---|---|---|---|---|
| U01 | Univers institution par ROR/OpenAlex ID | POC-C | Oui | Cœur | Périmètre Mines reproductible |
| U02 | Univers topic par OpenAlex topic/query | POC-S | Préconfiguré seulement | Mention | Même contrat que l'institution |
| U03 | Univers portefeuille multi-topics/institutions | POST-2 | Non | Mention | Agrégation inter-univers |
| U04 | Groupe de référence mondial | POC-C | Oui | Cœur | Même topic ID, périmètre auditable |
| U05 | Cohorte de pairs personnalisée | POST-1 | Non | Mention | Règles et version de cohorte |
| U06 | Règles d'inclusion/exclusion | POST-1 | Minimales en configuration | Non | Version du périmètre |
| U07 | Sauvegarde de plusieurs univers | POST-2 | Non | Non | Persistance utilisateurs |
| U08 | Versioning d'un univers | POC-C | Oui dans les métadonnées | Mention | `universe_version` dans chaque signal |
| U09 | Constructeur visuel d'univers | POST-3 | Non | Non | U06/U07 stables |
| U10 | Import d'une liste d'identifiants | POST-2 | Non | Non | Validation et résolution |
| U11 | Watchlist d'entités | POST-1 | Une liste statique éventuelle | Mention | Modèle d'entité stabilisé |
| U12 | Paramètres de pertinence stratégique | POST-2 | Non | Mention | Séparés du score factuel |

### B. Collecte, observations et qualité des données

| ID | Fonctionnalité | Classe | POC | Talk | Dépendances / critère principal |
|---|---|---|---|---|---|
| D01 | Collecte initiale OpenAlex | POC-C | Oui | Cœur | Snapshot et requête conservés |
| D02 | Sweep OpenAlex incrémental | POC-C | Oui | Cœur | Nouveaux et modifiés distingués |
| D03 | Journal normalisé d'observations | POC-C | Oui | Mention | Idempotence et horodatage |
| D04 | Quatre temporalités de l'observation | POC-C | Oui si disponibles | Mention | Absence explicitement marquée |
| D05 | Conservation des identifiants/provenance | POC-C | Oui | Cœur | Retour au document source |
| D06 | Détection des suppressions/corrections | POST-1 | Non | Mention | Comparaison de snapshots |
| D07 | OpenCitations : enrichissement citationnel | POC-S | Partiel | Mention | Valeur ajoutée vérifiée |
| D08 | Contrôle OpenAlex/OpenCitations | POST-1 | Non | Mention | Divergences observables |
| D09 | Crossref | POST-2 | Non | Non | Connecteur normalisé |
| D10 | DataCite | POST-2 | Non | Non | Datasets reliés aux œuvres |
| D11 | HAL | POST-2 | Non | Mention | Réutiliser connecteur existant |
| D12 | Preprints/arXiv | POST-2 | Non | Mention | Déduplication versions |
| D13 | theses.fr | POST-3 | Non | Non | Rythme et objets distincts |
| D14 | Software Heritage/dépôts de code | POST-2 | Non | Mention | Relations logiciel–publication |
| D15 | Sources de financements | POST-3 | Non | Mention | Couverture par territoire |
| D16 | Brevets | POST-3 | Non | Mention | Résolution publication–brevet |
| D17 | Essais cliniques | POST-3 | Non | Mention | Pertinent par domaine |
| D18 | Documents de politique publique | POST-4 | Non | Non | Source et liens robustes |
| D19 | Métriques de couverture/fraîcheur | POC-C | Oui | Cœur | Visibles par univers et signal |
| D20 | Résolution DOI/ORCID/ROR | POST-1 | Basique | Mention | Conflits conservés |
| D21 | Déduplication multi-source | POST-2 | Non | Non | D20 préalable |
| D22 | Cache et budget d'API | POC-C | Oui | Non | Collecte rejouable et économique |

### C. Baselines et métriques

| ID | Fonctionnalité | Classe | POC | Talk | Dépendances / critère principal |
|---|---|---|---|---|---|
| B01 | Baseline de volume par topic | POC-C | Oui | Cœur | Historique 3–5 ans |
| B02 | Fenêtres mensuelles/trimestrielles configurées | POC-C | Oui | Mention | Comparaisons homogènes |
| B03 | Trajectoire multi-fenêtres | POC-C | Oui | Cœur | Pente et statut stables |
| B04 | Delta deux fenêtres | POC-C | Oui | Cœur | Secondaire à la trajectoire |
| B05 | Ajustement couverture/croissance du corpus | POST-1 | Approximation documentée | Mention | Test de sensibilité |
| B06 | Ajustement saisonnier | POST-1 | Non | Mention | Historique suffisant |
| B07 | Baseline citationnelle par âge/champ | POC-S | Première version | Mention | Cohortes de comparaison |
| B08 | Baseline de réseau de collaboration | POST-1 | Non | Mention | Snapshots de graphe |
| B09 | Baseline de présence institutionnelle | POC-C | Oui via positionnement | Cœur | Part mondiale et timing |
| B10 | Baseline sémantique méthode–domaine | POST-2 | Non | Mention | Frames/motifs disponibles |
| B11 | Baseline de translation | POST-3 | Non | Mention | Sources translationnelles |
| B12 | Shrinkage petits échantillons | POST-1 | Garde simple | Mention | Modèle statistique évalué |
| B13 | Versioning des baselines | POC-C | Oui dans la sortie | Mention | Paramètres conservés |

### D. Détecteurs

| ID | Fonctionnalité | Classe | POC | Talk | Dépendances / critère principal |
|---|---|---|---|---|---|
| S01 | Momentum thématique institutionnel | POC-C | Oui | Cœur | Hérite du Tier 1 existant |
| S02 | Topic nouveau/persistant/disparu | POC-C | Oui | Cœur | Fenêtres comparables |
| S03 | Accélération/décélération thématique | POC-C | Oui | Cœur | Au moins 3 fenêtres |
| S04 | Positionnement institution vs monde | POC-C | Oui | Cœur | Timing, part, confiance |
| S05 | Accélération citationnelle normalisée | POC-S | Version minimale | Mention | B07 |
| S06 | Résurgence d'un article ancien | POST-2 | Non | Non | Historique citationnel |
| S07 | Nouvel acteur dans un domaine | POC-S | Version minimale | Mention | Résolution entités correcte |
| S08 | Changement de centralité d'un acteur | POST-1 | Non | Mention | B08 |
| S09 | Collaboration inhabituelle | POC-S | Version minimale | Mention | Graphe de référence simple |
| S10 | Article-pont entre clusters | POST-2 | Non | Mention | Communautés stables |
| S11 | Migration méthode–domaine | POST-2 | Non | Mention | B10 et contribution frames |
| S12 | Convergence d'équipes indépendantes | POST-2 | Non | Mention | Relations acteurs normalisées |
| S13 | Réactivation d'une idée dormante | POST-2 | Non | Mention | Historique sémantique long |
| S14 | Apparition dataset/logiciel | POST-2 | Non | Mention | D10/D14 |
| S15 | Publication → financement | POST-3 | Non | Non | D15 |
| S16 | Publication → brevet | POST-3 | Non | Mention | D16 |
| S17 | Publication → essai clinique | POST-3 | Non | Mention | D17 |
| S18 | Signal de correction/rétractation | POST-2 | Non | Mention | D06 et source fiable |
| S19 | Changement géopolitique de production | POST-3 | Non | Mention | Affiliations/pays fiables |
| S20 | Saturation ou déclin d'un topic | POST-1 | Non | Mention | Baseline globale |
| S21 | Niche sous-financée à fort momentum | POST-4 | Non | Non | Financement + momentum |
| S22 | Détecteur configurable/DSL | POST-4 | Non | Non | Registre stable et sécurité |

### E. Couche sémantique et IA

| ID | Fonctionnalité | Classe | POC | Talk | Dépendances / critère principal |
|---|---|---|---|---|---|
| A01 | Utilisation des topics OpenAlex comme headline | POC-C | Oui | Cœur | Méthode actuelle conservée |
| A02 | Drill-down de claims dans les topics signalés | POC-S | Démonstration ciblée | Cœur | Preuves et limites visibles |
| A03 | Claim delta corpus-wide | TALK | Non | Cœur comme leçon | Ne pas intégrer au produit initial |
| A04 | Clusters cross-cutting de claims | TALK | Figure existante | Mention | Présenté comme exploratoire |
| A05 | Extraction de contribution frames | POST-1 | Petit spike éventuel | Mention | Schéma et échantillon évalué |
| A06 | Motifs méthode × objet × domaine | POST-2 | Non | Mention | A05 + normalisation |
| A07 | Détection accord/contradiction | HOLD | Non | Non | Évaluation spécifique nécessaire |
| A08 | Classification de pertinence par SLM | POST-1 | Non | Mention | Rejet explicable et échantillon test |
| A09 | Résumé grounded d'un signal | POC-S | Oui si temps | Démo possible | Entrée limitée au dossier de preuves |
| A10 | Brief multi-signaux par SLM | POST-1 | Markdown semi-automatique | Mention | A09 stabilisé |
| A11 | Lecture recommandée | POST-1 | Non | Mention | Critères explicites |
| A12 | Prédiction des développements futurs | HOLD | Non | Mention prudente | Scénarios, jamais certitudes |
| A13 | Modèle local CPU remplaçable | POST-1 | Non requis | Mention | Interface provider standardisée |
| A14 | Évaluation des extractions sémantiques | POST-1 | Échantillon claims existant | Cœur | Précision par champ/type |
| A15 | Traçabilité phrase-source | POC-S | Oui pour claims montrés | Cœur | Citation exacte de l'abstract |

### F. Objet Signal, scoring et cycle de vie

| ID | Fonctionnalité | Classe | POC | Talk | Dépendances / critère principal |
|---|---|---|---|---|---|
| G01 | Schéma commun `Signal` | POC-C | Oui | Cœur | Valide pour les 3 détecteurs |
| G02 | Dossier de preuves normalisé | POC-C | Oui | Cœur | Sources et calculs liés |
| G03 | Dimensions magnitude/velocity/anomaly | POC-C | Oui | Cœur | Affichées séparément |
| G04 | Score composite de tri | POST-1 | Tri simple seulement | Mention | Poids visibles/configurables |
| G05 | Confidence guard | POC-C | Oui | Cœur | Taille, couverture, stabilité |
| G06 | Convergence multi-détecteurs | POST-2 | Non | Mention | Signaux dédupliqués |
| G07 | Déduplication de signaux | POST-1 | Basique si nécessaire | Non | Identité/temporalité |
| G08 | États candidate/confirmed | POC-C | Oui | Mention | Transition déterministe |
| G09 | États watch/dismissed/resolved | POST-1 | Contrôle UI minimal possible | Non | Persistance analyste |
| G10 | Réouverture d'un signal | POST-2 | Non | Non | Historique d'état |
| G11 | Feedback utile/bruit | POST-1 | Boutons éventuellement factices | Mention | Ne modifie pas les faits |
| G12 | Pertinence propre au workspace | POST-2 | Non | Mention | Séparée de confiance |
| G13 | Budget d'attention / quota de signaux | POST-2 | Non | Mention | Mesure de charge utilisateur |
| G14 | Historique/version d'un signal | POC-C | Oui dans JSON | Mention | Rejeu possible |

### G. Situation room et drill-down

| ID | Fonctionnalité | Classe | POC | Talk | Dépendances / critère principal |
|---|---|---|---|---|---|
| UI01 | Feed de signaux | POC-C | Oui | Démo cœur | Liste priorisée compréhensible |
| UI02 | Carte de signal compacte | POC-C | Oui | Démo cœur | Changement, confiance, date |
| UI03 | Dossier de signal | POC-C | Oui | Démo cœur | Preuve vérifiable en un écran |
| UI04 | Pourquoi c'est inhabituel | POC-C | Oui | Démo cœur | Observé vs attendu explicite |
| UI05 | Chronologie du signal | POC-C | Oui | Démo cœur | Événements sourcés |
| UI06 | Documents clés | POC-C | Oui | Démo cœur | Lien OpenAlex/DOI |
| UI07 | Acteurs clés | POC-C | Oui | Démo cœur | Affiliation et rôle dans signal |
| UI08 | Confiance, limites et couverture | POC-C | Oui | Démo cœur | Toujours visible |
| UI09 | Graphe citationnel | POC-S | Statique ou réduit | Mention | Lisible et utile |
| UI10 | Graphe de collaboration | POST-1 | Non | Mention | Détecteur réseau stabilisé |
| UI11 | Frontier radar interactif | POST-1 | Figure statique seulement | Mention | Définition visuelle validée |
| UI12 | Carte institutionnelle/géographique | POST-2 | Non | Mention | Données d'affiliation fiables |
| UI13 | Comparaison de périodes | POST-1 | Non | Mention | Snapshots persistés |
| UI14 | Comparaison d'univers | POST-2 | Non | Non | Mode portefeuille |
| UI15 | Recherche dans les signaux | POST-1 | Non | Non | Volume suffisant |
| UI16 | Filtres avancés | POST-2 | Non | Non | Besoins utilisateurs observés |
| UI17 | Annotations analyste | POST-1 | Non | Mention | Auth/persistance minimale |
| UI18 | Lecture recommandée | POST-1 | Non | Mention | A11 |
| UI19 | Responsive et clavier | POC-C | Oui | Non | Utilisation réelle possible |
| UI20 | Terminal à panneaux composables | POST-3 | Non | Mention | Workspaces et instruments stables |
| UI21 | Constructeur de dashboard | POST-4 | Non | Non | Après validation des usages |

### H. Briefings, alertes et exports

| ID | Fonctionnalité | Classe | POC | Talk | Dépendances / critère principal |
|---|---|---|---|---|---|
| R01 | Dossier Markdown d'un signal | POC-C | Oui | Cœur | Généré depuis le JSON |
| R02 | Brief hebdomadaire Markdown | POC-S | Oui si moteur stable | Mention | Sélection explicite |
| R03 | Export JSON | POC-C | Oui | Non | Schéma versionné |
| R04 | Export CSV | POST-1 | Non | Non | Besoin confirmé |
| R05 | Export PDF/rapport institutionnel | POST-2 | Non | Non | Gabarit et citations |
| R06 | Brief quotidien | POST-2 | Non | Mention | Volume et fraîcheur suffisants |
| R07 | Notifications e-mail | POST-2 | Non | Non | Préférences et consentement |
| R08 | Slack/Teams/webhooks | POST-3 | Non | Non | Auth et intégrations |
| R09 | Alertes par seuil/watchlist | POST-2 | Non | Mention | Budget d'attention |
| R10 | API de consultation des signaux | POST-2 | Non | Non | Auth/versioning |
| R11 | Notebook/dossier d'enquête | POST-2 | Non | Mention | Annotations et exports |
| R12 | Partage contrôlé d'un dossier | POST-3 | Non | Non | Permissions |

### I. Évaluation, supervision et gouvernance

| ID | Fonctionnalité | Classe | POC | Talk | Dépendances / critère principal |
|---|---|---|---|---|---|
| Q01 | Backtest historique | POC-C | Oui | Cœur | Dates de coupure strictes |
| Q02 | Jeu de signaux annotés | POST-1 | Petit échantillon | Mention | Protocole d'annotation |
| Q03 | Stabilité aux seuils | POC-C | Oui pour momentum | Cœur | Résultat documenté |
| Q04 | Mesure du délai de détection | POST-1 | Cas illustratif | Mention | Q01 |
| Q05 | Analyse des faux positifs | POC-C | Oui | Cœur | Au moins 3 cas expliqués |
| Q06 | Test utilisateur de compréhension | POC-S | 3–5 personnes si possible | Mention | Tâche en moins de 30 secondes |
| Q07 | Feedback analyste persistant | POST-1 | Non | Mention | G11 |
| Q08 | Versioning détecteurs/paramètres | POC-C | Oui | Cœur | Visible dans sortie |
| Q09 | Monitoring des sweeps | POST-1 | Logs simples | Non | Scheduler stabilisé |
| Q10 | Détection de dérive de couverture | POST-2 | Non | Mention | Historique de qualité |
| Q11 | Registre des limites connues | POC-C | Oui | Cœur | Associé aux signaux |
| Q12 | Audit/rejeu d'un signal | POST-1 | Rejeu manuel | Mention | Snapshots conservés |

### J. Infrastructure et productisation

| ID | Fonctionnalité | Classe | POC | Talk | Dépendances / critère principal |
|---|---|---|---|---|---|
| I01 | Pipeline Python réutilisable | POC-C | Oui | Mention | Modules séparés |
| I02 | Stockage local DuckDB/Parquet ou SQLite | POC-C | Oui | Non | Choix par spike court |
| I03 | Exécution manuelle reproductible | POC-C | Oui | Non | Une commande documentée |
| I04 | Scheduler simple | POST-1 | Optionnel | Mention | Sweep idempotent |
| I05 | Conteneurisation | POST-1 | Non requise | Non | Instrument validé |
| I06 | API backend | POST-1 | Minimale si UI l'exige | Non | Schéma stable |
| I07 | Authentification utilisateurs | POST-3 | Non | Non | Produit multi-utilisateur confirmé |
| I08 | Workspaces isolés | POST-3 | Non | Non | I07 |
| I09 | Multi-tenant | POST-3 | Non | Non | Modèle commercial choisi |
| I10 | RBAC et partage | POST-3 | Non | Non | I07/I08 |
| I11 | Déploiement VPS léger | POST-1 | Démo locale ou privée | Non | Sécurité minimale |
| I12 | Déploiement institutionnel interne | POST-3 | Non | Non | Packaging/support |
| I13 | Inférence locale CPU | POST-1 | Non requise | Mention | Provider interchangeable |
| I14 | Fournisseur OpenAI-compatible | POST-1 | Si résumé POC | Non | Configuration simple |
| I15 | Cache embeddings/modèles | POST-1 | Réutiliser existant si besoin | Non | Coût mesuré |
| I16 | Observabilité/coûts | POST-2 | Logs basiques | Non | Usage récurrent |
| I17 | Sauvegardes et reprise | POST-2 | Non | Non | Persistance serveur |
| I18 | CI/tests automatisés | POST-1 | Tests critiques POC | Non | Contrats stabilisés |

### K. Produit commercial et administration

| ID | Fonctionnalité | Classe | POC | Talk | Dépendances / critère principal |
|---|---|---|---|---|---|
| C01 | Template d'observatoire institutionnel | POST-1 | Mines comme prototype | Mention | POC validé |
| C02 | Template de radar thématique | POST-2 | Univers préconfiguré éventuel | Mention | U02 stabilisé |
| C03 | Catalogue de détecteurs activables | POST-2 | Configuration fichier | Mention | Registre technique |
| C04 | Détecteur sur mesure | POST-3 | Non | Non | Processus de qualification |
| C05 | White-label | POST-3 | Non | Non | Demande client réelle |
| C06 | Administration des sources/budgets | POST-3 | Non | Non | Multi-client |
| C07 | Tableau d'usage | POST-3 | Non | Non | Auth et observabilité |
| C08 | Offre installation/configuration | POST-2 | Non | Non | Documentation de déploiement |
| C09 | Offre maintenance des détecteurs | POST-3 | Non | Non | Versioning et SLA |
| C10 | Facturation/abonnement intégré | HOLD | Non | Non | Modèle commercial éprouvé |
| C11 | API commerciale | POST-4 | Non | Non | Contrats et limites |
| C12 | Marketplace de détecteurs | HOLD | Non | Non | Écosystème suffisant |

### L. Livrables spécifiques OpenAlex Users Meeting

| ID | Livrable | Classe | POC | Talk | Critère principal |
|---|---|---|---|---|---|
| T01 | Proposition de 250 mots | TALK | Non | Cœur | Soumise avant le 14 septembre |
| T02 | Résultat Mines Paris–PSL | TALK | Réutilisé | Cœur | Méthode et corpus expliqués |
| T03 | Figure trajectoire par topics | TALK | Réutilisée/actualisée | Cœur | Lisible en quelques secondes |
| T04 | Résultat counts vs claims | TALK | Réutilisé | Cœur | Spearman et coût expliqués |
| T05 | Figure claim exploration | TALK | Réutilisée | Cœur | Présentée comme limite/leçon |
| T06 | Positionnement institution vs monde | TALK | Réutilisé | Cœur | Prudence du verdict visible |
| T07 | Backtest d'au moins un détecteur | POC-C | Oui | Cœur si probant | Pas de sélection rétrospective cachée |
| T08 | Mini situation room | POC-C | Oui | Démo cœur | Feed + dossier de signal |
| T09 | Démonstration live | TALK | Selon stabilité | Cœur ou vidéo | Durée inférieure à 2 minutes |
| T10 | Capture/vidéo de secours | TALK | Non | Cœur logistique | Fonctionne hors réseau |
| T11 | Slide limites et rough edges | TALK | Non | Cœur | Claims, couverture, retards |
| T12 | Vision du Research Signal Terminal | TALK | Non | Mention finale | Une seule slide, sans surpromesse |
| T13 | Script de talk 10 minutes | TALK | Non | Cœur | 8–9 minutes répétées |
| T14 | Questions souhaitées à OpenAlex | TALK | Non | Mention | Données modifiées, historique, topics |

---

## 22. Roadmap consolidée

### Phase 0 — POC et meeting OpenAlex

Objectif : démontrer une chaîne complète et explicable sur l'univers Mines Paris–PSL.

- observation store minimal ;
- topic momentum et positionnement ;
- un ou deux détecteurs supplémentaires en stretch ;
- schéma de signal ;
- backtest ;
- feed et dossier de preuve ;
- résultats méthodologiques du claim-delta-radar ;
- talk de dix minutes.

### Phase 1 — Consolidation de l'instrument

Objectif : rendre le moteur durable et rejouable.

- baselines plus robustes ;
- persistance des sweeps ;
- cycle de vie des signaux ;
- contribution frames ;
- tests et versioning ;
- premier déploiement privé léger ;
- tests utilisateurs.

### Phase 2 — Extension de l'intelligence

Objectif : démontrer la généralisation institution/topic et la convergence multi-source.

- mode topic complet ;
- portfolio ;
- nouveaux connecteurs académiques ;
- transfert de méthodes ;
- convergence ;
- logiciels/datasets ;
- briefings et alertes ;
- API de consultation.

### Phase 3 — Productisation institutionnelle

Objectif : déployer auprès de plusieurs utilisateurs ou clients.

- authentification et isolation ;
- déploiements institutionnels ;
- administration ;
- brevets, financements et essais selon marchés ;
- white-label ;
- offres et maintenance.

### Phase 4 — Échelle et écosystème

Objectif : plateforme composable et catalogue extensible.

- terminal de panneaux ;
- API commerciale ;
- détecteurs configurables ;
- analyses multi-portefeuilles avancées ;
- éventuel écosystème de détecteurs.

---

## 23. Portes de décision

Le développement ne passe à la phase suivante que si les questions suivantes reçoivent une réponse positive.

### Gate POC-1 — Valeur du signal

- Un signal est-il utile avant toute narration LLM ?
- L'anomalie est-elle visible par rapport à une baseline explicite ?

### Gate POC-2 — Confiance

- Le signal peut-il être reproduit ?
- Les retards d'indexation et petits échantillons sont-ils contrôlés ?

### Gate POC-3 — Compréhension

- Un utilisateur comprend-il en moins de 30 secondes pourquoi le signal existe ?
- Peut-il consulter les preuves et les limites ?

### Gate Phase 1 — Répétabilité

- Plusieurs sweeps produisent-ils un historique stable ?
- Le volume de signaux reste-t-il soutenable ?

### Gate Phase 2 — Généralisation

- Le même contrat fonctionne-t-il sur un topic et une seconde institution ?
- Une deuxième source apporte-t-elle un signal distinct et vérifiable ?

### Gate Phase 3 — Produit

- Un utilisateur réel revient-il consulter ou recevoir les signaux ?
- Un commanditaire est-il prêt à payer pour la configuration, les détecteurs ou la maintenance ?

---

## 24. Journal initial de décisions

| Date | Décision | Justification | Révisable quand ? |
|---|---|---|---|
| 2026-08-28 | Construire un moteur de signaux, pas un moteur de recherche | Différenciation et valeur stratégique | Si les tests montrent une demande principalement documentaire |
| 2026-08-28 | OpenAlex comme référentiel principal | Couverture, identifiants et topics | Après comparaison multi-source |
| 2026-08-28 | Claims hors du headline | Résultats counts/claims et bruit observé | Si une unité sémantique mieux validée apparaît |
| 2026-08-28 | Contribution frames pour le drill-down futur | Plus adaptées que le comptage de claims | Après spike et annotation |
| 2026-08-28 | Mode institution pour le premier POC | Travail Mines déjà disponible | Après meeting, pour mode topic |
| 2026-08-28 | Instrument et backtest avant UI | Réduire les itérations coûteuses | Non, principe général |
| 2026-08-28 | Score multidimensionnel visible | Éviter un score opaque | Après tests utilisateurs |
| 2026-08-28 | Meeting OpenAlex comme jalon, pas comme fin produit | Périmètre réaliste et récit honnête | Non |

---

## 25. Questions ouvertes contrôlées

Ces questions sont volontairement conservées sans lancer immédiatement leur résolution :

1. Quel est le premier acheteur : direction de la recherche, bibliothèque, laboratoire ou entreprise ?
2. Le premier mode topic doit-il surveiller « AI agents » ou un domaine scientifique moins réflexif ?
3. OpenCitations apporte-t-il assez de valeur par rapport aux citations OpenAlex dans la première version ?
4. DuckDB/Parquet ou SQLite pour l'observation store initial ?
5. Quel protocole d'annotation pour les contribution frames ?
6. Quel budget d'attention par utilisateur et par semaine ?
7. Quels groupes de pairs constituent des comparaisons institutionnelles honnêtes ?
8. Quelle partie peut fonctionner avec un SLM local CPU sans perte excessive ?
9. Quelle forme de déploiement sera réellement demandée : service hébergé, interne ou portable ?
10. Quel nom final et quelle identité commerciale pour le produit ?

Ces questions deviennent des tâches seulement lorsqu'elles conditionnent la phase active.

