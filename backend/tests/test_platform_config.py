"""Tests for configuration parser (task 8)."""

import json
from pathlib import Path

import pytest
import yaml

from services.platform_config import Configuration, parse_config, pretty_print_config


def test_parse_json_config(tmp_path: Path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "backend_url": "http://localhost:8000",
        "storage_path": "/data",
        "retention_days": 30,
        "api_keys": ["key-1"],
        "metadata": {},
    }))
    cfg = parse_config(path)
    assert cfg.retention_days == 30


def test_parse_yaml_config(tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({
        "backend_url": "https://api.example.com",
        "storage_path": "./store",
        "retention_days": 90,
    }))
    cfg = parse_config(path)
    assert cfg.backend_url == "https://api.example.com"


def test_missing_file(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        parse_config(tmp_path / "missing.json")


def test_missing_required_fields_reports_error(tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"backend_url": "http://localhost:8000"}))

    with pytest.raises(ValueError, match="Missing fields: storage_path, retention_days"):
        parse_config(path)


def test_malformed_yaml_reports_error(tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_text("backend_url: [unterminated")

    with pytest.raises(ValueError, match="Malformed YAML"):
        parse_config(path)


def test_pretty_print_masks_api_keys():
    cfg = Configuration(
        backend_url="http://localhost:8000",
        storage_path="/data",
        retention_days=90,
        api_keys=["secret-key"],
    )
    text = pretty_print_config(cfg)
    assert "secret-key" not in text
    assert "***" in text


@pytest.mark.parametrize("retention_days", [1, 30, 365])
def test_configuration_round_trip_property(retention_days: int):
    """Property-style test without Hypothesis dependency in CI."""
    original = Configuration(
        backend_url="http://localhost:8000",
        storage_path="/tmp/obs",
        retention_days=retention_days,
        api_keys=[],
        metadata={"env": "test"},
    )
    text = pretty_print_config(original, mask_sensitive=False)
    restored = Configuration.model_validate(yaml.safe_load(text))
    assert restored == original
