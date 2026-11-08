"""Genereer concept-SFT-voorbeelden uit gelicentieerde bronfragmenten (issue #34).

Pipeline: bronfragmenten (JSONL) -> teacher-prompts (OpenAI-batchformaat) of
directe gesprekken -> antwoorden verifiëren -> deduplicatie -> n-gram-overlap
met de evalset -> conceptdraft + data card + reviewsteekproef.

Er wordt nooit direct `sft.jsonl` geschreven: kandidaten wachten op menselijke
review, zoals de data card beschrijft. Deze generator verzint geen wettekst;
alle inhoud komt uit `--sources` en de teacher.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from answer_v1 import validate_row

NGRAM_SIZE = 8
TEACHER_TIMEOUT_SECONDS = 120.0
FRAGMENTS_URLS_KEY = "bron_uri"


class SourceError(ValueError):
    """Bronfragmenten zijn onbruikbaar."""


@dataclass(frozen=True)
class Fragment:
    id: str
    tekst: str
    bron_uri: str
    peildatum: str
    status: str
    documentsoort: str
    licentie: str

    @property
    def bron_label(self) -> str:
        return "s1"

    @property
    def blok(self) -> str:
        return f"[{self.bron_label}] {self.tekst.strip()}"


@dataclass
class GenerationStats:
    """Boekhouding van de pipeline: alleen tellingen, geen schattingen."""

    kandidaten: int = 0
    geaccepteerd: int = 0
    negatief_geaccepteerd: int = 0
    afgewezen: Counter[str] = field(default_factory=Counter)
    overlap_gecontroleerd: bool = False

    def afwijzing(self, reden: str) -> None:
        self.afgewezen[reden] += 1

    @property
    def negatiefaandeel_pct(self) -> float | None:
        if self.geaccepteerd == 0:
            return None
        return round(100.0 * self.negatief_geaccepteerd / self.geaccepteerd, 1)


SYSTEM_PROMPT = (
    "Je bent data-assistent voor Wetvia-training.\n"
    "Genereer precies één kandidaat als JSON-object met precies deze velden:\n"
    '{"vraag": "...", "negatief": true|false, "antwoord": '
    '{"status": "...", "samenvatting": "...", "punten": [], "voorbehouden": [], '
    '"vervolgstappen": [], "peildatum": "..."}}\n'
    "\n"
    "Regels:\n"
    "- Gebruik uitsluitend de meegegeven BRONNEN; citeer in `punten` alleen de "
    "gegeven bron-ID's zoals [s1].\n"
    "- negatief=false: schrijf een vraag die de bronnen wél beantwoorden; "
    '`status` is dan "beantwoord" met minstens één punt.\n'
    "- negatief=true: schrijf een vraag die bij het onderwerp past maar die de "
    'bronnen NIET beantwoorden; `status` is dan "onzeker", zonder punten.\n'
    "- Schrijf begrijpelijk Nederlands (B1). `peildatum` is de peildatum van de "
    "bron. Geef alleen JSON, geen markdown."
)

SLOTS = ("samenvatting", "bronvraag", "toelichting")

_SLOT_INSTRUCTIE = {
    "samenvatting": "laat de vraag om een korte samenvatting vragen",
    "bronvraag": "laat de vraag naar één specifiek gegeven uit de bronnen vragen",
    "toelichting": "laat de vraag om een uitleg van één bronpunt vragen",
}


def slot_instructie(slot: str, negatief: bool) -> str:
    soort = _SLOT_INSTRUCTIE[slot]
    if negatief:
        return f"{soort}, maar dan zó dat de bronnen het antwoord niet bevatten (negatief)."
    return f"{soort}."


def load_fragmenten(path: Path) -> list[Fragment]:
    """Lees bronfragmenten; één rij = één fragment."""
    if not path.is_file():
        msg = f"Bronbestand bestaat niet: {path}"
        raise SourceError(msg)
    required = ("bron_uri", "peildatum", "status", "documentsoort", "licentie")
    fragmenten: list[Fragment] = []
    seen_ids: set[str] = set()
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            row: object = json.loads(stripped)
        except json.JSONDecodeError as exc:
            msg = f"{path}: regel {line_number}: ongeldige JSON ({exc.msg})"
            raise SourceError(msg) from exc
        if not isinstance(row, dict):
            msg = f"{path}: regel {line_number}: is geen JSON-object"
            raise SourceError(msg)

        item_id = row.get("id")
        tekst = row.get("tekst")
        if not isinstance(item_id, str) or not item_id.strip():
            msg = f"{path}: regel {line_number}: veld 'id' moet een niet-lege string zijn"
            raise SourceError(msg)
        if item_id in seen_ids:
            msg = f"{path}: regel {line_number}: dubbele id {item_id!r}"
            raise SourceError(msg)
        seen_ids.add(item_id)
        if not isinstance(tekst, str) or not tekst.strip():
            msg = f"{path}: regel {line_number} ({item_id}): veld 'tekst' moet tekst bevatten"
            raise SourceError(msg)

        velden: dict[str, str] = {}
        for key in required:
            value = row.get(key)
            if not isinstance(value, str) or not value.strip():
                msg = f"{path}: regel {line_number} ({item_id}): veld '{key}' ontbreekt"
                raise SourceError(msg)
            velden[key] = value
        try:
            datetime.strptime(velden["peildatum"], "%Y-%m-%d")
        except ValueError as exc:
            msg = f"{path}: regel {line_number} ({item_id}): peildatum moet YYYY-MM-DD zijn"
            raise SourceError(msg) from exc
        if velden["status"] not in {"geldig", "voorstel"}:
            msg = (
                f"{path}: regel {line_number} ({item_id}): status moet 'geldig' of "
                f"'voorstel' zijn (kreeg {velden['status']!r})"
            )
            raise SourceError(msg)

        fragmenten.append(
            Fragment(
                id=item_id,
                tekst=tekst,
                bron_uri=velden["bron_uri"],
                peildatum=velden["peildatum"],
                status=velden["status"],
                documentsoort=velden["documentsoort"],
                licentie=velden["licentie"],
            )
        )
    if not fragmenten:
        msg = f"{path} bevat geen bronfragmenten"
        raise SourceError(msg)
    return fragmenten


def user_prompt(fragment: Fragment, slot: str, negatief: bool) -> str:
    return f"TAAK: {slot_instructie(slot, negatief)}\n\nBRONNEN ({fragment.id}):\n{fragment.blok}\n"


def messages_voor(fragment: Fragment, slot: str, negatief: bool) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt(fragment, slot, negatief)},
    ]


def request_body(messages: list[dict[str, str]], model: str) -> dict[str, Any]:
    return {"model": model, "messages": messages, "temperature": 0.0}


def batch_request_row(custom_id: str, messages: list[dict[str, str]], model: str) -> dict[str, Any]:
    """OpenAI-batchformaat; geschikt voor de Scaleway batch-API (upload apart)."""
    return {
        "custom_id": custom_id,
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": request_body(messages, model),
    }


def teacher_call(
    messages: list[dict[str, str]], model: str, base_url: str, api_key: str | None
) -> str:
    """Eén OpenAI-compatibele chat-completion; alleen voor `--mode direct`."""
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    response = httpx.post(
        f"{base_url.rstrip('/')}/chat/completions",
        json=request_body(messages, model),
        headers=headers,
        timeout=TEACHER_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload: object = response.json()
    if not isinstance(payload, dict):
        msg = "teacher gaf geen JSON-object terug"
        raise ValueError(msg)
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        msg = "teacher-respons heeft geen choices"
        raise ValueError(msg)
    message = choices[0].get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        msg = "teacher-respons heeft geen content"
        raise ValueError(msg)
    return content


def parse_batch_result(row: object) -> tuple[str, str | None]:
    """Geef (custom_id, content|None) uit één OpenAI-batch-resultaatregel."""
    if not isinstance(row, dict):
        return "", None
    custom_id = row.get("custom_id")
    if not isinstance(custom_id, str) or not custom_id.strip():
        return "", None
    if row.get("error") is not None:
        return custom_id, None
    response = row.get("response")
    if not isinstance(response, dict):
        return custom_id, None
    body = response.get("body")
    if not isinstance(body, dict):
        return custom_id, None
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return custom_id, None
    message = choices[0].get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        return custom_id, None
    return custom_id, content


def strip_json_fencing(text: str) -> str:
    """Tolerante lezer: teachers geven soms markdown-fences om JSON heen."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return match.group(0) if match else text


def normalize_vraag(vraag: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", vraag.lower()).strip()


def ngramen(tekst: str) -> set[tuple[str, ...]]:
    woorden = tuple(normalize_vraag(tekst).split())
    return {woorden[i : i + NGRAM_SIZE] for i in range(len(woorden) - NGRAM_SIZE + 1)}


def eval_ngramen(path: Path | None) -> set[tuple[str, ...]]:
    """n-grammen van de evalvragen; zonder bestand is de check leeg."""
    if path is None or not path.is_file():
        return set()
    gramen: set[tuple[str, ...]] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            row: object = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and isinstance(row.get("vraag"), str):
            gramen |= ngramen(row["vraag"])
    return gramen


def request_id(fragment: Fragment, index: int, negatief: bool) -> str:
    """custom_id waarmee request-regels en resultaten koppelen."""
    return f"{fragment.id}:slot{index}:{'neg' if negatief else 'pos'}"


def verify_kandidaat(
    raw: str,
    fragment: Fragment,
    verwachte_negatief: bool,
    gezien_vragen: set[str],
    eval_gramen: set[tuple[str, ...]],
) -> tuple[dict[str, Any] | None, str | None]:
    """Keur één teacher-antwoord; geef (rij|None, reden|None)."""
    try:
        kandidaat: object = json.loads(strip_json_fencing(raw))
    except json.JSONDecodeError:
        return None, "teacher gaf geen geldige JSON"
    if not isinstance(kandidaat, dict):
        return None, "kandidaat is geen object"
    if set(kandidaat) != {"vraag", "negatief", "antwoord"}:
        return None, "kandidaat heeft niet precies vraag/negatief/antwoord"
    if not isinstance(kandidaat["vraag"], str) or not kandidaat["vraag"].strip():
        return None, "vraag is leeg"
    if not isinstance(kandidaat["negatief"], bool):
        return None, "negatief is geen boolean"
    if kandidaat["negatief"] != verwachte_negatief:
        return None, "teacher volgde de negatief-instructie niet"

    normaal = normalize_vraag(kandidaat["vraag"])
    if normaal in gezien_vragen:
        return None, "dubbele vraag"
    if eval_gramen:
        gram = ngramen(kandidaat["vraag"])
        if gram and (gram & eval_gramen):
            return None, "n-gram-overlap met de evalset"

    antwoord = kandidaat["antwoord"]
    if not isinstance(antwoord, dict):
        return None, "antwoord is geen object"
    bron_label = fragment.bron_label
    for punt in antwoord.get("punten", []):
        if isinstance(punt, dict):
            cited = set(punt.get("bron_ids", []))
            if not cited <= {bron_label}:
                return None, f"citeert onbekende bronnen: {sorted(cited - {bron_label})}"
    if antwoord.get("peildatum") != fragment.peildatum:
        return None, f"peildatum {antwoord.get('peildatum')!r} past niet bij de bron"

    rij = build_row(kandidaat, fragment, rij_id=f"{fragment.id}:kandidaat")
    structurele_fouten = validate_row(rij)
    if structurele_fouten:
        return None, "verifier: " + "; ".join(structurele_fouten)

    gezien_vragen.add(normaal)
    return rij, None


def build_row(kandidaat: dict[str, Any], fragment: Fragment, rij_id: str) -> dict[str, Any]:
    negatief = bool(kandidaat.get("negatief", False))
    return {
        "id": rij_id,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Antwoord alleen met JSON volgens het schema. Gebruik "
                    "uitsluitend de BRONNEN. Staat het antwoord er niet in, "
                    "zet status op onzeker."
                ),
            },
            {
                "role": "user",
                "content": (f"{kandidaat['vraag'].strip()}\n\nBRONNEN:\n{fragment.blok}\n"),
            },
            {
                "role": "assistant",
                "content": json.dumps(kandidaat["antwoord"], ensure_ascii=False),
            },
        ],
        "metadata": {
            "source_uris": [fragment.bron_uri],
            "license": fragment.licentie,
            "negative": negatief,
            "reviewed": False,
            "peildatum": fragment.peildatum,
            "bron_status": fragment.status,
            "documentsoort": fragment.documentsoort,
        },
    }


def run_pipeline(
    fragmenten: list[Fragment],
    content_per_request: dict[str, str],
    *,
    per_fragment: int,
    deel_negatief: float,
    eval_gramen: set[tuple[str, ...]],
    seen_vragen: set[str] | None = None,
) -> tuple[list[dict[str, Any]], GenerationStats, set[str]]:
    """Verwerk alle kandidaten: verificatie en boekhouding, geen netwerk.

    Geeft (rijen, statistieken, gezien_vragen) terug, zodat een volgende
    batch dezelfde deduplicatie voortzet.
    """
    stats = GenerationStats()
    stats.kandidaten = 0
    stats.overlap_gecontroleerd = bool(eval_gramen)
    rows: list[dict[str, Any]] = []
    if seen_vragen is None:
        seen_vragen = set()
    negatief_slots = round(per_fragment * deel_negatief)

    for fragment in fragmenten:
        for index in range(per_fragment):
            negatief = index < negatief_slots
            custom_id = request_id(fragment, index, negatief)
            content = content_per_request.get(custom_id)
            stats.kandidaten += 1
            if content is None:
                stats.afwijzing("geen teacher-antwoord")
                continue
            rij, reden = verify_kandidaat(content, fragment, negatief, seen_vragen, eval_gramen)
            if rij is None or reden is not None:
                if reden is not None:
                    stats.afwijzing(reden)
                continue
            rij["id"] = f"{fragment.id}:{index}"
            if rij["metadata"]["negative"]:
                stats.negatief_geaccepteerd += 1
            rows.append(rij)
            stats.geaccepteerd += 1
    return rows, stats, seen_vragen


def all_requests(
    fragmenten: list[Fragment], *, per_fragment: int, deel_negatief: float, model: str
) -> list[dict[str, Any]]:
    """Bouw alle batch-requestregels; het negatiefaandeel is slot-gebaseerd."""
    negatief_slots = round(per_fragment * deel_negatief)
    regels: list[dict[str, Any]] = []
    for fragment in fragmenten:
        for index in range(per_fragment):
            negatief = index < negatief_slots
            slot = SLOTS[index % len(SLOTS)]
            messages = messages_voor(fragment, slot, negatief)
            regels.append(batch_request_row(request_id(fragment, index, negatief), messages, model))
    return regels


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def render_stats(stats: GenerationStats) -> str:
    negatief = (
        f"{stats.negatiefaandeel_pct}%" if stats.negatiefaandeel_pct is not None else "niet gemeten"
    )
    overlap = "uitgevoerd" if stats.overlap_gecontroleerd else "overgeslagen (evalset afwezig)"
    regels = [
        f"kandidaten: {stats.kandidaten}",
        f"geaccepteerd: {stats.geaccepteerd} (negatief: {negatief})",
        f"n-gram-overlap-check: {overlap}",
        "afwijzingen:",
    ]
    if stats.afgewezen:
        regels.extend(f"- {reden}: {aantal}" for reden, aantal in stats.afgewezen.most_common())
    else:
        regels.append("- geen")
    return "\n".join(regels) + "\n"


def render_data_card(
    *,
    fragmenten: list[Fragment],
    sources_path: Path,
    sources_sha256: str,
    teacher_model: str,
    per_fragment: int,
    deel_negatief: float,
    eval_path: Path | None,
    stats: GenerationStats,
    when: datetime,
    review_pad: Path,
) -> str:
    bronrijen = "\n".join(
        f"| {fragment.id} | {fragment.documentsoort} | {fragment.status} | "
        f"{fragment.peildatum} | {fragment.licentie} | {fragment.bron_uri} |"
        for fragment in fragmenten
    )
    overlap = (
        f"8-gram-overlap tegen `{eval_path}` uitgevoerd"
        if stats.overlap_gecontroleerd
        else (
            "overgeslagen: er was geen evalset; herhaal de generatie zodra "
            "`eval/data/v0.jsonl` er is"
        )
    )
    return f"""# DATA_CARD (concept)

**Status: CONCEPT {when.date().isoformat()}.** Geen enkele rij in het draftbestand is
goedgekeurd. Verwijder dit kopje pas na menselijke review: minimaal een
steekproef van 100 voorbeelden (issue #34) en het bewust weglaten van
afgekeurde rijen. Het draftbestand heet bewust niet `sft.jsonl`.

## Doel

Gedragstraining op het Wetvia-antwoord: AnswerV1-structuur, abstentie
(`onzeker` bij ontbrekende bron), consistent citatieformaat en begrijpelijk
Nederlands (B1). Geen actuele juridische feiten in de gewichten; wetgeving en
voorstellen blijven uit retrieval en de regels-engine komen (docs/02 §7).
Tweede Kamerfragmenten zijn voorstellen en worden nooit als geldend recht
getraind.

## Bronnen en rechten

Bronbestand: `{sources_path}` (sha256 `{sources_sha256[:16]}…`).

| fragment | documentsoort | status | peildatum | licentie | bron-uri |
|---|---|---|---|---|---|
{bronrijen}

## Generatie

- Teacher-model: `{teacher_model}`.
- Slots per fragment: {per_fragment}; doel negatiefaandeel: {deel_negatief:.0%}
  (slotgedreven: de eerste {round(per_fragment * deel_negatief)} slot(s) per
  fragment zijn negatief).
- Chat-template: rijen zijn message-lijsten (system/user/assistant); de trainer
  past `apply_chat_template` toe met exact het Qwen3.5-template dat bij
  inferentie gebruikt wordt (docs/02 §7).
- System-prompt (letterlijk):

    ```
    {SYSTEM_PROMPT}
    ```

- Taaksjablonen per slot: {"; ".join(f"`{slot}` = {_SLOT_INSTRUCTIE[slot]}" for slot in SLOTS)}.

## Filters

1. Verifier: AnswerV1-structuur en negatieveregel via `training/answer_v1.py`
   (`validate_row`); citeert alleen bekende bron-ID's; peildatum moet bij de bron passen.
2. Deduplicatie: genormaliseerde vraag (kleine letters, alleen a-z0-9 en spatie).
3. n-gram-overlap: {overlap}.

## Aantallen

```
{render_stats(stats).rstrip()}
```

## Bekende beperkingen (invullen: Luca)

- TODO

## Review (invullen: Luca)

- Steekproefbestand: `{review_pad}`
- TODO: notities per gecontroleerd voorbeeld en de definitieve go/no-go.
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("requests", "direct", "ingest"), default="requests")
    parser.add_argument("--sources", type=Path, default=Path("training/data/bronnen.jsonl"))
    parser.add_argument("--batch-results", type=Path, help="OpenAI-batchresultaat (mode ingest)")
    parser.add_argument("--teacher-model", default="Qwen/Qwen3.8-27B")
    parser.add_argument(
        "--teacher-url", default="http://127.0.0.1:11434/v1", help="OpenAI-compat endpoint"
    )
    parser.add_argument(
        "--api-key-env",
        default=None,
        help="naam van de omgevingsvariabele met de API-sleutel (alleen mode direct)",
    )
    parser.add_argument("--questions-per-fragment", type=int, default=4)
    parser.add_argument("--share-negative", type=float, default=0.3)
    parser.add_argument("--eval-set", type=Path, default=Path("eval/data/v0.jsonl"))
    parser.add_argument("--out-dir", type=Path, default=Path("training/data"))
    parser.add_argument("--review-sample", type=int, default=100)
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args(argv)

    try:
        fragmenten = load_fragmenten(args.sources)
    except SourceError as exc:
        print(f"Fout: {exc}", file=sys.stderr)
        return 2
    if args.questions_per_fragment < 1:
        print("Fout: --questions-per-fragment moet minstens 1 zijn", file=sys.stderr)
        return 2
    if not 0 <= args.share_negative <= 1:
        print("Fout: --share-negative moet tussen 0 en 1 liggen", file=sys.stderr)
        return 2

    regels = all_requests(
        fragmenten,
        per_fragment=args.questions_per_fragment,
        deel_negatief=args.share_negative,
        model=args.teacher_model,
    )

    if args.mode == "requests":
        requests_pad = args.out_dir / "sft-batch-requests.jsonl"
        write_jsonl(requests_pad, regels)
        print(
            f"{len(regels)} batch-requestregels in {requests_pad}; "
            "upload naar de batch-API en verwerk met --mode ingest."
        )
        return 0

    content_per_request: dict[str, str] = {}
    if args.mode == "direct":
        api_key = os.environ.get(args.api_key_env) if args.api_key_env else None
        for regel in regels:
            try:
                content = teacher_call(
                    regel["body"]["messages"],  # type: ignore[index]
                    args.teacher_model,
                    args.teacher_url,
                    api_key,
                )
            except (httpx.HTTPError, ValueError) as exc:
                print(f"Skip {regel['custom_id']}: {exc}", file=sys.stderr)  # type: ignore[index]
                continue
            content_per_request[str(regel["custom_id"])] = content  # type: ignore[index]
    else:
        if args.batch_results is None:
            print("Fout: --mode ingest vereist --batch-results", file=sys.stderr)
            return 2
        if not args.batch_results.is_file():
            print(f"Fout: resultaatbestand bestaat niet: {args.batch_results}", file=sys.stderr)
            return 2
        for raw_line in args.batch_results.read_text(encoding="utf-8").splitlines():
            if not raw_line.strip():
                continue
            try:
                row: object = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            custom_id, content = parse_batch_result(row)
            if custom_id and content is not None:
                content_per_request[custom_id] = content

    eval_gramen = eval_ngramen(args.eval_set)
    rows, stats, _ = run_pipeline(
        fragmenten,
        content_per_request,
        per_fragment=args.questions_per_fragment,
        deel_negatief=args.share_negative,
        eval_gramen=eval_gramen,
    )

    now = datetime.now(UTC)
    stamp = now.strftime("%Y%m%d-%H%M%S")
    draft_pad = args.out_dir / f"sft-concept-{stamp}.jsonl"
    write_jsonl(draft_pad, rows)

    sources_sha = hashlib.sha256(args.sources.read_bytes()).hexdigest()
    sample_n = min(args.review_sample, len(rows))
    sample = random.Random(args.seed).sample(rows, sample_n) if sample_n else []
    review_pad = args.out_dir / f"review-steekproef-{stamp}.jsonl"
    write_jsonl(review_pad, sample)

    card_pad = args.out_dir / f"DATA_CARD-concept-{stamp}.md"
    card_pad.write_text(
        render_data_card(
            fragmenten=fragmenten,
            sources_path=args.sources,
            sources_sha256=sources_sha,
            teacher_model=args.teacher_model,
            per_fragment=args.questions_per_fragment,
            deel_negatief=args.share_negative,
            eval_path=args.eval_set,
            stats=stats,
            when=now,
            review_pad=review_pad,
        ),
        encoding="utf-8",
    )

    print(render_stats(stats))
    print(f"Conceptdraft: {draft_pad}")
    print(f"Reviewsteekproef ({len(sample)}): {review_pad}")
    print(f"Data card (concept): {card_pad}")
    if not rows:
        print("Niets geaccepteerd; kijk naar de afwijzingsredenen hierboven.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (SourceError, ValueError) as exc:
        print(f"Fout: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
