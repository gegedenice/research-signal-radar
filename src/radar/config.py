"""Load and validate config/ird.toml (specs/03 §1)."""

import dataclasses
import hashlib
import json
import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Universe:
    id: str
    label: str
    root_institution: str
    filter: str
    first_year: int
    last_year: int


@dataclass(frozen=True)
class Sweep:
    data_dir: str = "data"
    select: list[str] = field(default_factory=list)
    refetch_truncated_authors: bool = True


@dataclass(frozen=True)
class Periods:
    mode: str = "year"
    window_months: int = 12
    baseline_months: int = 36


@dataclass(frozen=True)
class Engine:
    alpha: float = 0.05
    min_log2_ratio: float = 0.585


@dataclass(frozen=True)
class Topics:
    levels: list[str] = field(default_factory=lambda: ["topic", "subfield"])
    min_support: int = 10


@dataclass(frozen=True)
class Citations:
    min_age_years: int = 2
    min_current: int = 5
    min_cohort_size: int = 20
    directions: list[str] = field(default_factory=lambda: ["up"])


@dataclass(frozen=True)
class Collaborations:
    levels: list[str] = field(default_factory=lambda: ["institution", "country"])
    min_support: int = 5
    max_authors: int = 50
    exclude_countries: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Detectors:
    topics: Topics = field(default_factory=Topics)
    citations: Citations = field(default_factory=Citations)
    collaborations: Collaborations = field(default_factory=Collaborations)


@dataclass(frozen=True)
class Semantic:
    base_url: str = "https://albert.api.etalab.gouv.fr/v1"
    model: str = "BAAI/bge-m3"
    api_key_env: str = "ALBERT_API_KEY"
    batch_size: int = 64
    max_chars: int = 4000
    min_cluster_size: int = 60
    n_regions: int = 20
    extra_stopwords: list[str] = field(default_factory=list)
    random_state: int = 42


@dataclass(frozen=True)
class Config:
    universe: Universe
    sweep: Sweep = field(default_factory=Sweep)
    periods: Periods = field(default_factory=Periods)
    engine: Engine = field(default_factory=Engine)
    detectors: Detectors = field(default_factory=Detectors)
    semantic: Semantic = field(default_factory=Semantic)

    @property
    def config_hash(self) -> str:
        canonical = json.dumps(dataclasses.asdict(self), sort_keys=True, separators=(",", ":"))
        return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @property
    def data_dir(self) -> Path:
        return Path(self.sweep.data_dir)


_SECRET_NAME = re.compile(r"(api_?key|token|secret|password)", re.IGNORECASE)
_SECRET_VALUE = re.compile(r"^(sk-|ghp_|github_pat_)|^[A-Za-z0-9_\-]{32,}$")
_YEAR_RANGE = re.compile(r"(?:^|,)publication_year:(\d{4})(?:-(\d{4}))?(?:,|$)")


def _check_secrets(table, path=""):
    for key, value in table.items():
        where = f"{path}.{key}" if path else key
        if isinstance(value, dict):
            _check_secrets(value, where)
            continue
        values = value if isinstance(value, list) else [value]
        for item in values:
            if not isinstance(item, str) or not item:
                continue
            if (_SECRET_NAME.search(key) and not key.endswith("_env")) or _SECRET_VALUE.search(item):
                raise ConfigError(f"{where} looks like a secret; put keys in .env, not in the config")


def _build(cls, table, path):
    names = {f.name: f for f in dataclasses.fields(cls)}
    unknown = set(table) - set(names)
    if unknown:
        raise ConfigError(f"unknown key(s) in [{path}]: {', '.join(sorted(unknown))}")
    kwargs = {}
    for name, value in table.items():
        sub = names[name].type
        if dataclasses.is_dataclass(sub):
            if not isinstance(value, dict):
                raise ConfigError(f"[{path}.{name}] must be a table")
            value = _build(sub, value, f"{path}.{name}" if path else name)
        kwargs[name] = value
    try:
        return cls(**kwargs)
    except TypeError as exc:
        raise ConfigError(f"[{path or 'root'}]: {exc}") from None


def parse_config(table: dict) -> Config:
    _check_secrets(table)
    if "universe" not in table:
        raise ConfigError("missing [universe]")
    config = _build(Config, table, "")
    u = config.universe
    match = _YEAR_RANGE.search(u.filter)
    if not match:
        raise ConfigError("universe.filter must contain a publication_year range")
    start, end = int(match.group(1)), int(match.group(2) or match.group(1))
    if (start, end) != (u.first_year, u.last_year):
        raise ConfigError(
            f"first_year/last_year ({u.first_year}-{u.last_year}) disagree with the filter ({start}-{end})"
        )
    if config.periods.mode not in {"year", "semester"}:
        raise ConfigError("periods.mode must be 'year' or 'semester'")
    return config


def load_env(path: str | Path = ".env") -> None:
    """Load KEY=VALUE lines from a git-ignored .env into os.environ (existing values win)."""
    path = Path(path)
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if value:
            os.environ.setdefault(key.strip(), value)


def load_config(path: str | Path) -> Config:
    with open(path, "rb") as fh:
        return parse_config(tomllib.load(fh))
