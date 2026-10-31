"""OpenAI-compatible chat.

``json_schema`` with a strict schema falls back to ``json_object`` only when the
server rejects the schema (HTTP 400 or 422). Auth and rate-limit errors propagate.
"""

import json
from collections.abc import AsyncIterator, Callable, Sequence
from typing import Any, cast, get_args, get_origin

from openai import APIStatusError, AsyncOpenAI
from pydantic import AliasChoices, AliasPath, BaseModel

from wetvia.llm.parsing import parse_with_one_retry
from wetvia.llm.ports import ChatMessage, ModelT, StreamMetrics

_SCHEMA_UNSUPPORTED = frozenset({400, 422})
_MISSING = object()


def _strict_schema_compatible(schema: object) -> bool:
    """Return whether strict mode can represent this schema without changing it."""
    if isinstance(schema, list):
        return all(_strict_schema_compatible(item) for item in schema)
    if not isinstance(schema, dict):
        return True
    additional = schema.get("additionalProperties", False)
    if additional is not False:
        return False
    return all(_strict_schema_compatible(value) for value in schema.values())


def _allows_null(schema: object) -> bool:
    if not isinstance(schema, dict):
        return False
    if schema.get("type") == "null":
        return True
    for key in ("anyOf", "oneOf", "allOf"):
        variants = schema.get(key)
        if isinstance(variants, list) and any(_allows_null(item) for item in variants):
            return True
    return False


def _nullable(schema: object) -> object:
    if _allows_null(schema):
        return schema
    return {"anyOf": [schema, {"type": "null"}]}


def strict_json_schema(schema: object) -> object:
    """Normalize a strict-compatible schema without discarding dictionary semantics."""
    if isinstance(schema, list):
        return [strict_json_schema(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    result: dict[str, object] = {key: strict_json_schema(value) for key, value in schema.items()}
    properties = result.get("properties")
    is_object = result.get("type") == "object" or isinstance(properties, dict)
    if is_object:
        original_required = schema.get("required", [])
        required = set(original_required) if isinstance(original_required, list) else set()
        if isinstance(properties, dict):
            result["properties"] = {
                name: value if name in required else _nullable(value)
                for name, value in properties.items()
            }
            result["required"] = list(properties)
        elif "required" not in result:
            result["required"] = []
        # An object with additionalProperties true or a value schema represents
        # arbitrary keys. OpenAI strict mode cannot encode that contract.
        if result.get("additionalProperties", False) is False:
            result["additionalProperties"] = False
    return result


def _allows_none(annotation: object) -> bool:
    if annotation is type(None):
        return True
    return any(_allows_none(arg) for arg in get_args(annotation))


def _drop_defaulted_nulls(value: object, model: type[BaseModel]) -> object:
    """Let strict-mode null placeholders take the model's declared default."""
    if not isinstance(value, dict):
        return value
    for name, field in model.model_fields.items():
        for path in _validation_paths(name, field):
            target = _path_target(value, path)
            if target is None:
                continue
            container, key = target
            item = container[key]
            annotation = field.annotation
            if item is None and not field.is_required() and not _allows_none(annotation):
                del container[key]
                continue
            container[key] = _drop_nested_defaulted_nulls(item, annotation)
    return value


def _validation_paths(name: str, field: Any) -> list[tuple[str | int, ...]]:
    alias = field.validation_alias
    if isinstance(alias, str):
        aliases: list[str | AliasPath] = [alias]
    elif isinstance(alias, AliasPath):
        aliases = [alias]
    elif isinstance(alias, AliasChoices):
        aliases = alias.choices
    else:
        aliases = [name]

    paths = [tuple([alias] if isinstance(alias, str) else alias.path) for alias in aliases]
    if (name,) not in paths:
        paths.append((name,))
    return paths


def _path_target(
    value: dict[str, Any], path: tuple[str | int, ...]
) -> tuple[dict[str, Any], str] | None:
    if not path or not isinstance(path[-1], str):
        return None
    container: Any = value
    for part in path[:-1]:
        child = _path_child(container, part)
        if child is _MISSING:
            return None
        container = child
    key = path[-1]
    if isinstance(container, dict) and key in container:
        return container, key
    return None


def _path_child(container: Any, part: str | int) -> Any:
    if isinstance(container, dict) and isinstance(part, str) and part in container:
        return container[part]
    if isinstance(container, list) and isinstance(part, int) and 0 <= part < len(container):
        return container[part]
    return _MISSING


def _drop_nested_defaulted_nulls(value: object, annotation: object) -> object:
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin is not None and args:
        if origin in (list, tuple, set, frozenset, Sequence):
            item_type = args[0]
            if isinstance(value, list):
                return [_drop_nested_defaulted_nulls(item, item_type) for item in value]
        elif origin is dict and len(args) == 2 and isinstance(value, dict):
            return {key: _drop_nested_defaulted_nulls(item, args[1]) for key, item in value.items()}
        # Optional and other unions can contain a BaseModel branch. Select that
        # branch when the JSON value has object shape.
        for arg in args:
            if isinstance(arg, type) and issubclass(arg, BaseModel) and isinstance(value, dict):
                return _drop_defaulted_nulls(value, arg)
        return value
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return _drop_defaulted_nulls(value, annotation)
    return value


def _parse_openai_json(schema: type[ModelT], raw: str) -> ModelT:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return schema.model_validate_json(raw)
    normalized = _drop_defaulted_nulls(parsed, schema)
    return schema.model_validate_json(json.dumps(normalized))


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
        *,
        on_metrics: Callable[[StreamMetrics], None] | None = None,
    ) -> ModelT | str | AsyncIterator[str]:
        if stream and schema is not None:
            if not _strict_schema_compatible(schema.model_json_schema()):
                raise ValueError("schema is not supported for strict JSON-schema streaming")
            return self._stream(
                messages,
                temperature,
                self._json_schema_format(schema),
            )
        if schema is not None:
            model_schema = schema.model_json_schema()
            json_object_only = not _strict_schema_compatible(model_schema)

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

            return await parse_with_one_retry(
                schema,
                messages,
                complete,
                parse_json=lambda raw: (
                    schema.model_validate_json(raw)
                    if json_object_only
                    else _parse_openai_json(schema, raw)
                ),
            )
        if stream:
            return self._stream(messages, temperature, None)
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
            schema.model_json_schema(),
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
        response_format: dict[str, object] | None,
    ) -> AsyncIterator[str]:
        client = AsyncOpenAI(base_url=self._base_url, api_key=self._api_key, max_retries=0)
        payload = cast(Any, [dict(message) for message in messages])
        try:
            if response_format is None:
                stream = await client.chat.completions.create(
                    model=self._model,
                    messages=payload,
                    temperature=temperature,
                    stream=True,
                )
            else:
                stream = await client.chat.completions.create(
                    model=self._model,
                    messages=payload,
                    temperature=temperature,
                    response_format=cast(Any, response_format),
                    stream=True,
                )
            async for chunk in stream:
                choice = chunk.choices[0]
                delta = choice.delta.content
                if isinstance(delta, str) and delta:
                    yield delta
        finally:
            await client.close()
