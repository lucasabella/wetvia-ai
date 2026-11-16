"""Score zonder model en zonder netwerk."""

from __future__ import annotations

from pathlib import Path

import pytest

from nl_overheid_benchmark import load_items, score_response
from nl_overheid_benchmark.items import BenchItem


def _item(**overrides: object) -> BenchItem:
    base = BenchItem(
        id="x",
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
    data = dict(base.__dict__)
    data.update(overrides)
    return BenchItem(**data)


def test_exact_json_answer_and_citation() -> None:
    score = score_response(_item(), '{"antwoord": "artikel 1:2", "bron": "1:2"}')
    assert score.antwoord_goed is True
    assert score.bron_goed is True


def test_wrong_option_is_not_a_match() -> None:
    item = _item(
        type="meerkeuze",
        antwoord="2.29",
        bron_label="2.29",
        opties=("2.29", "2.28", "2.11", "2.5"),
    )
    score = score_response(item, '{"antwoord": "2.28", "bron": "2.29"}')
    assert score.antwoord_goed is False
    assert score.bron_goed is True


def test_a_quote_that_is_not_in_the_source_fails_the_citation() -> None:
    score = score_response(
        _item(),
        '{"antwoord": "1:2", "bron": "1:2", "citaat": "deze zin staat er niet"}',
    )
    assert score.antwoord_goed is True
    assert score.bron_goed is False


def test_a_contradiction_that_mentions_the_key_is_wrong() -> None:
    assert score_response(_item(), "Niet 1:2 maar 2:4").antwoord_goed is False
    assert score_response(_item(), '{"antwoord": "Geen 1:2"}').antwoord_goed is False
    choice = _item(
        type="meerkeuze",
        antwoord="2:6",
        bron_label="2:6",
        opties=("2:6", "2:7", "1:2", "2:4"),
    )
    assert score_response(choice, '{"antwoord": "Niet 2:6"}').antwoord_goed is False
    soort = _item(type="vast_feit", antwoord="Motie", bron_label="2026D58283")
    assert score_response(soort, '{"antwoord": "Geen motie"}').antwoord_goed is False


def test_missing_citation_is_not_a_failure() -> None:
    score = score_response(_item(), "1:2")
    assert score.antwoord_goed is True
    assert score.bron_goed is None


def test_open_items_are_not_exact_matched() -> None:
    score = score_response(_item(type="open", antwoord="vrij"), '{"antwoord": "vrij"}')
    assert score.antwoord_goed is False


def test_loader_rejects_a_multiple_choice_answer_outside_the_options(tmp_path: Path) -> None:
    path = tmp_path / "set.jsonl"
    path.write_text(
        '{"id":"a","type":"meerkeuze","vraag":"Kies","antwoord":"nee",'
        '"citaat":"zin","brontekst":"zin","bron_url":"https://example.test",'
        '"bron_label":"1","concept":true,"herkomst":"test","opties":["ja","anders"]}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="staat niet in de opties"):
        load_items(path)
