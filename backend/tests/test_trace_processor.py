"""Unit tests for trace_processor enrichment logic."""

import pytest

from services.trace_processor import (
    _compute_aggregate_deltas,
    _estimate_confidence,
    _hash_payload,
    _is_infinite_loop,
    _process_trace_event_with_retry,
    _shannon_entropy,
    RECENT_EVENT_HASHES,
)


@pytest.fixture(autouse=True)
def clear_loop_cache():
    RECENT_EVENT_HASHES.clear()
    yield
    RECENT_EVENT_HASHES.clear()


def test_shannon_entropy_empty():
    assert _shannon_entropy("") == 0.0


def test_shannon_entropy_non_empty():
    assert _shannon_entropy("aaa") == 0.0
    assert _shannon_entropy("ab") > 0.0


def test_compute_aggregate_deltas_reasoning():
    deltas = _compute_aggregate_deltas({
        "event_type": "reasoning_step",
        "input_tokens": 10,
        "output_tokens": 5,
        "cost": "0.01",
    })
    assert deltas["total_reasoning_steps"] == 1
    assert deltas["total_tokens"] == 15


def test_infinite_loop_detection():
    session = "sess-1"
    payload = {"prompt": "same"}
    h = _hash_payload(payload)
    for _ in range(4):
        assert _is_infinite_loop(session, h) is False
    assert _is_infinite_loop(session, h) is True


def test_estimate_confidence_explicit():
    assert _estimate_confidence({"confidence": 0.8}) == 0.8


def test_compute_aggregate_deltas_memory_hit():
    deltas = _compute_aggregate_deltas({
        "event_type": "memory_access",
        "num_results": 2,
    })
    assert deltas["total_memory_accesses"] == 1
    assert deltas["total_memory_hits"] == 1


def test_compute_aggregate_deltas_memory_miss():
    deltas = _compute_aggregate_deltas({
        "event_type": "memory_access",
        "num_results": 0,
        "results": [],
    })
    assert deltas["total_memory_accesses"] == 1
    assert deltas["total_memory_hits"] == 0


@pytest.mark.asyncio
async def test_process_trace_event_retries_transient_failure(monkeypatch):
    attempts = []

    async def fake_once(event_data):
        attempts.append(event_data)
        if len(attempts) == 1:
            raise RuntimeError("temporary")

    monkeypatch.setattr("services.trace_processor._process_trace_event_once", fake_once)
    async def fake_sleep(*_):
        return None

    monkeypatch.setattr("services.trace_processor.asyncio.sleep", fake_sleep)

    await _process_trace_event_with_retry({"event_id": "e1"}, max_attempts=2)

    assert len(attempts) == 2
