"""Offline tests against saved official BWB SRU responses."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from xml.etree import ElementTree

import httpx
import pytest

from nl_wetten_ingest import (
    BwbSRUClient,
    SRUDiagnosticError,
    SRUProtocolError,
    Toestand,
    changed_since,
    classify,
    search_toestanden,
    select_toestand,
)
from nl_wetten_ingest.bwb import USER_AGENT

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(filename: str) -> bytes:
    return (FIXTURES / filename).read_bytes()


def _xml_response(request: httpx.Request, filename: str) -> httpx.Response:
    return httpx.Response(
        200,
        content=_fixture(filename),
        headers={"content-type": "application/xml"},
        request=request,
    )


def test_search_toestanden_parses_bbl_metadata_and_follows_pages() -> None:
    pages = {"1": "bbl-page-1.xml", "6": "bbl-page-2.xml", "11": "bbl-page-3.xml"}
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _xml_response(request, pages[request.url.params["startRecord"]])

    with BwbSRUClient(transport=httpx.MockTransport(respond), maximum_records=5) as client:
        toestanden = client.search_toestanden("BWBR0041297")

    assert len(toestanden) == 11
    assert [request.url.params["startRecord"] for request in requests] == ["1", "6", "11"]
    assert all(request.url.params["maximumRecords"] == "5" for request in requests)
    assert all(request.url.params["operation"] == "searchRetrieve" for request in requests)
    assert all(request.url.params["version"] == "2.0" for request in requests)
    assert all(request.url.params["x-connection"] == "BWB" for request in requests)
    assert all(
        request.url.params["query"] == "dcterms.identifier==BWBR0041297" for request in requests
    )
    assert all(request.headers["user-agent"] == USER_AGENT for request in requests)
    assert all(request.headers["accept"] == "application/xml" for request in requests)

    first = toestanden[0]
    assert first == Toestand(
        bwb_id="BWBR0041297",
        titel="Besluit bouwwerken leefomgeving",
        geldig_vanaf=date(2024, 1, 1),
        geldig_tot=date(2024, 6, 30),
        toestand_url=(
            "https://repository.officiele-overheidspublicaties.nl/bwb/BWBR0041297/"
            "2024-01-01_0/xml/BWBR0041297_2024-01-01_0.xml"
        ),
        modified=date(2026, 5, 12),
    )


def test_search_toestanden_parses_all_awb_fixture_pages() -> None:
    pages = {"1": "awb-page-1.xml", "101": "awb-page-2.xml", "201": "awb-page-3.xml"}
    starts: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        start_record = request.url.params["startRecord"]
        starts.append(start_record)
        return _xml_response(request, pages[start_record])

    with BwbSRUClient(transport=httpx.MockTransport(respond)) as client:
        toestanden = client.search_toestanden("BWBR0005537")

    assert len(toestanden) == 236
    assert len({toestand.toestand_url for toestand in toestanden}) == 236
    assert starts == ["1", "101", "201"]
    assert toestanden[0].bwb_id == "BWBR0005537"
    assert toestanden[0].titel == "Algemene wet bestuursrecht"
    assert toestanden[0].geldig_vanaf == date(2002, 4, 1)
    assert toestanden[0].geldig_tot == date(2002, 5, 7)
    assert toestanden[0].modified == date(2023, 2, 1)
    assert toestanden[-1].geldig_vanaf == date(2026, 8, 15)


def test_changed_since_sends_modified_filter_and_accepts_date() -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _xml_response(request, "changed-since-9999-12-31.xml")

    with BwbSRUClient(transport=httpx.MockTransport(respond)) as client:
        result = client.changed_since(date(9999, 12, 31))

    assert result == []
    assert requests[0].url.params["query"] == "dcterms.modified>=9999-12-31"
    assert requests[0].url.params["startRecord"] == "1"


def test_retry_uses_retry_after_and_exponential_backoff() -> None:
    requests: list[httpx.Request] = []
    delays: list[float] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(503, headers={"Retry-After": "0.7"}, request=request)
        if len(requests) == 2:
            return httpx.Response(500, request=request)
        return _xml_response(request, "changed-since-9999-12-31.xml")

    with BwbSRUClient(
        transport=httpx.MockTransport(respond),
        max_attempts=3,
        backoff_seconds=0.2,
        sleep=delays.append,
    ) as client:
        assert client.changed_since("9999-12-31") == []

    assert len(requests) == 3
    assert delays == [0.7, 0.4]


def test_retry_exhaustion_raises_after_all_server_errors() -> None:
    requests: list[httpx.Request] = []
    delays: list[float] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(503, request=request)

    with (
        BwbSRUClient(
            transport=httpx.MockTransport(respond),
            max_attempts=3,
            backoff_seconds=0.1,
            sleep=delays.append,
        ) as client,
        pytest.raises(httpx.HTTPStatusError, match="503"),
    ):
        client.changed_since("9999-12-31")

    assert len(requests) == 3
    assert delays == [0.1, 0.2]


def test_malformed_xml_raises_protocol_error() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<searchRetrieveResponse><records>", request=request)

    with (
        BwbSRUClient(transport=httpx.MockTransport(respond)) as client,
        pytest.raises(SRUProtocolError, match="geen geldige XML"),
    ):
        client.changed_since("9999-12-31")


def test_official_sru_diagnostic_is_exposed_clearly() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return _xml_response(request, "diagnostic-invalid-query.xml")

    with (
        BwbSRUClient(transport=httpx.MockTransport(respond)) as client,
        pytest.raises(SRUDiagnosticError, match="Unsupported index") as error,
    ):
        client.changed_since("9999-12-31")

    assert error.value.uri == "info:srw/diagnostic/1/16"
    assert error.value.details == "wetvia.invalidField"


def test_classify_and_select_use_inclusive_official_validity_dates() -> None:
    pages = {"1": "bbl-page-1.xml", "6": "bbl-page-2.xml", "11": "bbl-page-3.xml"}

    def respond(request: httpx.Request) -> httpx.Response:
        return _xml_response(request, pages[request.url.params["startRecord"]])

    with BwbSRUClient(transport=httpx.MockTransport(respond), maximum_records=5) as client:
        bbl = client.search_toestanden("BWBR0041297")

    first, second = bbl[:2]
    assert classify(first, date(2024, 6, 30)) == "geldend"
    assert classify(first, date(2024, 7, 1)) == "vervallen"
    assert classify(second, date(2024, 6, 30)) == "toekomstig"
    assert classify(second, date(2024, 7, 1)) == "geldend"
    assert select_toestand(bbl, date(2024, 6, 30)) == first
    assert select_toestand(bbl, date(2024, 7, 1)) == second
    assert select_toestand(bbl, date(2026, 10, 31)) == bbl[-1]
    with pytest.raises(ValueError, match="geen geldende toestand"):
        select_toestand(bbl, date(2023, 12, 31))
    with pytest.raises(ValueError, match="meerdere geldende toestanden"):
        select_toestand([first, first], date(2024, 6, 30))


def test_missing_geldig_tot_is_open_ended() -> None:
    # Derive a one-record parser case from the official Bbl fixture and omit only
    # the optional end-date element; no law metadata values are added or changed.
    root = ElementTree.fromstring(_fixture("bbl-page-1.xml"))
    sru = "{http://docs.oasis-open.org/ns/search-ws/sruResponse}"
    bwb = "{http://standaarden.overheid.nl/bwb/terms/}"
    records_element = root.find(f"{sru}records")
    assert records_element is not None
    records = records_element.findall(f"{sru}record")
    first = records[0]
    for record in records[1:]:
        records_element.remove(record)
    number_of_records = root.find(f"{sru}numberOfRecords")
    assert number_of_records is not None
    number_of_records.text = "1"
    next_position = root.find(f"{sru}nextRecordPosition")
    assert next_position is not None
    root.remove(next_position)
    end_date = next(
        element for element in first.iter() if element.tag == f"{bwb}geldigheidsperiode_einddatum"
    )
    parent = next(parent for parent in first.iter() if end_date in list(parent))
    parent.remove(end_date)
    content = ElementTree.tostring(root)

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=content, request=request)

    with BwbSRUClient(transport=httpx.MockTransport(respond)) as client:
        toestand = client.search_toestanden("BWBR0041297")[0]

    assert toestand.geldig_tot is None
    assert classify(toestand, date(9999, 12, 31)) == "geldend"


def test_search_rejects_invalid_identifier_before_request() -> None:
    def fail_if_called(_: httpx.Request) -> httpx.Response:
        raise AssertionError("invalid BWB-ID must not make an HTTP request")

    with (
        BwbSRUClient(transport=httpx.MockTransport(fail_if_called)) as client,
        pytest.raises(ValueError, match="ongeldig BWB-ID"),
    ):
        client.search_toestanden("BWBR0041297 OR dcterms.identifier==*")


def test_invalid_pagination_is_reported() -> None:
    content = _fixture("bbl-page-1.xml").replace(
        b"<nextRecordPosition>6</nextRecordPosition>",
        b"<nextRecordPosition>1</nextRecordPosition>",
    )

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=content, request=request)

    with (
        BwbSRUClient(transport=httpx.MockTransport(respond), maximum_records=5) as client,
        pytest.raises(SRUProtocolError, match="geen vooruitgang"),
    ):
        client.search_toestanden("BWBR0041297")


def test_missing_pagination_marker_does_not_return_a_partial_result() -> None:
    content = _fixture("bbl-page-1.xml").replace(b"<nextRecordPosition>6</nextRecordPosition>", b"")

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=content, request=request)

    with (
        BwbSRUClient(transport=httpx.MockTransport(respond), maximum_records=5) as client,
        pytest.raises(SRUProtocolError, match="mist nextRecordPosition"),
    ):
        client.search_toestanden("BWBR0041297")


def test_public_convenience_functions_are_exported() -> None:
    # This check is intentionally offline; the network-backed wrappers are exercised
    # through BwbSRUClient with MockTransport above.
    assert callable(search_toestanden)
    assert callable(changed_since)
