"""Deterministic Markdown dossier renderer."""

from decimal import Decimal
from urllib.parse import quote

from wetvia.dossier.schema import DossierV1


def render_markdown(dossier: DossierV1) -> str:
    """Render dossier fields without allowing input text to create Markdown structure."""
    lines = [
        "# Conceptdossier dakkapel",
        "",
        f"> **{dossier.disclosure}**",
        "",
        "## Aanvrager",
        "",
        f"- Naam: {_escape(dossier.aanvrager.naam)}",
        f"- Contactgegevens: {_escape(dossier.aanvrager.contactgegevens)}",
        "",
        "## Project",
        "",
        f"- Locatie: {_escape(dossier.locatie)}",
        f"- Peildatum: {dossier.peildatum.isoformat()}",
        "",
        _escape(dossier.projectomschrijving),
        "",
        "## Ingevoerde feiten",
        "",
        f"- Dakvlak: {_escape(dossier.invoer.dakvlak.value)}",
        "- Naar openbaar toegankelijk gebied: "
        f"{_yes_no_unknown(dossier.invoer.dakvlak_naar_openbaar_toegankelijk_gebied)}",
        f"- Plat dak: {_yes_no_unknown(dossier.invoer.plat_dak)}",
        f"- Monumentrelatie: {_escape(dossier.invoer.monumentrelatie.value)}",
        f"- Gebiedsbescherming: {_escape(dossier.invoer.gebiedsbescherming.value)}",
        f"- Hoogte: {_measurement(dossier.invoer.hoogte_m)}",
        f"- Onderzijde boven dakvoet: {_measurement(dossier.invoer.onderzijde_boven_dakvoet_m)}",
        f"- Bovenzijde onder daknok: {_measurement(dossier.invoer.bovenzijde_onder_daknok_m)}",
        "- Linkerzijkant tot dakvlakrand: "
        f"{_measurement(dossier.invoer.linker_zijkant_tot_dakvlakrand_m)}",
        "- Rechterzijkant tot dakvlakrand: "
        f"{_measurement(dossier.invoer.rechter_zijkant_tot_dakvlakrand_m)}",
        "",
        "## Regeltoets",
        "",
        f"Eindoordeel: **{_escape(dossier.toetsing.eindoordeel.value)}**",
        "",
    ]
    for requirement in dossier.toetsing.eisen:
        lines.extend(
            [
                f"### {_escape(requirement.omschrijving)} ({_escape(requirement.artikel)})",
                "",
                f"- Uitkomst: {_status(requirement.voldaan)}",
                f"- Citaat: “{_escape(requirement.citaat)}”",
            ]
        )
        if requirement.contextcitaat:
            lines.append(f"- Contextcitaat: “{_escape(requirement.contextcitaat)}”")
        if requirement.toelichting:
            lines.append(f"- Toelichting: {_escape(requirement.toelichting)}")
        lines.append(f"- Voorbehoud: {_escape(requirement.voorbehoud)}")
        lines.append("")

    technical = dossier.toetsing.technische_bouwactiviteit
    lines.extend(
        [
            "### Technische bouwactiviteit",
            "",
            f"- Oordeel: {_escape(technical.oordeel.value)}",
            f"- Citaat ({_escape(technical.artikel)}): “{_escape(technical.citaat)}”",
            f"- Contextcitaat: “{_escape(technical.contextcitaat)}”",
            f"- Voorbehoud: {_escape(technical.voorbehoud)}",
            "",
            "## Checklist van stukken",
            "",
            f"- Status: `{dossier.checklist.status.value}`",
            f"- Bronstatus: {_escape(dossier.checklist.bron)}; niet opgehaald of geverifieerd",
            f"- Toelichting: {_escape(dossier.checklist.toelichting)}",
        ]
    )
    if dossier.checklist.items:
        lines.append("")
        for item in dossier.checklist.items:
            lines.append(
                f"- [{_escape(item.status.value)}] {_escape(item.omschrijving)} "
                f"(bron: {_escape(item.bron)})"
            )
    lines.extend(["", "## Open vragen", ""])
    if dossier.open_vragen:
        lines.extend(f"- {_escape(question)}" for question in dossier.open_vragen)
    else:
        lines.append("- Geen open invoervragen.")
    lines.extend(["", "## Bronnen", "", f"Peildatum: {dossier.peildatum.isoformat()}", ""])
    for source in dossier.bronnen:
        lines.extend(
            [
                f"- {_escape(source.regeling)}, {_escape(source.artikel)}: "
                f"[{_escape(source.url)}]({_escape_url(source.url)})",
                f"  - BWB-id: `{_escape(source.bwb_id)}`; toestand geldig vanaf "
                f"{source.toestand_geldig_vanaf.isoformat()} t/m "
                f"{source.toestand_geldig_tot.isoformat()}; gewijzigd "
                f"{source.toestand_modified.isoformat()}; opgehaald "
                f"{source.opgehaald_op.isoformat()}",
                f"  - Bronbestand: `{_escape(source.bronbestand)}`; "
                f"SHA-256 `{_escape(source.sha256)}`",
            ]
        )
    lines.extend(["", f"**{dossier.disclosure}**", ""])
    return "\n".join(lines)


def _status(value: bool | None) -> str:
    if value is True:
        return "voldaan"
    if value is False:
        return "niet voldaan"
    return "onbekend"


def _yes_no_unknown(value: bool | None) -> str:
    if value is True:
        return "ja"
    if value is False:
        return "nee"
    return "onbekend"


def _measurement(value: Decimal | None) -> str:
    return f"{value} m" if value is not None else "onbekend"


def _escape_url(value: str) -> str:
    """Keep URL query separators valid in Markdown link destinations."""
    return quote(value, safe=":/?&=%#")


def _escape(value: str) -> str:
    escaped = value.replace("&", "&amp;").replace("\r", " ").replace("\n", " ")
    escaped = escaped.replace("\\", "\\\\")
    escaped = escaped.replace("<", "&lt;").replace(">", "&gt;")
    for character in "`*_{}[]()#+-.!|":
        escaped = escaped.replace(character, f"\\{character}")
    return escaped


__all__ = ["render_markdown"]
