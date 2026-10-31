"""Opt-in live Ollama answer test over an official saved BWB fixture."""

from __future__ import annotations

import asyncio
import os
from datetime import date
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import pytest

from nl_wetten_ingest import Toestand, parse_bwb_xml
from wetvia.answer import AnswerPipeline
from wetvia.bootstrap import get_ollama_provider
from wetvia.config import Settings
from wetvia.retrieval import ScoredChunk, SourceDocument, SourceMetadata
from wetvia.retrieval.testing import FakeRetriever


@pytest.mark.llm
def test_ollama_answers_from_saved_official_bbl_article() -> None:
    if os.getenv("RUN_LLM_TESTS") != "1":
        pytest.skip("set RUN_LLM_TESTS=1 to run the live Ollama acceptance test")

    fixture_path = (
        Path(__file__).resolve().parents[3]
        / "packages/nl-wetten-ingest/tests/fixtures/bwb_xml/bbl-2026-09-24.xml"
    )
    toestand = Toestand(
        bwb_id="BWBR0041297",
        titel="Besluit bouwwerken leefomgeving",
        geldig_vanaf=date(2026, 9, 24),
        geldig_tot=date(9999, 12, 31),
        toestand_url=(
            "https://repository.officiele-overheidspublicaties.nl/bwb/BWBR0041297/"
            "2026-09-24_0/xml/BWBR0041297_2026-09-24_0.xml"
        ),
        modified=date(2026, 9, 30),
    )
    chunks = parse_bwb_xml(fixture_path.read_bytes(), toestand)
    chunk = next(item for item in chunks if item.artikel == "2.29" and item.onderdeel == "b")
    chunk_id = uuid5(NAMESPACE_URL, f"{chunk.toestand_url}#{chunk.artikel}#{chunk.onderdeel}")
    source = SourceDocument(
        chunk_id=chunk_id,
        tekst=chunk.tekst,
        metadata=SourceMetadata(
            bwb_id=chunk.bwb_id,
            regeling_titel=chunk.regeling_titel,
            artikel=chunk.artikel,
            lid=chunk.lid,
            onderdeel=chunk.onderdeel,
            opschrift=chunk.opschrift,
            kop_pad=chunk.kop_pad,
            bron_url=chunk.bron_url,
            toestand_url=chunk.toestand_url,
            geldig_vanaf=chunk.geldig_vanaf,
            geldig_tot=chunk.geldig_tot,
            status="geldend",
            artikel_status=chunk.status,
        ),
    )
    settings = Settings()
    provider = get_ollama_provider(base_url=settings.llm_base_url, model=settings.llm_model)
    pipeline = AnswerPipeline(
        FakeRetriever([ScoredChunk(source, 1.0)]),
        provider,
    )

    answer = asyncio.run(
        pipeline.answer(
            "Welke maximale hoogte noemt deze bron voor een dakkapel?",
            date(2026, 10, 31),
        )
    )

    assert answer.status == "beantwoord"
    assert answer.punten
    assert any(chunk_id in point.bron_ids for point in answer.punten)
