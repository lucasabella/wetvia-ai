"""Gedeeld AnswerV1-contract voor trainer en SFT-generator (docs/02 §4).

Beide tools accepteren geen invented content: dit is puur structuurvalidatie.
Een rij `messages` volgt precies het formaat dat `train_qwen35_lora.py` naar
de chat-template stuurt: optioneel system vooraan, precies één user en één
laatste assistant-bericht, waarvan de content geldige AnswerV1-JSON is.
"""

from __future__ import annotations

import json
from datetime import date
from urllib.parse import urlparse

ANSWER_FIELDS = frozenset(
    {"status", "samenvatting", "punten", "voorbehouden", "vervolgstappen", "peildatum"}
)
STATUSES = frozenset({"beantwoord", "onzeker", "buiten_scope"})
_ROLES = frozenset({"system", "user", "assistant"})


def validate_answer_v1(answer: object) -> list[str]:
    """Geef een lege lijst terug bij geldig AnswerV1; anders de foutmeldingen."""
    errors: list[str] = []
    if not isinstance(answer, dict):
        return ["assistant-uitvoer is geen JSON-object"]
    if set(answer) != ANSWER_FIELDS:
        missing = sorted(ANSWER_FIELDS - set(answer))
        extra = sorted(set(answer) - ANSWER_FIELDS)
        detail = []
        if missing:
            detail.append(f"ontbrekend: {missing}")
        if extra:
            detail.append(f"onbekend: {extra}")
        return [f"antwoord bevat niet precies de AnswerV1-velden ({'; '.join(detail)})"]

    if not isinstance(answer["status"], str) or answer["status"] not in STATUSES:
        errors.append(f"onbekende status {answer['status']!r}")
    samenvatting = answer["samenvatting"]
    if not isinstance(samenvatting, str) or not samenvatting.strip():
        errors.append("`samenvatting` moet tekst bevatten")
    elif len(samenvatting.split()) > 80:
        errors.append("`samenvatting` is langer dan 80 woorden")

    if not isinstance(answer["punten"], list) or not isinstance(answer["voorbehouden"], list):
        errors.append("`punten` en `voorbehouden` moeten lijsten zijn")
    else:
        if any(
            not isinstance(voorbehoud, str) or not voorbehoud.strip()
            for voorbehoud in answer["voorbehouden"]
        ):
            errors.append("elk voorbehoud moet tekst bevatten")
        if answer["status"] == "beantwoord" and not answer["punten"]:
            errors.append("`beantwoord` vereist geciteerde punten")
        seen_bron_ids: set[str] | None = None
        for index, point in enumerate(answer["punten"], start=1):
            if (
                not isinstance(point, dict)
                or set(point) != {"tekst", "bron_ids"}
                or not isinstance(point["tekst"], str)
                or not point["tekst"].strip()
                or not isinstance(point["bron_ids"], list)
                or not point["bron_ids"]
                or any(
                    not isinstance(source_id, str) or not source_id.strip()
                    for source_id in point["bron_ids"]
                )
                or len(point["bron_ids"]) != len(set(point["bron_ids"]))
            ):
                errors.append(f"punt {index} vereist tekst en unieke bron-ID's")
                continue
            current = set(point["bron_ids"])
            if seen_bron_ids is None:
                seen_bron_ids = current
            else:
                seen_bron_ids |= current

    verderstappen = answer["vervolgstappen"]
    if not isinstance(verderstappen, list):
        errors.append("`vervolgstappen` moet een lijst zijn")
    else:
        for index, step in enumerate(verderstappen, start=1):
            if not isinstance(step, dict) or set(step) != {"tekst", "url"}:
                errors.append(f"vervolgstap {index} vereist precies tekst en url")
                continue
            parsed_url = urlparse(step["url"] if isinstance(step["url"], str) else "")
            if (
                not isinstance(step["tekst"], str)
                or not step["tekst"].strip()
                or parsed_url.scheme not in {"http", "https"}
                or not parsed_url.netloc
            ):
                errors.append(f"vervolgstap {index} vereist tekst en een HTTP(S)-URL")

    try:
        peildatum = answer["peildatum"]
        date.fromisoformat(peildatum if isinstance(peildatum, str) else "")
    except (TypeError, ValueError):
        errors.append("`peildatum` moet YYYY-MM-DD zijn")
    return errors


def validate_row(row: object) -> list[str]:
    """Valideer één SFT-rij structuurgewijs; een lege lijst betekent geldig."""
    errors: list[str] = []
    if not isinstance(row, dict):
        return ["verwacht een JSON-object"]

    item_id = row.get("id")
    if not isinstance(item_id, str) or not item_id.strip():
        errors.append("`id` moet een niet-lege string zijn")

    messages = row.get("messages")
    if not isinstance(messages, list) or len(messages) < 2:
        errors.append("`messages` moet minstens twee berichten bevatten")
        return errors
    if any(
        not isinstance(message, dict)
        or message.get("role") not in _ROLES
        or not isinstance(message.get("content"), str)
        or not message["content"].strip()
        for message in messages
    ):
        errors.append("elk bericht vereist role (system/user/assistant) en tekstuele content")
        return errors
    roles = [message["role"] for message in messages]
    if roles[-1] != "assistant" or roles.count("user") != 1 or roles.count("assistant") != 1:
        errors.append("verwacht precies één user- en één laatste assistant-bericht")
        return errors
    if roles.count("system") > 1 or ("system" in roles and roles[0] != "system"):
        errors.append("optioneel system-bericht moet vooraan staan")

    metadata = row.get("metadata")
    if not isinstance(metadata, dict):
        errors.append("`metadata` met bronprovenance ontbreekt")
        return errors
    source_uris = metadata.get("source_uris")
    if (
        not isinstance(source_uris, list)
        or not source_uris
        or any(
            not isinstance(uri, str) or not uri.startswith(("https://", "http://"))
            for uri in source_uris
        )
    ):
        errors.append("`metadata.source_uris` moet bron-URL's bevatten")
    if not isinstance(metadata.get("license"), str) or not metadata["license"].strip():
        errors.append("`metadata.license` ontbreekt")
    if not isinstance(metadata.get("negative"), bool):
        errors.append("`metadata.negative` moet true/false zijn")
        negative: bool | None = None
    else:
        negative = metadata["negative"]

    content = messages[-1]["content"]
    try:
        answer: object = json.loads(content)
    except json.JSONDecodeError:
        errors.append("laatste assistant-bericht is geen ruwe JSON")
        return errors
    answer_errors = validate_answer_v1(answer)
    errors.extend(answer_errors)
    if negative is True and (
        not isinstance(answer, dict) or answer.get("status") != "onzeker" or answer.get("punten")
    ):
        errors.append("negatieve voorbeelden moeten `onzeker` zijn zonder antwoordpunten")
    return errors
