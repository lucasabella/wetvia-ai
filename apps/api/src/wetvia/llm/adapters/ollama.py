"""Ollama native ``/api/chat``. Structured calls always send ``think: false``."""

import json
from collections.abc import AsyncIterator, Sequence

import httpx

from wetvia.llm.parsing import parse_with_one_retry
from wetvia.llm.ports import ChatMessage, ModelT

_TIMEOUT = httpx.Timeout(60.0)


def _raise_if_ollama_error(body: object) -> None:
    if not isinstance(body, dict) or "error" not in body:
        return
    detail = body["error"]
    if isinstance(detail, str) and detail:
        raise RuntimeError(f"Ollama error: {detail}")
    raise RuntimeError("Ollama error")


class OllamaProvider:
    def __init__(self, base_url: str, model: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model

    def __repr__(self) -> str:
        return f"OllamaProvider(base_url={self._base_url!r}, model={self._model!r})"

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        schema: type[ModelT] | None,
        stream: bool,
        temperature: float,
    ) -> ModelT | str | AsyncIterator[str]:
        if schema is not None:
            if stream:
                raise ValueError("schema and stream cannot be combined")
            return await parse_with_one_retry(
                schema,
                messages,
                lambda current: self._complete(current, schema, temperature),
            )
        if stream:
            return self._stream(messages, temperature)
        return await self._complete_text(messages, temperature)

    async def _complete(
        self,
        messages: Sequence[ChatMessage],
        schema: type[ModelT],
        temperature: float,
    ) -> str:
        payload = self._payload(messages, temperature, stream=False)
        payload["format"] = schema.model_json_schema()
        payload["think"] = False
        return await self._post(payload)

    async def _complete_text(self, messages: Sequence[ChatMessage], temperature: float) -> str:
        return await self._post(self._payload(messages, temperature, stream=False))

    async def _post(self, payload: dict[str, object]) -> str:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(f"{self._base_url}/api/chat", json=payload)
            response.raise_for_status()
            body = response.json()
        _raise_if_ollama_error(body)
        message = body.get("message")
        if not isinstance(message, dict):
            return ""
        content = message.get("content")
        return content if isinstance(content, str) else ""

    async def _stream(
        self,
        messages: Sequence[ChatMessage],
        temperature: float,
    ) -> AsyncIterator[str]:
        payload = self._payload(messages, temperature, stream=True)
        url = f"{self._base_url}/api/chat"
        async with (
            httpx.AsyncClient(timeout=_TIMEOUT) as client,
            client.stream("POST", url, json=payload) as streamed,
        ):
            streamed.raise_for_status()
            async for line in streamed.aiter_lines():
                if not line.strip():
                    continue
                data = json.loads(line)
                _raise_if_ollama_error(data)
                message = data.get("message")
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str) and content:
                        yield content
                if data.get("done") is True:
                    break

    def _payload(
        self,
        messages: Sequence[ChatMessage],
        temperature: float,
        *,
        stream: bool,
    ) -> dict[str, object]:
        return {
            "model": self._model,
            "messages": [dict(message) for message in messages],
            "stream": stream,
            "options": {"temperature": temperature},
        }
