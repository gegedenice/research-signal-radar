from __future__ import annotations

import json
import calendar
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .errors import ConfigurationError


PUBLISHED_CORE_TYPES = (
    "article",
    "review",
    "conference-paper",
    "book",
    "book-chapter",
    "data-paper",
    "software-paper",
    "report",
)

_ROR_RE = re.compile(r"^(?:https?://ror\.org/)?([0-9a-z]{9})$", re.IGNORECASE)
_ALLOWED_SCOPES = {"exact", "lineage", "curated_set"}


def normalize_ror(value: str) -> str:
    match = _ROR_RE.match(value.strip())
    if not match:
        raise ConfigurationError(f"invalid ROR identifier: {value!r}")
    return match.group(1).lower()


def parse_date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ConfigurationError(f"{field} must be an ISO date: {value!r}") from exc


def parse_datetime(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ConfigurationError(f"{field} must be an ISO datetime: {value!r}") from exc
    if parsed.tzinfo is None:
        raise ConfigurationError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class OpenAlexConfig:
    base_url: str
    api_key_env: str
    timeout_seconds: float
    max_retries: int
    user_agent: str


@dataclass(frozen=True)
class OpenCitationsConfig:
    base_url: str
    api_key_env: str
    timeout_seconds: float
    max_retries: int
    user_agent: str
    requests_per_minute: int


@dataclass(frozen=True)
class UniverseConfig:
    id: str
    label: str
    version: int
    root_ror: str
    scope_modes: tuple[str, ...]
    curated_institution_ids: tuple[str, ...]
    excluded_institution_ids: tuple[str, ...]


@dataclass(frozen=True)
class StreamConfig:
    id: str
    types: tuple[str, ...]
    corpus: str
    has_abstract_filter: bool
    counting_method: str


@dataclass(frozen=True)
class CollectionConfig:
    from_publication_date: date
    to_publication_date: date
    include_work_observations: bool
    enrich_topics: bool
    group_page_size: int
    work_page_size: int
    strict_group_totals: bool
    strict_work_crosscheck: bool


@dataclass(frozen=True)
class TopicMomentumConfig:
    analysis_window_months: int
    evaluation_step_months: int
    history_min_months: int
    min_total_history: int
    min_current: int
    min_previous: int
    min_active_months: int
    min_abs_delta: int
    rise_count_ratio: float
    fall_count_ratio: float
    rise_share_ratio: float
    fall_share_ratio: float
    acceleration_epsilon: float
    share_epsilon: float
    min_topic_coverage: float
    min_supporting_evaluations: int
    # v0.2 — agrégation multi-échelle (topic + niveaux parents de la taxonomie).
    # scale_levels est une liste (et non un tuple) pour rester égal à sa forme
    # sérialisée JSON, que TM-05..08 comparent après relecture.
    multi_scale: bool = True
    scale_levels: list[str] = field(default_factory=lambda: ["subfield", "field"])


@dataclass(frozen=True)
class CitationAccelerationConfig:
    window_months: int
    min_temporal_coverage: float
    min_cohort_size: int
    age_band_boundaries_months: tuple[int, ...]
    min_recent_citations: int
    min_absolute_delta: int
    min_acceleration_ratio: float
    min_cohort_percentile: float
    headline_priority_threshold: float
    dossier_limit: int
    backtest_start_date: str
    backtest_step_months: int
    outcome_horizon_months: int


@dataclass(frozen=True)
class ActorCollaborationNoveltyConfig:
    current_window_months: int
    recent_baseline_months: int
    min_current_works: int
    min_active_months: int
    min_locally_verified_works: int


@dataclass(frozen=True)
class RunConfig:
    run_id: str
    data_vintage: datetime
    temporal_semantics: str
    output_root: Path
    openalex: OpenAlexConfig
    opencitations: OpenCitationsConfig
    universe: UniverseConfig
    stream: StreamConfig
    collection: CollectionConfig
    topic_momentum: TopicMomentumConfig
    citation_acceleration: CitationAccelerationConfig
    actor_collaboration_novelty: ActorCollaborationNoveltyConfig


def _required(mapping: dict[str, Any], key: str, section: str) -> Any:
    if key not in mapping:
        raise ConfigurationError(f"missing {section}.{key}")
    return mapping[key]


def _reject_embedded_secrets(raw: dict[str, Any]) -> None:
    forbidden = {"api_key", "apikey", "token", "secret", "password"}

    def walk(value: Any, path: str = "") -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                lowered = key.lower()
                if lowered in forbidden or lowered.endswith("_api_key"):
                    raise ConfigurationError(
                        f"embedded secret field {path + key!r} is forbidden; use an environment variable name"
                    )
                walk(item, path + key + ".")
        elif isinstance(value, list):
            for item in value:
                walk(item, path)

    walk(raw)


def load_config(path: str | Path) -> RunConfig:
    config_path = Path(path)
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    _reject_embedded_secrets(raw)

    run = _required(raw, "run", "root")
    oa = _required(raw, "openalex", "root")
    oc = raw.get("opencitations", {})
    universe = _required(raw, "universe", "root")
    stream = _required(raw, "stream", "root")
    collection = _required(raw, "collection", "root")
    momentum = raw.get("topic_momentum", {})
    citation_acceleration = raw.get("citation_acceleration", {})
    actor_collaboration_novelty = raw.get("actor_collaboration_novelty", {})

    start = parse_date(_required(collection, "from_publication_date", "collection"), "collection.from_publication_date")
    end = parse_date(_required(collection, "to_publication_date", "collection"), "collection.to_publication_date")
    if start > end:
        raise ConfigurationError("from_publication_date must not be after to_publication_date")

    scopes = tuple(universe.get("scope_modes", ["lineage", "exact"]))
    unknown_scopes = set(scopes) - _ALLOWED_SCOPES
    if unknown_scopes:
        raise ConfigurationError(f"unsupported scope modes: {sorted(unknown_scopes)}")
    if len(scopes) != len(set(scopes)):
        raise ConfigurationError("scope_modes must be unique")

    curated = tuple(universe.get("curated_institution_ids", []))
    if "curated_set" in scopes and not curated:
        raise ConfigurationError("curated_set requires curated_institution_ids")

    types = tuple(stream.get("types", PUBLISHED_CORE_TYPES))
    if not types or len(types) != len(set(types)):
        raise ConfigurationError("stream.types must be non-empty and unique")
    if bool(stream.get("has_abstract_filter", False)):
        raise ConfigurationError("Topic Momentum census forbids has_abstract_filter=true")
    if stream.get("counting_method", "full_counting") != "full_counting":
        raise ConfigurationError("TM-02 currently implements full_counting only")

    data_vintage_raw = run.get("data_vintage")
    data_vintage = (
        parse_datetime(data_vintage_raw, "run.data_vintage")
        if data_vintage_raw
        else datetime.now(timezone.utc)
    )
    if data_vintage.date() < end:
        raise ConfigurationError("run.data_vintage must not precede to_publication_date")
    temporal_semantics = run.get("temporal_semantics", "retrospective_snapshot")
    if temporal_semantics not in {"retrospective_snapshot", "observed_vintage"}:
        raise ConfigurationError("run.temporal_semantics is unsupported")
    corpus = stream.get("corpus", "core")
    if corpus != "core":
        raise ConfigurationError("TM-02 requires corpus='core' explicitly")
    group_page_size = int(collection.get("group_page_size", 200))
    work_page_size = int(collection.get("work_page_size", 200))
    if not 1 <= group_page_size <= 200:
        raise ConfigurationError("collection.group_page_size must be between 1 and 200")
    if not 1 <= work_page_size <= 200:
        raise ConfigurationError("collection.work_page_size must be between 1 and 200")
    oc_requests_per_minute = int(oc.get("requests_per_minute", 150))
    if not 1 <= oc_requests_per_minute <= 180:
        raise ConfigurationError(
            "opencitations.requests_per_minute must be between 1 and 180"
        )
    run_id = run.get("id") or (
        f"tm-{data_vintage.date().isoformat()}-{universe['id']}-v{universe.get('version', 1)}"
    )
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*$", run_id):
        raise ConfigurationError("run.id contains unsafe path characters")

    analysis_window_months = int(momentum.get("analysis_window_months", 12))
    evaluation_step_months = int(momentum.get("evaluation_step_months", 3))
    history_min_months = int(momentum.get("history_min_months", 36))
    if analysis_window_months < 1:
        raise ConfigurationError("topic_momentum.analysis_window_months must be positive")
    if evaluation_step_months < 1:
        raise ConfigurationError("topic_momentum.evaluation_step_months must be positive")
    if analysis_window_months % evaluation_step_months:
        raise ConfigurationError(
            "topic_momentum.analysis_window_months must be divisible by evaluation_step_months"
        )
    if history_min_months < 3 * analysis_window_months:
        raise ConfigurationError(
            "topic_momentum.history_min_months must cover current, previous and prior windows"
        )

    integer_parameters = {
        "min_total_history": int(momentum.get("min_total_history", 6)),
        "min_current": int(momentum.get("min_current", 3)),
        "min_previous": int(momentum.get("min_previous", 3)),
        "min_active_months": int(momentum.get("min_active_months", 2)),
        "min_abs_delta": int(momentum.get("min_abs_delta", 2)),
        "min_supporting_evaluations": int(momentum.get("min_supporting_evaluations", 2)),
    }
    if any(value < 0 for value in integer_parameters.values()):
        raise ConfigurationError("topic_momentum integer thresholds must be non-negative")
    if integer_parameters["min_active_months"] > analysis_window_months:
        raise ConfigurationError(
            "topic_momentum.min_active_months exceeds analysis_window_months"
        )

    ratio_parameters = {
        "rise_count_ratio": float(momentum.get("rise_count_ratio", 1.5)),
        "fall_count_ratio": float(momentum.get("fall_count_ratio", 0.67)),
        "rise_share_ratio": float(momentum.get("rise_share_ratio", 1.25)),
        "fall_share_ratio": float(momentum.get("fall_share_ratio", 0.8)),
    }
    if any(value <= 0 for value in ratio_parameters.values()):
        raise ConfigurationError("topic_momentum ratio thresholds must be positive")
    acceleration_epsilon = float(momentum.get("acceleration_epsilon", 0.15))
    share_epsilon = float(momentum.get("share_epsilon", 1e-12))
    min_topic_coverage = float(momentum.get("min_topic_coverage", 0.95))
    if acceleration_epsilon < 0 or share_epsilon <= 0:
        raise ConfigurationError("topic_momentum epsilon values are invalid")
    if not 0 <= min_topic_coverage <= 1:
        raise ConfigurationError("topic_momentum.min_topic_coverage must be between 0 and 1")

    multi_scale = bool(momentum.get("multi_scale", True))
    scale_levels = list(momentum.get("scale_levels", ["subfield", "field"]))
    unknown_levels = set(scale_levels) - {"subfield", "field", "domain"}
    if unknown_levels:
        raise ConfigurationError(
            f"topic_momentum.scale_levels unsupported: {sorted(unknown_levels)}"
        )
    if len(scale_levels) != len(set(scale_levels)):
        raise ConfigurationError("topic_momentum.scale_levels must be unique")

    citation_window_months = int(citation_acceleration.get("window_months", 12))
    min_temporal_coverage = float(
        citation_acceleration.get("min_temporal_coverage", 0.75)
    )
    min_cohort_size = int(citation_acceleration.get("min_cohort_size", 20))
    age_band_boundaries = tuple(
        int(item)
        for item in citation_acceleration.get(
            "age_band_boundaries_months", [24, 48, 84]
        )
    )
    min_recent_citations = int(citation_acceleration.get("min_recent_citations", 3))
    min_absolute_delta = int(citation_acceleration.get("min_absolute_delta", 2))
    min_acceleration_ratio = float(
        citation_acceleration.get("min_acceleration_ratio", 1.5)
    )
    min_cohort_percentile = float(
        citation_acceleration.get("min_cohort_percentile", 0.90)
    )
    headline_priority_threshold = float(
        citation_acceleration.get("headline_priority_threshold", 0.82)
    )
    dossier_limit = int(citation_acceleration.get("dossier_limit", 25))
    backtest_start_date = citation_acceleration.get(
        "backtest_start_date", end.isoformat()
    )
    backtest_start = parse_date(
        backtest_start_date, "citation_acceleration.backtest_start_date"
    )
    backtest_step_months = int(
        citation_acceleration.get("backtest_step_months", 6)
    )
    outcome_horizon_months = int(
        citation_acceleration.get("outcome_horizon_months", 12)
    )
    if citation_window_months < 1:
        raise ConfigurationError("citation_acceleration.window_months must be positive")
    if not 0 <= min_temporal_coverage <= 1:
        raise ConfigurationError(
            "citation_acceleration.min_temporal_coverage must be between 0 and 1"
        )
    if min_cohort_size < 2:
        raise ConfigurationError(
            "citation_acceleration.min_cohort_size must be at least 2"
        )
    if (
        not age_band_boundaries
        or any(item < 12 for item in age_band_boundaries)
        or tuple(sorted(set(age_band_boundaries))) != age_band_boundaries
    ):
        raise ConfigurationError(
            "citation_acceleration.age_band_boundaries_months must be sorted, unique and >= 12"
        )
    if min_recent_citations < 1 or min_absolute_delta < 1:
        raise ConfigurationError("citation_acceleration candidate counts must be positive")
    if min_acceleration_ratio <= 1:
        raise ConfigurationError(
            "citation_acceleration.min_acceleration_ratio must exceed 1"
        )
    if not 0 <= min_cohort_percentile <= 1:
        raise ConfigurationError(
            "citation_acceleration.min_cohort_percentile must be between 0 and 1"
        )
    if not 0 <= headline_priority_threshold <= 1:
        raise ConfigurationError(
            "citation_acceleration.headline_priority_threshold must be between 0 and 1"
        )
    if dossier_limit < 1:
        raise ConfigurationError("citation_acceleration.dossier_limit must be positive")
    if backtest_start > end:
        raise ConfigurationError(
            "citation_acceleration.backtest_start_date must not follow the collection cutoff"
        )
    if backtest_start.day != calendar.monthrange(
        backtest_start.year, backtest_start.month
    )[1]:
        raise ConfigurationError(
            "citation_acceleration.backtest_start_date must be a month-end date"
        )
    if backtest_step_months < 1 or outcome_horizon_months < 1:
        raise ConfigurationError(
            "citation_acceleration backtest intervals must be positive"
        )

    acn_current_window_months = int(
        actor_collaboration_novelty.get("current_window_months", 12)
    )
    acn_recent_baseline_months = int(
        actor_collaboration_novelty.get("recent_baseline_months", 36)
    )
    acn_min_current_works = int(
        actor_collaboration_novelty.get("min_current_works", 2)
    )
    acn_min_active_months = int(
        actor_collaboration_novelty.get("min_active_months", 2)
    )
    acn_min_locally_verified_works = int(
        actor_collaboration_novelty.get("min_locally_verified_works", 2)
    )
    if acn_current_window_months < 1 or acn_recent_baseline_months < 1:
        raise ConfigurationError(
            "actor_collaboration_novelty windows must be positive"
        )
    if min(
        acn_min_current_works,
        acn_min_active_months,
        acn_min_locally_verified_works,
    ) < 1:
        raise ConfigurationError(
            "actor_collaboration_novelty candidate thresholds must be positive"
        )
    if acn_min_active_months > acn_current_window_months:
        raise ConfigurationError(
            "actor_collaboration_novelty.min_active_months exceeds current_window_months"
        )

    output_root = Path(run.get("output_root", "runs"))
    if not output_root.is_absolute():
        output_root = (config_path.parent / output_root).resolve()

    return RunConfig(
        run_id=run_id,
        data_vintage=data_vintage,
        temporal_semantics=temporal_semantics,
        output_root=output_root,
        openalex=OpenAlexConfig(
            base_url=oa.get("base_url", "https://api.openalex.org"),
            api_key_env=oa.get("api_key_env", "OPENALEX_API_KEY"),
            timeout_seconds=float(oa.get("timeout_seconds", 30)),
            max_retries=int(oa.get("max_retries", 4)),
            user_agent=oa.get("user_agent", "research-signal-instrument/0.13.0"),
        ),
        opencitations=OpenCitationsConfig(
            base_url=oc.get(
                "base_url", "https://api.opencitations.net/index/v2"
            ),
            api_key_env=oc.get(
                "api_key_env", "OPENCITATIONS_API_KEY"
            ),
            timeout_seconds=float(oc.get("timeout_seconds", 45)),
            max_retries=int(oc.get("max_retries", 4)),
            user_agent=oc.get(
                "user_agent", "research-signal-instrument/0.13.0"
            ),
            requests_per_minute=oc_requests_per_minute,
        ),
        universe=UniverseConfig(
            id=_required(universe, "id", "universe"),
            label=_required(universe, "label", "universe"),
            version=int(universe.get("version", 1)),
            root_ror=normalize_ror(_required(universe, "root_ror", "universe")),
            scope_modes=scopes,
            curated_institution_ids=curated,
            excluded_institution_ids=tuple(universe.get("excluded_institution_ids", [])),
        ),
        stream=StreamConfig(
            id=stream.get("id", "published_core"),
            types=types,
            corpus=corpus,
            has_abstract_filter=False,
            counting_method="full_counting",
        ),
        collection=CollectionConfig(
            from_publication_date=start,
            to_publication_date=end,
            include_work_observations=bool(collection.get("include_work_observations", True)),
            enrich_topics=bool(collection.get("enrich_topics", True)),
            group_page_size=group_page_size,
            work_page_size=work_page_size,
            strict_group_totals=bool(collection.get("strict_group_totals", True)),
            strict_work_crosscheck=bool(collection.get("strict_work_crosscheck", False)),
        ),
        topic_momentum=TopicMomentumConfig(
            analysis_window_months=analysis_window_months,
            evaluation_step_months=evaluation_step_months,
            history_min_months=history_min_months,
            min_total_history=integer_parameters["min_total_history"],
            min_current=integer_parameters["min_current"],
            min_previous=integer_parameters["min_previous"],
            min_active_months=integer_parameters["min_active_months"],
            min_abs_delta=integer_parameters["min_abs_delta"],
            rise_count_ratio=ratio_parameters["rise_count_ratio"],
            fall_count_ratio=ratio_parameters["fall_count_ratio"],
            rise_share_ratio=ratio_parameters["rise_share_ratio"],
            fall_share_ratio=ratio_parameters["fall_share_ratio"],
            acceleration_epsilon=acceleration_epsilon,
            share_epsilon=share_epsilon,
            min_topic_coverage=min_topic_coverage,
            min_supporting_evaluations=integer_parameters[
                "min_supporting_evaluations"
            ],
            multi_scale=multi_scale,
            scale_levels=scale_levels,
        ),
        citation_acceleration=CitationAccelerationConfig(
            window_months=citation_window_months,
            min_temporal_coverage=min_temporal_coverage,
            min_cohort_size=min_cohort_size,
            age_band_boundaries_months=age_band_boundaries,
            min_recent_citations=min_recent_citations,
            min_absolute_delta=min_absolute_delta,
            min_acceleration_ratio=min_acceleration_ratio,
            min_cohort_percentile=min_cohort_percentile,
            headline_priority_threshold=headline_priority_threshold,
            dossier_limit=dossier_limit,
            backtest_start_date=backtest_start_date,
            backtest_step_months=backtest_step_months,
            outcome_horizon_months=outcome_horizon_months,
        ),
        actor_collaboration_novelty=ActorCollaborationNoveltyConfig(
            current_window_months=acn_current_window_months,
            recent_baseline_months=acn_recent_baseline_months,
            min_current_works=acn_min_current_works,
            min_active_months=acn_min_active_months,
            min_locally_verified_works=acn_min_locally_verified_works,
        ),
    )
