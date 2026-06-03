"""Platform configuration parser and pretty printer (task 8)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml
from pydantic import BaseModel, Field, field_validator


SENSITIVE_KEYS = frozenset({"api_key", "api_keys", "password", "secret", "token", "jwt_secret_key"})


class Configuration(BaseModel):
    """Agent observability platform configuration."""

    backend_url: str
    storage_path: str
    retention_days: int = Field(ge=1)
    api_keys: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("backend_url")
    @classmethod
    def validate_backend_url(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("backend_url must start with http:// or https://")
        return value


def _line_number_for_key(text: str, key: str) -> Optional[int]:
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*:", re.MULTILINE)
    match = pattern.search(text)
    if match:
        return text[: match.start()].count("\n") + 1
    return None


def parse_config(path: Union[str, Path]) -> Configuration:
    """Parse YAML or JSON configuration file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    raw_text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()

    try:
        if suffix in {".yaml", ".yml"}:
            data = yaml.safe_load(raw_text) or {}
        elif suffix == ".json":
            data = json.loads(raw_text)
        else:
            raise ValueError(f"Unsupported configuration format: {suffix}")
    except yaml.YAMLError as exc:
        raise ValueError(f"Malformed YAML in {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        line = exc.lineno or _line_number_for_key(raw_text, "")
        raise ValueError(f"Malformed JSON in {path} near line {line}: {exc.msg}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"Configuration root must be an object (file: {path})")

    required_fields = ("backend_url", "storage_path", "retention_days")
    missing = [field for field in required_fields if field not in data]
    if missing:
        raise ValueError(
            f"Invalid configuration in {path}. Missing fields: {', '.join(missing)}. "
            f"(see near line {_line_number_for_key(raw_text, missing[0]) or '?'})"
        )

    try:
        return Configuration.model_validate(data)
    except Exception as exc:
        raise ValueError(f"Invalid configuration in {path}: {exc}") from exc


def pretty_print_config(config: Configuration, mask_sensitive: bool = True) -> str:
    """Format configuration with stable field order and optional secret masking."""
    data = config.model_dump()
    ordered = {
        "backend_url": data["backend_url"],
        "storage_path": data["storage_path"],
        "retention_days": data["retention_days"],
        "api_keys": list(data["api_keys"]),
        "metadata": dict(data["metadata"]),
    }

    if mask_sensitive:
        if ordered["api_keys"]:
            ordered["api_keys"] = ["***" if k else k for k in ordered["api_keys"]]
        for key in list(ordered["metadata"].keys()):
            if key.lower() in SENSITIVE_KEYS:
                ordered["metadata"][key] = "***"

    return yaml.safe_dump(ordered, sort_keys=False, default_flow_style=False).rstrip() + "\n"
