"""BWB search and validity metadata from the official SRU endpoint."""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime
from importlib.metadata import PackageNotFoundError, version
from types import TracebackType
from typing import Literal
from xml.etree import ElementTree

import httpx

SRU_URL = "https://zoekservice.overheid.nl/sru/Search"
SRU_CONNECTION = "BWB"
_BWB_REPOSITORY_HOST = "repository.officiele-overheidspublicaties.nl"
_SRU_NAMESPACE = "http://docs.oasis-open.org/ns/search-ws/sruResponse"
_SRU_DIAGNOSTIC_NAMESPACE = "http://docs.oasis-open.org/ns/search-ws/diagnostic"
_GZD_NAMESPACE = "http://standaarden.overheid.nl/sru"
_DCTERMS_NAMESPACE = "http://purl.org/dc/terms/"
_BWB_NAMESPACE = "http://standaarden.overheid.nl/bwb/terms/"
_DEFAULT_PAGE_SIZE = 100
_DEFAULT_TIMEOUT_SECONDS = 20.0
_DEFAULT_MAX_ATTEMPTS = 3
_DEFAULT_BACKOFF_SECONDS = 0.25
_BWB_ID_PATTERN = re.compile(r"BWBR\d+\Z")

try:
    _VERSION = version("nl-wetten-ingest")
except PackageNotFoundError:
    _VERSION = "0.0.0"

USER_AGENT = f"wetvia-ai/{_VERSION} (+https://github.com/lucasabella/wetvia-ai)"


class SRUError(RuntimeError):
    """An SRU response could not be retrieved or interpreted."""


class SRUProtocolError(SRUError):
    """The SRU endpoint returned an invalid or incomplete response."""


class ToestandDownloadError(RuntimeError):
    """An official BWB Toestand XML document could not be downloaded."""


class SRUDiagnosticError(SRUError):
    """The SRU service returned a diagnostic instead of search results."""

    def __init__(self, diagnostics: tuple[tuple[str | None, str | None, str | None], ...]) -> None:
        self.diagnostics = diagnostics
        self.uri, self.details, self.diagnostic_message = diagnostics[0]
        summaries = []
        for uri, details, message in diagnostics:
            parts = [
                part for part in (uri, message, f"details: {details}" if details else None) if part
            ]
            summaries.append("; ".join(parts) or "unspecified diagnostic")
        super().__init__("SRU diagnostic: " + " | ".join(summaries))


@dataclass(frozen=True, slots=True)
class Toestand:
    """One BWB version and its official validity metadata."""

    bwb_id: str
    titel: str
    geldig_vanaf: date
    geldig_tot: date | None
    toestand_url: str
    modified: date


ToestandStatus = Literal["geldend", "toekomstig", "vervallen"]


def classify(toestand: Toestand, peildatum: date) -> ToestandStatus:
    """Classify a BWB version for an inclusive validity date range."""
    if peildatum < toestand.geldig_vanaf:
        return "toekomstig"
    if toestand.geldig_tot is not None and peildatum > toestand.geldig_tot:
        return "vervallen"
    return "geldend"


def select_toestand(toestanden: Iterable[Toestand], peildatum: date) -> Toestand:
    """Return the unique version valid on ``peildatum``.

    An empty or overlapping result is treated as an explicit data error so a
    caller never silently chooses a version that was not uniquely applicable.
    """
    geldende = [toestand for toestand in toestanden if classify(toestand, peildatum) == "geldend"]
    if len(geldende) == 1:
        return geldende[0]
    if not geldende:
        raise ValueError(f"geen geldende toestand gevonden voor {peildatum.isoformat()}")
    raise ValueError(f"meerdere geldende toestanden gevonden voor {peildatum.isoformat()}")


class BwbSRUClient:
    """Synchronous client for BWB version metadata in the official SRU service."""

    def __init__(
        self,
        *,
        base_url: str = SRU_URL,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        maximum_records: int = _DEFAULT_PAGE_SIZE,
        max_attempts: int = _DEFAULT_MAX_ATTEMPTS,
        backoff_seconds: float = _DEFAULT_BACKOFF_SECONDS,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if maximum_records <= 0:
            raise ValueError("maximum_records must be positive")
        if max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        if backoff_seconds < 0:
            raise ValueError("backoff_seconds cannot be negative")

        self._base_url = base_url
        self._maximum_records = maximum_records
        self._max_attempts = max_attempts
        self._backoff_seconds = backoff_seconds
        self._sleep = sleep
        self._http = httpx.Client(
            headers={"Accept": "application/xml", "User-Agent": USER_AGENT},
            timeout=timeout_seconds,
            transport=transport,
        )

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._http.close()

    def __enter__(self) -> BwbSRUClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def search_toestanden(self, bwb_id: str) -> list[Toestand]:
        """Fetch all versions for one BWB identifier, following SRU pages."""
        if not _BWB_ID_PATTERN.fullmatch(bwb_id):
            raise ValueError(f"ongeldig BWB-ID: {bwb_id!r}")
        return self._search(f"dcterms.identifier=={bwb_id}", expected_bwb_id=bwb_id)

    def changed_since(self, datum: date | str) -> list[Toestand]:
        """Fetch all BWB versions whose official ``dcterms:modified`` is recent."""
        since = _parse_input_date(datum)
        return self._search(f"dcterms.modified>={since.isoformat()}")

    def fetch_toestand_xml(self, toestand: Toestand) -> bytes:
        """Download an official XML document for one validated BWB ``Toestand``."""
        url = httpx.URL(toestand.toestand_url)
        expected_path = f"/bwb/{toestand.bwb_id}/"
        if (
            not _BWB_ID_PATTERN.fullmatch(toestand.bwb_id)
            or url.scheme != "https"
            or url.host != _BWB_REPOSITORY_HOST
            or url.port not in (None, 443)
            or bool(url.username)
            or bool(url.password)
            or not url.path.startswith(expected_path)
            or not url.path.endswith(".xml")
        ):
            raise ValueError("Toestand URL is not an official BWB XML URL")

        for attempt in range(1, self._max_attempts + 1):
            try:
                response = self._http.get(toestand.toestand_url)
            except httpx.TransportError as exc:
                if attempt == self._max_attempts:
                    raise ToestandDownloadError(
                        "BWB Toestand XML download failed after retries"
                    ) from exc
                self._sleep(self._backoff_seconds * (2.0 ** (attempt - 1)))
                continue

            if response.status_code in {408, 429} or response.status_code >= 500:
                if attempt == self._max_attempts:
                    response.raise_for_status()
                self._sleep(self._retry_delay(response, attempt))
                continue

            response.raise_for_status()
            if not response.content:
                raise ToestandDownloadError("BWB Toestand XML download returned an empty body")
            return response.content

        raise AssertionError("unreachable retry loop")

    def _search(self, query: str, *, expected_bwb_id: str | None = None) -> list[Toestand]:
        results: list[Toestand] = []
        start_record = 1
        visited_positions: set[int] = set()
        expected_total: int | None = None

        while True:
            response = self._get_page(query, start_record)
            page, record_positions, next_record_position, total_records = _parse_sru_page(
                response.content
            )
            if expected_total is None:
                expected_total = total_records
            elif total_records != expected_total:
                raise SRUProtocolError(
                    "SRU numberOfRecords veranderde tijdens paginering "
                    f"({expected_total} naar {total_records})"
                )

            expected_positions = tuple(range(start_record, start_record + len(page)))
            if record_positions != expected_positions:
                raise SRUProtocolError(
                    "SRU recordPosition-waarden sluiten niet aaneengesloten aan op startRecord"
                )

            if expected_bwb_id is not None:
                unexpected = [item.bwb_id for item in page if item.bwb_id != expected_bwb_id]
                if unexpected:
                    raise SRUProtocolError(
                        f"SRU-query voor {expected_bwb_id} bevat onverwachte BWB-ID's: "
                        f"{', '.join(unexpected)}"
                    )
            results.extend(page)

            if next_record_position is None:
                last_record = start_record + len(page) - 1
                if last_record < total_records:
                    raise SRUProtocolError(
                        "SRU-response mist nextRecordPosition voor volgende pagina"
                    )
                if last_record > total_records:
                    raise SRUProtocolError("SRU-response bevat records voorbij numberOfRecords")
                break
            if next_record_position <= start_record or next_record_position in visited_positions:
                raise SRUProtocolError("SRU-pagination gaf geen vooruitgang")
            expected_next = start_record + len(page)
            if next_record_position != expected_next:
                raise SRUProtocolError(
                    "SRU nextRecordPosition slaat recordposities over of overlapt een pagina"
                )
            if next_record_position > total_records:
                raise SRUProtocolError("SRU nextRecordPosition ligt voorbij numberOfRecords")
            visited_positions.add(next_record_position)
            start_record = next_record_position

        return results

    def _get_page(self, query: str, start_record: int) -> httpx.Response:
        params = {
            "operation": "searchRetrieve",
            "version": "2.0",
            "x-connection": SRU_CONNECTION,
            "query": query,
            "startRecord": str(start_record),
            "maximumRecords": str(self._maximum_records),
        }

        for attempt in range(1, self._max_attempts + 1):
            try:
                response = self._http.get(self._base_url, params=params)
            except httpx.TransportError as exc:
                if attempt == self._max_attempts:
                    raise SRUError("SRU-verbinding mislukt na retries") from exc
                self._sleep(self._backoff_seconds * (2.0 ** (attempt - 1)))
                continue

            if response.status_code in {408, 429} or response.status_code >= 500:
                if attempt == self._max_attempts:
                    response.raise_for_status()
                self._sleep(self._retry_delay(response, attempt))
                continue

            response.raise_for_status()
            return response

        raise AssertionError("unreachable retry loop")

    def _retry_delay(self, response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after is not None:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                pass
        return self._backoff_seconds * (2.0 ** (attempt - 1))


def search_toestanden(bwb_id: str) -> list[Toestand]:
    """Convenience function to fetch all versions for a BWB identifier."""
    with BwbSRUClient() as client:
        return client.search_toestanden(bwb_id)


def changed_since(datum: date | str) -> list[Toestand]:
    """Convenience function to fetch all versions modified since a date."""
    with BwbSRUClient() as client:
        return client.changed_since(datum)


def _parse_sru_page(content: bytes) -> tuple[list[Toestand], tuple[int, ...], int | None, int]:
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError as exc:
        raise SRUProtocolError("SRU-response is geen geldige XML") from exc

    diagnostic_elements = root.findall(f".//{_tag(_SRU_DIAGNOSTIC_NAMESPACE, 'diagnostic')}")
    if root.tag == _tag(_SRU_NAMESPACE, "diagnostics") or diagnostic_elements:
        if not diagnostic_elements:
            raise SRUError("SRU-response bevat diagnostics maar geen diagnostic-element")
        raise SRUDiagnosticError(
            tuple(
                (
                    _element_text(diagnostic, _tag(_SRU_DIAGNOSTIC_NAMESPACE, "uri")),
                    _element_text(diagnostic, _tag(_SRU_DIAGNOSTIC_NAMESPACE, "details")),
                    _element_text(diagnostic, _tag(_SRU_DIAGNOSTIC_NAMESPACE, "message")),
                )
                for diagnostic in diagnostic_elements
            )
        )

    total_text = _element_text(root, _tag(_SRU_NAMESPACE, "numberOfRecords"))
    if total_text is None:
        raise SRUProtocolError("SRU-response mist numberOfRecords")
    try:
        total_records = int(total_text)
    except ValueError as exc:
        raise SRUProtocolError("SRU numberOfRecords is geen integer") from exc
    if total_records < 0:
        raise SRUProtocolError("SRU numberOfRecords kan niet negatief zijn")

    records_element = root.find(_tag(_SRU_NAMESPACE, "records"))
    if records_element is None:
        if total_records == 0:
            return [], (), None, total_records
        raise SRUProtocolError("SRU-response mist records ondanks een positieve recordcount")

    record_elements = records_element.findall(_tag(_SRU_NAMESPACE, "record"))
    page = [_parse_record(record) for record in record_elements]
    positions = tuple(_parse_record_position(record) for record in record_elements)
    if total_records > 0 and not page:
        raise SRUProtocolError("SRU-response bevat geen records ondanks een positieve recordcount")

    next_text = _element_text(root, _tag(_SRU_NAMESPACE, "nextRecordPosition"))
    if next_text is None:
        return page, positions, None, total_records
    try:
        next_position = int(next_text)
    except ValueError as exc:
        raise SRUProtocolError("SRU nextRecordPosition is geen integer") from exc
    return page, positions, next_position, total_records


def _parse_record_position(record: ElementTree.Element) -> int:
    value = _element_text(record, _tag(_SRU_NAMESPACE, "recordPosition"))
    if value is None:
        raise SRUProtocolError("SRU-record mist recordPosition")
    try:
        position = int(value)
    except ValueError as exc:
        raise SRUProtocolError("SRU recordPosition is geen integer") from exc
    if position < 1:
        raise SRUProtocolError("SRU recordPosition moet positief zijn")
    return position


def _parse_record(record: ElementTree.Element) -> Toestand:
    record_data = record.find(f"{_tag(_SRU_NAMESPACE, 'recordData')}/{_tag(_GZD_NAMESPACE, 'gzd')}")
    if record_data is None:
        raise SRUProtocolError("SRU-record mist gzd recordData")
    original_data = record_data.find(_tag(_GZD_NAMESPACE, "originalData"))
    if original_data is None:
        raise SRUProtocolError("SRU-record mist originalData")
    metadata = original_data.find(_tag(_BWB_NAMESPACE, "meta"))
    if metadata is None:
        raise SRUProtocolError("SRU-record mist overheidbwb:meta")
    enriched_data = record_data.find(_tag(_GZD_NAMESPACE, "enrichedData"))
    if enriched_data is None:
        raise SRUProtocolError("SRU-record mist enrichedData")

    return Toestand(
        bwb_id=_required_text(
            metadata, _tag(_DCTERMS_NAMESPACE, "identifier"), "dcterms:identifier"
        ),
        titel=_required_text(metadata, _tag(_DCTERMS_NAMESPACE, "title"), "dcterms:title"),
        geldig_vanaf=_required_date(
            metadata,
            _tag(_BWB_NAMESPACE, "geldigheidsperiode_startdatum"),
            "overheidbwb:geldigheidsperiode_startdatum",
        ),
        geldig_tot=_optional_date(
            metadata,
            _tag(_BWB_NAMESPACE, "geldigheidsperiode_einddatum"),
            "overheidbwb:geldigheidsperiode_einddatum",
        ),
        toestand_url=_required_text(
            enriched_data,
            _tag(_BWB_NAMESPACE, "locatie_toestand"),
            "overheidbwb:locatie_toestand",
        ),
        modified=_required_date(metadata, _tag(_DCTERMS_NAMESPACE, "modified"), "dcterms:modified"),
    )


def _element_text(element: ElementTree.Element, tag: str) -> str | None:
    child = element.find(f".//{tag}")
    if child is None or child.text is None:
        return None
    text = child.text.strip()
    return text or None


def _required_text(element: ElementTree.Element, tag: str, field: str) -> str:
    value = _element_text(element, tag)
    if value is None:
        raise SRUProtocolError(f"SRU-record mist {field}")
    return value


def _required_date(element: ElementTree.Element, tag: str, field: str) -> date:
    value = _required_text(element, tag, field)
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SRUProtocolError(f"SRU-veld {field} bevat geen ISO-datum: {value!r}") from exc


def _optional_date(element: ElementTree.Element, tag: str, field: str) -> date | None:
    value = _element_text(element, tag)
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SRUProtocolError(f"SRU-veld {field} bevat geen ISO-datum: {value!r}") from exc


def _parse_input_date(value: date | str) -> date:
    if isinstance(value, datetime):
        raise ValueError("datum moet een kalenderdatum zijn, geen datetime")
    if isinstance(value, date):
        return value
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"datum moet YYYY-MM-DD zijn: {value!r}") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"datum moet YYYY-MM-DD zijn: {value!r}")
    return parsed


def _tag(namespace: str, name: str) -> str:
    return f"{{{namespace}}}{name}"
