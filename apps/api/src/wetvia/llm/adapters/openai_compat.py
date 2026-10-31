"""OpenAI-compatible chat.

``json_schema`` with a strict schema falls back to ``json_object`` only when the
server rejects the schema (HTTP 400 or 422). Auth and rate-limit errors propagate.
"""

import json
from collections.abc import AsyncIterator, Sequence
from typing import Any, cast

from openai import APIStatusError, AsyncOpenAI

from wetvia.llm.parsing import parse_with_one_retry
from wetvia.llm.ports import ChatMessage, ModelT

_SCHEMA_UNSUPPORTED = frozenset({400, 422})


def strict_json_schema(schema: object) -> object:
    """Close every object, including ``$defs``, so ``strict: true`` is accepted."""
    if isinstance(schema, list):
        return [strict_json_schema(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    result: dict[str, object] = {key: strict_json_schema(value) for key, value in schema.items()}
    properties = result.get("properties")
    is_object = result.get("type") == "object" or isinstance(properties, dict)
    if is_object:
        if isinstance(properties, dict):
            result["required"] = list(properties)
        elif "required" not in result:
            result["required"] = []
        result["additionalProperties"] = False
    return result


class OpenAICompatProvider:
    def __init__(self, base_url: str, model: str, api_key: str) -> None:
        self._base_url = base_url
        self._model = model
        self._api_key = api_key

    def __repr__(self) -> str:
        return f"OpenAICompatProvider(base_url={self._base_url!r}, model={self._model!r})"

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
            json_object_only = False

            async def complete(current: Sequence[ChatMessage]) -> str:
                nonlocal json_object_only
                if json_object_only:
                    return await self._create_json_object(current, schema, temperature)
                try:
                    schema_format = self._json_schema_format(schema)
                    return await self._create(current, temperature, schema_format)
                except APIStatusError as exc:
                    if exc.status_code not in _SCHEMA_UNSUPPORTED:
                        raise
                    json_object_only = True
                    return await self._create_json_object(current, schema, temperature)

            return await parse_with_one_retry(schema, messages, complete)
        if stream:
            return self._stream(messages, temperature)
        return await self._complete_text(messages, temperature)

    def _json_schema_format(self, schema: type[ModelT]) -> dict[str, object]:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": schema.__name__,
                "schema": strict_json_schema(schema.model_json_schema()),
                "strict": True,
            },
        }

    async def _create_json_object(
        self,
        messages: Sequence[ChatMessage],
        schema: type[ModelT],
        temperature: float,
    ) -> str:
        encoded = json.dumps(
            strict_json_schema(schema.model_json_schema()),
            separators=(",", ":"),
        )
        instruction = ChatMessage(
            role="system",
            content=f"Reply with JSON only. JSON schema: {encoded}",
        )
        return await self._create((instruction, *messages), temperature, {"type": "json_object"})

    async def _complete_text(self, messages: Sequence[ChatMessage], temperature: float) -> str:
        return await self._create(messages, temperature, None)

    async def _create(
        self,
        messages: Sequence[ChatMessage],
        temperature: float,
        response_format: dict[str, object] | None,
    ) -> str:
        client = AsyncOpenAI(base_url=self._base_url, api_key=self._api_key, max_retries=0)
        payload = cast(Any, [dict(message) for message in messages])
        try:
            if response_format is None:
                completion = await client.chat.completions.create(
                    model=self._model,
                    messages=payload,
                    temperature=temperature,
                    stream=False,
                )
            else:
                completion = await client.chat.completions.create(
                    model=self._model,
                    messages=payload,
                    temperature=temperature,
                    response_format=cast(Any, response_format),
                    stream=False,
                )
        finally:
            await client.close()
        content = completion.choices[0].message.content
        return content if isinstance(content, str) else ""

    async def _stream(
        self,
        messages: Sequence[ChatMessage],
        temperature: float,
    ) -> AsyncIterator[str]:
        client = AsyncOpenAI(base_url=self._base_url, api_key=self._api_key, max_retries=0)
        payload = cast(Any, [dict(message) for message in messages])
        try:
            stream = await client.chat.completions.create(
                model=self._model,
                messages=payload,
                temperature=temperature,
                stream=True,
            )
            async for chunk in stream:
                choice = chunk.choices[0]
                delta = choice.delta.content
                if isinstance(delta, str) and delta:
                    yield delta
        finally:
            await client.close()
