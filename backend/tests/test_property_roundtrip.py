"""Hypothesis property tests (tasks 8.4, 9.4)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

from services.platform_config import Configuration, parse_config, pretty_print_config
from services.trace_serialization import (
    CompressionType,
    SerializationFormat,
    deserialize_trace,
    serialize_trace,
)

pytest.importorskip("hypothesis")


@settings(max_examples=100, deadline=None)
@given(
    retention_days=st.integers(min_value=1, max_value=3650),
    backend_url=st.sampled_from(["http://localhost:8000", "https://api.example.com"]),
)
def test_config_round_trip_property(retention_days: int, backend_url: str):
    original = Configuration(
        backend_url=backend_url,
        storage_path="/tmp/observability",
        retention_days=retention_days,
        api_keys=[],
        metadata={"tier": "test"},
    )
    text = pretty_print_config(original, mask_sensitive=False)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.yaml"
        path.write_text(text, encoding="utf-8")
        restored = parse_config(path)
    assert restored == original


def event_strategy(session_id: str):
    event_type = st.sampled_from([
        "reasoning_step",
        "tool_call",
        "memory_access",
        "decision_point",
        "planning_phase",
        "custom_metric",
        "annotation",
    ])
    return st.builds(
        lambda idx, kind, text: {
            "event_id": f"e{idx}",
            "session_id": session_id,
            "event_type": kind,
            "sequence_number": idx,
            "text": text,
            "payload": {"value": text},
        },
        idx=st.integers(min_value=1, max_value=10_000),
        kind=event_type,
        text=st.text(min_size=0, max_size=50),
    )


@settings(max_examples=100, deadline=None)
@given(
    session_id=st.uuids().map(str),
    compression=st.sampled_from([CompressionType.NONE, CompressionType.GZIP]),
    fmt=st.sampled_from([SerializationFormat.JSON, SerializationFormat.PROTOBUF]),
    data=st.data(),
)
def test_trace_serialization_round_trip_property(session_id: str, compression, fmt, data):
    events = data.draw(st.lists(event_strategy(session_id), min_size=1, max_size=100))
    raw = serialize_trace(session_id, events, fmt=fmt, compression=compression)
    restored = deserialize_trace(raw, compression=compression, fmt=fmt)
    assert restored.session_id == session_id
    assert restored.events == events
