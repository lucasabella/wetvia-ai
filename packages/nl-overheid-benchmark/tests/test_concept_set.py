"""De meegeleverde set is een concept en elke zin komt uit een opgeslagen bron."""

from __future__ import annotations

from pathlib import Path

from nl_overheid_benchmark import concept_set_path, load_items
from nl_overheid_benchmark.items import BenchItem

_PACKAGE = Path(__file__).resolve().parents[1]
_REPO = _PACKAGE.parents[1]
_BWB = _REPO / "packages" / "nl-wetten-ingest" / "tests" / "fixtures"
_HERKOMST = _PACKAGE / "src" / "nl_overheid_benchmark" / "data" / "herkomst"


def test_package_source_does_not_import_wetvia() -> None:
    for path in (_PACKAGE / "src").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "import wetvia" not in text
        assert "from wetvia" not in text


def test_concept_set_is_small_unchecked_and_grounded() -> None:
    items = load_items(concept_set_path())
    assert 20 <= len(items) <= 40
    assert all(item.concept for item in items)
    kinds = {item.type for item in items}
    assert {"welk_artikel", "welk_document", "vast_feit", "meerkeuze"} <= kinds
    awb = (_BWB / "bwb_xml" / "awb-2026-08-15.xml").read_text(encoding="utf-8")
    bbl = (_BWB / "bwb_xml" / "bbl-2026-09-24.xml").read_text(encoding="utf-8")
    awb_meta = (_BWB / "awb-page-1.xml").read_text(encoding="utf-8")
    bbl_meta = (_BWB / "bbl-page-1.xml").read_text(encoding="utf-8")
    tk = (_HERKOMST / "tk-documenten-2026-11-16.json").read_text(encoding="utf-8")
    stcrt = (_HERKOMST / "stcrt-2026-sample.xml").read_text(encoding="utf-8")
    for item in items:
        if item.id.startswith("awb-") and item.type != "vast_feit":
            _assert_law_quote(awb, item)
        elif item.id.startswith("bbl-") and (
            item.type != "vast_feit" or item.id == "bbl-2-29-hoogte-feit"
        ):
            _assert_law_quote(bbl, item)
        elif item.id == "awb-bwb-id":
            assert item.citaat in awb_meta
            assert "BWBR0005537" in awb_meta
        elif item.id == "bbl-titel":
            assert item.citaat in bbl_meta
            assert "BWBR0041297" in bbl_meta
        elif item.id.startswith("tk-"):
            assert item.citaat in tk
            assert item.antwoord in tk
        elif item.id.startswith("stcrt-"):
            assert item.citaat in stcrt
            assert item.bron_label in stcrt
        else:
            raise AssertionError(f"onbekende herkomst voor {item.id}")
        assert item.citaat in item.brontekst or item.antwoord in item.brontekst


def _assert_law_quote(xml: str, item: BenchItem) -> None:
    index = xml.find(item.citaat)
    assert index != -1, item.id
    window = xml[max(0, index - 12000) : index]
    assert f">{item.bron_label}</nr>" in window, item.id
