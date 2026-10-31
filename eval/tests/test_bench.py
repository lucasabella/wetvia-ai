"""Harness tests with a fake public LLM provider; no model and no benchmark numbers."""

from __future__ import annotations

import asyncio
import json
import subprocess
import threading
from collections.abc import AsyncIterator, Callable, Sequence
from datetime import datetime
from pathlib import Path

import pytest
from pydantic import BaseModel

from wetvia.llm import ChatMessage, LLMProvider, StreamMetrics
from wetvia_eval.bench import (
    DEFAULT_MODELS,
    ModelResult,
    OllamaUnreachableError,
    main,
    model_is_listed,
    render_report,
    run_benchmark,
)
from wetvia_eval.questions import BenchQuestion, load_questions, prompt_for
from wetvia_eval.schema import AnswerV1, validate_answer
from wetvia_eval.vram import (
    VramSampler,
    parse_nvidia_smi_memory_mib,
    peak_mib,
    query_nvidia_smi_mib,
)


def _valid_answer() -> str:
    return AnswerV1(
        status="onzeker",
        samenvatting="niet beoordeeld",
        punten=[],
        voorbehouden=[],
        vervolgstappen=[],
        peildatum="2026-10-30",
    ).model_dump_json()


class _FakeProvider:
    def __init__(
        self,
        *,
        model: str,
        response: str,
        metrics: StreamMetrics | None = None,
        error_for: Callable[[str], str | None] | None = None,
        active_model: dict[str, str | None] | None = None,
        delay_seconds: float = 0.0,
    ) -> None:
        self.model = model
        self.response = response
        self.metrics = metrics
        self.error_for = error_for
        self.active_model = active_model
        self.delay_seconds = delay_seconds

    async def chat[ModelT: BaseModel](
        self,
        messages: Sequence[ChatMessage],
        schema: type[ModelT] | None,
        stream: bool,
        temperature: float,
        *,
        on_metrics: Callable[[StreamMetrics], None] | None = None,
    ) -> ModelT | str | AsyncIterator[str]:
        if schema is not AnswerV1 or not stream or temperature != 0.0:
            raise AssertionError("benchmark moet AnswerV1 in een tekststream meesturen")

        async def chunks() -> AsyncIterator[str]:
            prompt = "\n".join(message["content"] for message in messages)
            phase = "warmup" if "VRAAG:\nping\n" in prompt else "measured"
            if self.active_model is not None:
                self.active_model["model"] = f"{self.model}:{phase}"
            try:
                if self.delay_seconds:
                    await asyncio.sleep(self.delay_seconds)
                error = self.error_for(prompt) if self.error_for is not None else None
                if error is not None:
                    raise RuntimeError(error)
                yield self.response
                if on_metrics is not None and self.metrics is not None:
                    on_metrics(self.metrics)
            finally:
                if self.active_model is not None:
                    self.active_model["model"] = None

        return chunks()


def _factory(
    *,
    response: str | Callable[[str], str] | None = None,
    metrics: StreamMetrics | None = None,
    active_model: dict[str, str | None] | None = None,
    delay_seconds: float = 0.0,
    error_for: Callable[[str], str | None] | None = None,
) -> tuple[Callable[[str, int | str | None], LLMProvider], list[tuple[str, int | str | None]]]:
    created: list[tuple[str, int | str | None]] = []
    default_response = _valid_answer() if response is None else response
    default_metrics = (
        StreamMetrics(completion_tokens=4, generation_seconds=2.0) if metrics is None else metrics
    )

    def create(model: str, keep_alive: int | str | None) -> LLMProvider:
        created.append((model, keep_alive))
        return _FakeProvider(
            model=model,
            response=default_response(model) if callable(default_response) else default_response,
            metrics=default_metrics,
            error_for=error_for,
            active_model=active_model,
            delay_seconds=delay_seconds,
        )

    return create, created


def test_default_models_match_issue() -> None:
    assert DEFAULT_MODELS == ("qwen3.5:9b", "qwen3.5:4b", "gemma4:12b", "ministral-3:8b")


def test_model_tags_match_an_exact_tag_or_its_latest_tag() -> None:
    assert model_is_listed({"qwen3.5:9b"}, "qwen3.5:9b")
    assert model_is_listed({"qwen3.5:9b:latest"}, "qwen3.5:9b")
    assert not model_is_listed({"qwen3.5:4b"}, "qwen3.5:9b")


def test_prompt_uses_only_the_given_source_text() -> None:
    question = BenchQuestion(id="x", vraag="Ping?", brontekst="Alleen deze tekst.")
    prompt = prompt_for(question)
    assert "Ping?" in prompt
    assert "Alleen deze tekst." in prompt
    assert "zet status op onzeker" in prompt


def test_load_questions_rejects_a_missing_question(tmp_path: Path) -> None:
    path = tmp_path / "bench.jsonl"
    path.write_text('{"id": "a"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="vraag"):
        load_questions(path)


def test_schema_accepts_the_documented_shape_and_rejects_prose() -> None:
    assert validate_answer(_valid_answer())
    assert not validate_answer("dit is geen json")


def test_summary_limit_is_80_words() -> None:
    payload = json.loads(_valid_answer())
    assert isinstance(payload, dict)
    payload["samenvatting"] = " ".join(["woord"] * 80)
    assert validate_answer(json.dumps(payload))
    payload["samenvatting"] = " ".join(["woord"] * 81)
    assert not validate_answer(json.dumps(payload))


def test_broken_json_line_includes_path_and_line_number(tmp_path: Path) -> None:
    path = tmp_path / "bench.jsonl"
    path.write_text('{"id": "a", "vraag": "ok"}\n{kapot\n', encoding="utf-8")
    with pytest.raises(ValueError, match=rf"{path.name}:2: ongeldige JSON"):
        load_questions(path)


def test_duplicate_ids_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bench.jsonl"
    line = '{"id": "a", "vraag": "een"}\n'
    path.write_text(line + line, encoding="utf-8")
    with pytest.raises(ValueError, match=r":2: dubbele id 'a'"):
        load_questions(path)


def test_nvidia_smi_parser_and_missing_binary() -> None:
    assert parse_nvidia_smi_memory_mib("100\n250\n") == 250
    assert parse_nvidia_smi_memory_mib("N/A\n") is None
    assert peak_mib([None, None]) is None
    assert peak_mib([100, None, 80]) == 100

    def missing(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError

    assert query_nvidia_smi_mib(missing) is None


def test_vram_sampler_collects_during_the_request() -> None:
    active = threading.Event()

    def probe() -> int | None:
        if active.is_set():
            return 850
        return 100

    sampler = VramSampler(probe, interval_seconds=0.005)
    sampler.start()
    active.set()
    threading.Event().wait(0.04)
    active.clear()
    sampler.stop()
    assert sampler.peak_mib == 850
    assert len(sampler.readings) >= 3


def test_missing_model_is_skipped_without_a_provider_call() -> None:
    factory, created = _factory()
    results, note = run_benchmark(
        models=["gemma4:12b"],
        questions=[BenchQuestion(id="q", vraag="Ping?", brontekst="")],
        provider_factory=factory,
        model_lister=lambda: {"qwen3.5:9b"},
        vram_probe=lambda: None,
    )
    assert note is None
    assert created == []
    assert results[0].status == "overgeslagen"
    assert results[0].items == []
    assert "niet gemeten" in _row(results[0].model, results)


def test_unreachable_ollama_skips_every_model() -> None:
    factory, created = _factory()

    def unavailable() -> set[str]:
        raise OllamaUnreachableError("down")

    results, note = run_benchmark(
        models=["qwen3.5:9b", "ministral-3:8b"],
        questions=[BenchQuestion(id="q", vraag="Ping?", brontekst="tekst")],
        provider_factory=factory,
        model_lister=unavailable,
    )
    assert note is not None
    assert "niet bereikbaar" in note
    assert created == []
    assert all(result.status == "overgeslagen" for result in results)


def test_public_provider_stream_measures_ttft_tokens_and_schema() -> None:
    factory, created = _factory()
    results, _note = run_benchmark(
        models=["qwen3.5:4b"],
        questions=[BenchQuestion(id="probe", vraag="Ping?", brontekst="bron")],
        provider_factory=factory,
        model_lister=lambda: {"qwen3.5:4b"},
        vram_probe=lambda: None,
    )
    result = results[0]
    assert created == [("qwen3.5:4b", None), ("qwen3.5:4b", 0)]
    assert result.status == "gemeten"
    assert result.items[0].schema_valid is True
    assert result.items[0].seconds_to_first_token is not None
    assert result.items[0].tokens_per_second == 2.0


def test_invalid_json_counts_as_schema_failure() -> None:
    factory, _created = _factory(response="geen json")
    results, _note = run_benchmark(
        models=["qwen3.5:9b"],
        questions=[BenchQuestion(id="probe", vraag="Ping?", brontekst="")],
        provider_factory=factory,
        model_lister=lambda: {"qwen3.5:9b"},
        vram_probe=lambda: None,
    )
    assert results[0].items[0].schema_valid is False
    assert results[0].items[0].error is None
    assert results[0].status == "gemeten"
    assert results[0].peak_vram_mib is None


def test_generation_peak_is_kept_per_model_when_keep_alive_unloads() -> None:
    active: dict[str, str | None] = {"model": None}
    factory, created = _factory(active_model=active, delay_seconds=0.08)
    peaks = {"model-a": 810, "model-b": 710}

    def probe() -> int:
        model = active["model"]
        if model is None or model.endswith(":warmup"):
            return 100
        assert model.endswith(":measured")
        return peaks[model.removesuffix(":measured")]

    results, _note = run_benchmark(
        models=["model-a", "model-b"],
        questions=[BenchQuestion(id="probe", vraag="Ping?", brontekst="")],
        provider_factory=factory,
        model_lister=lambda: set(peaks),
        vram_probe=probe,
        vram_sample_interval_seconds=0.005,
    )
    assert [result.peak_vram_mib for result in results] == [810, 710]
    assert created == [
        ("model-a", None),
        ("model-a", 0),
        ("model-b", None),
        ("model-b", 0),
    ]


def test_stream_error_is_a_request_failure_not_invalid_schema() -> None:
    factory, _created = _factory(
        error_for=lambda prompt: "model requires more system memory" if "Ping?" in prompt else None
    )
    results, _note = run_benchmark(
        models=["qwen3.5:9b"],
        questions=[BenchQuestion(id="vram", vraag="Ping?", brontekst="")],
        provider_factory=factory,
        model_lister=lambda: {"qwen3.5:9b"},
        vram_probe=lambda: None,
    )
    assert results[0].status == "mislukt"
    assert results[0].items[0].error is not None
    assert "system memory" in results[0].items[0].error
    text = _row(results[0].model, results)
    assert "niet gemeten" in text
    assert "HTTP-fout" in text


def test_schema_percent_ignores_http_failures() -> None:
    factory, _created = _factory(error_for=lambda prompt: "boom" if "FAIL" in prompt else None)
    questions = [
        BenchQuestion(id="ok", vraag="Ping?", brontekst=""),
        BenchQuestion(id="fail", vraag="FAIL", brontekst=""),
    ]
    results, _note = run_benchmark(
        models=["qwen3.5:9b"],
        questions=questions,
        provider_factory=factory,
        model_lister=lambda: {"qwen3.5:9b"},
        vram_probe=lambda: None,
    )
    result = results[0]
    assert result.status == "gemeten"
    assert "HTTP-fout" in result.note
    assert "100.0" in _row(result.model, results)


def test_main_writes_a_report_without_numbers_when_the_set_is_missing(tmp_path: Path) -> None:
    out = tmp_path / "reports"
    code = main(
        [
            "--questions",
            str(tmp_path / "missing.jsonl"),
            "--out-dir",
            str(out),
            "--base-url",
            "http://127.0.0.1:9",
        ]
    )
    assert code == 0
    reports = list(out.glob("bench-*.md"))
    assert len(reports) == 1
    text = reports[0].read_text(encoding="utf-8")
    assert "geen items" in text.lower() or "Geen items" in text
    assert "niet gemeten" in text
    assert "tokens/s" in text
    assert "qwen3.5:9b" in text
    assert "gemma4:12b" in text


def _row(model: str, results: list[ModelResult]) -> str:
    text = render_report(
        when=datetime(2026, 10, 31),
        base_url="http://ollama.test",
        questions_path=Path("eval/data/bench.jsonl"),
        question_count=1,
        results=results,
        ollama_note=None,
    )
    assert model in text
    return text
