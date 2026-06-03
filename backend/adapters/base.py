"""Framework adapter base classes (task 7.3)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

class BaseAdapter(ABC):
    """Hooks for framework-specific trace capture."""

    def __init__(self, tracer: Any) -> None:
        self.tracer = tracer

    @abstractmethod
    def on_session_start(self, agent_type: str, goal: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        ...

    def on_reasoning_start(self, prompt: str, model: str, **kwargs: Any) -> None:
        self.tracer.record_event({
            "event_type": "reasoning_step",
            "prompt": prompt,
            "response": kwargs.get("response", ""),
            "model": model,
            "input_tokens": kwargs.get("input_tokens", 0),
            "output_tokens": kwargs.get("output_tokens", 0),
            "cost": str(kwargs.get("cost", 0)),
            **{k: v for k, v in kwargs.items() if k not in {"response", "input_tokens", "output_tokens", "cost"}},
        })

    def on_tool_call(
        self,
        tool_name: str,
        inputs: Dict[str, Any],
        outputs: Optional[Dict[str, Any]] = None,
        status: str = "completed",
        **kwargs: Any,
    ) -> None:
        self.tracer.record_event({
            "event_type": "tool_call",
            "tool_name": tool_name,
            "tool_type": kwargs.get("tool_type", "function"),
            "inputs": inputs,
            "outputs": outputs,
            "start_time": kwargs.get("start_time"),
            "end_time": kwargs.get("end_time"),
            "status": status,
            **{k: v for k, v in kwargs.items() if k not in {"tool_type", "start_time", "end_time"}},
        })

    def on_memory_access(self, query: str, num_results: int, **kwargs: Any) -> None:
        self.tracer.record_event({
            "event_type": "memory_access",
            "query": query,
            "num_results": num_results,
            "memory_type": kwargs.get("memory_type", "long_term"),
            "retrieval_method": kwargs.get("retrieval_method", "semantic_search"),
            "results": kwargs.get("results", []),
        })

    def on_custom_metric(self, name: str, value: float, metric_type: str = "gauge", **kwargs: Any) -> None:
        self.tracer.record_event({
            "event_type": "custom_metric",
            "metric_name": name,
            "metric_value": value,
            "metric_type": metric_type,
            **kwargs,
        })

    def on_annotation(self, text: str, severity: str = "info", **kwargs: Any) -> None:
        self.tracer.record_event({
            "event_type": "annotation",
            "text": text,
            "severity": severity,
            **kwargs,
        })
