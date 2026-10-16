import { createContext, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";

export type Lang = "fr" | "en";

type Dict = Record<string, string>;

// Chaînes d'interface. Les libellés de données (noms de topics, titres d'œuvres)
// viennent d'OpenAlex et ne sont pas traduits.
const FR: Dict = {
  "app.eyebrow": "Radar de signaux de recherche · vue locale",
  "header.scope": "Périmètre",
  "header.cutoff": "Publications jusqu’au",
  "header.collected": "Données OpenAlex collectées le",
  "header.themes": "Thèmes en mouvement",
  "header.works": "Œuvres qui accélèrent",
  "header.actors": "Nouveaux acteurs / liens",
  "lang.switch": "Langue",
  "lang.fr": "FR",
  "lang.en": "EN",

  "warning.title": "Comment lire cette vue.",
  "warning.body":
    "Trois « détecteurs » repèrent des changements inhabituels dans la production scientifique de l’institution. Chaque changement est un signal, accompagné des œuvres qui le justifient. L’analyse est reconstituée après coup à partir d’un jeu de données figé — elle éclaire des mouvements à investiguer, elle ne prédit rien.",

  "help.summary": "Comment lire les indicateurs",
  "help.salient.term": "Signal saillant",
  "help.salient.def":
    "Un signal est émis quand un thème change nettement entre deux fenêtres de 12 mois : le nombre de publications ET la part du thème dans le portefeuille varient dans le même sens, au-delà de seuils fixés (au moins 5 publications sur la fenêtre, hausse ou baisse d’au moins 50 % du volume et de 25 % de la part). Un thème stable ou trop petit n’émet pas de signal.",
  "help.priority.term": "Priorité",
  "help.priority.def":
    "Ordonne les signaux d’un même détecteur, du plus au moins saillant (0 à 1). Elle combine l’ampleur du mouvement, sa rareté par rapport à l’historique du thème, sa répétition dans le temps et la taille de l’échantillon. Ce n’est ni une probabilité, ni une mesure d’importance scientifique.",
  "help.confidence.term": "Confiance",
  "help.confidence.def":
    "Solidité du signal : taille de l’échantillon, couverture des thèmes, constance dans le temps et stabilité sous d’autres seuils. Élevée, Moyenne ou Faible.",
  "help.corroboration.term": "Corroboration",
  "help.corroboration.def":
    "Le sous-domaine parent bouge-t-il dans le même sens ? Confirmé (preuve convergente entre échelles), Isolé (émergence focalisée, sous-domaine stable), Contredit (probable artefact de petit effectif, à vérifier).",

  "detector.topic_momentum.name": "Dynamique des thèmes",
  "detector.citation_acceleration.name": "Accélération des citations",
  "detector.actor_collaboration_novelty.name": "Nouveaux acteurs et collaborations",
  "detector.topic_momentum.desc":
    "Repère les thèmes dont le volume et la part dans le portefeuille évoluent de façon inhabituelle.",
  "detector.citation_acceleration.desc":
    "Repère les travaux dont les citations progressent plus vite que celles de travaux comparables.",
  "detector.actor_collaboration_novelty.desc":
    "Repère les partenaires externes et les liens institutionnels qui apparaissent ou reviennent.",

  "detector.signals": "signaux",
  "conf.compo.high": "Confiance élevée",
  "conf.compo.medium": "Confiance moyenne",
  "conf.compo.low": "Confiance faible",

  "tab.flux": "Flux — signaux de mouvement",
  "tab.stock": "Stock — plus gros thèmes",

  "feed.title": "Flux des signaux",
  "feed.subtitle": "Triés par priorité, propre à chaque détecteur",
  "feed.empty": "Aucun signal ne correspond aux filtres courants.",
  "feed.detail_empty": "Sélectionnez un signal pour voir son dossier.",

  "filter.detector": "Détecteur",
  "filter.detector.all": "Tous",
  "filter.change": "Type de changement",
  "filter.change.all": "Tous les types",
  "filter.confidence": "Confiance",
  "filter.confidence.all": "Toutes",
  "filter.corroboration": "Corroboration",
  "filter.corroboration.all": "Toutes",
  "filter.search": "Recherche",
  "filter.search.placeholder": "Titre, sujet ou type de changement…",
  "filter.reset": "Réinitialiser",

  "conf.HIGH": "Élevée",
  "conf.MEDIUM": "Moyenne",
  "conf.LOW": "Faible",
  "conf.VERY_LOW": "Très faible",
  "conf.absent": "Absente",

  "card.detector": "Détecteur",
  "card.priority": "Priorité",
  "card.confidence": "Confiance",

  "dossier.eyebrow": "Dossier du signal",
  "dossier.why": "Pourquoi c’est inhabituel",
  "dossier.info_absent": "Information absente.",
  "dossier.priority": "Priorité",
  "dossier.confidence": "Confiance",
  "dossier.change": "Type de changement",
  "dossier.review":
    "Revue humaine recommandée avant publication",
  "dossier.metrics": "Mesures",
  "dossier.docs": "Œuvres représentatives",
  "dossier.docs_absent": "Aucune œuvre représentative dans ce dossier.",
  "dossier.flags": "À garder en tête",
  "dossier.flags_none": "Aucune réserve particulière signalée.",
  "dossier.tech": "Références techniques (traçabilité)",
  "tech.signal_id": "Identifiant du signal",
  "tech.change_code": "Code du type de changement",
  "tech.detector_version": "Détecteur (version)",
  "tech.code_version": "Version du code",
  "tech.cutoff": "Cutoff exact",
  "tech.collected": "Collecte des données",
  "tech.method": "Méthode",
  "tech.bundle": "Dossier de preuve",
  "tech.evidence": "Preuves (identifiants source)",
  "tech.bundle_full": "Dossier de preuve complet (JSON)",
  "value.absent": "Absente",
  "value.absent_m": "Absent",
  "value.yes": "Oui",
  "value.no": "Non",

  "ctx.topic.copy":
    "Publications et part du portefeuille : période étudiée comparée à la même période un an plus tôt.",
  "ctx.topic.chart_pub": "Publications par fenêtre",
  "ctx.topic.chart_share": "Part du portefeuille",
  "ctx.window.studied": "Période étudiée",
  "ctx.window.year_before": "Un an plus tôt",
  "ctx.window.previous": "Fenêtre précédente",
  "ctx.citation.copy":
    "Citations reçues sur la période étudiée, comparées à la fenêtre précédente et à leur évolution mensuelle.",
  "ctx.citation.chart_win": "Citations par fenêtre",
  "ctx.citation.chart_month": "Citations observées par mois",
  "ctx.actor.copy":
    "Lien observé entre l’unité interne et le partenaire externe dans le portefeuille.",
  "ctx.actor.relation": "Relation institutionnelle observée",
  "ctx.actor.internal": "Unité interne",
  "ctx.actor.external": "Partenaire externe",
  "ctx.actor.publications": "publications",
  "ctx.actor.chart_rel": "Publications matérialisant la relation",
  "ctx.data_absent": "Données de comparaison absentes.",
  "ctx.timeline_absent": "Chronologie absente dans le dossier de preuve.",
  "ctx.eval_date": "Fenêtres arrêtées à la date d’évaluation :",

  "metric.topic.current": "Publications, période étudiée",
  "metric.topic.reference": "Publications, un an plus tôt",
  "metric.topic.current_share": "Part du portefeuille, période étudiée",
  "metric.topic.reference_share": "Part du portefeuille, un an plus tôt",
  "metric.topic.percentile": "Rang historique (percentile)",
  "metric.topic.streak": "Trimestres consécutifs dans cette direction",
  "metric.cit.current": "Citations, période étudiée",
  "metric.cit.previous": "Citations, fenêtre précédente",
  "metric.cit.delta": "Écart de citations",
  "metric.cit.ratio": "Ratio d’accélération",
  "metric.cit.cohort_pct": "Rang dans les travaux comparables (percentile)",
  "metric.cit.cohort_size": "Nombre de travaux comparables",
  "metric.acn.works": "Publications soutenant le lien",
  "metric.acn.months": "Mois avec activité",
  "metric.acn.recent": "Publications, période de comparaison récente",
  "metric.acn.older": "Publications, historique plus ancien",
  "metric.acn.topics": "Thèmes distincts",
  "metric.acn.pairs": "Paires d’auteurs distinctes (au moins)",

  "stock.title": "Plus gros thèmes du portefeuille",
  "stock.summary": "{count} thèmes · {rising} en hausse · {falling} en recul",
  "stock.intro":
    "Classés par volume total de publications sur la période (vue « stock »). La pastille indique la tendance récente (vue « flux ») : un gros thème peut reculer, un thème moyen être en forte hausse. Un thème souligné a un signal — cliquez pour l’ouvrir.",
  "stock.unavailable":
    "Vue stock indisponible : régénérez le bundle pour inclure les plus gros thèmes.",
  "stock.meta": "{count} publications (période) · {current} sur les 12 derniers mois",

  "dir.RISING": "Hausse",
  "dir.FALLING": "Recul",
  "dir.STABLE": "Stable",
  "dir.RISING.long": "en hausse",
  "dir.FALLING.long": "en recul",
  "dir.STABLE.long": "stable",
  "dir.UNDETERMINED.long": "indéterminé",

  "label.RISING": "Hausse",
  "label.FALLING": "Recul",
  "label.BREAKOUT": "Décollage",
  "label.ACCELERATING": "Accélération",
  "label.NEW_EXTERNAL_ACTOR": "Nouveau partenaire",
  "label.REACTIVATED_EXTERNAL_ACTOR": "Partenaire de retour",
  "label.NEW_COLLABORATION": "Nouvelle collaboration",
  "label.REACTIVATED_COLLABORATION": "Collaboration relancée",
  "labeldesc.RISING": "Hausse inhabituelle du thème",
  "labeldesc.FALLING": "Recul inhabituel du thème",
  "labeldesc.BREAKOUT": "Décollage des citations",
  "labeldesc.ACCELERATING": "Accélération des citations",
  "labeldesc.NEW_EXTERNAL_ACTOR": "Nouveau partenaire externe",
  "labeldesc.REACTIVATED_EXTERNAL_ACTOR": "Partenaire externe de retour",
  "labeldesc.NEW_COLLABORATION": "Nouvelle collaboration",
  "labeldesc.REACTIVATED_COLLABORATION": "Collaboration relancée",

  "scale.badge.CORROBORATED": "Confirmé",
  "scale.badge.ISOLATED_WITHIN_PARENT": "Isolé",
  "scale.badge.CONTRADICTED": "Contredit",
  "scale.opt.CORROBORATED": "Confirmé par le sous-domaine",
  "scale.opt.ISOLATED_WITHIN_PARENT": "Isolé dans son sous-domaine",
  "scale.opt.CONTRADICTED": "Contredit par le sous-domaine",
  "scale.sentence.CORROBORATED":
    "Confirmé à l’échelle supérieure : le sous-domaine évolue dans le même sens — signal le plus solide.",
  "scale.sentence.ISOLATED_WITHIN_PARENT":
    "Isolé dans son sous-domaine, qui reste stable : émergence focalisée, réelle mais localisée.",
  "scale.sentence.CONTRADICTED":
    "Contredit par son sous-domaine, qui évolue en sens opposé : probable artefact de petit effectif, à vérifier.",
  "scale.subfield": "sous-domaine :",

  "scope.lineage": "l’institution et les unités rattachées dans sa généalogie",
  "scope.exact": "l’institution au sens strict",
  "temporal.retrospective_reconstruction":
    "analyse reconstituée après coup à partir d’un jeu de données collecté ultérieurement.",
  "temporal.observed_vintage":
    "analyse produite à partir du jeu de données observé à cette date.",

  "flag.WEAK_SAMPLE_SUPPORT": "Effectif faible : peu d’œuvres soutiennent ce signal.",
  "flag.ADEQUATE_SAMPLE_SUPPORT": "Effectif suffisant pour interpréter le signal.",
  "flag.STRONG_SAMPLE_SUPPORT": "Effectif solide.",
  "flag.LOW_TOPIC_COVERAGE": "Beaucoup d’œuvres sans thème attribué (couverture faible).",
  "flag.HIGH_TOPIC_COVERAGE": "La quasi-totalité des œuvres ont un thème attribué.",
  "flag.INCOMPLETE_WINDOW": "La période d’analyse est incomplète.",
  "flag.SINGLE_EVALUATION_DIRECTION": "Direction observée sur une seule évaluation.",
  "flag.MULTI_EVALUATION_DIRECTION": "Direction confirmée sur plusieurs évaluations.",
  "flag.NO_SUSTAINED_DIRECTION": "La direction n’est pas soutenue dans le temps.",
  "flag.HIGH_PARAMETER_SENSITIVITY":
    "Résultat instable : le sens du signal change selon les seuils choisis.",
  "flag.PARTIAL_PARAMETER_SENSITIVITY": "Signal en partie sensible au choix des seuils.",
  "flag.STABLE_ACROSS_PARAMETER_PROFILES": "Signal stable sous plusieurs jeux de seuils.",
  "flag.RETROSPECTIVE_TAXONOMY_PROJECTION":
    "Thème projeté avec la taxonomie OpenAlex de 2026 (reconstruction).",
  "flag.TAXONOMY_CHANGE_DURING_OBSERVED_BASELINE":
    "La définition du thème a changé pendant la période de référence.",
  "flag.SCALE_CORROBORATED": "Confirmé par le sous-domaine parent (mouvement convergent).",
  "flag.SCALE_CONTRADICTED":
    "Contredit par le sous-domaine parent : probable artefact de petit effectif.",
  "flag.SCOPE_EVIDENCE_PARTIALLY_MATERIALIZED":
    "Rattachement à l’institution seulement partiellement visible dans les métadonnées.",
  "flag.NO_LOCALLY_VERIFIED_SCOPE_EVIDENCE":
    "Aucune œuvre dont le rattachement à l’institution est vérifié localement.",
  "flag.EVIDENCE_COUNT_MISMATCH": "Écart entre le décompte agrégé et les œuvres détaillées.",
  "flag.UNRESOLVED_AUTHOR_ID": "Certains auteurs ne sont pas identifiés de façon unique.",
  "flag.UNRESOLVED_AUTHOR_IDENTITIES_IN_REPRESENTATIVE_WORKS":
    "Certains auteurs des œuvres représentatives ne sont pas identifiés de façon unique.",
  "flag.INSTITUTION_MATCH_NOT_MATERIALIZED":
    "Rattachement affirmé par le filtre OpenAlex mais non visible dans les métadonnées de l’œuvre.",
  "flag.RETROSPECTIVE_RECONSTRUCTION":
    "Analyse reconstituée après coup à partir de données collectées plus tard.",
  "flag.generic": "Point technique : {code}",

  "status.loading.title": "Chargement",
  "status.loading.body": "Lecture du bundle statique du POC…",
  "status.error.title": "Erreur",
  "load.failed": "Chargement impossible ({status})",
  "load.unknown": "Erreur inconnue pendant le chargement du bundle.",
};

const EN: Dict = {
  "app.eyebrow": "Research signal radar · local view",
  "header.scope": "Scope",
  "header.cutoff": "Publications up to",
  "header.collected": "OpenAlex data collected on",
  "header.themes": "Themes on the move",
  "header.works": "Works accelerating",
  "header.actors": "New actors / links",
  "lang.switch": "Language",
  "lang.fr": "FR",
  "lang.en": "EN",

  "warning.title": "How to read this view.",
  "warning.body":
    "Three “detectors” spot unusual changes in the institution’s research output. Each change is a signal, backed by the works that justify it. The analysis is reconstructed after the fact from a frozen dataset — it highlights movements to investigate, it predicts nothing.",

  "help.summary": "How to read the indicators",
  "help.salient.term": "Salient signal",
  "help.salient.def":
    "A signal is emitted when a theme changes markedly between two 12-month windows: both the number of publications AND the theme’s share of the portfolio move in the same direction, beyond set thresholds (at least 5 publications in the window, a rise or fall of at least 50% in volume and 25% in share). A stable or too-small theme emits no signal.",
  "help.priority.term": "Priority",
  "help.priority.def":
    "Ranks the signals of a single detector, from most to least salient (0 to 1). It combines the size of the movement, its rarity relative to the theme’s history, its repetition over time and the sample size. It is neither a probability nor a measure of scientific importance.",
  "help.confidence.term": "Confidence",
  "help.confidence.def":
    "How solid the signal is: sample size, topic coverage, consistency over time and stability under other thresholds. High, Medium or Low.",
  "help.corroboration.term": "Corroboration",
  "help.corroboration.def":
    "Does the parent subfield move in the same direction? Corroborated (converging evidence across scales), Isolated (focused emergence, stable subfield), Contradicted (likely small-sample artefact, to be checked).",

  "detector.topic_momentum.name": "Theme dynamics",
  "detector.citation_acceleration.name": "Citation acceleration",
  "detector.actor_collaboration_novelty.name": "New actors and collaborations",
  "detector.topic_momentum.desc":
    "Spots themes whose volume and share of the portfolio change in an unusual way.",
  "detector.citation_acceleration.desc":
    "Spots works whose citations grow faster than those of comparable works.",
  "detector.actor_collaboration_novelty.desc":
    "Spots external partners and institutional links that appear or reappear.",

  "detector.signals": "signals",
  "conf.compo.high": "High confidence",
  "conf.compo.medium": "Medium confidence",
  "conf.compo.low": "Low confidence",

  "tab.flux": "Flow — movement signals",
  "tab.stock": "Stock — largest themes",

  "feed.title": "Signal flow",
  "feed.subtitle": "Sorted by priority, specific to each detector",
  "feed.empty": "No signal matches the current filters.",
  "feed.detail_empty": "Select a signal to see its dossier.",

  "filter.detector": "Detector",
  "filter.detector.all": "All",
  "filter.change": "Type of change",
  "filter.change.all": "All types",
  "filter.confidence": "Confidence",
  "filter.confidence.all": "All",
  "filter.corroboration": "Corroboration",
  "filter.corroboration.all": "All",
  "filter.search": "Search",
  "filter.search.placeholder": "Title, subject or type of change…",
  "filter.reset": "Reset",

  "conf.HIGH": "High",
  "conf.MEDIUM": "Medium",
  "conf.LOW": "Low",
  "conf.VERY_LOW": "Very low",
  "conf.absent": "Absent",

  "card.detector": "Detector",
  "card.priority": "Priority",
  "card.confidence": "Confidence",

  "dossier.eyebrow": "Signal dossier",
  "dossier.why": "Why it is unusual",
  "dossier.info_absent": "Information missing.",
  "dossier.priority": "Priority",
  "dossier.confidence": "Confidence",
  "dossier.change": "Type of change",
  "dossier.review": "Human review recommended before publication",
  "dossier.metrics": "Measures",
  "dossier.docs": "Representative works",
  "dossier.docs_absent": "No representative work in this dossier.",
  "dossier.flags": "Worth keeping in mind",
  "dossier.flags_none": "No particular caveat flagged.",
  "dossier.tech": "Technical references (traceability)",
  "tech.signal_id": "Signal identifier",
  "tech.change_code": "Change-type code",
  "tech.detector_version": "Detector (version)",
  "tech.code_version": "Code version",
  "tech.cutoff": "Exact cutoff",
  "tech.collected": "Data collection",
  "tech.method": "Method",
  "tech.bundle": "Evidence bundle",
  "tech.evidence": "Evidence (source identifiers)",
  "tech.bundle_full": "Full evidence bundle (JSON)",
  "value.absent": "Absent",
  "value.absent_m": "Absent",
  "value.yes": "Yes",
  "value.no": "No",

  "ctx.topic.copy":
    "Publications and portfolio share: studied period compared with the same period a year earlier.",
  "ctx.topic.chart_pub": "Publications per window",
  "ctx.topic.chart_share": "Portfolio share",
  "ctx.window.studied": "Studied period",
  "ctx.window.year_before": "A year earlier",
  "ctx.window.previous": "Previous window",
  "ctx.citation.copy":
    "Citations received over the studied period, compared with the previous window and their monthly evolution.",
  "ctx.citation.chart_win": "Citations per window",
  "ctx.citation.chart_month": "Citations observed per month",
  "ctx.actor.copy":
    "Link observed between the internal unit and the external partner in the portfolio.",
  "ctx.actor.relation": "Observed institutional relationship",
  "ctx.actor.internal": "Internal unit",
  "ctx.actor.external": "External partner",
  "ctx.actor.publications": "publications",
  "ctx.actor.chart_rel": "Publications materialising the link",
  "ctx.data_absent": "Comparison data missing.",
  "ctx.timeline_absent": "Timeline missing from the evidence bundle.",
  "ctx.eval_date": "Windows closed at the evaluation date:",

  "metric.topic.current": "Publications, studied period",
  "metric.topic.reference": "Publications, a year earlier",
  "metric.topic.current_share": "Portfolio share, studied period",
  "metric.topic.reference_share": "Portfolio share, a year earlier",
  "metric.topic.percentile": "Historical rank (percentile)",
  "metric.topic.streak": "Consecutive quarters in this direction",
  "metric.cit.current": "Citations, studied period",
  "metric.cit.previous": "Citations, previous window",
  "metric.cit.delta": "Citation gap",
  "metric.cit.ratio": "Acceleration ratio",
  "metric.cit.cohort_pct": "Rank among comparable works (percentile)",
  "metric.cit.cohort_size": "Number of comparable works",
  "metric.acn.works": "Publications backing the link",
  "metric.acn.months": "Months with activity",
  "metric.acn.recent": "Publications, recent comparison period",
  "metric.acn.older": "Publications, older history",
  "metric.acn.topics": "Distinct themes",
  "metric.acn.pairs": "Distinct author pairs (at least)",

  "stock.title": "Largest themes in the portfolio",
  "stock.summary": "{count} themes · {rising} rising · {falling} declining",
  "stock.intro":
    "Ranked by total publication volume over the period (“stock” view). The pill shows the recent trend (“flow” view): a large theme may be declining, a mid-sized one strongly rising. An underlined theme has a signal — click to open it.",
  "stock.unavailable":
    "Stock view unavailable: regenerate the bundle to include the largest themes.",
  "stock.meta": "{count} publications (period) · {current} in the last 12 months",

  "dir.RISING": "Rising",
  "dir.FALLING": "Declining",
  "dir.STABLE": "Stable",
  "dir.RISING.long": "rising",
  "dir.FALLING.long": "declining",
  "dir.STABLE.long": "stable",
  "dir.UNDETERMINED.long": "undetermined",

  "label.RISING": "Rising",
  "label.FALLING": "Declining",
  "label.BREAKOUT": "Breakout",
  "label.ACCELERATING": "Accelerating",
  "label.NEW_EXTERNAL_ACTOR": "New partner",
  "label.REACTIVATED_EXTERNAL_ACTOR": "Returning partner",
  "label.NEW_COLLABORATION": "New collaboration",
  "label.REACTIVATED_COLLABORATION": "Revived collaboration",
  "labeldesc.RISING": "Unusual rise of the theme",
  "labeldesc.FALLING": "Unusual decline of the theme",
  "labeldesc.BREAKOUT": "Citation breakout",
  "labeldesc.ACCELERATING": "Citation acceleration",
  "labeldesc.NEW_EXTERNAL_ACTOR": "New external partner",
  "labeldesc.REACTIVATED_EXTERNAL_ACTOR": "Returning external partner",
  "labeldesc.NEW_COLLABORATION": "New collaboration",
  "labeldesc.REACTIVATED_COLLABORATION": "Revived collaboration",

  "scale.badge.CORROBORATED": "Corroborated",
  "scale.badge.ISOLATED_WITHIN_PARENT": "Isolated",
  "scale.badge.CONTRADICTED": "Contradicted",
  "scale.opt.CORROBORATED": "Corroborated by the subfield",
  "scale.opt.ISOLATED_WITHIN_PARENT": "Isolated within its subfield",
  "scale.opt.CONTRADICTED": "Contradicted by the subfield",
  "scale.sentence.CORROBORATED":
    "Corroborated at the higher scale: the subfield moves the same way — the strongest signal.",
  "scale.sentence.ISOLATED_WITHIN_PARENT":
    "Isolated within its subfield, which stays stable: focused emergence, real but localised.",
  "scale.sentence.CONTRADICTED":
    "Contradicted by its subfield, which moves the opposite way: likely small-sample artefact, to be checked.",
  "scale.subfield": "subfield:",

  "scope.lineage": "the institution and the units attached in its lineage",
  "scope.exact": "the institution in the strict sense",
  "temporal.retrospective_reconstruction":
    "analysis reconstructed after the fact from a dataset collected later.",
  "temporal.observed_vintage":
    "analysis produced from the dataset observed at that date.",

  "flag.WEAK_SAMPLE_SUPPORT": "Small sample: few works back this signal.",
  "flag.ADEQUATE_SAMPLE_SUPPORT": "Sample large enough to interpret the signal.",
  "flag.STRONG_SAMPLE_SUPPORT": "Solid sample.",
  "flag.LOW_TOPIC_COVERAGE": "Many works without an assigned theme (low coverage).",
  "flag.HIGH_TOPIC_COVERAGE": "Almost all works have an assigned theme.",
  "flag.INCOMPLETE_WINDOW": "The analysis window is incomplete.",
  "flag.SINGLE_EVALUATION_DIRECTION": "Direction seen on a single evaluation.",
  "flag.MULTI_EVALUATION_DIRECTION": "Direction confirmed over several evaluations.",
  "flag.NO_SUSTAINED_DIRECTION": "The direction is not sustained over time.",
  "flag.HIGH_PARAMETER_SENSITIVITY":
    "Unstable result: the signal’s direction changes with the chosen thresholds.",
  "flag.PARTIAL_PARAMETER_SENSITIVITY": "Signal partly sensitive to threshold choices.",
  "flag.STABLE_ACROSS_PARAMETER_PROFILES": "Signal stable under several threshold sets.",
  "flag.RETROSPECTIVE_TAXONOMY_PROJECTION":
    "Theme projected with the 2026 OpenAlex taxonomy (reconstruction).",
  "flag.TAXONOMY_CHANGE_DURING_OBSERVED_BASELINE":
    "The theme’s definition changed during the reference period.",
  "flag.SCALE_CORROBORATED": "Corroborated by the parent subfield (converging movement).",
  "flag.SCALE_CONTRADICTED":
    "Contradicted by the parent subfield: likely small-sample artefact.",
  "flag.SCOPE_EVIDENCE_PARTIALLY_MATERIALIZED":
    "Institutional attachment only partly visible in the metadata.",
  "flag.NO_LOCALLY_VERIFIED_SCOPE_EVIDENCE":
    "No work whose institutional attachment is locally verified.",
  "flag.EVIDENCE_COUNT_MISMATCH": "Gap between the aggregate count and the detailed works.",
  "flag.UNRESOLVED_AUTHOR_ID": "Some authors are not uniquely identified.",
  "flag.UNRESOLVED_AUTHOR_IDENTITIES_IN_REPRESENTATIVE_WORKS":
    "Some authors of the representative works are not uniquely identified.",
  "flag.INSTITUTION_MATCH_NOT_MATERIALIZED":
    "Attachment asserted by the OpenAlex filter but not visible in the work’s metadata.",
  "flag.RETROSPECTIVE_RECONSTRUCTION":
    "Analysis reconstructed after the fact from data collected later.",
  "flag.generic": "Technical point: {code}",

  "status.loading.title": "Loading",
  "status.loading.body": "Reading the POC’s static bundle…",
  "status.error.title": "Error",
  "load.failed": "Loading failed ({status})",
  "load.unknown": "Unknown error while loading the bundle.",
};

const MESSAGES: Record<Lang, Dict> = { fr: FR, en: EN };

export type Translate = (key: string, params?: Record<string, string | number>) => string;

function translate(lang: Lang, key: string, params?: Record<string, string | number>): string {
  let value = MESSAGES[lang][key] ?? MESSAGES.fr[key] ?? key;
  if (params) {
    for (const [name, replacement] of Object.entries(params)) {
      value = value.replace(new RegExp(`\\{${name}\\}`, "g"), String(replacement));
    }
  }
  return value;
}

interface LangContextValue {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: Translate;
}

const LangContext = createContext<LangContextValue | null>(null);

export function LangProvider({
  children,
  initialLang = "fr",
}: {
  children: ReactNode;
  initialLang?: Lang;
}) {
  const [lang, setLang] = useState<Lang>(initialLang);
  const value = useMemo<LangContextValue>(
    () => ({ lang, setLang, t: (key, params) => translate(lang, key, params) }),
    [lang],
  );
  return <LangContext.Provider value={value}>{children}</LangContext.Provider>;
}

export function useI18n(): LangContextValue {
  const context = useContext(LangContext);
  if (!context) {
    // Repli hors provider (utile pour des tests unitaires ciblés).
    return { lang: "fr", setLang: () => {}, t: (key, params) => translate("fr", key, params) };
  }
  return context;
}

export function LanguageSwitch() {
  const { lang, setLang, t } = useI18n();
  return (
    <div className="lang-switch" role="group" aria-label={t("lang.switch")}>
      {(["fr", "en"] as Lang[]).map((code) => (
        <button
          key={code}
          type="button"
          className={`lang-button ${lang === code ? "active" : ""}`}
          aria-pressed={lang === code}
          onClick={() => setLang(code)}
        >
          {t(`lang.${code}`)}
        </button>
      ))}
    </div>
  );
}
