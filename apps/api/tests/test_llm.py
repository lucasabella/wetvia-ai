"""LLM adapters. HTTP is mocked; no model and no paid API."""

import ast
import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import respx
from openai import APIStatusError
from pydantic import BaseModel, ValidationError

from wetvia.bootstrap import get_provider
from wetvia.config import Settings
from wetvia.core import LlmProvider
from wetvia.llm.adapters.fake import FakeProvider
from wetvia.llm.adapters.ollama import OllamaProvider
from wetvia.llm.adapters.openai_compat import OpenAICompatProvider, strict_json_schema
from wetvia.llm.ports import ChatMessage

_LLM_ROOT = Path(__file__).resolve().parents[1] / "src" / "wetvia" / "llm"


class Probe(BaseModel):
    value: str


class DictionaryProbe(BaseModel):
    values: dict[str, str]


class DefaultedProbe(BaseModel):
    label: str = "use the model default"


class NestedDefaultedProbe(BaseModel):
    item: DefaultedProbe


def _settings(provider: LlmProvider, *, api_key: str | None = None) -> Settings:
    return Settings(
        _env_file=None,
        database_url="postgresql+psycopg://wetvia:change-me@127.0.0.1:5432/wetvia",
        llm_provider=provider,
        llm_base_url="http://llm.test/v1" if provider == "openai_compat" else "http://ollama.test",
        llm_model="dummy-model",
        embedding_model="intfloat/multilingual-e5-large-instruct",
        llm_api_key=api_key,
    )


def _messages() -> list[ChatMessage]:
    return [ChatMessage(role="user", content="ping")]


def _ollama_body(content: str) -> dict[str, object]:
    return {"message": {"role": "assistant", "content": content}}


def _openai_body(content: str) -> dict[str, object]:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": "dummy-model",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }


def _sse(payload: dict[str, object]) -> bytes:
    return f"data: {json.dumps(payload)}\n\n".encode()


def _openai_chunk(content: str | None, *, done: bool = False) -> dict[str, object]:
    delta: dict[str, str] = {}
    if content is not None:
        delta["content"] = content
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion.chunk",
        "created": 0,
        "model": "dummy-model",
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": "stop" if done else None,
            }
        ],
    }


def test_llm_package_does_not_import_settings() -> None:
    for path in _LLM_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and "wetvia.config" in node.module:
                raise AssertionError(path)


def test_openai_compat_requires_an_api_key() -> None:
    with pytest.raises(RuntimeError, match="LLM_API_KEY"):
        get_provider(_settings("openai_compat"))


def test_get_provider_uses_settings_not_a_network() -> None:
    ollama = get_provider(_settings("ollama"))
    cloud = get_provider(_settings("openai_compat", api_key="should-not-leak"))
    assert isinstance(ollama, OllamaProvider)
    assert isinstance(cloud, OpenAICompatProvider)
    assert "should-not-leak" not in repr(cloud)


def test_ollama_schema_sets_format_and_disables_thinking() -> None:
    async def run() -> Probe:
        with respx.mock:
            route = respx.post("http://ollama.test/api/chat").mock(
                return_value=httpx.Response(200, json=_ollama_body('{"value":"ok"}'))
            )
            provider = OllamaProvider("http://ollama.test", "dummy-model")
            result = await provider.chat(_messages(), Probe, False, 0.0)
        body = json.loads(route.calls[0].request.content)
        assert body["think"] is False
        assert body["format"]["title"] == "Probe"
        assert body["stream"] is False
        assert isinstance(result, Probe)
        return result

    assert asyncio.run(run()).value == "ok"


def test_ollama_text_call_does_not_force_think() -> None:
    async def run() -> None:
        with respx.mock:
            route = respx.post("http://ollama.test/api/chat").mock(
                return_value=httpx.Response(200, json=_ollama_body("hello"))
            )
            provider = OllamaProvider("http://ollama.test", "dummy-model")
            text = await provider.chat(_messages(), None, False, 0.2)
        body = json.loads(route.calls[0].request.content)
        assert "think" not in body
        assert "format" not in body
        assert text == "hello"

    asyncio.run(run())


def test_ollama_retries_invalid_json_once() -> None:
    async def run() -> None:
        with respx.mock:
            route = respx.post("http://ollama.test/api/chat").mock(
                side_effect=[
                    httpx.Response(200, json=_ollama_body("not-json")),
                    httpx.Response(200, json=_ollama_body("still-not")),
                ]
            )
            provider = OllamaProvider("http://ollama.test", "dummy-model")
            with pytest.raises(ValidationError):
                await provider.chat(_messages(), Probe, False, 0.0)
        assert route.call_count == 2
        second = json.loads(route.calls[1].request.content)
        assert "Validation failed" in second["messages"][-1]["content"]

    asyncio.run(run())


def test_ollama_retries_then_accepts_valid_json() -> None:
    async def run() -> Probe:
        with respx.mock:
            respx.post("http://ollama.test/api/chat").mock(
                side_effect=[
                    httpx.Response(200, json=_ollama_body("not-json")),
                    httpx.Response(200, json=_ollama_body('{"value":"ok"}')),
                ]
            )
            provider = OllamaProvider("http://ollama.test", "dummy-model")
            result = await provider.chat(_messages(), Probe, False, 0.0)
        assert isinstance(result, Probe)
        return result

    assert asyncio.run(run()).value == "ok"


def test_ollama_error_body_is_raised() -> None:
    async def run() -> None:
        with respx.mock:
            respx.post("http://ollama.test/api/chat").mock(
                return_value=httpx.Response(200, json={"error": "model not found"})
            )
            provider = OllamaProvider("http://ollama.test", "dummy-model")
            with pytest.raises(RuntimeError, match="model not found"):
                await provider.chat(_messages(), None, False, 0.0)

    asyncio.run(run())


def test_ollama_stream_error_is_raised() -> None:
    async def run() -> None:
        with respx.mock:
            respx.post("http://ollama.test/api/chat").mock(
                return_value=httpx.Response(200, text='{"error":"model not found"}\n')
            )
            provider = OllamaProvider("http://ollama.test", "dummy-model")
            stream = await provider.chat(_messages(), None, True, 0.0)
            assert isinstance(stream, AsyncIterator)
            with pytest.raises(RuntimeError, match="model not found"):
                _ = [chunk async for chunk in stream]

    asyncio.run(run())


def test_ollama_streams_text_chunks() -> None:
    raw = (
        '{"message":{"role":"assistant","content":"Hel"},"done":false}\n'
        '{"message":{"role":"assistant","content":"lo"},"done":true}\n'
    )

    async def run() -> list[str]:
        with respx.mock:
            respx.post("http://ollama.test/api/chat").mock(
                return_value=httpx.Response(200, text=raw)
            )
            provider = OllamaProvider("http://ollama.test", "dummy-model")
            stream = await provider.chat(_messages(), None, True, 0.0)
            assert isinstance(stream, AsyncIterator)
            return [chunk async for chunk in stream]

    assert asyncio.run(run()) == ["Hel", "lo"]


def test_openai_falls_back_to_json_object_when_schema_is_rejected() -> None:
    async def run() -> None:
        with respx.mock:
            route = respx.post("http://llm.test/v1/chat/completions").mock(
                side_effect=[
                    httpx.Response(
                        400,
                        json={
                            "error": {
                                "message": "unsupported",
                                "type": "invalid_request_error",
                            }
                        },
                    ),
                    httpx.Response(200, json=_openai_body('{"value":"ok"}')),
                ]
            )
            provider = OpenAICompatProvider("http://llm.test/v1", "dummy-model", "test-key")
            result = await provider.chat(_messages(), Probe, False, 0.0)
        first = json.loads(route.calls[0].request.content)
        second = json.loads(route.calls[1].request.content)
        schema = first["response_format"]["json_schema"]["schema"]
        assert schema["additionalProperties"] is False
        assert schema["required"] == ["value"]
        assert first["response_format"]["json_schema"]["strict"] is True
        assert second["response_format"] == {"type": "json_object"}
        instruction = second["messages"][0]
        assert instruction["role"] == "system"
        assert "JSON" in instruction["content"]
        assert "Probe" in instruction["content"]
        assert '"additionalProperties":false' not in instruction["content"]
        assert route.calls[0].request.headers["authorization"] == "Bearer test-key"
        assert isinstance(result, Probe)
        assert result.value == "ok"

    asyncio.run(run())


@pytest.mark.parametrize("status_code", [401, 403, 404, 429])
def test_openai_does_not_fall_back_on_non_schema_errors(status_code: int) -> None:
    async def run() -> None:
        with respx.mock:
            route = respx.post("http://llm.test/v1/chat/completions").mock(
                return_value=httpx.Response(
                    status_code,
                    json={"error": {"message": "nope", "type": "invalid_request_error"}},
                )
            )
            provider = OpenAICompatProvider("http://llm.test/v1", "dummy-model", "test-key")
            with pytest.raises(APIStatusError) as caught:
                await provider.chat(_messages(), Probe, False, 0.0)
        assert caught.value.status_code == status_code
        assert route.call_count == 1

    asyncio.run(run())


def test_openai_json_object_fallback_is_kept_for_the_retry() -> None:
    async def run() -> None:
        with respx.mock:
            route = respx.post("http://llm.test/v1/chat/completions").mock(
                side_effect=[
                    httpx.Response(
                        422,
                        json={"error": {"message": "unsupported", "type": "invalid_request_error"}},
                    ),
                    httpx.Response(200, json=_openai_body("not-json")),
                    httpx.Response(200, json=_openai_body('{"value":"ok"}')),
                ]
            )
            provider = OpenAICompatProvider("http://llm.test/v1", "dummy-model", "test-key")
            result = await provider.chat(_messages(), Probe, False, 0.0)
        assert route.call_count == 3
        formats = [
            json.loads(call.request.content)["response_format"]["type"] for call in route.calls
        ]
        assert formats == ["json_schema", "json_object", "json_object"]
        retry = json.loads(route.calls[2].request.content)
        assert retry["messages"][0]["content"].startswith("Reply with JSON only")
        assert any("Validation failed" in message["content"] for message in retry["messages"])
        assert isinstance(result, Probe)

    asyncio.run(run())


def test_strict_json_schema_closes_objects_and_defs() -> None:
    strict = strict_json_schema(
        {
            "type": "object",
            "properties": {"child": {"$ref": "#/$defs/Child"}},
            "$defs": {
                "Child": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                }
            },
        }
    )
    assert isinstance(strict, dict)
    assert strict["additionalProperties"] is False
    assert strict["required"] == ["child"]
    child = strict["$defs"]["Child"]
    assert child["additionalProperties"] is False
    assert child["required"] == ["name"]


def test_strict_json_schema_makes_defaulted_fields_nullable() -> None:
    strict = strict_json_schema(DefaultedProbe.model_json_schema())

    assert isinstance(strict, dict)
    assert strict["required"] == ["label"]
    properties = strict["properties"]
    assert isinstance(properties, dict)
    assert properties["label"] == {
        "anyOf": [
            {"default": "use the model default", "title": "Label", "type": "string"},
            {"type": "null"},
        ]
    }


def test_openai_defaulted_null_uses_model_default() -> None:
    async def run() -> DefaultedProbe:
        with respx.mock:
            route = respx.post("http://llm.test/v1/chat/completions").mock(
                return_value=httpx.Response(200, json=_openai_body('{"label":null}'))
            )
            provider = OpenAICompatProvider("http://llm.test/v1", "dummy-model", "test-key")
            result = await provider.chat(_messages(), DefaultedProbe, False, 0.0)
        body = json.loads(route.calls[0].request.content)
        nullable = body["response_format"]["json_schema"]["schema"]["properties"]["label"]
        assert {"type": "null"} in nullable["anyOf"]
        assert isinstance(result, DefaultedProbe)
        return result

    assert asyncio.run(run()).label == "use the model default"


def test_openai_defaulted_null_uses_nested_model_default() -> None:
    async def run() -> NestedDefaultedProbe:
        with respx.mock:
            respx.post("http://llm.test/v1/chat/completions").mock(
                return_value=httpx.Response(200, json=_openai_body('{"item":{"label":null}}'))
            )
            provider = OpenAICompatProvider("http://llm.test/v1", "dummy-model", "test-key")
            result = await provider.chat(_messages(), NestedDefaultedProbe, False, 0.0)
        assert isinstance(result, NestedDefaultedProbe)
        return result

    assert asyncio.run(run()).item.label == "use the model default"


def test_openai_dict_schema_uses_original_json_object_schema() -> None:
    async def run() -> DictionaryProbe:
        with respx.mock:
            route = respx.post("http://llm.test/v1/chat/completions").mock(
                return_value=httpx.Response(200, json=_openai_body('{"values":{"a":"one"}}'))
            )
            provider = OpenAICompatProvider("http://llm.test/v1", "dummy-model", "test-key")
            result = await provider.chat(_messages(), DictionaryProbe, False, 0.0)
        body = json.loads(route.calls[0].request.content)
        assert body["response_format"] == {"type": "json_object"}
        instruction = body["messages"][0]["content"]
        original_schema = DictionaryProbe.model_json_schema()
        assert json.dumps(original_schema, separators=(",", ":")) in instruction
        assert '"additionalProperties":false' not in instruction
        assert isinstance(result, DictionaryProbe)
        return result

    assert asyncio.run(run()).values == {"a": "one"}


def test_openai_next_chat_starts_with_json_schema_again() -> None:
    async def run() -> None:
        with respx.mock:
            route = respx.post("http://llm.test/v1/chat/completions").mock(
                side_effect=[
                    httpx.Response(
                        400,
                        json={"error": {"message": "unsupported", "type": "invalid_request_error"}},
                    ),
                    httpx.Response(200, json=_openai_body('{"value":"ok"}')),
                    httpx.Response(200, json=_openai_body('{"value":"again"}')),
                ]
            )
            provider = OpenAICompatProvider("http://llm.test/v1", "dummy-model", "test-key")
            first = await provider.chat(_messages(), Probe, False, 0.0)
            second = await provider.chat(_messages(), Probe, False, 0.0)
        formats = [
            json.loads(call.request.content)["response_format"]["type"] for call in route.calls
        ]
        assert formats == ["json_schema", "json_object", "json_schema"]
        assert isinstance(first, Probe)
        assert first.value == "ok"
        assert isinstance(second, Probe)
        assert second.value == "again"

    asyncio.run(run())


def test_openai_retries_invalid_json_once() -> None:
    async def run() -> None:
        with respx.mock:
            route = respx.post("http://llm.test/v1/chat/completions").mock(
                side_effect=[
                    httpx.Response(200, json=_openai_body("not-json")),
                    httpx.Response(200, json=_openai_body('{"value":"fixed"}')),
                ]
            )
            provider = OpenAICompatProvider("http://llm.test/v1", "dummy-model", "test-key")
            result = await provider.chat(_messages(), Probe, False, 0.0)
        assert route.call_count == 2
        second = json.loads(route.calls[1].request.content)
        assert "Validation failed" in second["messages"][-1]["content"]
        assert isinstance(result, Probe)
        assert result.value == "fixed"

    asyncio.run(run())


def test_openai_streams_text_chunks() -> None:
    body = b"".join(
        [
            _sse(_openai_chunk("Hel")),
            _sse(_openai_chunk("lo")),
            _sse(_openai_chunk(None, done=True)),
            b"data: [DONE]\n\n",
        ]
    )

    async def run() -> list[str]:
        with respx.mock:
            respx.post("http://llm.test/v1/chat/completions").mock(
                return_value=httpx.Response(
                    200,
                    content=body,
                    headers={"content-type": "text/event-stream"},
                )
            )
            provider = OpenAICompatProvider("http://llm.test/v1", "dummy-model", "test-key")
            stream = await provider.chat(_messages(), None, True, 0.0)
            assert isinstance(stream, AsyncIterator)
            return [chunk async for chunk in stream]

    assert asyncio.run(run()) == ["Hel", "lo"]


def test_fake_validates_and_streams_without_http() -> None:
    async def run() -> tuple[Probe, list[str]]:
        provider = FakeProvider(["not-json", '{"value":"ok"}'], chunks=["a", "b"])
        parsed = await provider.chat(_messages(), Probe, False, 0.0)
        stream = await provider.chat(_messages(), None, True, 0.0)
        assert isinstance(parsed, Probe)
        assert isinstance(stream, AsyncIterator)
        chunks = [chunk async for chunk in stream]
        return parsed, chunks

    parsed, chunks = asyncio.run(run())
    assert parsed.value == "ok"
    assert chunks == ["a", "b"]


def test_schema_and_stream_cannot_be_combined() -> None:
    async def run() -> None:
        provider = FakeProvider(['{"value":"ok"}'])
        with pytest.raises(ValueError, match="schema and stream"):
            await provider.chat(_messages(), Probe, True, 0.0)

    asyncio.run(run())
