"""Harness-tests met een nepserver. Geen model en geen verzonnen bench-cijfers."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import httpx

from wetvia_eval.bench import DEFAULT_MODELS, ModelResult, main, render_report, run_benchmark
from wetvia_eval.ollama import NUM_CTX, OllamaProvider
from wetvia_eval.questions import BenchQuestion, load_questions, prompt_for
from wetvia_eval.schema import AnswerV1, validate_answer
from wetvia_eval.vram import parse_nvidia_smi_memory_mib, peak_mib, query_nvidia_smi_mib


def _valid_answer() -> str:
    return AnswerV1(
        status="onzeker",
        samenvatting="niet beoordeeld",
        punten=[],
        voorbehouden=[],
        vervolgstappen=[],
        peildatum="2026-10-30",
    ).model_dump_json()


def test_default_models_match_issue() -> None:
    assert DEFAULT_MODELS == ("qwen3.5:9b", "qwen3.5:4b", "gemma4:12b", "ministral-3:8b")


def test_prompt_uses_only_the_given_source_text() -> None:
    question = BenchQuestion(id="x", vraag="Ping?", brontekst="Alleen deze tekst.")
    prompt = prompt_for(question)
    assert "Ping?" in prompt
    assert "Alleen deze tekst." in prompt
    assert "zet status op onzeker" in prompt


def test_load_questions_rejects_a_missing_question(tmp_path: Path) -> None:
    path = tmp_path / "bench.jsonl"
    path.write_text('{"id": "a"}\n', encoding="utf-8")
    try:
        load_questions(path)
    except ValueError as exc:
        assert "vraag" in str(exc)
    else:
        raise AssertionError("lege vraag hoort te falen")


def test_schema_accepts_the_documented_shape_and_rejects_prose() -> None:
    assert validate_answer(_valid_answer())
    assert not validate_answer("dit is geen json")


def test_nvidia_smi_parser_and_missing_binary() -> None:
    assert parse_nvidia_smi_memory_mib("100\n250\n") == 250
    assert parse_nvidia_smi_memory_mib("N/A\n") is None
    assert peak_mib([None, None]) is None
    assert peak_mib([100, None, 80]) == 100

    def missing(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError

    assert query_nvidia_smi_mib(missing) is None


def _provider(
    handler: httpx.RequestHandler,
    clock: Callable[[], float] | None = None,
) -> OllamaProvider:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OllamaProvider("http://ollama.test", client, clock=clock)


def test_missing_model_is_skipped_without_a_chat_call() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen3.5:9b"}]})
        raise AssertionError(f"onverwachte call {request.url.path}")

    provider = _provider(handler)
    results, note = run_benchmark(
        models=["gemma4:12b"],
        questions=[BenchQuestion(id="q", vraag="Ping?", brontekst="")],
        provider=provider,
        vram_probe=lambda: None,
    )
    provider.close()
    assert note is None
    assert results[0].status == "overgeslagen"
    assert results[0].items == []
    assert "niet gemeten" in _row(results[0].model, results)


def test_unreachable_ollama_skips_every_model() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    provider = _provider(handler)
    results, note = run_benchmark(
        models=["qwen3.5:9b", "ministral-3:8b"],
        questions=[BenchQuestion(id="q", vraag="Ping?", brontekst="tekst")],
        provider=provider,
    )
    provider.close()
    assert note is not None
    assert "niet bereikbaar" in note
    assert all(result.status == "overgeslagen" for result in results)


def test_stream_measures_ttft_rate_and_schema() -> None:
    answer = _valid_answer()
    lines = [
        json.dumps({"message": {"role": "assistant", "content": answer[:1]}}),
        json.dumps({"message": {"role": "assistant", "content": answer[1:]}}),
        json.dumps({"done": True, "eval_count": 4, "eval_duration": 2_000_000_000}),
    ]
    body = ("\n".join(lines) + "\n").encode()
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen3.5:4b"}]})
        seen["payload"] = json.loads(request.content.decode())
        return httpx.Response(200, content=body)

    times = iter((10.0, 10.25))
    provider = OllamaProvider(
        "http://ollama.test",
        httpx.Client(transport=httpx.MockTransport(handler)),
        clock=lambda: next(times),
    )
    probes = iter((100, 250))
    results, _note = run_benchmark(
        models=["qwen3.5:4b"],
        questions=[BenchQuestion(id="probe", vraag="Ping?", brontekst="bron")],
        provider=provider,
        vram_probe=lambda: next(probes),
    )
    provider.close()
    payload = seen["payload"]
    assert isinstance(payload, dict)
    assert payload["think"] is False
    assert payload["options"] == {"num_ctx": NUM_CTX}
    result = results[0]
    assert result.status == "gemeten"
    assert result.peak_vram_mib == 250
    assert result.items[0].schema_valid is True
    assert result.items[0].seconds_to_first_token == 0.25
    assert result.items[0].tokens_per_second == 2.0


def test_invalid_json_counts_as_schema_failure() -> None:
    lines = [
        json.dumps({"message": {"content": "geen json"}}),
        json.dumps({"done": True, "eval_count": 1, "eval_duration": 1_000_000_000}),
    ]
    body = ("\n".join(lines) + "\n").encode()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen3.5:9b"}]})
        return httpx.Response(200, content=body)

    provider = _provider(handler)
    results, _note = run_benchmark(
        models=["qwen3.5:9b"],
        questions=[BenchQuestion(id="probe", vraag="Ping?", brontekst="")],
        provider=provider,
        vram_probe=lambda: None,
    )
    provider.close()
    assert results[0].items[0].schema_valid is False
    assert results[0].peak_vram_mib is None


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
