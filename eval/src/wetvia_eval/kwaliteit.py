"""Lokale toets: basis tegen bijgetraind, via een OpenAI-compatibel endpoint."""

from __future__ import annotations

import argparse
import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import httpx

from nl_overheid_benchmark import BenchItem, load_items, score_response
from nl_overheid_benchmark.score import AnswerScore
from wetvia_eval.doctor import (
    collect_checks,
    default_dataset,
    nvidia_smi_text,
    render_doctor,
    write_doctor_report,
)

DEFAULT_BASE_URL = "http://127.0.0.1:11434/v1"
DEFAULT_BASE_TAG = "qwen3.5:4b"
DEFAULT_FINETUNED_TAG = "wetvia-qwen3.5-4b"
DEFAULT_FINETUNED_PATH = Path("training/out/qwen3.5-4b-lora")
Completer = Callable[[str], str]


@dataclass(frozen=True)
class ItemResult:
    id: str
    type: str
    antwoord_goed: bool | None
    bron_goed: bool | None
    verwacht: str
    gegeven: str
    seconden: float | None
    fout: str | None


@dataclass(frozen=True)
class RunResult:
    rol: str
    status: str
    model: str
    toelichting: str
    concept: bool
    items: tuple[ItemResult, ...]

    def to_json(self) -> dict[str, object]:
        return {
            "rol": self.rol,
            "status": self.status,
            "model": self.model,
            "toelichting": self.toelichting,
            "concept": self.concept,
            "items": [
                {
                    "id": item.id,
                    "type": item.type,
                    "antwoord_goed": item.antwoord_goed,
                    "bron_goed": item.bron_goed,
                    "verwacht": item.verwacht,
                    "gegeven": item.gegeven,
                    "seconden": item.seconden,
                    "fout": item.fout,
                }
                for item in self.items
            ],
        }


def prompt_for(item: BenchItem) -> str:
    options = ""
    if item.opties:
        lines = "\n".join(f"- {option}" for option in item.opties)
        options = f"\nOPTIES:\n{lines}\n"
    return (
        "Je leest een officiële tekst en beantwoordt één vraag.\n"
        "Gebruik alleen de TEKST. Verzin geen artikel en geen nummer dat er niet in staat.\n"
        'Antwoord met alleen dit JSON-object: {"antwoord": "...", "bron": "..."}\n'
        "antwoord is het gevraagde feit. Als er OPTIES zijn, kies precies één daarvan.\n"
        "bron is het artikelnummer of documentnummer uit de TEKST.\n\n"
        f"VRAAG:\n{item.vraag.strip()}\n"
        f"{options}\n"
        f"TEKST:\n{item.brontekst.strip()}\n"
    )


def missing_finetuned_message(tag: str, path: Path) -> str:
    if path.is_dir() and (path / "adapter_config.json").is_file():
        return (
            f"{path} is een LoRA-adapter: een dun extra schrift bij het basismodel. "
            "Deze opdracht laadt dat schrift niet. Maak er eerst een model van in Ollama "
            f"of LM Studio en start opnieuw met --finetuned-tag. De tag {tag} staat er nu niet."
        )
    if not path.exists():
        return (
            f"Het bijgetrainde model ontbreekt. Geen tag {tag} op het endpoint en geen bestand "
            f"op {path}. Deze opdracht laadt geen LoRA-map en geen GGUF-bestand zelf. "
            "Zet het model in Ollama of LM Studio en geef de tag mee met --finetuned-tag. "
            "Tot die tijd blijft de rij 'niet gemeten'."
        )
    return (
        f"{path} staat op schijf, maar deze opdracht laadt het bestand niet zelf. "
        "Zet het in Ollama of LM Studio en geef de tag mee met --finetuned-tag."
    )


def missing_base_message(tag: str) -> str:
    return (
        f"Het basismodel {tag} staat niet op het endpoint. "
        f"Bij Ollama: ollama pull {tag}. Daarna opnieuw: uv run wetvia-bench --model base"
    )


def run_items(
    items: list[BenchItem],
    complete: Completer,
    *,
    rol: str,
    model: str,
    judge: Callable[[BenchItem, str], int] | None = None,
) -> RunResult:
    scored: list[ItemResult] = []
    for item in items:
        if item.type == "open" and judge is None:
            scored.append(
                ItemResult(
                    id=item.id,
                    type=item.type,
                    antwoord_goed=None,
                    bron_goed=None,
                    verwacht=item.antwoord,
                    gegeven="",
                    seconden=None,
                    fout="nakijker staat uit",
                )
            )
            continue
        started = time.perf_counter()
        try:
            raw = complete(prompt_for(item))
        except (httpx.HTTPError, OSError, RuntimeError, ValueError) as exc:
            scored.append(
                ItemResult(
                    id=item.id,
                    type=item.type,
                    antwoord_goed=None,
                    bron_goed=None,
                    verwacht=item.antwoord,
                    gegeven="",
                    seconden=None,
                    fout=str(exc),
                )
            )
            continue
        seconds = time.perf_counter() - started
        if item.type == "open":
            assert judge is not None
            verdict = judge(item, raw)
            scored.append(
                ItemResult(
                    id=item.id,
                    type=item.type,
                    antwoord_goed=verdict == 1,
                    bron_goed=None,
                    verwacht=item.antwoord,
                    gegeven=raw.strip(),
                    seconden=seconds,
                    fout=None,
                )
            )
            continue
        scored.append(_from_score(item, score_response(item, raw), seconds))
    concept = any(item.concept for item in items)
    return RunResult(
        rol=rol,
        status="gemeten",
        model=model,
        toelichting=_summary(scored, concept),
        concept=concept,
        items=tuple(scored),
    )


def blocked_result(rol: str, model: str, toelichting: str) -> RunResult:
    return RunResult(
        rol=rol,
        status="ontbreekt",
        model=model,
        toelichting=toelichting,
        concept=True,
        items=(),
    )


def write_run(directory: Path, result: RunResult) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"kwaliteit-{result.rol}.json"
    destination.write_text(
        json.dumps(result.to_json(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return destination


def load_run(path: Path) -> RunResult | None:
    if not path.is_file():
        return None
    payload: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return None
    items_raw = payload.get("items")
    items: list[ItemResult] = []
    if isinstance(items_raw, list):
        for entry in items_raw:
            if not isinstance(entry, dict):
                continue
            items.append(
                ItemResult(
                    id=str(entry.get("id", "")),
                    type=str(entry.get("type", "")),
                    antwoord_goed=_optional_bool(entry.get("antwoord_goed")),
                    bron_goed=_optional_bool(entry.get("bron_goed")),
                    verwacht=str(entry.get("verwacht", "")),
                    gegeven=str(entry.get("gegeven", "")),
                    seconden=_optional_float(entry.get("seconden")),
                    fout=entry.get("fout") if isinstance(entry.get("fout"), str) else None,
                )
            )
    return RunResult(
        rol=str(payload.get("rol", "")),
        status=str(payload.get("status", "")),
        model=str(payload.get("model", "")),
        toelichting=str(payload.get("toelichting", "")),
        concept=bool(payload.get("concept", True)),
        items=tuple(items),
    )


def render_comparison(base: RunResult | None, finetuned: RunResult | None) -> str:
    lines = [
        "# Vergelijking basis en bijgetraind",
        "",
        "Deze set is een concept. Een mens heeft de vragen nog niet afgevinkt "
        "(issues #95 en #92). Het percentage is geen eindcijfer.",
        "Elke vraag laat de brontekst meelezen. De score zegt of het model die tekst gebruikt.",
        "",
    ]
    lines.extend(_side_lines("Basis", base))
    lines.extend(_side_lines("Bijgetraind", finetuned))
    lines.extend(["", "## Per soort", "", "| Soort | Basis | Bijgetraind |", "| --- | --- | --- |"])
    kinds = sorted({item.type for item in _items(base)} | {item.type for item in _items(finetuned)})
    if not kinds:
        lines.append("| — | niet gemeten | niet gemeten |")
    for kind in kinds:
        lines.append(f"| {kind} | {_ratio(base, kind)} | {_ratio(finetuned, kind)} |")
    lines.extend(
        [
            f"| totaal | {_ratio(base, None)} | {_ratio(finetuned, None)} |",
            "",
            "## Waar het bijgetrainde model slechter is",
            "",
        ]
    )
    worse = _diffs(base, finetuned, finetuned_better=False)
    better = _diffs(base, finetuned, finetuned_better=True)
    if not _both_measured(base, finetuned):
        lines.append("Nog niet te vergelijken: een van de twee rijen is niet gemeten.")
    elif not worse:
        lines.append("Geen vraag waar het basismodel goed zat en het bijgetrainde model fout.")
    else:
        lines.extend(f"- `{item_id}`" for item_id in worse)
    lines.extend(["", "## Waar het bijgetrainde model beter is", ""])
    if not _both_measured(base, finetuned):
        lines.append("Nog niet te vergelijken.")
    elif not better:
        lines.append("Geen vraag waar alleen het bijgetrainde model goed zat.")
    else:
        lines.extend(f"- `{item_id}`" for item_id in better)
    lines.append("")
    return "\n".join(lines)


def complete_chat(base_url: str, model: str, prompt: str, *, timeout: float) -> str:
    url = base_url.rstrip("/") + "/chat/completions"
    api_key = os.environ.get("OPENAI_API_KEY", "ollama")
    response = httpx.post(
        url,
        json={
            "model": model,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        },
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=timeout,
    )
    response.raise_for_status()
    payload: object = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("endpoint gaf geen JSON-object terug")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise RuntimeError("endpoint gaf geen choices terug")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise RuntimeError("endpoint gaf geen message terug")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("endpoint gaf een leeg antwoord")
    return content


def dispatch(argv: list[str]) -> int:
    if argv and argv[0] == "doctor":
        return _doctor(argv[1:])
    if argv and argv[0] == "compare":
        return _compare(argv[1:])
    if argv and argv[0] == "run":
        argv = argv[1:]
    return _run(argv)


def _run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Scoor de concepttoets op een lokaal model.")
    parser.add_argument("--model", choices=["base", "finetuned"], required=True)
    parser.add_argument("--questions", type=Path, default=None)
    parser.add_argument("--out-dir", type=Path, default=Path("eval/reports"))
    parser.add_argument("--base-url", default=os.environ.get("LLM_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--base-tag", default=DEFAULT_BASE_TAG)
    parser.add_argument("--finetuned-tag", default=DEFAULT_FINETUNED_TAG)
    parser.add_argument("--finetuned-path", type=Path, default=DEFAULT_FINETUNED_PATH)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument(
        "--judge",
        action="store_true",
        help="Zet de nakijker aan. Standaard uit. Er is nog geen nakijk-endpoint.",
    )
    args = parser.parse_args(argv)
    dataset = args.questions if args.questions is not None else default_dataset()
    items = load_items(dataset)
    base_url = _normalize_base_url(args.base_url)
    if args.judge:
        print(
            "De nakijker-haak staat aan, maar er is geen nakijkmodel gekoppeld. "
            "Open vragen blijven buiten de score."
        )
    judge = None
    if args.model == "base":
        tag = args.base_tag
        if not _listed(base_url, tag):
            result = blocked_result("base", tag, missing_base_message(tag))
            path = write_run(args.out_dir, result)
            _refresh_comparison(args.out_dir)
            print(result.toelichting)
            print(path)
            return 2
    else:
        tag = args.finetuned_tag
        if not _listed(base_url, tag):
            result = blocked_result(
                "finetuned",
                tag,
                missing_finetuned_message(tag, args.finetuned_path),
            )
            path = write_run(args.out_dir, result)
            _refresh_comparison(args.out_dir)
            print(result.toelichting)
            print(path)
            return 2
    result = run_items(
        items,
        lambda prompt: complete_chat(base_url, tag, prompt, timeout=args.timeout),
        rol=args.model if args.model == "base" else "finetuned",
        model=tag,
        judge=judge,
    )
    path = write_run(args.out_dir, result)
    comparison = _refresh_comparison(args.out_dir)
    print(result.toelichting)
    print(path)
    print(comparison)
    return 0


def _doctor(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Kijk of deze pc de meting aankan.")
    parser.add_argument("--out-dir", type=Path, default=Path("eval/reports"))
    parser.add_argument("--base-url", default=os.environ.get("LLM_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--base-tag", default=DEFAULT_BASE_TAG)
    parser.add_argument("--finetuned-tag", default=DEFAULT_FINETUNED_TAG)
    parser.add_argument("--finetuned-path", type=Path, default=DEFAULT_FINETUNED_PATH)
    parser.add_argument("--questions", type=Path, default=None)
    args = parser.parse_args(argv)
    dataset = args.questions if args.questions is not None else default_dataset()
    checks = collect_checks(
        base_url=_normalize_base_url(args.base_url),
        base_tag=args.base_tag,
        finetuned_tag=args.finetuned_tag,
        finetuned_path=args.finetuned_path,
        dataset=dataset,
        get=_http_get,
        gpu_text=nvidia_smi_text(),
    )
    text = render_doctor(checks)
    destination = write_doctor_report(args.out_dir, checks, datetime.now().astimezone())
    print(text)
    print(destination)
    return 0


def _compare(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Zet de twee rijen naast elkaar.")
    parser.add_argument("--out-dir", type=Path, default=Path("eval/reports"))
    args = parser.parse_args(argv)
    destination = _refresh_comparison(args.out_dir)
    print(destination.read_text(encoding="utf-8"))
    return 0


def _refresh_comparison(directory: Path) -> Path:
    base = load_run(directory / "kwaliteit-base.json")
    finetuned = load_run(directory / "kwaliteit-finetuned.json")
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / "vergelijking.md"
    destination.write_text(render_comparison(base, finetuned), encoding="utf-8")
    return destination


def _listed(base_url: str, tag: str) -> bool:
    from wetvia_eval.doctor import probe_models

    reachable, models = probe_models(base_url, _http_get)
    if not reachable:
        return False
    if tag in models:
        return True
    return any(name == tag or name.startswith(f"{tag}:") for name in models)


def _http_get(url: str, timeout: float) -> httpx.Response:
    return httpx.get(url, timeout=timeout)


def _normalize_base_url(base_url: str) -> str:
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        return root
    return root + "/v1"


def _from_score(item: BenchItem, score: AnswerScore, seconds: float) -> ItemResult:
    return ItemResult(
        id=item.id,
        type=item.type,
        antwoord_goed=score.antwoord_goed,
        bron_goed=score.bron_goed,
        verwacht=item.antwoord,
        gegeven=score.gegeven_antwoord,
        seconden=seconds,
        fout=None,
    )


def _summary(items: list[ItemResult], concept: bool) -> str:
    scored = [item for item in items if item.fout is None and item.antwoord_goed is not None]
    if not scored:
        return "niet gemeten: geen bruikbaar antwoord"
    correct = sum(1 for item in scored if item.antwoord_goed)
    prefix = "Conceptset. " if concept else ""
    return f"{prefix}{correct} van {len(scored)} antwoorden komen overeen met de sleutel."


def _items(result: RunResult | None) -> tuple[ItemResult, ...]:
    if result is None or result.status != "gemeten":
        return ()
    return result.items


def _ratio(result: RunResult | None, kind: str | None) -> str:
    if result is None or result.status != "gemeten":
        return "niet gemeten"
    chosen = [
        item
        for item in result.items
        if item.fout is None
        and item.antwoord_goed is not None
        and (kind is None or item.type == kind)
    ]
    if not chosen:
        return "niet gemeten"
    correct = sum(1 for item in chosen if item.antwoord_goed)
    return f"{correct}/{len(chosen)}"


def _both_measured(base: RunResult | None, finetuned: RunResult | None) -> bool:
    return (
        base is not None
        and finetuned is not None
        and base.status == "gemeten"
        and finetuned.status == "gemeten"
    )


def _side_lines(label: str, result: RunResult | None) -> list[str]:
    if result is None or result.status != "gemeten":
        return [f"**{label}:** niet gemeten.", ""]
    return [f"**{label}** (`{result.model}`): {result.toelichting}", ""]


def _diffs(
    base: RunResult | None,
    finetuned: RunResult | None,
    *,
    finetuned_better: bool,
) -> list[str]:
    if base is None or finetuned is None:
        return []
    base_by_id = {item.id: item for item in base.items}
    found: list[str] = []
    for item in finetuned.items:
        other = base_by_id.get(item.id)
        if other is None or item.antwoord_goed is None or other.antwoord_goed is None:
            continue
        if finetuned_better and item.antwoord_goed and not other.antwoord_goed:
            found.append(item.id)
        if not finetuned_better and other.antwoord_goed and not item.antwoord_goed:
            found.append(item.id)
    return found


def _optional_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _optional_float(value: object) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None
