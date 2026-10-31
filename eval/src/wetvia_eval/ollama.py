"""Minimale Ollama-client voor de benchmark.

Issue #5 bouwt de echte LLMProvider-port in wetvia.llm. Deze klasse blijft
bewust in eval, met dezelfde rol (chat + schema), zodat die port hem later
kan vervangen. Geen cloud-endpoint en geen API-key.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from wetvia_eval.schema import answer_json_schema

NUM_CTX = 16384
_NANOSECONDS = 1_000_000_000


@dataclass(frozen=True)
class ChatMeasurement:
    content: str
    seconds_to_first_token: float | None
    tokens_per_second: float | None
    eval_count: int | None


class OllamaUnreachableError(Exception):
    pass


def model_is_listed(available: set[str], wanted: str) -> bool:
    if wanted in available:
        return True
    prefix = f"{wanted}:"
    return any(name.startswith(prefix) for name in available)


def tokens_per_second(eval_count: int | None, eval_duration_ns: int | None) -> float | None:
    """Ollama geeft eval_duration in nanoseconden (docs.ollama.com/api/chat)."""
    if eval_count is None or eval_duration_ns is None or eval_duration_ns <= 0:
        return None
    return eval_count / (eval_duration_ns / _NANOSECONDS)


class OllamaProvider:
    def __init__(
        self,
        base_url: str,
        client: httpx.Client | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = client if client is not None else httpx.Client(timeout=httpx.Timeout(600.0))
        self._owns_client = client is None
        self._clock = clock if clock is not None else time.perf_counter

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def list_models(self) -> set[str]:
        try:
            response = self._client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OllamaUnreachableError(str(exc)) from exc
        payload: object = response.json()
        if not isinstance(payload, dict):
            raise OllamaUnreachableError("Ollama /api/tags gaf geen object terug")
        models = payload.get("models")
        names: set[str] = set()
        if isinstance(models, list):
            for item in models:
                if isinstance(item, dict):
                    name = item.get("name")
                    if isinstance(name, str) and name:
                        names.add(name)
        return names

    def chat(self, model: str, prompt: str) -> ChatMeasurement:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
            "think": False,
            "format": answer_json_schema(),
            "options": {"num_ctx": NUM_CTX},
        }
        started = self._clock()
        first_token_at: float | None = None
        parts: list[str] = []
        eval_count: int | None = None
        eval_duration_ns: int | None = None
        try:
            with self._client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    event = _parse_event(line)
                    if event is None:
                        continue
                    content = _message_content(event)
                    if content and first_token_at is None:
                        first_token_at = self._clock()
                    if content:
                        parts.append(content)
                    if event.get("done") is True:
                        eval_count = _as_int(event.get("eval_count"))
                        eval_duration_ns = _as_int(event.get("eval_duration"))
        except httpx.HTTPError as exc:
            raise OllamaUnreachableError(str(exc)) from exc
        ttft = None if first_token_at is None else first_token_at - started
        return ChatMeasurement(
            content="".join(parts),
            seconds_to_first_token=ttft,
            tokens_per_second=tokens_per_second(eval_count, eval_duration_ns),
            eval_count=eval_count,
        )


def _parse_event(line: str) -> dict[str, object] | None:
    try:
        parsed: object = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    event: dict[str, object] = {}
    for key, value in parsed.items():
        if isinstance(key, str):
            event[key] = value
    return event


def _message_content(event: dict[str, object]) -> str:
    message = event.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    return ""


def _as_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value
