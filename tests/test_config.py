import copy
import os

import pytest

from radar.config import ConfigError, load_config, load_env, parse_config

from conftest import CONFIG_PATH


def test_loads_the_ird_config():
    config = load_config(CONFIG_PATH)
    assert config.universe.root_institution == "I4210166444"
    assert (config.universe.first_year, config.universe.last_year) == (2016, 2025)
    assert config.periods.mode == "year"
    assert config.detectors.collaborations.max_authors == 50
    assert config.config_hash.startswith("sha256:") and len(config.config_hash) == 71
    assert config.config_hash == load_config(CONFIG_PATH).config_hash


def test_hash_changes_with_parameters(config_table):
    other = copy.deepcopy(config_table)
    other["engine"]["alpha"] = config_table["engine"]["alpha"] / 2
    assert parse_config(config_table).config_hash != parse_config(other).config_hash


@pytest.mark.parametrize("section,key,value", [
    ("semantic", "api_key", "abc"),
    ("sweep", "token", "xyz"),
    ("semantic", "base_url", "sk-proj-1234"),
    ("universe", "label", "a8f3c2d19b7e4f6a8c0d2e4f6a8b0c2d4e6f8a0b"),
])
def test_rejects_inline_secrets(config_table, section, key, value):
    config_table[section][key] = value
    with pytest.raises(ConfigError, match="secret"):
        parse_config(config_table)


def test_api_key_env_name_is_allowed(config_table):
    assert parse_config(config_table).semantic.api_key_env == "ALBERT_API_KEY"


def test_rejects_year_range_that_disagrees_with_filter(config_table):
    config_table["universe"]["first_year"] = 2018
    with pytest.raises(ConfigError, match="disagree"):
        parse_config(config_table)
    config_table["universe"]["first_year"] = 2016
    config_table["universe"]["filter"] = "authorships.institutions.lineage:I4210166444,type:article"
    with pytest.raises(ConfigError, match="publication_year"):
        parse_config(config_table)


def test_rejects_unknown_keys_and_bad_mode(config_table):
    bad = copy.deepcopy(config_table)
    bad["engine"]["alhpa"] = 0.05
    with pytest.raises(ConfigError, match="alhpa"):
        parse_config(bad)
    config_table["periods"]["mode"] = "month"
    with pytest.raises(ConfigError, match="mode"):
        parse_config(config_table)


def test_load_env(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("# comment\nRADAR_TEST_KEY='abc'\nRADAR_EMPTY=\n", encoding="utf-8")
    monkeypatch.delenv("RADAR_TEST_KEY", raising=False)
    load_env(env)
    assert os.environ["RADAR_TEST_KEY"] == "abc"
    assert "RADAR_EMPTY" not in os.environ
    monkeypatch.setenv("RADAR_TEST_KEY", "kept")
    load_env(env)
    assert os.environ["RADAR_TEST_KEY"] == "kept"
