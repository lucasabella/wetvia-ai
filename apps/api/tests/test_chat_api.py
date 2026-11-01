"""HTTP and OpenAPI contract tests for server-sent-events chat."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from datetime import date
from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI

from wetvia.answer import AnswerPipeline
from wetvia.api import create_app
from wetvia.api.deps import ChatContext, HealthContext
from wetvia.api.routes.chat import chat
from wetvia.api.schemas.chat import ChatRequest
from wetvia.db.engine import DbStatus
from wetvia.llm import ChatMessage
from wetvia.llm.adapters.fake import FakeProvider
from wetvia.retrieval import ScoredChunk, SourceDocument, SourceMetadata
from wetvia.retrieval.testing import FakeRetriever

_CHUNK_ID = UUID("1d44e29c-b982-4f28-b789-c5cd24fa2de8")
_DATE = date(2026, 10, 31)


def _source() -> SourceDocument:
    return SourceDocument(
        chunk_id=_CHUNK_ID,
        tekst="Synthetic source fixture for chat serialization tests.",
        metadata=SourceMetadata(
            bwb_id="SYNTHETIC-CHAT",
            regeling_titel="Synthetic chat fixture; not a legal regulation",
            artikel="fixture-1",
            lid=None,
            onderdeel=None,
            opschrift=None,
            kop_pad="Synthetic fixture",
            bron_url="https://example.test/chat/source",
            toestand_url="https://example.test/chat/state",
            geldig_vanaf=date(2026, 1, 1),
            geldig_tot=None,
            status="geldend",
            artikel_status="geldend",
        ),
    )


def _reply() -> str:
    return json.dumps(
        {
            "status": "beantwoord",
            "samenvatting": "Synthetic answer summary.",
            "punten": [
                {
                    "tekst": "Synthetic point supported by its cited fixture.",
                    "bron_ids": ["[1]"],
                }
            ],
            "voorbehouden": [],
            "vervolgstappen": [],
            "peildatum": _DATE.isoformat(),
        }
    )


def _health_context(*, cloud_configured: bool = False) -> HealthContext:
    async def check_db() -> DbStatus:
        return "ok"

    return HealthContext(
        version="0.0.0",
        check_db=check_db,
        local_configured=True,
        cloud_configured=cloud_configured,
    )


def _pipeline(
    *,
    source: SourceDocument | None = None,
    replies: list[str] | None = None,
) -> tuple[AnswerPipeline, FakeRetriever, FakeProvider]:
    chunks = [] if source is None else [ScoredChunk(source=source, score=0.5)]
    retriever = FakeRetriever(chunks)
    provider = FakeProvider(replies or [])
    return AnswerPipeline(retriever, provider), retriever, provider


def _parse_sse(response: httpx.Response) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    for frame in response.text.split("\n\n"):
        if not frame:
            continue
        event_name = next(line[7:] for line in frame.splitlines() if line.startswith("event: "))
        data = next(line[6:] for line in frame.splitlines() if line.startswith("data: "))
        events.append((event_name, json.loads(data)))
    return events


def _post(app: FastAPI, body: dict[str, Any]) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)

    async def send() -> httpx.Response:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post("/api/chat", json=body)

    return asyncio.run(send())


def test_chat_streams_in_order_with_only_included_sources_and_verified_notes(
    caplog: pytest.LogCaptureFixture,
) -> None:
    source = _source()
    pipeline, retriever, provider = _pipeline(source=source, replies=[_reply()])
    app = create_app(_health_context(), answer_pipelines={"local": pipeline})

    response = _post(
        app,
        {
            "messages": [{"role": "user", "content": "Synthetic test question?"}],
            "peildatum": _DATE.isoformat(),
        },
    )

    parsed = _parse_sse(response)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache, no-transform"
    assert response.headers["x-accel-buffering"] == "no"
    assert [name for name, _payload in parsed] == ["sources", "answer", "done"]
    sources = parsed[0][1]["sources"]
    assert [item["label"] for item in sources] == ["[1]"]
    assert sources[0]["chunk_id"] == str(source.chunk_id)
    assert sources[0]["tekst"] == source.tekst
    assert sources[0]["metadata"]["bwb_id"] == "SYNTHETIC-CHAT"
    answer = parsed[1][1]["answer"]
    assert answer["punten"][0]["bron_ids"] == [str(source.chunk_id)]
    assert "verifier_notes" in answer
    assert parsed[-1][1] == {"type": "done"}
    assert len(retriever.search_calls) == 1
    assert len(provider.calls) == 1
    assert "Synthetic test question?" not in caplog.text


def test_empty_retrieval_sends_empty_sources_then_deterministic_abstention() -> None:
    pipeline, retriever, provider = _pipeline()
    app = create_app(_health_context(), answer_pipelines={"local": pipeline})

    response = _post(
        app,
        {"messages": [{"role": "user", "content": "Synthetic question?"}]},
    )

    parsed = _parse_sse(response)
    assert [name for name, _payload in parsed] == ["sources", "answer", "done"]
    assert parsed[0][1]["sources"] == []
    assert parsed[1][1]["answer"]["status"] == "onzeker"
    assert provider.calls == []
    assert len(retriever.search_calls) == 1


def test_provider_error_after_sources_is_safe_and_ends_once() -> None:
    class BrokenProvider:
        async def chat(self, *_args: Any, **_kwargs: Any) -> Any:
            raise RuntimeError("internal endpoint and secret details")

    source = _source()
    retriever = FakeRetriever([ScoredChunk(source=source, score=0.5)])
    pipeline = AnswerPipeline(retriever, BrokenProvider())  # type: ignore[arg-type]
    app = create_app(_health_context(), answer_pipelines={"local": pipeline})

    response = _post(
        app,
        {
            "messages": [{"role": "user", "content": "Synthetic question?"}],
            "peildatum": _DATE.isoformat(),
        },
    )

    parsed = _parse_sse(response)
    assert [name for name, _payload in parsed] == ["sources", "error", "done"]
    assert "internal endpoint" not in response.text
    assert parsed[1][1]["message"]
    assert sum(name == "done" for name, _payload in parsed) == 1
    assert not any(name == "answer" for name, _payload in parsed)


def test_local_provider_failure_does_not_fall_back_to_cloud() -> None:
    class BrokenLocalProvider:
        calls = 0

        async def chat(self, *_args: Any, **_kwargs: Any) -> Any:
            self.calls += 1
            raise RuntimeError("Synthetic local provider failure")

    local_provider = BrokenLocalProvider()
    local_pipeline = AnswerPipeline(
        FakeRetriever([ScoredChunk(source=_source(), score=0.5)]),
        local_provider,  # type: ignore[arg-type]
    )
    cloud_pipeline, _cloud_retriever, cloud_provider = _pipeline(
        source=_source(), replies=[_reply()]
    )
    app = create_app(
        _health_context(cloud_configured=True),
        answer_pipelines={"local": local_pipeline, "cloud": cloud_pipeline},
    )

    response = _post(
        app,
        {
            "messages": [{"role": "user", "content": "Synthetic local question?"}],
            "peildatum": _DATE.isoformat(),
        },
    )

    assert [name for name, _payload in _parse_sse(response)] == [
        "sources",
        "error",
        "done",
    ]
    assert local_provider.calls == 1
    assert cloud_provider.calls == []


@pytest.mark.parametrize(
    "messages",
    [
        [{"role": "system", "content": "caller system prompt"}, {"role": "user", "content": "Q"}],
        [{"role": "assistant", "content": "not a final user turn"}],
        [{"role": "user", "content": "q" * 2001}],
    ],
)
def test_chat_rejects_system_final_assistant_and_oversized_current_message(
    messages: list[dict[str, str]],
) -> None:
    pipeline, _retriever, provider = _pipeline()
    app = create_app(_health_context(), answer_pipelines={"local": pipeline})

    response = _post(app, {"messages": messages})

    assert response.status_code == 422
    assert provider.calls == []


def test_chat_rejects_unconfigured_cloud_before_streaming() -> None:
    pipeline, _retriever, provider = _pipeline()
    app = create_app(_health_context(), answer_pipelines={"local": pipeline})

    response = _post(
        app,
        {"messages": [{"role": "user", "content": "Synthetic question?"}], "mode": "cloud"},
    )

    assert response.status_code == 503
    assert provider.calls == []


def test_chat_routes_local_default_and_cloud_to_separate_providers_concurrently() -> None:
    local_pipeline, _local_retriever, local_provider = _pipeline(
        source=_source(), replies=[_reply()]
    )
    cloud_pipeline, _cloud_retriever, cloud_provider = _pipeline(
        source=_source(), replies=[_reply()]
    )
    app = create_app(
        _health_context(cloud_configured=True),
        answer_pipelines={"local": local_pipeline, "cloud": cloud_pipeline},
    )

    async def exercise() -> tuple[httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            local, cloud = await asyncio.gather(
                client.post(
                    "/api/chat",
                    json={
                        "messages": [{"role": "user", "content": "Synthetic local?"}],
                        "peildatum": _DATE.isoformat(),
                    },
                ),
                client.post(
                    "/api/chat",
                    json={
                        "messages": [
                            {"role": "user", "content": "Synthetic prior cloud question?"},
                            {"role": "assistant", "content": "Synthetic prior cloud answer."},
                            {"role": "user", "content": "Synthetic cloud?"},
                        ],
                        "mode": "cloud",
                        "peildatum": _DATE.isoformat(),
                    },
                ),
            )
        return local, cloud

    local_response, cloud_response = asyncio.run(exercise())

    assert local_response.status_code == cloud_response.status_code == 200
    assert [name for name, _payload in _parse_sse(local_response)] == [
        "sources",
        "answer",
        "done",
    ]
    assert [name for name, _payload in _parse_sse(cloud_response)] == [
        "sources",
        "answer",
        "done",
    ]
    assert len(local_provider.calls) == len(cloud_provider.calls) == 1
    assert "Synthetic local?" in local_provider.calls[0][0][-1]["content"]
    assert "Synthetic cloud?" in cloud_provider.calls[0][0][-1]["content"]
    cloud_prompt = "\n".join(message["content"] for message in cloud_provider.calls[0][0])
    assert "Synthetic prior cloud" not in cloud_prompt


def test_chat_passes_prior_history_to_provider_as_non_authoritative_context() -> None:
    source = _source()
    pipeline, _retriever, provider = _pipeline(source=source, replies=[_reply()])
    app = create_app(_health_context(), answer_pipelines={"local": pipeline})

    response = _post(
        app,
        {
            "messages": [
                {"role": "user", "content": "Earlier synthetic question."},
                {"role": "assistant", "content": "Earlier assistant response."},
                {"role": "user", "content": "Current synthetic question."},
            ],
            "peildatum": _DATE.isoformat(),
        },
    )

    assert response.status_code == 200
    messages = provider.calls[0][0]
    assert [message["role"] for message in messages] == ["system", "user", "assistant", "user"]
    assert messages[1]["content"] == "Earlier synthetic question."
    assert messages[2]["content"] == "Earlier assistant response."
    assert "BRONNEN:" not in messages[2]["content"]
    assert "BRONNEN:" in messages[-1]["content"]
    assert "Eerdere gebruikers- en assistentberichten" in messages[0]["content"]
    assert "uitsluitend gesprekcontext" in messages[0]["content"]


def test_chat_is_unavailable_without_an_injected_pipeline() -> None:
    response = _post(
        create_app(_health_context()),
        {"messages": [{"role": "user", "content": "Synthetic question?"}]},
    )

    assert response.status_code == 503


def _walk_refs(value: Any) -> list[str]:
    if isinstance(value, dict):
        refs = [value["$ref"]] if isinstance(value.get("$ref"), str) else []
        return refs + [ref for child in value.values() for ref in _walk_refs(child)]
    if isinstance(value, list):
        return [ref for child in value for ref in _walk_refs(child)]
    return []


def test_chat_openapi_registers_all_sse_event_components_and_resolves_refs() -> None:
    spec = create_app(_health_context()).openapi()
    schemas = spec["components"]["schemas"]
    response_schema = spec["paths"]["/api/chat"]["post"]["responses"]["200"]
    stream_content = response_schema["content"]["text/event-stream"]

    assert stream_content["x-event-schema"] == {"$ref": "#/components/schemas/ChatEvent"}
    assert "ChatEvent" in schemas
    assert "ChatRequest" in schemas
    assert {"ChatSourcesEvent", "ChatAnswerEvent", "ChatErrorEvent", "ChatDoneEvent"} <= set(
        schemas
    )
    assert "verifier_notes" in schemas["VerifiedAnswer"]["properties"]
    for reference in _walk_refs(spec):
        assert reference.startswith("#/components/schemas/")
        component_name = reference.removeprefix("#/components/schemas/")
        assert component_name in schemas, f"unresolved OpenAPI reference {reference}"


class _BlockingProvider:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = asyncio.Event()

    async def chat(
        self,
        _messages: Sequence[ChatMessage],
        _schema: type[object] | None,
        _stream: bool,
        _temperature: float,
    ) -> object:
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        raise AssertionError("test releases the provider only to exercise cancellation")


def test_sources_frame_is_yielded_before_provider_starts_and_disconnect_cancels_work() -> None:
    async def exercise() -> None:
        source = _source()
        provider = _BlockingProvider()
        retriever = FakeRetriever([ScoredChunk(source=source, score=0.5)])
        pipeline = AnswerPipeline(retriever, provider)  # type: ignore[arg-type]
        response = await chat(
            ChatRequest(
                messages=[{"role": "user", "content": "Synthetic question?"}],
                peildatum=_DATE,
            ),
            ChatContext(answer_pipelines={"local": pipeline}),
        )
        iterator = response.body_iterator
        source_frame = await anext(iterator)  # type: ignore[arg-type]
        assert source_frame.startswith(b"event: sources\n")
        assert not provider.started.is_set()

        pending_frame: asyncio.Task[bytes] = asyncio.create_task(anext(iterator))  # type: ignore[arg-type]
        await asyncio.wait_for(provider.started.wait(), timeout=1)
        assert not pending_frame.done()
        pending_frame.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending_frame
        await asyncio.wait_for(provider.cancelled.wait(), timeout=1)

    asyncio.run(exercise())
