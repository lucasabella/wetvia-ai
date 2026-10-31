"""Modelbenchmark: snelheid, schema-validiteit en VRAM. Geen verzonnen cijfers."""

from __future__ import annotations

import argparse
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from wetvia_eval.ollama import (
    NUM_CTX,
    ChatMeasurement,
    OllamaProvider,
    OllamaUnreachableError,
    model_is_listed,
)
from wetvia_eval.questions import BenchQuestion, load_questions, prompt_for
from wetvia_eval.schema import validate_answer
from wetvia_eval.vram import peak_mib, query_nvidia_smi_mib

DEFAULT_MODELS: tuple[str, ...] = (
    "qwen3.5:9b",
    "qwen3.5:4b",
    "gemma4:12b",
    "ministral-3:8b",
)
DEFAULT_BASE_URL = "http://127.0.0.1:11434"
_WARMUP_PROMPT = (
    "Antwoord alleen met JSON volgens het schema.\nVRAAG:\nping\n\nBRONNEN:\n(geen brontekst)\n"
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
        "Het echte schema hoort later in `wetvia.answer`.",
        "- Client: `OllamaProvider` in dit pakket. Issue #5 levert de `wetvia.llm`-port; "
        "deze client is daar nog niet op aangesloten.",
        "- Zonder RAG: de prompt bevat alleen `vraag` en `brontekst` uit de JSONL.",
        "- Tijd tot eerste token: wandklok tot het eerste niet-lege `message.content`.",
        "- tokens/s: `eval_count / (eval_duration / 1e9)` als Ollama beide velden in het "
        "laatste streamevent zet (`eval_duration` is nanoseconden).",
        "- Schema-validiteit: aandeel antwoorden dat als `AnswerV1` valideert, "
        "alleen over items met een antwoord. HTTP-fouten staan apart en zitten "
        "niet in die noemer. Zonder antwoord: niet gemeten.",
        "- Piek-VRAM: hoogste `nvidia-smi --query-gpu=memory.used` (MiB, hele GPU, "
        "dus ook andere processen) vlak voor en na elke gemeten vraag. "
        "Zonder `nvidia-smi`: niet beschikbaar. Op een Mac (Metal) blijft die kolom leeg.",
        "- Eerst een warm-up-call die niet meetelt, zodat laadtijd niet in de "
        "eerste TTFT zit. De laatste vraag per model stuurt `keep_alive: 0` "
        "zodat Ollama het model ontladt voor het volgende.",
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


def run_benchmark(
    *,
    models: list[str],
    questions: list[BenchQuestion],
    provider: OllamaProvider,
    vram_probe: Callable[[], int | None] = query_nvidia_smi_mib,
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
        available = provider.list_models()
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
        results.append(_run_model(model, questions, provider, vram_probe))
    return results, None


def _run_model(
    model: str,
    questions: list[BenchQuestion],
    provider: OllamaProvider,
    vram_probe: Callable[[], int | None],
) -> ModelResult:
    try:
        provider.chat(model, _WARMUP_PROMPT)
    except OllamaUnreachableError as exc:
        return ModelResult(
            model=model,
            status="mislukt",
            note=f"warm-up mislukt: {exc}",
        )
    items: list[ItemResult] = []
    readings: list[int | None] = []
    last_index = len(questions) - 1
    for index, question in enumerate(questions):
        keep_alive = 0 if index == last_index else None
        readings.append(vram_probe())
        try:
            measured = provider.chat(model, prompt_for(question), keep_alive=keep_alive)
        except OllamaUnreachableError as exc:
            items.append(
                ItemResult(
                    question_id=question.id,
                    schema_valid=False,
                    seconds_to_first_token=None,
                    tokens_per_second=None,
                    error=str(exc),
                )
            )
            readings.append(vram_probe())
            continue
        items.append(_item_from_measurement(question.id, measured))
        readings.append(vram_probe())
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


def _item_from_measurement(question_id: str, measured: ChatMeasurement) -> ItemResult:
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
    provider = OllamaProvider(args.base_url)
    try:
        results, ollama_note = run_benchmark(models=models, questions=questions, provider=provider)
    finally:
        provider.close()
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
