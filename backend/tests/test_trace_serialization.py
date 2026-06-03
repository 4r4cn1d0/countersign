"""Tests for trace serialization (task 9)."""

import json
import time

import pytest

from services.trace_serialization import (
    SCHEMA_VERSION,
    CompressionType,
    SerializationFormat,
    deserialize_trace,
    serialize_trace,
)


SAMPLE_EVENTS = [
    {
        "event_id": "e1",
        "session_id": "s1",
        "event_type": "reasoning_step",
        "sequence_number": 1,
    }
]


def test_json_gzip_round_trip():
    raw = serialize_trace("s1", SAMPLE_EVENTS, compression=CompressionType.GZIP)
    trace = deserialize_trace(raw)
    assert trace.session_id == "s1"
    assert trace.events == SAMPLE_EVENTS
    assert trace.schema_version == SCHEMA_VERSION


def test_uncompressed_round_trip():
    raw = serialize_trace("s1", SAMPLE_EVENTS, compression=CompressionType.NONE)
    trace = deserialize_trace(raw, compression=CompressionType.NONE)
    assert len(trace.events) == 1


def test_protobuf_round_trip():
    raw = serialize_trace(
        "s1",
        SAMPLE_EVENTS,
        fmt=SerializationFormat.PROTOBUF,
        compression=CompressionType.NONE,
    )
    trace = deserialize_trace(raw, fmt=SerializationFormat.PROTOBUF)

    assert trace.format == SerializationFormat.PROTOBUF
    assert trace.session_id == "s1"
    assert trace.events == SAMPLE_EVENTS


def test_zstd_round_trip():
    raw = serialize_trace("s1", SAMPLE_EVENTS, compression=CompressionType.ZSTD)
    trace = deserialize_trace(raw, compression=CompressionType.ZSTD)
    assert trace.events == SAMPLE_EVENTS


def test_invalid_schema_version():
    bad = json.dumps({"schema_version": "99.0", "session_id": "s", "events": []}).encode()
    with pytest.raises(ValueError, match="Unsupported schema version"):
        deserialize_trace(bad)


def test_invalid_json_payload_reports_error():
    with pytest.raises(ValueError, match="Invalid JSON"):
        deserialize_trace(b"not-json", fmt=SerializationFormat.JSON)


def test_gzip_size_reduction_exceeds_sixty_percent():
    events = [
        {
            "event_id": f"e{i}",
            "session_id": "s1",
            "event_type": "reasoning_step",
            "sequence_number": i,
            "prompt": "repeat " * 30,
            "response": "same response " * 30,
        }
        for i in range(200)
    ]

    raw = serialize_trace("s1", events, compression=CompressionType.NONE)
    compressed = serialize_trace("s1", events, compression=CompressionType.GZIP)

    assert len(compressed) <= len(raw) * 0.4


def test_large_trace_serializes_within_ten_seconds():
    events = [
        {
            "event_id": f"e{i}",
            "session_id": "s1",
            "event_type": "annotation",
            "sequence_number": i,
            "text": f"note-{i}",
            "annotation_type": "note",
        }
        for i in range(10_000)
    ]

    started = time.monotonic()
    raw = serialize_trace("s1", events, compression=CompressionType.GZIP)
    restored = deserialize_trace(raw)
    elapsed = time.monotonic() - started

    assert elapsed < 10
    assert len(restored.events) == 10_000
