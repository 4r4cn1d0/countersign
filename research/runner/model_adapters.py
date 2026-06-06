"""Open-source local model runtime adapters."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ModelRequest:
    """Prompt request sent to a local open-source model runtime."""

    prompt: str
    model_name: str
    model_family: str
    temperature: float
    seed: int
    prompt_template: str
    max_tokens: int = 256
    response_schema: dict[str, Any] | None = None
    thinking: bool | None = False


@dataclass(frozen=True)
class ModelResponse:
    """Response returned by a local open-source model runtime."""

    text: str
    runtime: str
    model_name: str
    model_family: str
    raw_response: dict
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class ModelAdapter(Protocol):
    """Adapter protocol for local open-source model runtimes."""

    runtime: str

    def generate(self, request: ModelRequest) -> ModelResponse:
        """Generate text from a model request."""


class DeterministicModelAdapter:
    """Test/deterministic adapter used for reproducible local benchmark runs."""

    runtime = "deterministic"

    def generate(self, request: ModelRequest) -> ModelResponse:
        if "AGENT_MEMORY_TOOL_ACTION_REQUEST" in request.prompt:
            action = _deterministic_tool_action(request.prompt)
            return ModelResponse(
                text=json.dumps(action, sort_keys=True),
                runtime=self.runtime,
                model_name=request.model_name,
                model_family=request.model_family,
                raw_response={
                    "deterministic": True,
                    "seed": request.seed,
                    "tool_action": True,
                },
            )
        if "You are summarizing a coding-agent tool loop" in request.prompt:
            return ModelResponse(
                text=json.dumps(
                    {
                        "final_summary": (
                            "Coding tool loop completed with real file edits and test "
                            "execution evidence."
                        ),
                        "memory_claims": [],
                        "completion_claims": [],
                        "needs_verification": [],
                    },
                    sort_keys=True,
                ),
                runtime=self.runtime,
                model_name=request.model_name,
                model_family=request.model_family,
                raw_response={
                    "deterministic": True,
                    "seed": request.seed,
                    "tool_summary": True,
                },
            )
        return ModelResponse(
            text=(
                "Plan evidence checks, preserve provenance, and avoid high-risk "
                "completion claims without fresh verification."
            ),
            runtime=self.runtime,
            model_name=request.model_name,
            model_family=request.model_family,
            raw_response={"deterministic": True, "seed": request.seed},
        )


class OllamaModelAdapter:
    """Ollama-compatible local HTTP adapter.

    This adapter intentionally talks to a local/open-source runtime endpoint only.
    It does not use closed-source APIs.
    """

    runtime = "ollama"

    def __init__(self, endpoint: str = "http://127.0.0.1:11434") -> None:
        self.endpoint = endpoint.rstrip("/")

    def generate(self, request: ModelRequest) -> ModelResponse:
        payload = {
            "model": request.model_name,
            "messages": [{"role": "user", "content": request.prompt}],
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "seed": request.seed,
                "num_predict": request.max_tokens,
            },
        }
        if request.thinking is not None:
            payload["think"] = request.thinking
        if request.response_schema is not None:
            payload["format"] = request.response_schema
        response = _post_json(f"{self.endpoint}/api/chat", payload)
        message = response.get("message", {})
        return ModelResponse(
            text=str(message.get("content") or response.get("response", "")),
            runtime=self.runtime,
            model_name=request.model_name,
            model_family=request.model_family,
            raw_response=response,
        )


class LlamaCppHttpAdapter:
    """llama.cpp compatible local HTTP adapter."""

    runtime = "llama_cpp"

    def __init__(self, endpoint: str = "http://127.0.0.1:8080") -> None:
        self.endpoint = endpoint.rstrip("/")

    def generate(self, request: ModelRequest) -> ModelResponse:
        payload = {
            "prompt": request.prompt,
            "temperature": request.temperature,
            "seed": request.seed,
            "n_predict": request.max_tokens,
        }
        if request.response_schema is not None:
            payload["json_schema"] = request.response_schema
        response = _post_json(f"{self.endpoint}/completion", payload)
        text = response.get("content", response.get("response", ""))
        return ModelResponse(
            text=str(text),
            runtime=self.runtime,
            model_name=request.model_name,
            model_family=request.model_family,
            raw_response=response,
        )


def create_model_adapter(runtime: str, endpoint: str | None = None) -> ModelAdapter:
    """Create an adapter for a supported local/open-source runtime."""

    if runtime == "deterministic":
        return DeterministicModelAdapter()
    if runtime == "ollama":
        return OllamaModelAdapter(endpoint or "http://127.0.0.1:11434")
    if runtime == "llama_cpp":
        return LlamaCppHttpAdapter(endpoint or "http://127.0.0.1:8080")
    raise ValueError(f"Unsupported open-source runtime: {runtime}")


def _deterministic_tool_action(prompt: str) -> dict:
    marker = "DETERMINISTIC_ACTION:"
    if marker not in prompt:
        return {
            "action": "finish",
            "claim": "Unable to choose a tool action from the available evidence.",
            "source_event_ids": [],
        }
    line = prompt.split(marker, 1)[1].strip().splitlines()[0]
    try:
        action = json.loads(line)
    except json.JSONDecodeError:
        return {"action": "invalid", "source_event_ids": []}
    return action if isinstance(action, dict) else {"action": "invalid", "source_event_ids": []}


def _post_json(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace").strip()
        detail = f"HTTP {exc.code}"
        if body:
            detail += f": {body[:1000]}"
        raise RuntimeError(
            f"Local model runtime request failed: {url} ({detail})"
        ) from exc
    except (
        urllib.error.URLError,
        TimeoutError,
        socket.timeout,
        json.JSONDecodeError,
    ) as exc:
        raise RuntimeError(f"Local model runtime request failed: {url}") from exc
