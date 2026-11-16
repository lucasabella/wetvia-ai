"""Kwaliteitstoets met een nepantwoord. Geen model en geen netwerk."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from nl_overheid_benchmark import BenchItem, concept_set_path, load_items
from wetvia_eval.bench import main
from wetvia_eval.doctor import Check, collect_checks, render_doctor
from wetvia_eval.kwaliteit import (
    blocked_result,
    missing_finetuned_message,
    render_comparison,
    run_items,
    write_run,
)


def _item() -> BenchItem:
    return BenchItem(
        id="awb-1-2",
        type="welk_artikel",
        vraag="In welk artikel staat deze zin?",
        antwoord="1:2",
        citaat="een zin",
        brontekst="Artikel 1:2\neen zin",
        bron_url="https://wetten.overheid.nl/BWBR0005537",
        bron_label="1:2",
        concept=True,
        herkomst="test",
    )


def test_run_scores_a_closed_answer_and_skips_the_judge() -> None:
    open_item = BenchItem(
        id="open-1",
        type="open",
        vraag="Leg uit.",
        antwoord="iets",
        citaat="zin",
        brontekst="zin",
        bron_url="https://wetten.overheid.nl/BWBR0005537",
        bron_label="1:2",
        concept=True,
        herkomst="test",
    )

    def judge(item: BenchItem, raw: str) -> int:
        assert item.id == "open-1"
        assert "klopt" in raw
        return 1

    without = run_items(
        [_item(), open_item],
        lambda _prompt: '{"antwoord": "1:2"}',
        rol="base",
        model="fake",
    )
    assert without.items[0].antwoord_goed is True
    assert without.items[1].fout == "nakijker staat uit"
    with_judge = run_items(
        [open_item],
        lambda _prompt: "klopt volgens de tekst",
        rol="base",
        model="fake",
        judge=judge,
    )
    assert with_judge.items[0].antwoord_goed is True


def test_comparison_shows_a_missing_row_and_where_finetuned_is_worse(tmp_path: Path) -> None:
    base = run_items(
        [_item()],
        lambda _prompt: '{"antwoord": "1:2"}',
        rol="base",
        model="qwen3.5:4b",
    )
    finetuned = run_items(
        [_item()],
        lambda _prompt: '{"antwoord": "9:9"}',
        rol="finetuned",
        model="wetvia",
    )
    text = render_comparison(base, finetuned)
    assert "1/1" in text
    assert "`awb-1-2`" in text
    assert "slechter" in text
    missing = blocked_result(
        "finetuned",
        "ontbreekt",
        "er is nog geen model",
        dataset_sha256=base.dataset_sha256,
    )
    only_base = render_comparison(base, missing)
    assert "niet gemeten" in only_base
    assert "niet volledig gemeten" in only_base
    write_run(tmp_path, base)
    assert (tmp_path / "kwaliteit-base.json").is_file()


def test_a_failed_request_is_incomplete_and_stays_in_the_denominator() -> None:
    def complete(prompt: str) -> str:
        if "FAIL" in prompt:
            raise RuntimeError("timeout")
        return '{"antwoord": "1:2"}'

    failed = BenchItem(
        id="fail",
        type="welk_artikel",
        vraag="FAIL",
        antwoord="1:2",
        citaat="een zin",
        brontekst="Artikel 1:2\neen zin",
        bron_url="https://wetten.overheid.nl/BWBR0005537",
        bron_label="1:2",
        concept=True,
        herkomst="test",
    )
    result = run_items([_item(), failed], complete, rol="base", model="fake")
    assert result.status == "onvolledig"
    text = render_comparison(result, None)
    assert "1/2, onvolledig" in text
    assert "niet volledig gemeten" in text


def test_different_question_sets_are_not_compared() -> None:
    base = run_items([_item()], lambda _prompt: '{"antwoord": "1:2"}', rol="base", model="a")
    other = BenchItem(
        id="andere",
        type="vast_feit",
        vraag="Welk nummer?",
        antwoord="9",
        citaat="9",
        brontekst="Nummer: 9",
        bron_url="https://example.test",
        bron_label="9",
        concept=True,
        herkomst="test",
    )
    finetuned = run_items([other], lambda _prompt: '{"antwoord": "9"}', rol="finetuned", model="b")
    text = render_comparison(base, finetuned)
    assert "niet bij dezelfde toets" in text
    assert "## Waar het bijgetrainde model slechter is" not in text


def test_lora_directory_gets_a_clear_message(tmp_path: Path) -> None:
    adapter = tmp_path / "lora"
    adapter.mkdir()
    (adapter / "adapter_config.json").write_text("{}", encoding="utf-8")
    message = missing_finetuned_message("wetvia-qwen3.5-4b", adapter)
    assert "LoRA-adapter" in message
    assert "laadt dat schrift niet" in message


def test_doctor_reports_vram_and_a_missing_endpoint() -> None:
    def get(url: str, timeout: float) -> httpx.Response:
        raise ValueError(f"down {url} {timeout}")

    checks = collect_checks(
        base_url="http://127.0.0.1:9/v1",
        base_tag="qwen3.5:4b",
        finetuned_tag="wetvia-qwen3.5-4b",
        finetuned_path=Path("training/out/missing"),
        dataset=concept_set_path(),
        get=get,
        gpu_text="NVIDIA GeForce RTX 3070, 8192\n",
    )
    text = render_doctor(checks)
    assert "8192" in text
    assert "4-bit" in text
    assert "niet bereikbaar" in text
    assert "Nog niet klaar" in text
    assert any(check.naam == "Toetsset" and check.ok for check in checks)


def test_concept_set_loads_from_the_package() -> None:
    items = load_items(concept_set_path())
    assert all(item.concept for item in items)


def test_cli_doctor_and_missing_base_model(tmp_path: Path, monkeypatch: object) -> None:
    from wetvia_eval import kwaliteit

    def fake_checks(**_kwargs: object) -> list[Check]:
        return [
            Check("Python", True, "3.12"),
            Check("Endpoint", True, "lokaal"),
            Check("Basismodel", True, "qwen3.5:4b"),
            Check("Toetsset", True, "28 concept"),
            Check("Videokaart", True, "3070"),
            Check("Bijgetraind model", False, "ontbreekt"),
        ]

    monkeypatch.setattr(kwaliteit, "collect_checks", fake_checks)  # type: ignore[attr-defined]
    out = tmp_path / "reports"
    assert main(["doctor", "--out-dir", str(out)]) == 0
    payload = json.loads((out / "doctor.json").read_text(encoding="utf-8"))
    assert payload["klaar_voor_basis"] is True
    assert payload["klaar_voor_vergelijking"] is False

    monkeypatch.setattr(kwaliteit, "_listed", lambda _url, _tag: False)  # type: ignore[attr-defined]
    questions = tmp_path / "mini.jsonl"
    questions.write_text(
        json.dumps(
            {
                "id": "a",
                "type": "vast_feit",
                "vraag": "Welk nummer?",
                "antwoord": "1",
                "citaat": "1",
                "brontekst": "Nummer: 1",
                "bron_url": "https://example.test",
                "bron_label": "1",
                "concept": True,
                "herkomst": "test",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    code = main(
        [
            "--model",
            "finetuned",
            "--questions",
            str(questions),
            "--out-dir",
            str(out),
            "--finetuned-path",
            str(tmp_path / "geen-model"),
        ]
    )
    assert code == 2
    saved = json.loads((out / "kwaliteit-finetuned.json").read_text(encoding="utf-8"))
    assert saved["status"] == "ontbreekt"
    assert "niet gemeten" in (out / "vergelijking.md").read_text(encoding="utf-8")
