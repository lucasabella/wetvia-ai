"""Controleert of deze pc een 4B-meting aankan. Geen verzonnen snelheden."""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

import httpx

from nl_overheid_benchmark import concept_set_path, load_items
from wetvia_eval.vram import parse_nvidia_smi_memory_mib

_MIN_VRAM_MIB = 6000
_PROBE_TIMEOUT_SECONDS = 3.0


class HttpGet(Protocol):
    def __call__(self, url: str, timeout: float) -> httpx.Response: ...


@dataclass(frozen=True)
class Check:
    naam: str
    ok: bool
    detail: str


def nvidia_smi_text(
    runner: subprocess.CompletedProcess[str] | None = None,
) -> str | None:
    if runner is not None:
        if runner.returncode != 0:
            return None
        return runner.stdout
    if shutil.which("nvidia-smi") is None:
        return None
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout


def parse_gpu_line(text: str) -> tuple[str, int] | None:
    """`name, total MiB` uit nvidia-smi. Lege of kapotte uitvoer geeft None."""
    for line in text.splitlines():
        if "," not in line:
            continue
        name, raw_total = line.split(",", 1)
        total = parse_nvidia_smi_memory_mib(raw_total)
        if total is None or not name.strip():
            continue
        return name.strip(), total
    return None


def probe_models(base_url: str, get: HttpGet) -> tuple[bool, set[str]]:
    """Eerste waarde is True als het endpoint minstens één lijst teruggaf."""
    root = base_url.rstrip("/")
    candidates = [f"{root}/models"]
    if root.endswith("/v1"):
        candidates.append(f"{root[:-3]}/api/tags")
    found: set[str] = set()
    reachable = False
    for url in candidates:
        try:
            response = get(url, _PROBE_TIMEOUT_SECONDS)
            response.raise_for_status()
            payload: object = response.json()
        except (httpx.HTTPError, ValueError):
            continue
        reachable = True
        found.update(_ids_from_payload(payload))
    return reachable, found


def _ids_from_payload(payload: object) -> set[str]:
    if not isinstance(payload, dict):
        return set()
    names: set[str] = set()
    data = payload.get("data")
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                names.add(item["id"])
    models = payload.get("models")
    if isinstance(models, list):
        for item in models:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                names.add(item["name"])
    return names


def collect_checks(
    *,
    base_url: str,
    base_tag: str,
    finetuned_tag: str,
    finetuned_path: Path,
    dataset: Path,
    get: HttpGet,
    gpu_text: str | None,
) -> list[Check]:
    checks = [
        Check(
            naam="Python",
            ok=sys.version_info >= (3, 12),
            detail=f"{platform.python_version()} op {platform.system()}",
        )
    ]
    checks.append(_gpu_check(gpu_text))
    reachable, models = probe_models(base_url, get)
    if reachable:
        endpoint_detail = f"{base_url} antwoordt, {len(models)} model(len)"
    else:
        endpoint_detail = f"{base_url} niet bereikbaar"
    checks.append(Check("Endpoint", reachable, endpoint_detail))
    checks.append(
        Check(
            naam="Basismodel",
            ok=_tag_listed(models, base_tag),
            detail=_model_detail(models, base_tag, f"ollama pull {base_tag}"),
        )
    )
    finetuned_ok, finetuned_detail = _finetuned_detail(models, finetuned_tag, finetuned_path)
    checks.append(Check("Bijgetraind model", finetuned_ok, finetuned_detail))
    checks.append(_dataset_check(dataset))
    return checks


def ready_for_base(checks: list[Check]) -> bool:
    needed = {"Python", "Endpoint", "Basismodel", "Toetsset"}
    return all(check.ok for check in checks if check.naam in needed)


def ready_for_comparison(checks: list[Check]) -> bool:
    return ready_for_base(checks) and any(
        check.ok for check in checks if check.naam == "Bijgetraind model"
    )


def render_doctor(checks: list[Check]) -> str:
    lines = [
        "Controle voor een meting op deze computer.",
        "Een 4B-model in 4-bit (bij Ollama heet dat Q4) is ongeveer 3 tot 4 GB.",
        "Een kaart van 8 GB kan dat draaien. Trainen hoort hier niet op: dat vraagt meer geheugen.",
        "",
    ]
    for check in checks:
        mark = "ok" if check.ok else "niet ok"
        lines.append(f"- {check.naam}: {mark}. {check.detail}")
    lines.append("")
    if ready_for_comparison(checks):
        lines.append("Klaar voor basis én bijgetraind model.")
    elif ready_for_base(checks):
        lines.append(
            "Klaar voor de basisrij. Het bijgetrainde model ontbreekt nog, "
            "dus een vergelijking kan nog niet."
        )
    else:
        lines.append("Nog niet klaar voor de basisrij. Zie de regels met 'niet ok'.")
    lines.append("")
    return "\n".join(lines)


def write_doctor_report(directory: Path, checks: list[Check], when: datetime) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / "doctor.json"
    payload = {
        "datum": when.date().isoformat(),
        "klaar_voor_basis": ready_for_base(checks),
        "klaar_voor_vergelijking": ready_for_comparison(checks),
        "checks": [
            {"naam": check.naam, "ok": check.ok, "detail": check.detail} for check in checks
        ],
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    destination.write_text(text, encoding="utf-8")
    return destination


def _gpu_check(gpu_text: str | None) -> Check:
    if gpu_text is None:
        return Check(
            naam="Videokaart",
            ok=False,
            detail=(
                "nvidia-smi niet gevonden. Op een 3070 hoort dat commando "
                "te werken na de NVIDIA-driver."
            ),
        )
    parsed = parse_gpu_line(gpu_text)
    if parsed is None:
        return Check("Videokaart", False, "nvidia-smi gaf geen leesbare kaart terug")
    name, total = parsed
    fits = total >= _MIN_VRAM_MIB
    if fits:
        detail = f"{name}, {total} MiB totaal. Dat is genoeg voor een 4B-model in 4-bit."
    else:
        detail = f"{name}, {total} MiB totaal. Dat is krap voor een 4B-model naast Windows."
    return Check("Videokaart", fits, detail)


def _tag_listed(models: set[str], tag: str) -> bool:
    if tag in models:
        return True
    return any(name == tag or name.startswith(f"{tag}:") for name in models)


def _model_detail(models: set[str], tag: str, hint: str) -> str:
    if _tag_listed(models, tag):
        return f"{tag} staat op het endpoint"
    if not models:
        return f"{tag} niet gezien. Is het endpoint aan? Daarna: {hint}"
    return f"{tag} staat er niet. {hint}"


def _finetuned_detail(models: set[str], tag: str, path: Path) -> tuple[bool, str]:
    if _tag_listed(models, tag):
        return True, f"tag {tag} staat op het endpoint"
    if path.is_dir() and (path / "adapter_config.json").is_file():
        return (
            False,
            f"{path} is een LoRA-adapter. Deze meting laadt die map niet. "
            f"Maak er een model van in Ollama of LM Studio en gebruik --finetuned-tag.",
        )
    if path.is_file():
        return (
            False,
            f"{path} staat op schijf, maar deze meting laadt het bestand niet zelf. "
            "Zet het in Ollama of LM Studio.",
        )
    return (
        False,
        f"Geen tag {tag} en geen bestand op {path}. "
        "Zonder bijgetraind model blijft die rij 'niet gemeten'.",
    )


def _dataset_check(dataset: Path) -> Check:
    try:
        items = load_items(dataset)
    except ValueError as exc:
        return Check("Toetsset", False, str(exc))
    if not items:
        return Check("Toetsset", False, f"{dataset} is leeg")
    concept = sum(1 for item in items if item.concept)
    return Check(
        "Toetsset",
        True,
        f"{len(items)} items in {dataset}, waarvan {concept} nog concept",
    )


def default_dataset() -> Path:
    return concept_set_path()
