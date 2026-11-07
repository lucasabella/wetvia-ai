"""Testen voor de SFT-generator: bronnen, requests, pipeline en schrijvers."""

from __future__ import annotations

import json
from pathlib import Path

import generate_sft as gen


class FragmentFactory:
    pass


def _fragment(**overrides: object) -> gen.Fragment:
    waarden: dict[str, object] = {
        "id": "br-001",
        "tekst": "(Fictief testvoorbeeld) Voorstel A: meldplicht vervangt registratieplicht.",
        "bron_uri": "https://opendata.tweedekamer.nl/voorbeelddataset",
        "peildatum": "2026-03-01",
        "status": "voorstel",
        "documentsoort": "Kamerstuk",
        "licentie": "CC0-1.0",
    }
    waarden.update(overrides)
    return gen.Fragment(**waarden)  # type: ignore[arg-type]


def _kandidaat(
    vraag: str = "Wat verandert er voor reparatiebedrijven?", **overrides: object
) -> str:
    antwoord = {
        "status": "beantwoord",
        "samenvatting": "Er komt een meldplicht in plaats van een registratieplicht.",
        "punten": [{"tekst": "Meldplicht.", "bron_ids": ["s1"]}],
        "voorbehouden": [],
        "vervolgstappen": [],
        "peildatum": "2026-03-01",
    }
    if overrides.get("negatief"):
        antwoord = {
            "status": "onzeker",
            "samenvatting": "Staat niet in de bronnen.",
            "punten": [],
            "voorbehouden": [],
            "vervolgstappen": [],
            "peildatum": "2026-03-01",
        }
    object_inhoud = {
        "vraag": vraag,
        "negatief": bool(overrides.get("negatief")),
        "antwoord": antwoord,
    }
    return json.dumps(object_inhoud)


def _bronnen_bestand(tmp_path: Path, **fragments: object) -> Path:
    pad = tmp_path / "bronnen.jsonl"
    fragment = _fragment(**fragments)
    pad.write_text(
        json.dumps(
            {
                "id": fragment.id,
                "tekst": fragment.tekst,
                "bron_uri": fragment.bron_uri,
                "peildatum": fragment.peildatum,
                "status": fragment.status,
                "documentsoort": fragment.documentsoort,
                "licentie": fragment.licentie,
            }
        ),
        encoding="utf-8",
    )
    return pad


class TestBronnen:
    def test_happy_path(self, tmp_path: Path) -> None:
        fragmenten = gen.load_fragmenten(_bronnen_bestand(tmp_path))
        assert len(fragmenten) == 1
        assert fragmenten[0].bron_label == "s1"
        assert "[s1]" in fragmenten[0].blok

    def test_missende_licentie_faalt(self, tmp_path: Path) -> None:
        pad = _bronnen_bestand(tmp_path)
        row = json.loads(pad.read_text(encoding="utf-8"))
        del row["licentie"]
        pad.write_text(json.dumps(row), encoding="utf-8")
        try:
            gen.load_fragmenten(pad)
        except gen.SourceError as exc:
            assert "licentie" in str(exc)
        else:
            raise AssertionError("verwachte SourceError")

    def test_bron_uri_moet_url_zijn(self, tmp_path: Path) -> None:
        pad = tmp_path / "bronnen.jsonl"
        pad.write_text("geen json", encoding="utf-8")
        try:
            gen.load_fragmenten(pad)
        except gen.SourceError as exc:
            assert "ongeldige JSON" in str(exc)
        else:
            raise AssertionError("verwachte SourceError")


class TestRequests:
    def test_all_requests_vormt_batchregels(self) -> None:
        fragmenten = [_fragment(), _fragment(id="br-002")]
        regels = gen.all_requests(fragmenten, per_fragment=4, deel_negatief=0.3, model="m")
        assert len(regels) == 8
        eerste = regels[0]
        assert eerste["custom_id"] == "br-001:slot0:neg"
        assert eerste["method"] == "POST"
        assert eerste["url"] == "/v1/chat/completions"
        assert eerste["body"]["temperature"] == 0.0

    def test_negatief_aandeel_is_slotgedreven(self) -> None:
        fragmenten = [_fragment()]
        regels = gen.all_requests(fragmenten, per_fragment=4, deel_negatief=0.5, model="m")
        negatief = [regel["custom_id"].endswith("neg") for regel in regels]
        assert negatief == [True, True, False, False]


class TestVerify:
    def test_geldige_positieve_kandidaat(self) -> None:
        fragment = _fragment()
        rij, reden = gen.verify_kandidaat(_kandidaat(), fragment, False, set(), set())
        assert reden is None
        assert rij is not None
        assert rij["metadata"]["negative"] is False
        assert rij["metadata"]["reviewed"] is False
        assert rij["metadata"]["license"] == "CC0-1.0"

    def test_negatief_verschil_wordt_geweigerd(self) -> None:
        _, reden = gen.verify_kandidaat(_kandidaat(), _fragment(), True, set(), set())
        assert reden == "teacher volgde de negatief-instructie niet"

    def test_onbekende_citatie_wordt_geweigerd(self) -> None:
        kandidaat = json.loads(_kandidaat())
        kandidaat["antwoord"]["punten"][0]["bron_ids"] = ["s9"]
        _, reden = gen.verify_kandidaat(json.dumps(kandidaat), _fragment(), False, set(), set())
        assert reden is not None and "onbekende bronnen" in reden

    def test_peildatum_moet_passen(self) -> None:
        kandidaat = json.loads(_kandidaat())
        kandidaat["antwoord"]["peildatum"] = "2025-01-01"
        _, reden = gen.verify_kandidaat(json.dumps(kandidaat), _fragment(), False, set(), set())
        assert reden is not None and "peildatum" in reden

    def test_dubbele_vraag_voortgezet_in_gezien(self) -> None:
        fragment = _fragment()
        gezien: set[str] = set()
        gen.verify_kandidaat(_kandidaat(), fragment, False, gezien, set())
        _, reden = gen.verify_kandidaat(
            _kandidaat(" WAT verandert er voor reparatiebedrijven? "),
            fragment,
            False,
            gezien,
            set(),
        )
        assert reden == "dubbele vraag"

    def test_ngram_overlap_met_evalset(self) -> None:
        eval_gramen = gen.ngramen(
            "Dit is een hele lange evalvraag die toevallig overeenkomt met"
            " de tekst van de gegenereerde vraag hieronder"
        )
        lange_vraag = (
            "Dit is een hele lange evalvraag die toevallig overeenkomt met"
            " de tekst van de gegenereerde vraag hieronder, toch?"
        )
        _, reden = gen.verify_kandidaat(
            _kandidaat(lange_vraag), _fragment(), False, set(), eval_gramen
        )
        assert reden is not None and "evalset" in reden

    def test_markdown_fences_worden_gelezen(self) -> None:
        fenced = "```json\n" + _kandidaat() + "\n```"
        rij, reden = gen.verify_kandidaat(fenced, _fragment(), False, set(), set())
        assert rij is not None and reden is None


class TestPipeline:
    def _content_map(self, fragment: gen.Fragment, per: int, deel: float) -> dict[str, str]:
        regels = gen.all_requests([fragment], per_fragment=per, deel_negatief=deel, model="m")
        return {
            str(regel["custom_id"]): _kandidaat(
                vraag=f"Wat verandert er voor reparatiebedrijven? (slot {regel['custom_id']})",
                negatief=str(regel["custom_id"]).endswith("neg"),
            )
            for regel in regels
        }

    def test_acceptatie_en_aantallen(self) -> None:
        fragment = _fragment()
        rows, stats, _ = gen.run_pipeline(
            [fragment],
            self._content_map(fragment, 4, 0.25),
            per_fragment=4,
            deel_negatief=0.25,
            eval_gramen=set(),
        )
        assert stats.kandidaten == 4
        assert stats.geaccepteerd == 4
        assert stats.negatief_geaccepteerd == 1
        assert stats.negatiefaandeel_pct == 25.0
        assert len({row["id"] for row in rows}) == 4
        assert all(row["id"] for row in rows)

    def test_ontbrekend_content_gaat_afwijzing_in(self) -> None:
        rows, stats, _ = gen.run_pipeline(
            [_fragment()], {}, per_fragment=2, deel_negatief=0.0, eval_gramen=set()
        )
        assert rows == []
        assert stats.afgewezen["geen teacher-antwoord"] == 2


class TestMain:
    def test_mode_requests_schrijft_bestand(self, tmp_path: Path) -> None:
        bron = _bronnen_bestand(tmp_path)
        out = tmp_path / "out"
        code = gen.main(
            [
                "--mode",
                "requests",
                "--sources",
                str(bron),
                "--out-dir",
                str(out),
            ]
        )
        assert code == 0
        bestand = out / "sft-batch-requests.jsonl"
        assert bestand.is_file()
        assert json.loads(bestand.read_text(encoding="utf-8").splitlines()[0])["custom_id"]

    def test_mode_ingest_zonder_resultaten_faalt(self, tmp_path: Path) -> None:
        assert gen.main(["--mode", "ingest", "--sources", str(_bronnen_bestand(tmp_path))]) == 2

    def test_mode_ingest_schrijft_draft_card_en_steekproef(self, tmp_path: Path) -> None:
        bron = _bronnen_bestand(tmp_path)
        fragment = gen.load_fragmenten(bron)[0]
        regels = gen.all_requests([fragment], per_fragment=4, deel_negatief=0.25, model="m")
        resultat = tmp_path / "batch.jsonl"
        resultat.write_text(
            "\n".join(
                json.dumps(
                    {
                        "custom_id": str(regel["custom_id"]),
                        "response": {
                            "status_code": 200,
                            "body": {
                                "choices": [
                                    {
                                        "message": {
                                            "content": _kandidaat(
                                                vraag=(
                                                    "Wat verandert er voor reparatiebedrijven?"
                                                    f" (slot {regel['custom_id']})"
                                                ),
                                                negatief=str(regel["custom_id"]).endswith("neg"),
                                            )
                                        }
                                    }
                                ]
                            },
                        },
                    }
                )
                for regel in regels
            ),
            encoding="utf-8",
        )
        out = tmp_path / "out"
        code = gen.main(
            [
                "--mode",
                "ingest",
                "--sources",
                str(bron),
                "--batch-results",
                str(resultat),
                "--out-dir",
                str(out),
                "--eval-set",
                str(tmp_path / "leeg.jsonl"),
            ]
        )
        assert code == 0
        draft = next(out.glob("sft-concept-*.jsonl"))
        card = next(out.glob("DATA_CARD-concept-*.md"))
        steekproef = next(out.glob("review-steekproef-*.jsonl"))
        assert len(draft.read_text(encoding="utf-8").strip().splitlines()) == 4
        assert "CONCEPT" in card.read_text(encoding="utf-8")
        assert steekproef.is_file()

    def test_ingest_filtert_lege_resultaten(self, tmp_path: Path) -> None:
        bron = _bronnen_bestand(tmp_path)
        fragment = gen.load_fragmenten(bron)[0]
        regels = gen.all_requests([fragment], per_fragment=1, deel_negatief=0.0, model="m")
        resultat = tmp_path / "batch.jsonl"
        resultat.write_text(
            json.dumps({"custom_id": str(regels[0]["custom_id"]), "error": {"code": "x"}}),
            encoding="utf-8",
        )
        out = tmp_path / "out"
        code = gen.main(
            [
                "--mode",
                "ingest",
                "--sources",
                str(bron),
                "--batch-results",
                str(resultat),
                "--out-dir",
                str(out),
                "--eval-set",
                str(tmp_path / "leeg.jsonl"),
            ]
        )
        assert code == 1
        assert next(out.glob("sft-concept-*.jsonl")).read_text(encoding="utf-8") == ""
