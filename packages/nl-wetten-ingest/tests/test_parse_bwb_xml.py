"""Offline tests for official BWB XML parsing and chunk provenance."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import httpx
import pytest
from lxml import etree

from nl_wetten_ingest import (
    BwbSRUClient,
    BWBXMLParseError,
    Chunk,
    Toestand,
    parse_bwb_xml,
    select_toestand,
)

FIXTURES = Path(__file__).parent / "fixtures"
XML_FIXTURES = FIXTURES / "bwb_xml"
PEILDATUM = date(2026, 10, 31)


def _sru_client(bwb_id: str) -> BwbSRUClient:
    if bwb_id == "BWBR0041297":
        pages = {"1": "bbl-page-1.xml", "6": "bbl-page-2.xml", "11": "bbl-page-3.xml"}
        page_size = 5
        page_dir = FIXTURES
    elif bwb_id == "BWBR0005537":
        pages = {"1": "awb-page-1.xml", "101": "awb-page-2.xml", "201": "awb-page-3.xml"}
        page_size = 100
        page_dir = FIXTURES
    else:
        raise AssertionError(f"unexpected fixture BWB-ID: {bwb_id}")

    def respond(request: httpx.Request) -> httpx.Response:
        start_record = request.url.params["startRecord"]
        return httpx.Response(
            200,
            content=(page_dir / pages[start_record]).read_bytes(),
            headers={"content-type": "application/xml"},
            request=request,
        )

    return BwbSRUClient(
        transport=httpx.MockTransport(respond),
        maximum_records=page_size,
    )


@pytest.fixture(scope="module")
def bbl_toestand() -> Toestand:
    with _sru_client("BWBR0041297") as client:
        return select_toestand(client.search_toestanden("BWBR0041297"), PEILDATUM)


@pytest.fixture(scope="module")
def awb_toestand() -> Toestand:
    with _sru_client("BWBR0005537") as client:
        return select_toestand(client.search_toestanden("BWBR0005537"), PEILDATUM)


@pytest.fixture(scope="module")
def bbl_chunks(bbl_toestand: Toestand) -> list[Chunk]:
    xml_bytes = (XML_FIXTURES / "bbl-2026-09-24.xml").read_bytes()
    return parse_bwb_xml(xml_bytes, bbl_toestand)


@pytest.fixture(scope="module")
def awb_chunks(awb_toestand: Toestand) -> list[Chunk]:
    xml_bytes = (XML_FIXTURES / "awb-2026-08-15.xml").read_bytes()
    return parse_bwb_xml(xml_bytes, awb_toestand)


def test_bbl_229_b_golden_text_and_provenance(
    bbl_chunks: list[Chunk], bbl_toestand: Toestand
) -> None:
    chunk = next(
        chunk for chunk in bbl_chunks if chunk.artikel == "2.29" and chunk.onderdeel == "b"
    )

    assert "een dakkapel" in chunk.tekst
    assert "1,75 m" in chunk.tekst
    assert "0,5 m" in chunk.tekst
    assert chunk.bwb_id == "BWBR0041297"
    assert chunk.regeling_titel == "Besluit bouwwerken leefomgeving"
    assert chunk.lid is None
    assert (
        chunk.opschrift
        == "(vergunningvrije omgevingsplanactiviteiten met betrekking tot bouwwerken)"
    )
    assert chunk.kop_pad == (
        "Hoofdstuk 2 — Algemene bepalingen voor bouwwerken > "
        "Afdeling 2.3 — Afbakening vergunningplichten > "
        "§ 2.3.3 — Vergunningvrije gevallen omgevingsplanactiviteiten met betrekking tot bouwwerken"
    )
    assert chunk.geldig_vanaf == date(2026, 9, 24)
    assert chunk.geldig_tot == date(9999, 12, 31)
    assert chunk.bron_url == "https://wetten.overheid.nl/jci1.3:c:BWBR0041297&artikel=2.29"
    assert chunk.toestand_url == bbl_toestand.toestand_url
    assert chunk.status == "geldend"


def test_awb_65_preserves_all_three_lids_and_provenance(
    awb_chunks: list[Chunk], awb_toestand: Toestand
) -> None:
    chunks = [chunk for chunk in awb_chunks if chunk.artikel == "6:5"]
    assert len(chunks) == 1
    chunk = chunks[0]

    assert chunk.tekst.startswith("1. Het bezwaar- of beroepschrift")
    assert "\n\n2. Bij het beroepschrift" in chunk.tekst
    assert "\n\n3. Indien het bezwaar- of beroepschrift" in chunk.tekst
    assert "a. de naam en het adres van de indiener;" in chunk.tekst
    assert chunk.bron_url == "https://wetten.overheid.nl/jci1.3:c:BWBR0005537&artikel=6:5"
    assert chunk.toestand_url == awb_toestand.toestand_url
    assert chunk.geldig_vanaf == date(2026, 8, 15)
    assert chunk.status == "geldend"


def test_table_is_rendered_as_markdown_and_repealed_articles_are_labeled(
    bbl_chunks: list[Chunk],
) -> None:
    table_article = next(chunk for chunk in bbl_chunks if chunk.artikel == "3.8")
    assert "**Tabel 3.8**" in table_article.tekst
    assert "| gebruiksfunctie |" in table_article.tekst
    assert "leden van toepassing" in table_article.tekst
    assert "| --- |" in table_article.tekst

    repealed = next(chunk for chunk in bbl_chunks if chunk.artikel == "2.10")
    assert repealed.status == "vervallen"
    assert "Vervallen" in repealed.tekst


def test_bbl_cals_rowspan_and_colspan_are_repeated_in_markdown(
    bbl_chunks: list[Chunk],
) -> None:
    article = next(chunk for chunk in bbl_chunks if chunk.artikel == "4.15b")
    lines = article.tekst.splitlines()
    expected_second_header = [
        "Waterdiepte (m)",
        "30",
        "50",
        "75",
        "100",
        "150",
        "200",
        "500",
        "700",
        "1.000",
        "1.500",
    ]

    for table_number in ("4.15b.1", "4.15b.2"):
        caption_index = next(
            index for index, line in enumerate(lines) if line.startswith(f"**Tabel {table_number} ")
        )
        colspan_header = [cell.strip() for cell in lines[caption_index + 1].strip("|").split("|")]
        second_header = [cell.strip() for cell in lines[caption_index + 3].strip("|").split("|")]

        assert colspan_header == ["Waterdiepte (m)", *["Strijklengte (m)"] * 10]
        assert second_header == expected_second_header


def test_long_lists_split_at_member_boundaries_and_repeat_lead_in(
    bbl_toestand: Toestand,
) -> None:
    xml_bytes = (XML_FIXTURES / "bbl-2026-09-24.xml").read_bytes()
    chunks = [
        chunk
        for chunk in parse_bwb_xml(xml_bytes, bbl_toestand, max_chars=700)
        if chunk.artikel == "2.29"
    ]

    assert len(chunks) > 18
    assert {chunk.onderdeel.split(".", maxsplit=1)[0] for chunk in chunks if chunk.onderdeel} >= {
        "a",
        "b",
        "m",
        "p",
        "r",
    }
    nested_m = [chunk for chunk in chunks if chunk.onderdeel and chunk.onderdeel.startswith("m.")]
    assert len(nested_m) > 1
    assert all("Onverminderd regels in het omgevingsplan" in chunk.tekst for chunk in nested_m)
    assert all("een antenne-installatie" in chunk.tekst for chunk in nested_m)
    b_text = " ".join(
        chunk.tekst for chunk in chunks if chunk.onderdeel and chunk.onderdeel.startswith("b")
    )
    assert "1,75 m" in b_text
    assert "0,5 m" in b_text


def test_split_keeps_post_list_paragraph_after_list_items_once(
    bbl_toestand: Toestand,
) -> None:
    xml_bytes = (XML_FIXTURES / "bbl-2026-09-24.xml").read_bytes()
    chunks = [
        chunk
        for chunk in parse_bwb_xml(xml_bytes, bbl_toestand, max_chars=400)
        if chunk.artikel == "3.31" and chunk.lid == "5"
    ]
    trailing_text = "aan brandklasse 4, bepaald volgens NEN 6065."
    matching_positions = [
        index for index, chunk in enumerate(chunks) if trailing_text in chunk.tekst
    ]

    assert len(chunks) > 1
    assert matching_positions == [len(chunks) - 1]


def test_malformed_xml_raises_a_parser_error(bbl_toestand: Toestand) -> None:
    with pytest.raises(BWBXMLParseError, match="malformed"):
        parse_bwb_xml(b"<toestand><wetgeving>", bbl_toestand)


def test_external_entities_are_not_expanded(tmp_path: Path, bbl_toestand: Toestand) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("sentinel-not-law-text", encoding="utf-8")
    root = etree.fromstring((XML_FIXTURES / "bbl-2026-09-24.xml").read_bytes())
    article = root.xpath(".//artikel[@label='Artikel 2.29']")[0]
    title = article.find("kop/titel")
    assert title is not None
    title.append(etree.Entity("external"))
    xml_bytes = etree.tostring(
        root,
        encoding="utf-8",
        xml_declaration=True,
        doctype=f'<!DOCTYPE toestand [<!ENTITY external SYSTEM "{secret.as_uri()}">]>',
    )

    chunks = parse_bwb_xml(xml_bytes, bbl_toestand)
    article_chunks = [chunk for chunk in chunks if chunk.artikel == "2.29"]
    assert article_chunks
    assert all("sentinel-not-law-text" not in chunk.tekst for chunk in article_chunks)
    assert all(
        chunk.opschrift is None or "sentinel-not-law-text" not in chunk.opschrift
        for chunk in article_chunks
    )


def test_xml_bwb_identifier_must_match_toestand(
    bbl_toestand: Toestand, awb_toestand: Toestand
) -> None:
    xml_bytes = (XML_FIXTURES / "bbl-2026-09-24.xml").read_bytes()
    with pytest.raises(BWBXMLParseError, match="does not match metadata"):
        parse_bwb_xml(xml_bytes, awb_toestand)
