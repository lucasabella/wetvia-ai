"""OpenAI-compatible chat.

``json_schema`` falls back to ``json_object`` when the server rejects it.
"""

from collections.abc import AsyncIterator, Sequence
from typing import Any, cast

from openai import APIStatusError, AsyncOpenAI

from wetvia.llm.parsing import parse_with_one_retry
from wetvia.llm.ports import ChatMessage, ModelT


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
            return await parse_with_one_retry(
                schema,
                messages,
                lambda current: self._complete_schema(current, schema, temperature),
            )
        if stream:
            return self._stream(messages, temperature)
        return await self._complete_text(messages, temperature)

    async def _complete_schema(
        self,
        messages: Sequence[ChatMessage],
        schema: type[ModelT],
        temperature: float,
    ) -> str:
        json_schema: dict[str, object] = {
            "type": "json_schema",
            "json_schema": {
                "name": schema.__name__,
                "schema": schema.model_json_schema(),
                "strict": True,
            },
        }
        try:
            return await self._create(messages, temperature, json_schema)
        except APIStatusError as exc:
            if exc.status_code >= 500:
                raise
            return await self._create(messages, temperature, {"type": "json_object"})

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
