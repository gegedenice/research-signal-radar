# De données OpenAlex à des signaux de veille

## Note méthodologique sur les trois détecteurs du POC

Cette note explique, sans entrer dans le code, comment le pipeline transforme un portefeuille de publications en trois familles de signaux :

1. **Topic Momentum** : des thèmes dont la place ou le rythme change ;
2. **Citation Acceleration** : des publications citées anormalement vite ;
3. **Actor & Collaboration Novelty** : des partenaires ou des relations institutionnelles qui apparaissent ou réapparaissent.

L’idée générale est simple : le système ne demande pas à une IA générative d’interpréter librement les données. Il construit des comparaisons temporelles explicites, applique des règles déterministes, puis conserve les publications qui permettent de vérifier chaque résultat.

Le mot **signal** doit être pris au sens de « changement inhabituel qui mérite d’être examiné ». Un signal n’est ni une découverte scientifique, ni une prédiction, ni une recommandation automatique.

Le pipeline est la première brique d’un instrument que l’on peut appeler **Research Signal Terminal (RST)** : une plateforme de veille stratégique appliquée aux métadonnées de la recherche, calquée sur une boucle d’*intelligence de situation* héritée de l’OSINT.

```text
Univers → Référence → Balayage → Observation → Delta → Candidat → Signal confirmé → Drill-down → Éclairage
```

Chaque terme correspond à une étape décrite plus bas : l’**univers** est le portefeuille institutionnel versionné ; la **référence** (baseline) est l’état antérieur ou la population de comparaison ; le **balayage** (sweep) est la collecte périodique ; le **delta** est l’écart mesuré entre deux fenêtres ; un **candidat** franchit les conditions minimales ; un **signal confirmé** ajoute confiance, priorité, provenance et preuves ; le **drill-down** ouvre le dossier de preuves. L’actif défendable n’est pas un modèle génératif : c’est le **catalogue versionné de détecteurs, de références contextuelles, de garde-fous de confiance et de dossiers de preuves**.

---

## 1. La chaîne commune aux trois détecteurs

Les trois détecteurs suivent le même raisonnement général :

```text
Définir le portefeuille
        ↓
Collecter et normaliser les œuvres
        ↓
Replacer les observations dans le temps
        ↓
Construire une référence de comparaison
        ↓
Appliquer une règle de détection
        ↓
Évaluer la qualité de la preuve
        ↓
Classer les signaux pour la lecture
        ↓
Relier chaque signal à ses preuves
        ↓
Rejouer la règle dans le passé
```

### 1.1 Définir exactement ce que l’on observe

Avant tout calcul, le pipeline fixe un **portefeuille institutionnel**. Dans le POC, il s’agit de Mines Paris–PSL, identifié à partir de son ROR, puis relié à son identifiant OpenAlex.

Le mode principal est le scope `lineage`. Cela signifie que le portefeuille ne contient pas seulement les œuvres rattachées à l’institution racine : il inclut aussi les institutions descendantes répertoriées dans la hiérarchie OpenAlex. La liste exacte des identifiants retenus est enregistrée dans un manifeste.

Le manifeste fixe également :

- la période étudiée ;
- les types de documents admis ;
- le corpus OpenAlex interrogé ;
- le mode de comptage ;
- la date du snapshot utilisé, appelée **vintage** ;
- la version de la configuration et du code.

Cette étape est essentielle. Sans un périmètre stable, une hausse peut simplement provenir de l’ajout d’une unité dans la requête, et non d’une évolution de la recherche.

Dans le POC, une œuvre est comptée entièrement dès qu’elle appartient au portefeuille : c’est un **comptage intégral**, et non un comptage fractionné entre institutions ou auteurs.

### 1.2 Collecter deux représentations complémentaires des œuvres

Le pipeline utilise deux vues des mêmes publications OpenAlex.

La première est un **recensement agrégé par mois et par topic principal**. OpenAlex renvoie directement le nombre d’œuvres correspondant à chaque topic. Cette vue est légère et sert au détecteur Topic Momentum.

La seconde est une liste détaillée des œuvres. Pour chaque œuvre, le pipeline conserve notamment :

- l’identifiant OpenAlex ;
- le DOI lorsqu’il existe ;
- le titre, le type et la date de publication ;
- le topic principal ;
- les auteurs et leurs affiliations institutionnelles ;
- le nombre de citations indiqué par OpenAlex au moment du snapshot ;
- les références bibliographiques déclarées.

Cette vue détaillée sert à produire les preuves, à construire les collaborations et à préparer la collecte citationnelle.

Les réponses brutes sont archivées. Les données normalisées ne remplacent donc pas la source : elles constituent une forme plus facile à calculer, reliée à la réponse d’origine.

### 1.3 Remettre les données sur un axe temporel régulier

Les données bibliographiques ne forment pas spontanément une série temporelle propre. Le pipeline les range donc dans des mois successifs et vérifie qu’aucun mois ne manque.

Un topic absent d’une réponse groupée pour un mois reçoit explicitement la valeur zéro. C’est important : « aucun résultat » ne doit pas être confondu avec « donnée manquante ».

Le pipeline contrôle aussi la couverture des topics : pour chaque mois, le total des œuvres classées par topic, augmenté des œuvres non classées, doit retrouver le total des œuvres incluses dans la requête.

### 1.4 Comparer une situation courante à une référence

Un nombre isolé ne constitue pas un signal. Chaque détecteur construit donc une référence adaptée à sa question :

| Détecteur | Objet observé | Référence utilisée |
|---|---|---|
| Topic Momentum | un topic OpenAlex | les douze mois précédents et l’historique du topic |
| Citation Acceleration | une œuvre | ses douze mois précédents et une cohorte d’œuvres comparables |
| Actor & Collaboration Novelty | une institution ou une relation | les 36 mois précédents et l’historique plus ancien |

Le **cutoff** est la date au-delà de laquelle aucune publication ou citation ne peut participer au calcul. Il matérialise la question : « qu’aurions-nous pu calculer en nous arrêtant à cette date ? »

### 1.5 Distinguer quatre niveaux de résultat

Le pipeline sépare volontairement quatre objets :

1. **Observation** : une donnée normalisée, par exemple une œuvre, une citation datée ou une relation entre institutions.
2. **Assessment** : l’examen mécanique d’un topic, d’une œuvre ou d’une relation, y compris lorsque la conclusion est de s’abstenir.
3. **Candidat** : un assessment qui satisfait toutes les conditions minimales du détecteur.
4. **Signal** : le candidat mis dans une enveloppe commune, avec sa confiance, sa priorité, son explication, sa provenance et son lien vers les preuves.

Cette séparation évite un piège fréquent : faire disparaître les cas non retenus. Ici, les abstentions sont conservées avec leur raison — historique insuffisant, couverture trop faible, cohorte trop petite, soutien insuffisant, etc.

### 1.6 Confiance, priorité et tier éditorial ne disent pas la même chose

- La **confiance** répond à la question : « la donnée qui soutient ce signal est-elle suffisamment solide ? »
- La **priorité** répond à la question : « parmi les signaux valides de ce détecteur, lequel paraît le plus saillant à lire en premier ? »
- Le **tier éditorial** (`HEADLINE_CANDIDATE`, `WATCH`, `EXPLORATION`) reste une étiquette interne du pipeline. L’interface de veille (« situation room ») ne l’affiche plus comme un drapeau de priorité de lecture — la mention « à surveiller » suggérait une action mal définie ; elle présente désormais, pour chaque détecteur, une barre de composition par **niveau de confiance** (élevée / moyenne / faible).
- Le **statut de revue** indique si une vérification humaine est particulièrement nécessaire (par exemple lorsqu’un signal est contredit à l’échelle supérieure, voir 2.6).

La priorité n’est jamais une probabilité. Une priorité de 0,85 ne signifie pas que le signal a 85 % de chances d’être important ou de persister.

### 1.7 Constituer un dossier de preuves

Chaque signal conserve un lien vers les éléments ayant servi au calcul : identifiants des œuvres, dates, métriques, fenêtres, affiliations ou événements de citation. Quelques œuvres représentatives sont détaillées pour faciliter la lecture, mais les identifiants du corpus justificatif complet restent disponibles.

Le dossier répond à trois questions :

- qu’a mesuré le détecteur ?
- par rapport à quoi ?
- sur quelles publications repose le résultat ?

### 1.8 Deux modes de lecture

L’interface de veille propose deux vues complémentaires du même portefeuille :

- une vue **flux** — les signaux de mouvement, triés par priorité au sein de chaque détecteur ;
- une vue **stock** — les plus gros thèmes par volume total sur la période, avec leur tendance courante ; un thème doté d’un signal renvoie d’un clic vers son dossier dans le flux.

Le flux répond à « qu’est-ce qui bouge ? », le stock à « de quoi le portefeuille est-il fait ? ». L’interface est bilingue français / anglais ; les libellés de données (noms de topics, titres d’œuvres) restent dans la langue source d’OpenAlex.

---

## 2. Détecteur 1 — Topic Momentum

### 2.1 La question posée

Topic Momentum cherche des changements dans la composition thématique du portefeuille :

> Un topic produit-il nettement plus ou moins d’œuvres qu’auparavant, et ce mouvement est-il également visible dans sa part du portefeuille ?

Le détecteur utilise le **topic principal attribué par OpenAlex** à chaque œuvre. Il ne refait pas lui-même une classification sémantique des textes.

### 2.2 Première manipulation : établir un recensement mensuel

Pour chaque mois, OpenAlex est interrogé sur le portefeuille institutionnel et regroupe les œuvres par topic principal. Le pipeline obtient ainsi, pour chaque couple `mois × topic` :

- le nombre d’œuvres du topic ;
- le nombre total d’œuvres classées ce mois-là ;
- la part du topic dans le portefeuille ;
- la couverture de la classification thématique.

La **part de portefeuille** est calculée ainsi :

```text
nombre d’œuvres du topic / nombre total d’œuvres classées
```

Conserver à la fois le volume et la part évite une conclusion trompeuse. Un topic peut publier davantage simplement parce que toute l’institution publie davantage. Dans ce cas, son poids relatif n’augmente pas nécessairement.

### 2.3 Deuxième manipulation : fabriquer des fenêtres comparables

Les mois sont agrégés en fenêtres glissantes de douze mois. Une évaluation est faite tous les trois mois.

À chaque évaluation, trois fenêtres symétriques sont distinguées :

```text
12 mois antérieurs     12 mois précédents     12 mois courants
       T-2                     T-1                     T
```

- `T` est la situation courante ;
- `T-1` sert de comparaison directe ;
- `T-2` permet de dire si la croissance accélère ou ralentit.

Le pipeline exige au moins 36 mois disponibles afin de construire ces trois fenêtres complètes.

### 2.4 Troisième manipulation : mesurer deux évolutions en parallèle

Entre `T-1` et `T`, le pipeline calcule :

- la différence du nombre d’œuvres ;
- le rapport entre les deux nombres ;
- la différence de part de portefeuille ;
- le rapport entre les deux parts ;
- un indicateur d’accélération, qui compare le changement récent au changement précédent.

Dans la configuration du POC, un mouvement haussier exige notamment :

- au moins 2 œuvres supplémentaires ;
- un volume multiplié au minimum par 1,5 ;
- une part de portefeuille multipliée au minimum par 1,25 ;
- au moins 5 œuvres dans la fenêtre courante (paramètre `min_current`) ;
- une activité répartie sur au moins 2 mois.

Le recul est construit symétriquement : baisse d’au moins 2 œuvres, au moins 5 œuvres dans la fenêtre de comparaison (paramètre `min_previous`), volume ramené au maximum à 67 % du précédent et part ramenée au maximum à 80 %.

Ce support minimal de 5 œuvres (contre 3 dans les premières versions) écarte du flux les tout petits topics, où trois publications sur douze mois ne constituent pas un mouvement interprétable. Il reste ajustable dans la configuration du portefeuille.

La décision importante est la suivante : pour déclarer un topic `RISING` ou `FALLING`, le mouvement doit être visible **à la fois en volume absolu et en part du portefeuille**. Les évolutions visibles sur un seul axe sont conservées comme diagnostic, mais ne suffisent pas à établir cette direction.

### 2.5 Quatrième manipulation : qualifier la présence du topic

Indépendamment de la hausse ou de la baisse, le pipeline examine si le topic était présent auparavant :

- `NEW` : présent maintenant, absent de la fenêtre précédente et sans historique suffisant plus ancien ;
- `REACTIVATED` : présent maintenant, absent de la fenêtre précédente, mais déjà bien attesté plus anciennement ;
- `DORMANT` : présent dans la fenêtre précédente, absent maintenant ;
- `PERSISTING` : présent dans les deux fenêtres ;
- `INTERMITTENT` : présence trop discontinue pour les cas précédents ;
- `INSUFFICIENT` : soutien historique trop faible.

Ici encore, `NEW` signifie « nouveau dans l’historique observable du portefeuille », pas « nouveau dans la science ».

### 2.6 Cinquième manipulation : corroborer le mouvement à l’échelle supérieure

Un topic OpenAlex est le niveau le plus fin d’une hiérarchie à quatre étages : 4 domaines → 26 champs (*fields*) → 252 sous-domaines (*subfields*) → 4 516 topics. À ce niveau fin, le portefeuille d’une institution ne compte souvent que quelques œuvres par topic : un mouvement peut alors n’être qu’une fluctuation d’échantillon.

Pour lever ce doute sans changer la granularité du signal, le pipeline agrège la même série mensuelle aux niveaux **subfield** et **field**, en sommant les comptes des topics enfants (avec un invariant de conservation de masse : la somme des œuvres est identique à tous les niveaux). Le classificateur déterministe, exactement le même, est ensuite appliqué à ces séries parentes.

Chaque signal de topic reçoit alors une **corroboration multi-échelle**, dérivée de la comparaison entre sa direction et celle de son sous-domaine parent :

- `CORROBORATED` : le sous-domaine bouge dans le même sens — preuve convergente entre échelles, le signal le plus solide ;
- `ISOLATED_WITHIN_PARENT` : le sous-domaine reste stable — émergence focalisée, réelle mais localisée ;
- `CONTRADICTED` : le sous-domaine bouge en sens opposé — probable artefact de petit effectif, à vérifier ;
- `NEUTRAL` : niveau parent indisponible ou non concluant.

Cette corroboration n’introduit **aucun nouveau seuil de détection** : elle réutilise les directions déjà calculées. Elle agit en aval comme un garde-fou : un signal `CONTRADICTED` conserve la limitation `SCALE_CONTRADICTED`, passe en `review_status = REQUIRED` et ne peut pas occuper le rang éditorial le plus élevé ; un signal `CORROBORATED` porte la raison `SCALE_CORROBORATED`. Le signal reste visible et filtrable — la corroboration éclaire sa lecture, elle ne le supprime pas.

### 2.7 Du candidat au signal

Un topic devient candidat lorsqu’il présente une direction `RISING` ou `FALLING`, ou un changement de présence pertinent (`NEW`, `REACTIVATED`, `DORMANT`).

Le pipeline vérifie ensuite la robustesse du résultat :

- assez d’œuvres et d’historique ;
- bonne couverture des topics ;
- fenêtres complètes ;
- mouvement observé à plusieurs évaluations consécutives ;
- stabilité lorsque les seuils sont rendus plus permissifs ou plus stricts ;
- absence de difficulté majeure liée à une modification de la taxonomie OpenAlex.

Seuls les niveaux de confiance `HIGH` et `MEDIUM` sont éligibles par défaut à l’émission d’un signal. Les autres résultats restent accessibles pour exploration.

La priorité combine ensuite quatre éléments : ampleur du changement de part, caractère inhabituel dans l’histoire du topic, persistance du mouvement et nombre d’œuvres qui le soutiennent.

### 2.8 Les preuves conservées

Pour chaque signal, le dossier contient notamment :

- les comptes et parts des fenêtres courante et précédente ;
- le percentile historique ;
- la durée du mouvement ;
- tous les identifiants d’œuvres des fenêtres utiles ;
- jusqu’à cinq œuvres représentatives, choisies en tenant compte des citations, de la récence et de la diversité des acteurs ;
- la matérialisation de l’appartenance institutionnelle ;
- la corroboration multi-échelle et la direction du sous-domaine parent ;
- les éventuels écarts entre le recensement agrégé et les œuvres détaillées.

### 2.9 Comment le backtest est construit

Le détecteur est rejoué à des cutoffs historiques, tous les trois mois, sans utiliser d’œuvre postérieure au cutoff. Les occurrences successives d’un même mouvement sont regroupées en **épisodes** afin de ne pas raconter trois fois la même hausse trimestrielle.

Le déplacement observé au moment du signal est ensuite comparé à la situation à +6 mois et +12 mois, en volume et en part de portefeuille. L’issue est classée :

- `STRENGTHENED` : le déplacement s’est renforcé sur les deux mesures ;
- `RETAINED` : au moins 50 % du déplacement subsiste sur chacune des deux mesures ;
- `FADED` : le déplacement s’est nettement atténué ;
- `REVERSED` : il s’est inversé sur les deux mesures ;
- `MIXED` : volume et part racontent des histoires différentes ;
- `RIGHT_CENSORED` : le recul temporel disponible ne permet pas encore de mesurer l’horizon.

À +6 mois, les deux fenêtres de douze mois se chevauchent partiellement. La lecture à +12 mois est donc plus nette. Comme les calculs historiques sont reconstruits à partir d’un snapshot OpenAlex actuel, le pipeline teste également plusieurs hypothèses simples de délai d’indexation.

---

## 3. Détecteur 2 — Citation Acceleration

### 3.1 La question posée

Citation Acceleration cherche des œuvres dont le rythme de citation a nettement augmenté :

> Cette publication reçoit-elle beaucoup plus de citations que pendant les douze mois précédents, et cette accélération est-elle inhabituelle parmi des œuvres comparables ?

Ce détecteur ne se contente pas du compteur `cited_by_count` d’OpenAlex, car un compteur courant ne permet pas de reconstituer correctement le rythme mois par mois. Il part des œuvres OpenAlex, puis collecte les **événements de citation datés auprès d’OpenCitations**. Le compteur OpenAlex reste un point de comparaison pour contrôler la couverture des sources.

### 3.2 Première manipulation : déterminer les œuvres analysables

À partir du portefeuille OpenAlex, le pipeline retient les œuvres :

- possédant un DOI valide et non ambigu ;
- publiées depuis au moins douze mois ;
- pour lesquelles la collecte OpenCitations est complète.

Les œuvres sans DOI, aux DOI invalides ou dupliqués, trop récentes ou insuffisamment couvertes ne disparaissent pas : elles sont enregistrées avec un motif d’abstention.

### 3.3 Deuxième manipulation : normaliser les citations

Chaque citation reçue devient un événement relié à l’œuvre citée. Le pipeline conserve :

- l’identifiant de l’événement lorsqu’il est disponible ;
- l’identifiant de la publication citante ;
- la date de la citation et son degré de précision ;
- l’indication de self-citation d’auteur lorsqu’elle est fournie ;
- la provenance OpenCitations ;
- les problèmes éventuels de date ou d’identifiant.

Une date connue seulement à l’année n’est pas artificiellement transformée en date mensuelle. Cela évite de fabriquer une précision qui n’existe pas dans la source.

La métrique principale exclut les self-citations d’auteur explicitement connues. Un calcul parallèle les incluant est conservé comme test de sensibilité.

### 3.4 Troisième manipulation : comparer deux vitesses de citation

Pour chaque œuvre et pour un cutoff donné, deux fenêtres consécutives sont construites :

```text
12 mois précédents     12 mois courants
        T-1                    T
```

Le pipeline compte les citations datées dans chaque fenêtre, puis calcule :

- le nombre récent ;
- le nombre précédent ;
- la différence absolue ;
- un rapport d’accélération lissé : `(récent + 1) / (précédent + 1)` ;
- une version logarithmique utilisée pour comparer les œuvres entre elles.

Le `+1` empêche une division par zéro. Il ne crée pas une citation supplémentaire dans le résultat affiché.

### 3.5 Quatrième manipulation : construire une comparaison équitable

Une hausse de trois citations n’a pas le même sens pour un article récent dans un petit domaine et pour une publication ancienne dans un champ très cité. Le pipeline construit donc une **cohorte de référence**.

Les œuvres sont rapprochées selon :

- leur type de document ;
- leur tranche d’âge depuis publication ;
- leur topic principal OpenAlex.

Une cohorte doit contenir au moins 20 œuvres. Si la cohorte au niveau du topic est trop petite, le pipeline élargit successivement au subfield, puis à l’ensemble du portefeuille pour le même type et la même tranche d’âge. Ce repli reste visible et diminue la confiance : une comparaison très précise par topic est préférable à une comparaison générale.

Pour chaque œuvre, le pipeline calcule ensuite son **percentile d’accélération** dans sa cohorte. Un percentile de 0,95 signifie que son accélération est au moins aussi forte que celle de 95 % des œuvres comparables ; cela ne signifie pas 95 % de probabilité de succès futur.

### 3.6 La règle qui produit un candidat

Dans le POC, toutes les conditions suivantes doivent être satisfaites :

- au moins 3 citations dans les douze mois courants ;
- au moins 2 citations de plus que dans les douze mois précédents ;
- un rapport d’accélération d’au moins 1,5 ;
- un percentile de cohorte d’au moins 0,90 ;
- une cohorte d’au moins 20 œuvres ;
- une couverture temporelle suffisante, fixée à 75 % au minimum ;
- aucune autre raison d’abstention.

Le candidat reçoit ensuite un label de lecture :

- `BREAKOUT` si l’œuvre avait au plus une citation dans la fenêtre précédente ;
- `ACCELERATING` si elle possédait déjà un rythme citationnel plus installé.

Le premier cas désigne donc une rupture depuis un niveau très bas ; le second, l’accélération d’une dynamique déjà visible.

### 3.7 Confiance, priorité et preuves

La confiance dépend notamment :

- de la proportion de citations pouvant être placées précisément dans le temps ;
- de la proximité entre le volume total observé dans OpenCitations et le compteur OpenAlex ;
- de la précision de la cohorte de référence ;
- de sa taille ;
- de la robustesse du résultat face aux self-citations connues.

La priorité combine : caractère exceptionnel dans la cohorte, volume récent, ampleur de l’augmentation et confiance de la preuve.

Le bundle de preuves conserve l’œuvre OpenAlex, les deux fenêtres, la cohorte, la chronologie mensuelle des citations, les métriques calculées et quelques événements de citation récents représentatifs.

### 3.8 Comment le backtest est construit

La détection est rejouée tous les six mois. Pour chaque cutoff historique :

1. les citations postérieures sont retirées de la détection ;
2. l’âge des œuvres et les cohortes sont recalculés à cette date ;
3. les mêmes seuils sont appliqués ;
4. les citations des douze mois suivants sont examinées séparément.

L’issue est :

- `SUSTAINED` si le nombre de citations reçu pendant les douze mois suivants est au moins égal au nombre reçu pendant la fenêtre courante au moment du signal ;
- `FADED` si ce rythme n’est pas maintenu ;
- `RIGHT_CENSORED` si les douze mois futurs ne sont pas entièrement observables.

`FADED` ne signifie pas « faux positif ». L’accélération était réelle au cutoff ; elle ne s’est simplement pas maintenue au même rythme.

---

## 4. Détecteur 3 — Actor & Collaboration Novelty

### 4.1 La question posée

Ce détecteur cherche des changements dans l’environnement institutionnel du portefeuille :

> Quelles institutions externes, ou quelles relations entre une unité du portefeuille et une institution externe, apparaissent ou réapparaissent dans les publications ?

Dans cette version du POC, les acteurs sont des **institutions**, pas des auteurs. Cela évite de prétendre détecter des trajectoires individuelles sans disposer d’un historique de carrière et d’une désambiguïsation suffisants.

### 4.2 Première manipulation : transformer les affiliations en relations

Pour chaque œuvre OpenAlex, le pipeline sépare :

- les institutions **ancres**, c’est-à-dire incluses dans le portefeuille ;
- les institutions **externes** ;
- les auteurs rattachés à chacune.

Il construit ensuite une relation, ou **arête**, entre une ancre et une institution externe.

Mais la simple présence des deux institutions dans l’affiliation d’un même auteur ne suffit pas. Pour matérialiser une collaboration, le pipeline exige deux auteurs OpenAlex distincts : au moins un auteur rattaché à l’ancre et un autre rattaché à l’institution externe.

Exemple :

```text
Auteur A → Mines Paris–PSL
Auteur B → Université X
⇒ relation Mines Paris–PSL ↔ Université X
```

En revanche :

```text
Auteur A → Mines Paris–PSL + Université X
aucun autre auteur distinct
⇒ double affiliation conservée, mais pas comptée comme collaboration
```

Cette règle empêche de confondre mobilité ou double rattachement individuel avec copublication entre équipes.

### 4.3 Deuxième manipulation : créer des événements institutionnels

Une œuvre peut matérialiser plusieurs relations, notamment dans un consortium. Le pipeline produit un événement par couple :

```text
œuvre × institution ancre × institution externe
```

Une œuvre ne compte qu’une fois pour une même relation, même si plusieurs paires d’auteurs la matérialisent. Le nombre exact de paires est conservé, mais seuls vingt exemples sont détaillés lorsque les consortiums sont très grands, afin d’éviter une explosion du volume des fichiers.

Chaque œuvre reçoit aussi un statut de couverture : utilisable, sans institution externe, double affiliation seulement, sans paire d’auteurs valide ou sans ancre institutionnelle matérialisée.

### 4.4 Troisième manipulation : construire deux sortes d’historique

Le pipeline construit séparément :

- l’historique d’un **acteur externe** dans l’ensemble du portefeuille ;
- l’historique d’une **arête précise** entre une ancre et cet acteur.

Il découpe le temps en trois parties :

```text
historique ancien       baseline récente        fenêtre courante
avant la baseline           36 mois                  12 mois
```

Ce découpage permet de distinguer une apparition réellement absente de l’historique observable d’un retour après une longue période sans activité.

### 4.5 Les quatre labels

- `NEW_EXTERNAL_ACTOR` : l’institution externe apparaît dans la fenêtre courante et n’avait jamais été observée auparavant dans le portefeuille.
- `REACTIVATED_EXTERNAL_ACTOR` : elle était visible dans l’historique ancien, absente pendant les 36 mois de baseline, puis revient.
- `NEW_COLLABORATION` : le partenaire était déjà actif récemment avec une autre unité du portefeuille, mais cette arête précise n’avait jamais été observée.
- `REACTIVATED_COLLABORATION` : cette arête existait dans l’historique ancien, avait disparu pendant 36 mois, puis revient ; pendant la baseline, le partenaire restait actif avec une autre unité.

La nuance entre acteur et collaboration est particulièrement utile avec le scope `lineage`. Une institution externe peut déjà collaborer avec une unité de Mines Paris–PSL, puis commencer à publier avec une autre unité interne : le partenaire n’est pas nouveau, mais la relation l’est.

### 4.6 La règle qui produit un candidat

Pour éviter qu’une publication isolée, notamment issue d’un grand consortium, produise une alerte, un acteur ou une arête doit réunir toutes les conditions suivantes dans les douze mois courants :

- au moins 2 œuvres distinctes ;
- réparties sur au moins 2 mois distincts ;
- au moins 2 œuvres dont le rattachement à l’ancre est vérifiable dans les données détaillées ;
- aucune œuvre dans les 36 mois de baseline récente ;
- la condition d’historique propre au label `NEW` ou `REACTIVATED`.

Pour les signaux de collaboration, le partenaire externe doit en plus avoir été actif avec une autre ancre pendant la baseline récente.

Une règle de **préséance** évite les doublons : si l’acteur externe lui-même est nouveau ou réactivé, le pipeline émet un signal acteur unique. Les différentes arêtes sont décrites dans ses preuves, mais ne deviennent pas simultanément plusieurs signaux de collaboration.

### 4.7 Du candidat au signal

La confiance mesure la qualité de la matérialisation institutionnelle, le nombre d’œuvres, la diversité observable des paires d’auteurs et l’étalement sur plusieurs mois.

La priorité combine : nombre d’œuvres, nombre d’unités internes concernées, diversité des topics et confiance.

Le pipeline repère aussi les signaux qui reposent exactement sur le même ensemble d’œuvres. C’est fréquent lorsqu’un petit nombre d’articles de consortium fait apparaître de nombreuses institutions en même temps.

Les signaux ne sont pas supprimés des données. En revanche :

- un groupe d’au moins trois signaux partageant les mêmes œuvres exige une revue humaine ;
- le dossier Markdown ne présente au plus que deux représentants du groupe ;
- les signaux et les preuves exhaustives restent disponibles dans les fichiers JSONL.

Ce mécanisme limite la domination éditoriale d’un consortium sans falsifier ce que montrent les données.

### 4.8 Les preuves conservées

Pour chaque signal, le dossier permet de retrouver :

- la chronologie mensuelle de l’acteur ou de l’arête ;
- les œuvres soutenant la détection ;
- les auteurs et affiliations qui matérialisent chaque relation ;
- les unités ancres concernées ;
- les topics des œuvres ;
- la première et la dernière apparition ;
- la raison exacte du label ;
- les éventuelles limites de granularité, de couverture ou de consortium.

La vérification humaine reste particulièrement importante ici, car les identités institutionnelles OpenAlex peuvent refléter des changements de nom, des niveaux hiérarchiques différents ou des affiliations étonnamment dispersées.

### 4.9 Comment le backtest est construit

Les mêmes règles sont rejouées tous les six mois. Un cutoff ne peut être évalué que si les 36 mois complets de baseline sont disponibles.

À +12 mois :

- `CONTINUED` : au moins une nouvelle œuvre matérialise le même acteur ou la même arête ;
- `ONE_OFF` : aucune nouvelle œuvre ne matérialise cette relation ;
- `RIGHT_CENSORED` : les douze mois suivants ne sont pas entièrement observables.

La continuation mesure uniquement une persistance opérationnelle dans les publications. Elle ne mesure ni la qualité scientifique ni l’importance stratégique de la collaboration.

---

## 5. Ce que signifie réellement le backtest rétrospectif

Les trois backtests respectent une séparation stricte :

```text
données autorisées au cutoff → détection du signal

données postérieures au cutoff → évaluation ultérieure du devenir
```

Les données futures ne sont jamais ajoutées a posteriori au signal historique. Elles sont stockées dans un objet d’outcome séparé.

Il faut toutefois comprendre une limite de source. Les backtests ont été reconstruits à partir de snapshots OpenAlex et OpenCitations consultés aujourd’hui. Le pipeline sait quelles publications ou citations portent une date postérieure au cutoff et peut les exclure. En revanche, il ne possède pas nécessairement le snapshot exact que les bases auraient présenté à cette date historique : une affiliation, un topic ou une citation peut avoir été corrigé ou indexé plus tard.

C’est pourquoi le mode est appelé `retrospective_reconstruction`. Il permet de tester la logique du détecteur et l’utilité potentielle des signaux, mais il ne prouve pas que toutes les mêmes métadonnées auraient été disponibles en temps réel.

Trois dates doivent donc rester distinctes :

- **cutoff d’information** : dernière date de publication ou de citation admise dans le calcul ;
- **vintage d’observation** : date du snapshot effectivement utilisé ;
- **date d’émission** : moment où le pipeline a produit ou reconstruit le signal.

---

## 6. Exemple simplifié de bout en bout

Prenons un cutoff au 30 juin 2026.

### Topic Momentum

Un topic compte 5 œuvres entre juillet 2025 et juin 2026, contre 2 pendant les douze mois précédents — il atteint tout juste le support minimal de 5. Sa part du portefeuille progresse elle aussi suffisamment. Le mouvement est visible sur plusieurs évaluations et les œuvres sont bien rattachées au périmètre. Il peut devenir un signal `RISING`. Si son sous-domaine parent progresse dans le même sens, le signal est `CORROBORATED` ; s’il recule, il est `CONTRADICTED` et exige une revue humaine.

### Citation Acceleration

Une œuvre reçoit 6 citations pendant les douze derniers mois, contre 1 pendant les douze mois précédents. Elle se situe au 94e percentile d’une cohorte d’articles du même âge et du même topic. Si la couverture temporelle est suffisante, elle satisfait les seuils et reçoit le label `BREAKOUT`.

### Actor & Collaboration Novelty

Une institution externe apparaît dans 2 publications, en octobre 2025 et mars 2026. Elle n’était visible ni pendant les 36 mois précédents ni dans l’historique plus ancien du portefeuille. Les deux publications contiennent chacune un auteur de l’ancre et un auteur distinct de l’institution externe. Elle peut devenir un signal `NEW_EXTERNAL_ACTOR`.

Dans les trois cas, le signal n’est pas la fin de l’analyse. Il indique où regarder, explique pourquoi le cas a franchi les seuils et fournit les œuvres nécessaires à sa vérification.

---

## 7. Les formulations justes pour présenter le POC

### On peut dire

- « Le système repère des changements inhabituels dans un portefeuille institutionnel versionné. »
- « Les règles sont déterministes et chaque signal est relié à ses preuves. »
- « Les signaux sont comparés à une histoire récente ou à une population comparable. »
- « Le backtest mesure si le mouvement ou la relation persiste ensuite. »
- « La validation humaine fait partie de la méthode. »

### Il vaut mieux éviter

- « Le système découvre les nouveaux domaines scientifiques. »
- « Il prédit les futurs sujets importants. »
- « Une priorité de 0,8 représente 80 % de chances de succès. »
- « Une collaboration `NEW` est nouvelle à l’échelle mondiale. »
- « Un signal qui ne persiste pas est un faux positif. »
- « Le backtest reproduit exactement ce qu’OpenAlex montrait historiquement. »

---

## 8. Glossaire minimal

| Terme | Définition simple |
|---|---|
| Portefeuille | Ensemble versionné des œuvres attribuées au périmètre institutionnel. |
| Scope | Règle qui détermine quelles institutions OpenAlex appartiennent au portefeuille. |
| Lineage | Institution racine et institutions descendantes incluses dans la hiérarchie OpenAlex. |
| Vintage | Date du snapshot de données effectivement observé. |
| Cutoff | Date après laquelle aucune observation ne peut servir à détecter le signal. |
| Fenêtre courante | Période la plus récente examinée au cutoff. |
| Baseline | Période ou population servant de référence. |
| Subfield / Field | Niveaux parents du topic dans la hiérarchie OpenAlex (252 sous-domaines, 26 champs). |
| Corroboration multi-échelle | Confirmation, isolement ou contradiction du mouvement d’un topic par la direction de son sous-domaine parent. |
| Observation | Donnée source normalisée : œuvre, citation ou relation. |
| Assessment | Examen complet d’un sujet, qu’il aboutisse ou non à un signal. |
| Abstention | Décision explicite de ne pas détecter, avec un motif conservé. |
| Candidat | Assessment qui franchit toutes les conditions minimales. |
| Signal | Candidat documenté, classé et relié à ses preuves. |
| Confiance | Qualité et solidité de la preuve disponible. |
| Priorité | Ordre de lecture au sein d’un détecteur, pas une probabilité. |
| Tier éditorial | Étiquette interne de mise en avant ; l’interface affiche désormais la composition par confiance plutôt que ce drapeau. |
| Preuve | Donnée permettant de vérifier le calcul et son rattachement au périmètre. |
| Outcome | Résultat observé après le signal, dans un objet séparé. |
| Reconstruction rétrospective | Replay historique effectué avec un snapshot actuel, en excluant les données datées après chaque cutoff. |

---

## 9. La logique des trois détecteurs en une phrase chacun

- **Topic Momentum** : comparer, topic par topic, deux fenêtres de douze mois en volume et en part du portefeuille, vérifier le mouvement dans l’histoire du topic, puis le corroborer par la direction de son sous-domaine parent.
- **Citation Acceleration** : comparer deux vitesses annuelles de citation et retenir seulement les accélérations situées parmi les plus fortes d’œuvres de même type, âge et domaine.
- **Actor & Collaboration Novelty** : transformer les affiliations OpenAlex en relations institutionnelles vérifiées, puis détecter leur apparition ou leur retour après 36 mois d’absence.

En résumé, le pipeline ne cherche pas à automatiser un jugement final. Il automatise la partie la plus répétitive et la plus vérifiable de la veille : **délimiter, compter, comparer, filtrer, documenter et remettre les résultats à un lecteur humain avec leur contexte et leurs limites**.
