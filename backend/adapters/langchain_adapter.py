"""LangChain adapter for translating LangChain callbacks into trace events."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from adapters.base import BaseAdapter


class LangChainAdapter(BaseAdapter):
    """Wrap LangChain callbacks and forward LLM/tool activity to the tracer."""

    def on_session_start(self, agent_type: str, goal: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        self.tracer.start_session(agent_type=agent_type, goal=goal, metadata=metadata)

    def handle_langchain_event(self, event: Dict[str, Any]) -> None:
        """Map a LangChain callback payload to observability events."""
        kind = event.get("kind")
        if kind == "llm":
            self.on_reasoning_start(
                prompt=event.get("prompt", ""),
                model=event.get("model", "unknown"),
                response=event.get("response", ""),
                input_tokens=event.get("input_tokens", 0),
                output_tokens=event.get("output_tokens", 0),
            )
        elif kind == "tool":
            self.on_tool_call(
                tool_name=event.get("tool_name", "tool"),
                inputs=event.get("inputs", {}),
                outputs=event.get("outputs"),
                status=event.get("status", "completed"),
            )

    def create_callback_handler(self):
        """Create a LangChain callback handler bound to this adapter.

        LangChain is optional for this project. When it is installed, this
        returns a BaseCallbackHandler subclass instance; otherwise it raises a
        clear error instead of silently behaving like a no-op adapter.
        """
        try:
            from langchain_core.callbacks import BaseCallbackHandler
        except ImportError:
            try:
                from langchain.callbacks.base import BaseCallbackHandler
            except ImportError as exc:
                raise RuntimeError(
                    "LangChain is not installed; install langchain-core or langchain "
                    "to create callback handlers."
                ) from exc

        adapter = self

        class ObservabilityCallbackHandler(BaseCallbackHandler):
            def __init__(self) -> None:
                super().__init__()
                self._llm_prompts: Dict[str, List[str]] = {}
                self._tool_starts: Dict[str, datetime] = {}
                self._tool_inputs: Dict[str, Any] = {}

            @staticmethod
            def _run_id(value: Any) -> str:
                return str(value or "default")

            def on_llm_start(self, serialized, prompts, *, run_id=None, **kwargs):
                self._llm_prompts[self._run_id(run_id)] = list(prompts or [])

            def on_llm_end(self, response, *, run_id=None, **kwargs):
                run_key = self._run_id(run_id)
                prompts = self._llm_prompts.pop(run_key, [])
                generations = getattr(response, "generations", []) or []
                first_generation = generations[0][0] if generations and generations[0] else None
                text = getattr(first_generation, "text", "") if first_generation else ""
                llm_output = getattr(response, "llm_output", {}) or {}
                token_usage = llm_output.get("token_usage", {}) if isinstance(llm_output, dict) else {}
                adapter.on_reasoning_start(
                    prompt="\n".join(prompts),
                    model=llm_output.get("model_name", "unknown") if isinstance(llm_output, dict) else "unknown",
                    response=text,
                    input_tokens=token_usage.get("prompt_tokens", 0),
                    output_tokens=token_usage.get("completion_tokens", 0),
                )

            def on_tool_start(self, serialized, input_str, *, run_id=None, **kwargs):
                run_key = self._run_id(run_id)
                self._tool_starts[run_key] = datetime.utcnow()
                self._tool_inputs[run_key] = input_str

            def on_tool_end(self, output, *, run_id=None, name=None, **kwargs):
                run_key = self._run_id(run_id)
                start = self._tool_starts.pop(run_key, None)
                tool_input = self._tool_inputs.pop(run_key, None)
                end = datetime.utcnow()
                adapter.on_tool_call(
                    tool_name=name or kwargs.get("tool_name") or "tool",
                    inputs={"input": tool_input},
                    outputs={"output": output},
                    status="completed",
                    start_time=start.isoformat() if start else None,
                    end_time=end.isoformat(),
                )

            def on_tool_error(self, error, *, run_id=None, name=None, **kwargs):
                run_key = self._run_id(run_id)
                start = self._tool_starts.pop(run_key, None)
                tool_input = self._tool_inputs.pop(run_key, None)
                adapter.on_tool_call(
                    tool_name=name or kwargs.get("tool_name") or "tool",
                    inputs={"input": tool_input},
                    outputs=None,
                    status="failed",
                    start_time=start.isoformat() if start else None,
                    end_time=datetime.utcnow().isoformat(),
                    error={"type": type(error).__name__, "message": str(error)},
                )

        return ObservabilityCallbackHandler()

    def wrap_agent(self, agent: Any) -> Any:
        """Attach the observability callback to a LangChain runnable/agent."""
        handler = self.create_callback_handler()
        if hasattr(agent, "with_config"):
            return agent.with_config(callbacks=[handler])
        if hasattr(agent, "callbacks"):
            callbacks = list(getattr(agent, "callbacks") or [])
            callbacks.append(handler)
            setattr(agent, "callbacks", callbacks)
            return agent
        raise TypeError("LangChain agent does not support callbacks or with_config().")
