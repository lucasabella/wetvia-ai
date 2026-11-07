"""Testen voor het gedeelde AnswerV1-contract (trainer + generator)."""

from __future__ import annotations

import json

from answer_v1 import validate_answer_v1, validate_row


def _answer(**overrides: object) -> dict[str, object]:
    answer: dict[str, object] = {
        "status": "beantwoord",
        "samenvatting": "Kort antwoord.",
        "punten": [{"tekst": "Punt.", "bron_ids": ["s1"]}],
        "voorbehouden": [],
        "vervolgstappen": [{"tekst": "Lees verder.", "url": "https://example.org"}],
        "peildatum": "2026-03-01",
    }
    answer.update(overrides)
    return answer


def _row(answer: object, *, negative: bool = False) -> dict[str, object]:
    return {
        "id": "br-001:0",
        "messages": [
            {"role": "system", "content": "Antwoord alleen met JSON."},
            {"role": "user", "content": "Vraag?\n\nBRONNEN:\n[s1] Tekst."},
            {"role": "assistant", "content": json.dumps(answer)},
        ],
        "metadata": {
            "source_uris": ["https://example.org/bron"],
            "license": "CC0-1.0",
            "negative": negative,
        },
    }


class TestValidateAnswer:
    def test_geldig(self) -> None:
        assert validate_answer_v1(_answer()) == []

    def test_extra_en_missende_velden(self) -> None:
        answer = _answer()
        del answer["voorbehouden"]
        answer[" netto"] = "x"  # type: ignore[dict-item]
        errors = validate_answer_v1(answer)
        assert any("ontbrekend" in error for error in errors)
        assert any("onbekend" in error for error in errors)

    def test_samenvatting_te_lang(self) -> None:
        errors = validate_answer_v1(_answer(samenvatting=" ".join(["woord"] * 81)))
        assert any("80 woorden" in error for error in errors)

    def test_beantwoord_zonder_punten(self) -> None:
        errors = validate_answer_v1(_answer(punten=[]))
        assert any("geciteerde punten" in error for error in errors)

    def test_verkeerde_peildatum(self) -> None:
        errors = validate_answer_v1(_answer(peildatum="01-03-2026"))
        assert any("peildatum" in error for error in errors)

    def test_slechte_url(self) -> None:
        errors = validate_answer_v1(
            _answer(vervolgstappen=[{"tekst": "x", "url": "ftp://example.org"}])
        )
        assert any("HTTP" in error for error in errors)

    def test_dubbele_bron_ids_in_punt(self) -> None:
        errors = validate_answer_v1(_answer(punten=[{"tekst": "P.", "bron_ids": ["s1", "s1"]}]))
        assert any("unieke bron-ID" in error for error in errors)


class TestValidateRow:
    def test_geldige_rij(self) -> None:
        assert validate_row(_row(_answer())) == []

    def test_negatieve_rij_moet_onzeker_zijn(self) -> None:
        errors = validate_row(_row(_answer(), negative=True))
        assert any("onzeker" in error for error in errors)

    def test_negatieve_onzeker_met_punten_faalt(self) -> None:
        antwoord = _answer(status="onzeker", samenvatting="Weet ik niet.")
        errors = validate_row(_row(antwoord, negative=True))
        assert any("zonder antwoordpunten" in error for error in errors)

    def test_negatieve_onzeker_zonder_punten_is_geldig(self) -> None:
        antwoord = _answer(status="onzeker", samenvatting="Niet in de bronnen.", punten=[])
        assert validate_row(_row(antwoord, negative=True)) == []

    def test_verkeerde_rolvolgorde(self) -> None:
        row = _row(_answer())
        row["messages"] = [
            {"role": "user", "content": "Vraag?"},
            {"role": "system", "content": "S."},
            {"role": "assistant", "content": "{}"},
        ]
        errors = validate_row(row)
        assert any("vooraan" in error for error in errors)

    def test_metadata_ontbreekt(self) -> None:
        row = _row(_answer())
        del row["metadata"]
        errors = validate_row(row)
        assert any("metadata" in error for error in errors)

    def test_assistent_geen_json(self) -> None:
        row = _row(_answer())
        row["messages"][-1]["content"] = "geen json"
        errors = validate_row(row)
        assert any("geen ruwe JSON" in error for error in errors)
