"""Tests for LangChain adapter event mapping."""

from adapters.langchain_adapter import LangChainAdapter


class RecordingTracer:
    def __init__(self):
        self.events = []
        self.sessions = []

    def start_session(self, **kwargs):
        self.sessions.append(kwargs)

    def record_event(self, event):
        self.events.append(event)


def test_handle_langchain_llm_event_records_reasoning_step():
    tracer = RecordingTracer()
    adapter = LangChainAdapter(tracer)

    adapter.handle_langchain_event({
        "kind": "llm",
        "prompt": "think",
        "response": "done",
        "model": "test-model",
        "input_tokens": 2,
        "output_tokens": 3,
    })

    assert tracer.events[0]["event_type"] == "reasoning_step"
    assert tracer.events[0]["prompt"] == "think"
    assert tracer.events[0]["output_tokens"] == 3


def test_handle_langchain_tool_event_records_tool_call():
    tracer = RecordingTracer()
    adapter = LangChainAdapter(tracer)

    adapter.handle_langchain_event({
        "kind": "tool",
        "tool_name": "search",
        "inputs": {"q": "x"},
        "outputs": {"result": "y"},
    })

    assert tracer.events[0]["event_type"] == "tool_call"
    assert tracer.events[0]["tool_name"] == "search"
