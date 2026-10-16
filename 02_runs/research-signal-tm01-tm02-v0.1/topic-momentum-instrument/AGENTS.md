# Research Signal — instructions pour le POC

## Mission

Construire une première verticale d'interface démontrable à partir des sorties
existantes des trois détecteurs :

1. `topic_momentum` ;
2. `citation_acceleration` ;
3. `actor_collaboration_novelty`.

Lire intégralement `handoff/POC_BRIEF.md` avant de modifier le projet.

## Source de vérité

- Les contrats dans `contracts/` définissent la sémantique.
- Les `SignalEnvelope` et bundles de preuves déjà produits définissent les
  données réellement disponibles.
- Les scores, labels, niveaux de confiance, tiers éditoriaux et outcomes sont
  calculés par l'instrument Python. L'interface les affiche ; elle ne les
  recalcule pas et ne les réinterprète pas silencieusement.

## Périmètre autorisé

Créer ou modifier uniquement :

- `ui/` pour l'application ;
- `scripts/build_poc_bundle.py` pour préparer les données de l'interface ;
- les tests directement liés à cet adaptateur et à l'interface ;
- la documentation du POC.

Ne pas modifier sans demande explicite :

- `src/research_signal/tm*.py` ;
- `src/research_signal/ca*.py` ;
- `src/research_signal/acn*.py` ;
- `contracts/` ;
- les configurations et seuils des détecteurs ;
- les artefacts d'un run existant.

## Contraintes d'architecture

- Application locale, desktop-first, en lecture seule.
- React + TypeScript + Vite dans `ui/`.
- Pas de backend applicatif, base de données, authentification, API live,
  conteneurisation ou orchestration.
- Aucun appel OpenAlex, OpenCitations ou LLM depuis l'interface.
- Les `.jsonl.gz` sont transformés avant le lancement du front par un script
  Python déterministe utilisant uniquement la bibliothèque standard.
- Le navigateur charge un bundle JSON statique généré dans `ui/public/data/`.
- Le bundle généré est un artefact dérivé : ne pas committer de données de run
  volumineuses ou sensibles.
- Limiter les dépendances front. Une bibliothèque de graphiques légère est
  acceptable si elle apporte une visualisation réellement utile.

## Règles produit et éditoriales

- Interface en français.
- Employer « signal », « preuve », « cutoff », « confiance » et « priorité »
  avec leur sens contractuel.
- Ne jamais présenter la priorité comme une probabilité.
- `NEW_*` signifie nouveau dans l'historique observable du portefeuille, pas
  nouveau dans le monde académique.
- `CONTINUED` signifie persistance opérationnelle à douze mois, pas importance
  scientifique.
- Toujours rendre visibles le scope, le cutoff, le vintage et le mode
  `retrospective_reconstruction` lorsqu'ils sont disponibles.
- Une donnée absente doit produire un état explicite, jamais une valeur
  inventée.
- Pas de prédiction « likely next developments » dans ce POC.

## Méthode de travail

1. Inspecter les schémas et un petit échantillon de chaque artefact avant de
   coder l'adaptateur.
2. Écrire l'adaptateur et ses tests avant de construire les vues.
3. Conserver les IDs sources dans le bundle afin que chaque vue puisse remonter
   au signal et à son bundle de preuves.
4. Implémenter d'abord le parcours principal décrit dans le brief.
5. Vérifier les états vide, chargement, erreur et données partielles.
6. Exécuter les tests et un build de production avant de déclarer le POC fini.

## Définition de terminé

Le travail s'arrête lorsque les critères d'acceptation du brief sont satisfaits.
Ne pas étendre spontanément le projet à une plateforme générique, une seconde
institution, un topic explorer, une ingestion temps réel ou un système de
comptes.

