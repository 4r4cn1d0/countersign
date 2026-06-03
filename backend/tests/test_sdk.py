"""Tests for Python SDK instrumentation helpers."""

import sys
from pathlib import Path
from uuid import uuid4

import pytest
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "sdk"))

from agent_observability.decorators import set_active_tracer, trace_agent, trace_tool, trace_tool_call
from agent_observability.tracer import AgentTracer


def make_tracer() -> AgentTracer:
    tracer = AgentTracer(api_key="test", flush_interval_seconds=999)
    tracer._session_id = uuid4()
    return tracer


def test_tool_call_context_manager_records_completed_event():
    tracer = make_tracer()

    with tracer.tool_call("lookup", inputs={"q": "abc"}):
        pass

    assert tracer._buffer[0]["event_type"] == "tool_call"
    assert tracer._buffer[0]["tool_name"] == "lookup"
    assert tracer._buffer[0]["status"] == "completed"


def test_tool_call_context_manager_records_failed_event():
    tracer = make_tracer()

    with pytest.raises(ValueError):
        with tracer.tool_call("lookup"):
            raise ValueError("bad input")

    assert tracer._buffer[0]["status"] == "failed"
    assert tracer._buffer[0]["error"]["type"] == "ValueError"


def test_custom_metric_and_annotation_helpers():
    tracer = make_tracer()

    tracer.record_custom_metric("tokens", 42, metric_type="counter")
    tracer.annotate("checkpoint", annotation_type="milestone")

    assert tracer._buffer[0]["event_type"] == "custom_metric"
    assert tracer._buffer[1]["event_type"] == "annotation"


def test_trace_tool_call_uses_active_tracer():
    tracer = make_tracer()
    set_active_tracer(tracer)

    with trace_tool_call("manual"):
        pass

    assert tracer._buffer[0]["tool_name"] == "manual"


def test_buffer_size_triggers_flush(monkeypatch):
    tracer = make_tracer()
    tracer.buffer_size = 1
    calls = []

    monkeypatch.setattr(tracer, "flush", lambda: calls.append("flush"))
    tracer.record_event({"event_type": "annotation", "text": "x", "annotation_type": "note"})

    assert calls == ["flush"]


def test_post_with_retry_retries_until_success(monkeypatch):
    tracer = AgentTracer(api_key="test", max_retries=3)
    calls = []
    monkeypatch.setattr("agent_observability.tracer.time.sleep", lambda *_: None)

    class FakeResponse:
        def __init__(self, ok):
            self.ok = ok

        def raise_for_status(self):
            if not self.ok:
                raise httpx.HTTPStatusError(
                    "failed",
                    request=httpx.Request("POST", "http://example.test"),
                    response=httpx.Response(500),
                )

    class FakeClient:
        def post(self, *args, **kwargs):
            calls.append((args, kwargs))
            return FakeResponse(ok=len(calls) == 2)

    tracer._client = FakeClient()
    tracer._post_with_retry("http://example.test", {"events": []})

    assert len(calls) == 2


def test_trace_tool_decorator_records_success():
    tracer = make_tracer()
    set_active_tracer(tracer)

    @trace_tool("adder")
    def add(a, b):
        return a + b

    assert add(1, 2) == 3
    assert tracer._buffer[0]["tool_name"] == "adder"
    assert tracer._buffer[0]["outputs"] == {"result": 3}


def test_trace_agent_decorator_starts_and_flushes_session():
    calls = []

    class FakeTracer:
        def start_session(self, **kwargs):
            calls.append(("start", kwargs))

        def flush(self):
            calls.append(("flush", {}))

    @trace_agent(agent_type="test", goal="run", tracer=FakeTracer())
    def run_agent():
        return "done"

    assert run_agent() == "done"
    assert calls[0][0] == "start"
    assert calls[0][1]["goal"] == "run"
    assert calls[-1][0] == "flush"
