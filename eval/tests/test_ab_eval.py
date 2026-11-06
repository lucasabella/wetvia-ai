"""Testen voor de A/B-benchmark: loader, prompt en deterministische score."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from wetvia_eval.ab_eval import (
    ModelRun,
    ProbeDataError,
    ProbeItem,
    ProbeSource,
    load_probes,
    prompt_for_probe,
    render_report,
    score_response,
    summarize,
)


def _probe() -> ProbeItem:
    return ProbeItem(
        id="t1",
        vraag="Vat het voorstel samen.",
        bronnen=(ProbeSource(bron_id="s1", tekst="Tekst van bron s1."),),
        verwachte_status="beantwoord",
        peildatum="2026-03-01",
        categorie="samenvatten",
    )


def _answer_json(**overrides: object) -> str:
    answer: dict[str, object] = {
        "status": "beantwoord",
        "samenvatting": "Kort antwoord.",
        "punten": [{"tekst": "Punt.", "bron_ids": ["s1"]}],
        "voorbehouden": [],
        "vervolgstappen": [],
        "peildatum": "2026-03-01",
    }
    answer.update(overrides)
    return json.dumps(answer)


class TestLoadProbes:
    def test_rejects_missing_concept_flag(self, tmp_path: Path) -> None:
        row = {
            "id": "x1",
            "categorie": "a",
            "peildatum": "2026-03-01",
            "verwachte_status": "beantwoord",
            "vraag": "Vraag?",
            "bronnen": [{"bron_id": "s1", "tekst": "Tekst."}],
        }
        path = tmp_path / "probes.jsonl"
        path.write_text(json.dumps(row), encoding="utf-8")
        with pytest.raises(ProbeDataError, match="concept"):
            load_probes(path)

    def test_rejects_unknown_verwachte_status(self, tmp_path: Path) -> None:
        row = {
            "id": "x1",
            "concept": True,
            "categorie": "a",
            "peildatum": "2026-03-01",
            "verwachte_status": "buiten_scope",
            "vraag": "Vraag?",
            "bronnen": [{"bron_id": "s1", "tekst": "Tekst."}],
        }
        path = tmp_path / "probes.jsonl"
        path.write_text(json.dumps(row), encoding="utf-8")
        with pytest.raises(ProbeDataError, match="verwachte_status"):
            load_probes(path)

    def test_rejects_duplicate_ids_and_bron_ids(self, tmp_path: Path) -> None:
        path = tmp_path / "probes.jsonl"
        row = {
            "id": "x1",
            "concept": True,
            "categorie": "a",
            "peildatum": "2026-03-01",
            "verwachte_status": "beantwoord",
            "vraag": "Vraag?",
            "bronnen": [
                {"bron_id": "s1", "tekst": "Tekst."},
                {"bron_id": "s2", "tekst": "Andere tekst."},
            ],
        }
        path.write_text("\n".join([json.dumps(row)] * 2), encoding="utf-8")
        with pytest.raises(ProbeDataError, match="dubbele id"):
            load_probes(path)

        row["bronnen"][1]["bron_id"] = "s1"
        (path.unlink)()
        path.write_text(json.dumps(row), encoding="utf-8")
        with pytest.raises(ProbeDataError, match="dubbele bron_id"):
            load_probes(path)

    def test_happy_path_keeps_bronnen(self, tmp_path: Path) -> None:
        row = {
            "id": "x1",
            "concept": True,
            "categorie": "a",
            "peildatum": "2026-03-01",
            "verwachte_status": "onzeker",
            "vraag": "Vraag?",
            "bronnen": [{"bron_id": "s1", "tekst": "Tekst."}],
        }
        path = tmp_path / "probes.jsonl"
        path.write_text(json.dumps(row), encoding="utf-8")
        probes = load_probes(path)
        assert len(probes) == 1
        assert probes[0].bron_ids == frozenset({"s1"})


class TestScore:
    def test_wrong_citation_outside_bronnen(self) -> None:
        verdict = score_response(_probe(), _answer_json())
        assert verdict.schema_valid is True
        assert verdict.citation_supported is True
        bad = score_response(_probe(), _answer_json(punten=[{"tekst": "P.", "bron_ids": ["s9"]}]))
        assert bad.citation_supported is False

    def test_beantwoord_without_punten_fails_citation(self) -> None:
        verdict = score_response(_probe(), _answer_json(punten=[]))
        assert verdict.schema_valid is True
        assert verdict.citation_supported is False

    def test_abstention_scored_only_on_onzeker_items(self) -> None:
        onzeker_probe = ProbeItem(
            id="t2",
            vraag="Hoeveel stemmen?",
            bronnen=(ProbeSource(bron_id="s1", tekst="Geen stemming."),),
            verwachte_status="onzeker",
            peildatum="2026-03-01",
            categorie="weigeren",
        )
        verdict = score_response(onzeker_probe, _answer_json(status="onzeker", punten=[]))
        assert verdict.abstained is True
        assert verdict.citation_supported is None
        assert verdict.status_match is True

    def test_peildatum_mismatch(self) -> None:
        verdict = score_response(_probe(), _answer_json(peildatum="2025-01-01"))
        assert verdict.peildatum_match is False

    def test_onverstaanbare_output(self) -> None:
        verdict = score_response(_probe(), "geen json")
        assert verdict.schema_valid is False
        assert verdict.status is None

    def test_leeg_antwoord_heeft_error(self) -> None:
        verdict = score_response(_probe(), "")
        assert verdict.error == "leeg antwoord"
        assert verdict.schema_valid is False


class TestSummarizeAndReport:
    def test_summarize_ignores_errors(self) -> None:
        verdicts = [score_response(_probe(), _answer_json()), score_response(_probe(), "stuk")]
        metrics = summarize("m", verdicts, total=3)
        assert metrics.items_total == 3
        assert metrics.answered_items == 2
        assert metrics.schema_valid_pct == 50.0

    def test_render_report_uses_gehaald_labels(self) -> None:
        base_metrics = summarize("qwen3.5:0.8b", [], total=0)
        run = ModelRun(model="qwen3.5:0.8b", metrics=base_metrics)
        rendered = render_report(
            when=datetime.now(UTC),
            base_url="http://127.0.0.1:11434",
            num_ctx=8192,
            keep_alive="0",
            questions_path=Path("eval/data/ab_kamervragen.jsonl"),
            questions_sha256="0" * 64,
            runs=[run, run],
        )
        assert "niet gemeten" in rendered
        assert "concept" in rendered


class TestPrompt:
    def test_prompt_contains_bron_ids_en_vraag(self) -> None:
        prompt = prompt_for_probe(_probe())
        assert "[s1]" in prompt
        assert "Vat het voorstel samen." in prompt
        assert "onzeker" in prompt

    def test_prompt_leeg_bronnen_valt_niet_uit(self) -> None:
        empty = ProbeItem(
            id="t3",
            vraag="Vraag?",
            bronnen=(),
            verwachte_status="onzeker",
            peildatum="2026-03-01",
            categorie="weigeren",
        )
        assert "(geen bronnen in dit item)" in prompt_for_probe(empty)


class TestRunModel:
    def test_provider_receives_keep_alive_en_think_uit(self) -> None:
        """8 GB-bewaking: elke vraag moet de vorige uit VRAM laten gaan."""
        from typing import Any

        from wetvia_eval import ab_eval

        captured: dict[str, Any] = {}

        class FakeProvider:
            async def chat(self, *args: object, **kw: object) -> object:
                async def _gen() -> object:
                    yield _answer_json()

                return _gen()

        def factory(**kwargs: Any) -> object:
            captured.update(kwargs)
            return FakeProvider()

        run = ab_eval._run_model(
            "m", [_probe()], "http://127.0.0.1:11434", 2048, "0", provider_factory=factory
        )
        assert captured["keep_alive"] == "0"
        assert captured["think"] is False
        assert run.metrics.answered_items == 1
        assert run.metrics.schema_valid_pct == 100.0
