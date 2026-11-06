"""Testen voor de datasetvalidator (structuurregels uit eval/data/README.md)."""

from __future__ import annotations

import json
from pathlib import Path

from wetvia_eval.validate import DatasetReport, main, validate_dataset


def _write(path: Path, rows: list[dict[str, object]]) -> Path:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    return path


def _golden(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "id": "v1",
        "vraag": "Welke voorwaarden gelden volgens de bronnen?",
        "categorie": "A",
        "verwachte_status": "beantwoord",
        "kernfeiten": ["Voorwaarde X geldt op deze peildatum."],
        "gouden_bronnen": [{"bwb_id": "BWBR0010388", "artikel": "2.29", "onderdeel": "b"}],
        "peildatum": "2026-11-01",
        "concept": True,
    }
    row.update(overrides)
    return row


class TestBench:
    def test_geldige_bench_set(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path / "bench.jsonl",
            [
                {"id": "b1", "vraag": "Vraag?", "brontekst": "Tekst."},
                {"id": "b2", "vraag": "Zonder brontekst."},
            ],
        )
        report = validate_dataset(path, "bench")
        assert report.ok
        assert report.items == 2

    def test_missende_vraag_faalt(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "bench.jsonl", [{"id": "b1"}])
        report = validate_dataset(path, "bench")
        assert not report.ok
        assert any("vraag" in error for error in report.errors)


class TestRetrieval:
    def test_gouden_set_happy_path(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "v0.jsonl", [_golden(), _golden(id="v2")])
        report = validate_dataset(path, "retrieval")
        assert report.ok
        assert report.items == 2
        assert report.per_categorie == {"A": 2}
        assert report.concept_true == 2

    def test_onzeker_mag_lege_gouden_bronnen_hebben(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "v0.jsonl", [_golden(verwachte_status="onzeker")])
        report = validate_dataset(path, "retrieval")
        assert report.ok

    def test_beantwoord_zonder_gouden_bronnen_faalt(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path / "v0.jsonl", [_golden(gouden_bronnen=[], verwachte_status="beantwoord")]
        )
        report = validate_dataset(path, "retrieval")
        assert not report.ok

    def test_verkeerde_onderdeel_enum(self, tmp_path: Path) -> None:
        path = _write(
            tmp_path / "v0.jsonl",
            [_golden(gouden_bronnen=[{"bwb_id": "X", "artikel": "1", "onderdeel": 5}])],
        )
        report = validate_dataset(path, "retrieval")
        assert not report.ok
        assert any("onderdeel" in error for error in report.errors)

    def test_missende_concept_vlag_faalt(self, tmp_path: Path) -> None:
        row = _golden()
        del row["concept"]
        path = _write(tmp_path / "v0.jsonl", [row])
        report = validate_dataset(path, "retrieval")
        assert not report.ok
        assert any("concept" in error for error in report.errors)

    def test_onbekende_categorie_faalt(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "v0.jsonl", [_golden(categorie="Z")])
        report = validate_dataset(path, "retrieval")
        assert not report.ok

    def test_dubbele_id_faalt_met_regelverwijzing(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "v0.jsonl", [_golden(), _golden()])
        report = validate_dataset(path, "retrieval")
        assert not report.ok
        assert any("dubbele id" in error and "regel 1" in error for error in report.errors)


class TestDetectieEnAb:
    def test_auto_detectie_retrieval(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "auto.jsonl", [_golden()])
        report = validate_dataset(path)
        assert report.kind == "retrieval"

    def test_auto_detectie_ab(self, tmp_path: Path) -> None:
        path = tmp_path / "probes.jsonl"
        path.write_text(
            json.dumps(
                {
                    "id": "p1",
                    "concept": True,
                    "categorie": "samenvatten",
                    "peildatum": "2026-03-01",
                    "verwachte_status": "onzeker",
                    "vraag": "V?",
                    "bronnen": [{"bron_id": "s1", "tekst": "T."}],
                }
            ),
            encoding="utf-8",
        )
        report = validate_dataset(path)
        assert report.kind == "ab"
        assert report.ok
        assert report.per_status == {"onzeker": 1}

    def test_onbekende_soort_geeft_fout(self, tmp_path: Path) -> None:
        path = _write(tmp_path / "x.jsonl", [{"id": "a"}])
        report = validate_dataset(path, "rommel")
        assert not report.ok
        assert any("datasetsoort" in error for error in report.errors)


class TestMainEnRender:
    def test_exitcodes(self, tmp_path: Path, capsys: object) -> None:
        good = _write(tmp_path / "good.jsonl", [_golden()])
        bad = tmp_path / "bad.jsonl"
        bad.write_text("{geen json}", encoding="utf-8")
        missing = tmp_path / "ontbreekt.jsonl"
        assert main(["--dataset", str(good)]) == 0
        assert main(["--dataset", str(bad)]) == 1
        assert main(["--dataset", str(missing)]) == 1
        out = capsys.readouterr().out  # type: ignore[attr-defined]
        assert "dataset bestaat niet" in out

    def test_render_noemt_concept_waarschuwing(self, tmp_path: Path) -> None:
        report = DatasetReport(path=tmp_path / "x.jsonl", kind="retrieval")
        report.items = 1
        report.concept_false = 1
        assert "menselijke controle" in report.render()

    def test_render_lege_set(self, tmp_path: Path) -> None:
        report = DatasetReport(path=tmp_path / "lege.jsonl", kind="bench")
        assert "Geen items" in report.render()
