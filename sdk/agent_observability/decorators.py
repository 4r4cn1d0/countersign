"""Decorator-based instrumentation for agents and tools."""

from __future__ import annotations

import functools
import inspect
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime
from typing import Any, Callable, Optional, TypeVar

from agent_observability.tracer import AgentTracer

F = TypeVar("F", bound=Callable[..., Any])

_active_tracer: Optional[AgentTracer] = None


def set_active_tracer(tracer: AgentTracer) -> None:
    global _active_tracer
    _active_tracer = tracer


def get_active_tracer() -> AgentTracer:
    if _active_tracer is None:
        raise RuntimeError("No active AgentTracer; use trace_agent or set_active_tracer()")
    return _active_tracer


def trace_agent(
    agent_type: str = "custom",
    goal: str = "agent run",
    tracer: Optional[AgentTracer] = None,
) -> Callable[[F], F]:
    """Decorator that starts a session and records tool/reasoning events."""

    def decorator(func: F) -> F:
        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                t = tracer or _active_tracer
                if t is None:
                    return await func(*args, **kwargs)
                t.start_session(agent_type=agent_type, goal=goal)
                set_active_tracer(t)
                try:
                    return await func(*args, **kwargs)
                finally:
                    t.flush()

            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            t = tracer or _active_tracer
            if t is None:
                return func(*args, **kwargs)
            t.start_session(agent_type=agent_type, goal=goal)
            set_active_tracer(t)
            try:
                return func(*args, **kwargs)
            finally:
                t.flush()

        return sync_wrapper  # type: ignore[return-value]

    return decorator


def trace_tool(tool_name: Optional[str] = None, tool_type: str = "function") -> Callable[[F], F]:
    """Decorator that records a tool_call event around a function."""

    def decorator(func: F) -> F:
        name = tool_name or func.__name__

        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                t = get_active_tracer()
                start = datetime.utcnow()
                try:
                    result = await func(*args, **kwargs)
                    t.record_event({
                        "event_type": "tool_call",
                        "tool_name": name,
                        "tool_type": tool_type,
                        "inputs": {"args": list(args), "kwargs": kwargs},
                        "outputs": {"result": result},
                        "start_time": start.isoformat(),
                        "end_time": datetime.utcnow().isoformat(),
                        "status": "completed",
                    })
                    return result
                except Exception as exc:
                    t.record_event({
                        "event_type": "tool_call",
                        "tool_name": name,
                        "tool_type": tool_type,
                        "inputs": {"args": list(args), "kwargs": kwargs},
                        "start_time": start.isoformat(),
                        "status": "failed",
                        "error": {"type": type(exc).__name__, "message": str(exc)},
                    })
                    raise

            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            t = get_active_tracer()
            start = datetime.utcnow()
            try:
                result = func(*args, **kwargs)
                t.record_event({
                    "event_type": "tool_call",
                    "tool_name": name,
                    "tool_type": tool_type,
                    "inputs": {"args": list(args), "kwargs": kwargs},
                    "outputs": {"result": result},
                    "start_time": start.isoformat(),
                    "end_time": datetime.utcnow().isoformat(),
                    "status": "completed",
                })
                return result
            except Exception as exc:
                t.record_event({
                    "event_type": "tool_call",
                    "tool_name": name,
                    "tool_type": tool_type,
                    "inputs": {"args": list(args), "kwargs": kwargs},
                    "start_time": start.isoformat(),
                    "status": "failed",
                    "error": {"type": type(exc).__name__, "message": str(exc)},
                })
                raise

        return sync_wrapper  # type: ignore[return-value]

    return decorator


@contextmanager
def trace_tool_call(tool_name: str, tool_type: str = "function", **metadata: Any):
    """Manual context manager for recording a tool call."""
    tracer = get_active_tracer()
    with tracer.tool_call(tool_name, tool_type=tool_type, **metadata):
        yield


@asynccontextmanager
async def atrace_tool_call(tool_name: str, tool_type: str = "function", **metadata: Any):
    """Async manual context manager for recording a tool call."""
    tracer = get_active_tracer()
    async with tracer.atool_call(tool_name, tool_type=tool_type, **metadata):
        yield
