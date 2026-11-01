"""Dakkapel dossier generation using the public rules result and injected local LLM."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from wetvia.dossier.schema import DossierV1, ProjectomschrijvingV1
from wetvia.llm import ChatMessage, LLMProvider
from wetvia.rules import Bronverwijzing, DakkapelInvoer, Toetsresultaat, toets

_SYSTEM_PROMPT = """\
Schrijf in het Nederlands op B1-niveau alleen de projectomschrijving van een
conceptdossier. Beschrijf de voorgenomen werkzaamheden uitsluitend met de
feiten uit de invoer. Verzin geen ontbrekende maten, adres, aanvragergegevens,
bronnen of juridische conclusies. Beoordeel niet of een vergunning nodig is.
Noem geen adres of persoonsgegevens. Houd de omschrijving onder 120 woorden.
"""

_ROOF_LABELS = {
    "achterdakvlak": "het achterdakvlak",
    "zijdakvlak": "een zijdakvlak",
    "ander_dakvlak": "een ander dakvlak",
    "onbekend": "een nog onbekend dakvlak",
}
_MONUMENT_LABELS = {
    "geen_monument": "geen beschermd monument",
    "in_aan_of_op_monument": "een activiteit in, aan of op een beschermd monument",
    "bij_monument": "een activiteit bij een beschermd monument",
    "onbekend": "een nog onbekende monumentrelatie",
}
_AREA_LABELS = {
    "geen_rijksbeschermd_stads_of_dorpsgezicht": "geen rijksbeschermd stads- of dorpsgezicht",
    "rijksbeschermd_stads_of_dorpsgezicht": "een rijksbeschermd stads- of dorpsgezicht",
    "onbekend": "een nog onbekende gebiedsbescherming",
}


@dataclass(frozen=True, slots=True)
class DossierAttachment:
    """Rendered file bytes and the metadata needed for an HTTP attachment."""

    content: bytes
    filename: str
    media_type: str


class DossierFormat(StrEnum):
    """Supported attachment format values."""

    DOCX = "docx"
    PDF = "pdf"
    MARKDOWN = "md"


class DakkapelDossierService:
    """Create a concept dossier; only its short project text uses the injected LLM."""

    def __init__(
        self,
        description_provider: LLMProvider,
        *,
        today: Callable[[], date] = date.today,
    ) -> None:
        self.description_provider = description_provider
        self._today = today

    async def create(
        self,
        input: DakkapelInvoer,
        *,
        location: str | None,
    ) -> DossierV1:
        """Build the structured dossier, omitting the address from the LLM prompt."""
        result = toets(input)
        description = await self._projectomschrijving(input)
        normalized_location = (
            location.strip() if location and location.strip() else "[Locatie invullen]"
        )
        return DossierV1(
            locatie=normalized_location,
            projectomschrijving=description.projectomschrijving,
            invoer=input,
            toetsing=result,
            open_vragen=_open_questions(input, normalized_location),
            bronnen=_unique_sources(result),
            peildatum=self._today(),
        )

    async def create_attachment(
        self,
        input: DakkapelInvoer,
        *,
        location: str | None,
        format: DossierFormat,
    ) -> DossierAttachment:
        dossier = await self.create(input, location=location)
        if format == DossierFormat.DOCX:
            from wetvia.dossier.renderers.docx import render_docx

            return DossierAttachment(
                content=await asyncio.to_thread(render_docx, dossier),
                filename="wetvia-dakkapel-concept.docx",
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        if format == DossierFormat.PDF:
            from wetvia.dossier.renderers.pdf import render_pdf

            return DossierAttachment(
                content=await asyncio.to_thread(render_pdf, dossier),
                filename="wetvia-dakkapel-concept.pdf",
                media_type="application/pdf",
            )
        if format == DossierFormat.MARKDOWN:
            from wetvia.dossier.renderers.md import render_markdown

            return DossierAttachment(
                content=(await asyncio.to_thread(render_markdown, dossier)).encode("utf-8"),
                filename="wetvia-dakkapel-concept.md",
                media_type="text/markdown; charset=utf-8",
            )
        raise ValueError(f"Unsupported dossier format: {format}")

    async def _projectomschrijving(self, input: DakkapelInvoer) -> ProjectomschrijvingV1:
        messages: list[ChatMessage] = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _facts_for_prompt(input)},
        ]
        output = await self.description_provider.chat(
            messages,
            schema=ProjectomschrijvingV1,
            stream=False,
            temperature=0.2,
        )
        if not isinstance(output, ProjectomschrijvingV1):
            raise TypeError("the dossier description provider did not return the schema model")
        return output


def _facts_for_prompt(input: DakkapelInvoer) -> str:
    measurements: tuple[tuple[str, Decimal | None], ...] = (
        ("hoogte", input.hoogte_m),
        ("afstand onderzijde tot dakvoet", input.onderzijde_boven_dakvoet_m),
        ("afstand bovenzijde tot daknok", input.bovenzijde_onder_daknok_m),
        ("afstand linkerzijde tot dakvlakrand", input.linker_zijkant_tot_dakvlakrand_m),
        ("afstand rechterzijde tot dakvlakrand", input.rechter_zijkant_tot_dakvlakrand_m),
    )
    lines = [
        "Voorgenomen activiteit: plaatsen van een dakkapel.",
        f"Dakvlak: {_ROOF_LABELS[input.dakvlak.value]}.",
        f"Plat dak: {_yes_no_unknown(input.plat_dak)}.",
        f"Monumentrelatie: {_MONUMENT_LABELS[input.monumentrelatie.value]}.",
        f"Gebiedsbescherming: {_AREA_LABELS[input.gebiedsbescherming.value]}.",
    ]
    if input.dakvlak_naar_openbaar_toegankelijk_gebied is not None:
        lines.append(
            "Dakvlak naar openbaar toegankelijk gebied: "
            f"{_yes_no_unknown(input.dakvlak_naar_openbaar_toegankelijk_gebied)}."
        )
    for label, value in measurements:
        lines.append(f"{label}: {value} m." if value is not None else f"{label}: onbekend.")
    return "\n".join(lines)


def _yes_no_unknown(value: bool | None) -> str:
    if value is True:
        return "ja"
    if value is False:
        return "nee"
    return "onbekend"


def _unique_sources(result: Toetsresultaat) -> list[Bronverwijzing]:
    sources: list[Bronverwijzing] = []
    for requirement in result.eisen:
        if requirement.bron not in sources:
            sources.append(requirement.bron)
    activity_source = result.technische_bouwactiviteit.bron
    if activity_source not in sources:
        sources.append(activity_source)
    return sources


def _open_questions(input: DakkapelInvoer, location: str) -> list[str]:
    questions: list[str] = [
        "Welke indieningsstukken zijn van toepassing? De officiële DSO-LV-lijst is in "
        "deze versie niet opgehaald of geverifieerd."
    ]
    if location == "[Locatie invullen]":
        questions.append("Wat is het adres of de locatie van het project?")
    if input.dakvlak.value == "onbekend":
        questions.append("Op welk dakvlak komt de dakkapel?")
    if input.monumentrelatie.value == "onbekend":
        questions.append(
            "Is de activiteit in, aan of op een beschermd monument, alleen erbij, of "
            "geen van beide?"
        )
    if input.gebiedsbescherming.value == "onbekend":
        questions.append("Ligt de woning in een rijksbeschermd stads- of dorpsgezicht?")
    if input.plat_dak is None:
        questions.append("Heeft de dakkapel een plat dak?")
    if (
        input.dakvlak.value == "zijdakvlak"
        or (
            input.dakvlak.value == "achterdakvlak"
            and input.gebiedsbescherming.value == "rijksbeschermd_stads_of_dorpsgezicht"
        )
    ) and input.dakvlak_naar_openbaar_toegankelijk_gebied is None:
        questions.append("Keert dit dakvlak naar openbaar toegankelijk gebied?")
    measurements: tuple[tuple[str, Decimal | None], ...] = (
        ("hoogte", input.hoogte_m),
        ("afstand onderzijde tot dakvoet", input.onderzijde_boven_dakvoet_m),
        ("afstand bovenzijde tot daknok", input.bovenzijde_onder_daknok_m),
        ("afstand linkerzijde tot dakvlakrand", input.linker_zijkant_tot_dakvlakrand_m),
        ("afstand rechterzijde tot dakvlakrand", input.rechter_zijkant_tot_dakvlakrand_m),
    )
    questions.extend(
        f"Wat is de {label} van de dakkapel?" for label, value in measurements if value is None
    )
    return questions


__all__ = ["DakkapelDossierService", "DossierAttachment", "DossierFormat"]
