"""Modelbenchmark: snelheid, schema-validiteit en VRAM. Geen verzonnen cijfers."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import httpx

from wetvia.bootstrap import get_ollama_provider
from wetvia.llm import ChatMessage, LLMProvider, StreamMetrics
from wetvia_eval.questions import BenchQuestion, load_questions, prompt_for
from wetvia_eval.schema import AnswerV1, validate_answer
from wetvia_eval.vram import VramSampler, peak_mib, query_nvidia_smi_mib

DEFAULT_MODELS: tuple[str, ...] = (
    "qwen3.5:9b",
    "qwen3.5:4b",
    "gemma4:12b",
    "ministral-3:8b",
)
DEFAULT_BASE_URL = "http://127.0.0.1:11434"
NUM_CTX = 16384
_VRAM_SAMPLE_INTERVAL_SECONDS = 0.1
_ANSWER_SCHEMA = json.dumps(AnswerV1.model_json_schema(), ensure_ascii=False)
_WARMUP_PROMPT = (
    "Antwoord alleen met JSON volgens dit JSON Schema:\n"
    f"{_ANSWER_SCHEMA}\n\nVRAAG:\nping\n\nBRONNEN:\n(geen brontekst)\n"
)


@dataclass
class ItemResult:
    question_id: str
    schema_valid: bool
    seconds_to_first_token: float | None
    tokens_per_second: float | None
    error: str | None = None


@dataclass
class ModelResult:
    model: str
    status: str
    note: str
    items: list[ItemResult] = field(default_factory=list)
    peak_vram_mib: int | None = None


@dataclass(frozen=True)
class StreamMeasurement:
    content: str
    seconds_to_first_token: float | None
    tokens_per_second: float | None


class OllamaUnreachableError(RuntimeError):
    pass


ProviderFactory = Callable[[str, int | str | None], LLMProvider]
ModelLister = Callable[[], set[str]]


def mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def answered_items(items: list[ItemResult]) -> list[ItemResult]:
    return [item for item in items if item.error is None]


def schema_validity_percent(items: list[ItemResult]) -> float | None:
    """Alleen items met een antwoord. HTTP-fouten zitten niet in de noemer."""
    answered = answered_items(items)
    if not answered:
        return None
    valid = sum(1 for item in answered if item.schema_valid)
    return 100.0 * valid / len(answered)


def format_optional(value: float | None, digits: int) -> str:
    if value is None:
        return "niet gemeten"
    return f"{value:.{digits}f}"


def render_report(
    *,
    when: datetime,
    base_url: str,
    questions_path: Path,
    question_count: int,
    results: list[ModelResult],
    ollama_note: str | None,
) -> str:
    lines = [
        f"# Modelbenchmark {when.date().isoformat()}",
        "",
        "Dit bestand is de uitvoer van `eval/bench_models.py`. "
        "Een cel `niet gemeten` of `niet beschikbaar` betekent dat die run "
        "het getal niet heeft opgeleverd. "
        "Er staan geen geschatte of overgenomen benchmarkcijfers in.",
        "",
        "## Methode",
        "",
        f"- Endpoint: `{base_url}` `/api/chat`, streaming.",
        f"- Context vast: `num_ctx={NUM_CTX}`. `think` staat uit (docs/02 §4).",
        "- Schema: dummy `AnswerV1` uit docs/02 §4, lokaal in `wetvia_eval.schema`. "
        "Het schema wordt in de prompt meegestuurd en na de stream lokaal gevalideerd. "
        "Het echte schema hoort later in `wetvia.answer`.",
        "- Client: `wetvia.bootstrap.get_ollama_provider` levert de publieke "
        "`wetvia.llm.LLMProvider`-API met de Ollama-adapter.",
        "- Zonder RAG: de prompt bevat alleen `vraag` en `brontekst` uit de JSONL.",
        "- Tijd tot eerste token: wandklok tot het eerste niet-lege gestreamde contentdeel.",
        "- tokens/s: de `StreamMetrics`-callback uit de provider meldt tokens en "
        "generatietijd op basis van `eval_count` en `eval_duration`.",
        "- Schema-validiteit: aandeel antwoorden dat als `AnswerV1` valideert, "
        "alleen over items met een antwoord. HTTP-fouten staan apart en zitten "
        "niet in die noemer. Zonder antwoord: niet gemeten.",
        "- Piek-VRAM: tijdens elke generatie loopt elke 0,1 seconde een "
        "`nvidia-smi --query-gpu=memory.used`-steekproef, met extra metingen ervoor en erna. "
        "Dit meet de hele GPU (dus ook andere processen). "
        "Zonder `nvidia-smi`: niet beschikbaar. Op een Mac (Metal) blijft die kolom leeg.",
        "- Eerst een warm-up-call die niet in TTFT of tokens/s meetelt, zodat laadtijd "
        "de eerste vraag niet vervormt; VRAM wordt ook tijdens die call bemonsterd. "
        "De laatste vraag per model stuurt `keep_alive: 0` "
        "zodat Ollama het model ontlaadt na de generatie; de gemeten piek komt uit "
        "de steekproeven tijdens die generatie.",
        "- Een model dat niet in `GET /api/tags` staat, wordt overgeslagen.",
        "",
        "## Vragen",
        "",
    ]
    if question_count == 0:
        lines.append(
            f"Geen items gelezen uit `{questions_path}`. "
            "De 30 eval-vragen zijn niet verzonnen en staan nog niet in de repo. "
            "Zonder items is er geen kwaliteits- of snelheidsmeting."
        )
    else:
        lines.append(f"{question_count} items uit `{questions_path}`.")
    if ollama_note:
        lines.extend(["", f"Ollama: {ollama_note}"])
    lines.extend(
        [
            "",
            "## Resultaten",
            "",
            "| Model | Status | Items | Tijd tot eerste token (s) | tokens/s | "
            "Schema-validiteit (%) | Piek-VRAM (MiB) | Opmerking |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    if not results:
        lines.append(
            "| — | niet gemeten | 0 | niet gemeten | niet gemeten | "
            "niet gemeten | niet beschikbaar | geen modellen |"
        )
    for result in results:
        lines.append(_result_row(result))
    lines.extend(["", "## Per item", ""])
    any_item = False
    for result in results:
        for item in result.items:
            any_item = True
            ttft = format_optional(item.seconds_to_first_token, 3)
            rate = format_optional(item.tokens_per_second, 1)
            if item.error:
                lines.append(f"- `{result.model}` / `{item.question_id}`: HTTP-fout: {item.error}")
                continue
            valid = "ja" if item.schema_valid else "nee"
            lines.append(
                f"- `{result.model}` / `{item.question_id}`: schema {valid}, "
                f"eerste token {ttft} s, tokens/s {rate}."
            )
    if not any_item:
        lines.append("Geen itemmetingen.")
    lines.append("")
    return "\n".join(lines)


def _result_row(result: ModelResult) -> str:
    if result.status != "gemeten":
        vram = "niet beschikbaar" if result.peak_vram_mib is None else str(result.peak_vram_mib)
        return (
            f"| {result.model} | {result.status} | {len(result.items)} | "
            f"niet gemeten | niet gemeten | niet gemeten | {vram} | {result.note} |"
        )
    ttft_values = [
        item.seconds_to_first_token
        for item in result.items
        if item.seconds_to_first_token is not None
    ]
    rate_values = [
        item.tokens_per_second for item in result.items if item.tokens_per_second is not None
    ]
    validity = schema_validity_percent(result.items)
    vram = "niet beschikbaar" if result.peak_vram_mib is None else str(result.peak_vram_mib)
    return (
        f"| {result.model} | {result.status} | {len(result.items)} | "
        f"{format_optional(mean(ttft_values), 3)} | "
        f"{format_optional(mean(rate_values), 1)} | "
        f"{format_optional(validity, 1)} | {vram} | {result.note} |"
    )


def model_is_listed(available: set[str], wanted: str) -> bool:
    if wanted in available:
        return True
    prefix = f"{wanted}:"
    return any(name.startswith(prefix) for name in available)


def _with_answer_schema(prompt: str) -> str:
    return f"Antwoord alleen met JSON volgens dit JSON Schema:\n{_ANSWER_SCHEMA}\n\n{prompt}"


def list_models(base_url: str) -> set[str]:
    """Read installed tags. Chat requests themselves go through wetvia.llm."""
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(f"{base_url.rstrip('/')}/api/tags")
            response.raise_for_status()
            payload: object = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise OllamaUnreachableError(str(exc)) from exc
    if not isinstance(payload, dict):
        raise OllamaUnreachableError("Ollama /api/tags gaf geen object terug")
    models = payload.get("models")
    if not isinstance(models, list):
        return set()
    return {
        name
        for item in models
        if isinstance(item, dict)
        if isinstance(name := item.get("name"), str) and name
    }


def run_benchmark(
    *,
    models: list[str],
    questions: list[BenchQuestion],
    provider_factory: ProviderFactory,
    model_lister: ModelLister,
    vram_probe: Callable[[], int | None] = query_nvidia_smi_mib,
    vram_sample_interval_seconds: float = _VRAM_SAMPLE_INTERVAL_SECONDS,
) -> tuple[list[ModelResult], str | None]:
    if not questions:
        return [
            ModelResult(
                model=model,
                status="overgeslagen",
                note="geen vragen in de JSONL",
            )
            for model in models
        ], None
    try:
        available = model_lister()
    except OllamaUnreachableError as exc:
        note = f"niet bereikbaar ({exc})"
        return [
            ModelResult(model=model, status="overgeslagen", note=note) for model in models
        ], note
    results: list[ModelResult] = []
    for model in models:
        if not model_is_listed(available, model):
            results.append(
                ModelResult(
                    model=model,
                    status="overgeslagen",
                    note="staat niet in ollama list (/api/tags)",
                )
            )
            continue
        results.append(
            _run_model(
                model,
                questions,
                provider_factory,
                vram_probe,
                vram_sample_interval_seconds,
            )
        )
    return results, None


def _run_model(
    model: str,
    questions: list[BenchQuestion],
    provider_factory: ProviderFactory,
    vram_probe: Callable[[], int | None],
    vram_sample_interval_seconds: float,
) -> ModelResult:
    readings: list[int | None] = []
    warmup_sampler = VramSampler(
        vram_probe,
        interval_seconds=vram_sample_interval_seconds,
    )
    warmup_sampler.start()
    warmup_error: str | None = None
    try:
        _measure_stream(provider_factory(model, None), _WARMUP_PROMPT)
    except (httpx.HTTPError, RuntimeError, ValueError) as exc:
        warmup_error = str(exc)
    finally:
        warmup_sampler.stop()
        readings.extend(warmup_sampler.readings)
    if warmup_error is not None:
        return ModelResult(
            model=model,
            status="mislukt",
            note=f"warm-up mislukt: {warmup_error}",
            peak_vram_mib=peak_mib(readings),
        )
    items: list[ItemResult] = []
    last_index = len(questions) - 1
    for index, question in enumerate(questions):
        keep_alive = 0 if index == last_index else None
        sampler = VramSampler(vram_probe, interval_seconds=vram_sample_interval_seconds)
        sampler.start()
        try:
            measured = _measure_stream(
                provider_factory(model, keep_alive),
                _with_answer_schema(prompt_for(question)),
            )
        except (httpx.HTTPError, RuntimeError, ValueError) as exc:
            items.append(
                ItemResult(
                    question_id=question.id,
                    schema_valid=False,
                    seconds_to_first_token=None,
                    tokens_per_second=None,
                    error=str(exc),
                )
            )
        else:
            items.append(_item_from_measurement(question.id, measured))
        finally:
            sampler.stop()
            readings.extend(sampler.readings)
    failures = sum(1 for item in items if item.error is not None)
    answered = answered_items(items)
    if not answered:
        return ModelResult(
            model=model,
            status="mislukt",
            note=f"{failures} HTTP-fout(en), geen antwoord",
            items=items,
            peak_vram_mib=peak_mib(readings),
        )
    note = "gemeten"
    if failures:
        note = f"gemeten; {failures} HTTP-fout(en) niet in schema-%"
    return ModelResult(
        model=model,
        status="gemeten",
        note=note,
        items=items,
        peak_vram_mib=peak_mib(readings),
    )


async def _collect_stream(provider: LLMProvider, prompt: str) -> StreamMeasurement:
    metrics: list[StreamMetrics] = []
    started = time.perf_counter()
    stream = await provider.chat(
        [ChatMessage(role="user", content=prompt)],
        schema=None,
        stream=True,
        temperature=0.0,
        on_metrics=metrics.append,
    )
    if not isinstance(stream, AsyncIterator):
        raise RuntimeError("LLM-provider gaf geen stream terug")
    parts: list[str] = []
    first_token_at: float | None = None
    async for chunk in stream:
        if chunk and first_token_at is None:
            first_token_at = time.perf_counter()
        if chunk:
            parts.append(chunk)
    latest = metrics[-1] if metrics else None
    tokens_per_second: float | None = None
    if (
        latest is not None
        and latest.completion_tokens is not None
        and latest.generation_seconds is not None
        and latest.generation_seconds > 0
    ):
        tokens_per_second = latest.completion_tokens / latest.generation_seconds
    return StreamMeasurement(
        content="".join(parts),
        seconds_to_first_token=None if first_token_at is None else first_token_at - started,
        tokens_per_second=tokens_per_second,
    )


def _measure_stream(provider: LLMProvider, prompt: str) -> StreamMeasurement:
    return asyncio.run(_collect_stream(provider, prompt))


def _item_from_measurement(question_id: str, measured: StreamMeasurement) -> ItemResult:
    return ItemResult(
        question_id=question_id,
        schema_valid=validate_answer(measured.content),
        seconds_to_first_token=measured.seconds_to_first_token,
        tokens_per_second=measured.tokens_per_second,
    )


def report_path(directory: Path, when: datetime) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = when.strftime("%Y-%m-%d")
    candidate = directory / f"bench-{stamp}.md"
    if not candidate.exists():
        return candidate
    return directory / f"bench-{when.strftime('%Y-%m-%d-%H%M%S')}.md"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark lokale Ollama-modellen voor Wetvia.")
    parser.add_argument(
        "models",
        nargs="*",
        help="Ollama-tags. Default: qwen3.5:9b qwen3.5:4b gemma4:12b ministral-3:8b",
    )
    parser.add_argument("--questions", type=Path, default=Path("eval/data/bench.jsonl"))
    parser.add_argument("--out-dir", type=Path, default=Path("eval/reports"))
    parser.add_argument(
        "--base-url",
        default=os.environ.get("LLM_BASE_URL", DEFAULT_BASE_URL),
    )
    args = parser.parse_args(argv)
    models = list(args.models) if args.models else list(DEFAULT_MODELS)
    questions = load_questions(args.questions)
    when = datetime.now().astimezone()

    def provider_factory(model: str, keep_alive: int | str | None) -> LLMProvider:
        return get_ollama_provider(
            base_url=args.base_url,
            model=model,
            num_ctx=NUM_CTX,
            keep_alive=keep_alive,
            think=False,
        )

    results, ollama_note = run_benchmark(
        models=models,
        questions=questions,
        provider_factory=provider_factory,
        model_lister=lambda: list_models(args.base_url),
    )
    text = render_report(
        when=when,
        base_url=args.base_url,
        questions_path=args.questions,
        question_count=len(questions),
        results=results,
        ollama_note=ollama_note,
    )
    destination = report_path(args.out_dir, when)
    destination.write_text(text, encoding="utf-8")
    print(destination)
    return 0
