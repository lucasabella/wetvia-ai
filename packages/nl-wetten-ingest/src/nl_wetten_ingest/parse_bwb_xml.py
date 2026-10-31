"""Stream official BWB toestand XML into article and member chunks."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from io import BytesIO
from typing import Literal

from lxml import etree

from nl_wetten_ingest.bwb import Toestand

_HIERARCHY_TAGS = {
    "boek",
    "deel",
    "titel",
    "titeldeel",
    "hoofdstuk",
    "afdeling",
    "subafdeling",
    "paragraaf",
    "subparagraaf",
    "bijlage",
}
_BLOCK_TAGS = {"al", "lid", "lijst", "table"}
_IGNORED_TAGS = {"kop", "meta-data"}
_ARTICLE_LABEL = re.compile(r"^Artikel\s+(.+?)\s*$", re.IGNORECASE)
_ARTICLE_NUMBER = re.compile(r"[\w:.-]+\Z")
_REPEALED_MARKER = re.compile(r"\[\s*vervallen\s+per\b", re.IGNORECASE)


class BWBXMLParseError(ValueError):
    """The official BWB XML is malformed or does not match its metadata."""


ChunkStatus = Literal["geldend", "vervallen"]


@dataclass(frozen=True, slots=True)
class Chunk:
    """A legal text unit with its BWB and toestand provenance."""

    bwb_id: str
    regeling_titel: str
    artikel: str
    lid: str | None
    onderdeel: str | None
    opschrift: str | None
    kop_pad: str
    tekst: str
    geldig_vanaf: date
    geldig_tot: date | None
    bron_url: str
    toestand_url: str
    status: ChunkStatus


@dataclass(frozen=True, slots=True)
class _Heading:
    tag: str
    text: str


def parse(xml_bytes: bytes, toestand: Toestand, *, max_chars: int = 4000) -> list[Chunk]:
    """Parse BWB XML into article chunks without building a document tree.

    ``max_chars`` is a structural split threshold. Long articles are split at
    lid or list-item boundaries; an indivisible legal unit is never cut mid-text.
    """
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if not xml_bytes:
        raise BWBXMLParseError("BWB XML is empty")

    chunks: list[Chunk] = []
    element_stack: list[etree._Element] = []
    heading_stack: list[_Heading] = []
    root_seen = False

    try:
        context = etree.iterparse(
            BytesIO(xml_bytes),
            events=("start", "end"),
            resolve_entities=False,
            load_dtd=False,
            no_network=True,
            huge_tree=False,
            recover=False,
            remove_comments=True,
        )
        for event, element in context:
            name = _local_name(element)
            if event == "start":
                is_hierarchy_element = name in _HIERARCHY_TAGS and (
                    not element_stack or _local_name(element_stack[-1]) != "kop"
                )
                element_stack.append(element)
                if len(element_stack) == 1:
                    root_seen = True
                    if name != "toestand":
                        raise BWBXMLParseError("BWB XML root must be toestand")
                    root_bwb_id = element.get("bwb-id", "")
                    root_reference = element.get("bwb-ng-vast-deel", "")
                    if root_bwb_id and root_bwb_id != toestand.bwb_id:
                        raise BWBXMLParseError(
                            f"XML BWB-ID does not match metadata {toestand.bwb_id}"
                        )
                    if root_reference and f"/{toestand.bwb_id}/" not in root_reference:
                        raise BWBXMLParseError(
                            f"XML BWB-ID does not match metadata {toestand.bwb_id}"
                        )
                if is_hierarchy_element:
                    heading_stack.append(_Heading(name, element.get("label", "")))
                continue

            is_hierarchy_element = name in _HIERARCHY_TAGS and (
                len(element_stack) < 2 or _local_name(element_stack[-2]) != "kop"
            )
            if name == "kop" and len(element_stack) > 1:
                parent = element_stack[-2]
                if _local_name(parent) in _HIERARCHY_TAGS and heading_stack:
                    heading_stack[-1] = _Heading(
                        _local_name(parent), _heading_text(parent, element)
                    )
            elif name == "artikel":
                chunks.extend(_parse_article(element, tuple(heading_stack), toestand, max_chars))
                _clear_processed(element)
            elif is_hierarchy_element:
                if heading_stack:
                    heading_stack.pop()
                _clear_processed(element)

            element_stack.pop()
    except etree.XMLSyntaxError as exc:
        raise BWBXMLParseError(f"BWB XML is malformed: {exc}") from exc

    if not root_seen:
        raise BWBXMLParseError("BWB XML has no root element")
    return chunks


def _parse_article(
    article: etree._Element,
    headings: tuple[_Heading, ...],
    toestand: Toestand,
    max_chars: int,
) -> list[Chunk]:
    label = article.get("label", "")
    match = _ARTICLE_LABEL.fullmatch(label)
    if match is None:
        return []
    article_number = match.group(1).strip()
    if not _ARTICLE_NUMBER.fullmatch(article_number):
        raise BWBXMLParseError(f"Unsupported BWB article label: {label!r}")

    kop = article.find("kop")
    opschrift_node = kop.find("titel") if kop is not None else None
    opschrift = (
        _normalise_inline(_inline_text(opschrift_node)) if opschrift_node is not None else None
    )
    if not opschrift:
        opschrift = None
    kop_pad = " > ".join(heading.text for heading in headings if heading.text)
    status = _article_status(article)
    body_nodes = [child for child in article if _local_name(child) not in _IGNORED_TAGS]
    full_text = _render_blocks(body_nodes)
    if not full_text:
        return []

    if len(full_text) <= max_chars:
        return [
            _make_chunk(
                toestand,
                article_number,
                None,
                None,
                opschrift,
                kop_pad,
                full_text,
                status,
            )
        ]

    lids = [node for node in body_nodes if _local_name(node) == "lid"]
    if lids:
        first_lid_index = next(
            index for index, node in enumerate(body_nodes) if _local_name(node) == "lid"
        )
        prefix = _render_blocks(body_nodes[:first_lid_index])
        chunks: list[Chunk] = []
        current_prefix = prefix
        for node in body_nodes[first_lid_index:]:
            name = _local_name(node)
            if name == "lid":
                chunks.extend(
                    _split_lid(
                        node,
                        current_prefix,
                        article_number,
                        toestand,
                        opschrift,
                        kop_pad,
                        status,
                        max_chars,
                    )
                )
            elif name == "lijst":
                chunks.extend(
                    _split_list(
                        node,
                        current_prefix,
                        None,
                        None,
                        article_number,
                        toestand,
                        opschrift,
                        kop_pad,
                        status,
                        max_chars,
                    )
                )
            elif rendered := _render_block(node):
                chunks.append(
                    _make_chunk(
                        toestand,
                        article_number,
                        None,
                        None,
                        opschrift,
                        kop_pad,
                        _join_text(current_prefix, rendered),
                        status,
                    )
                )
                current_prefix = _join_text(current_prefix, rendered)
        return chunks

    lists = [node for node in body_nodes if _local_name(node) == "lijst"]
    if lists:
        first_list_index = next(
            index for index, node in enumerate(body_nodes) if _local_name(node) == "lijst"
        )
        prefix = _render_blocks(body_nodes[:first_list_index])
        chunks = []
        current_prefix = prefix
        for node in body_nodes[first_list_index:]:
            if _local_name(node) == "lijst":
                chunks.extend(
                    _split_list(
                        node,
                        current_prefix,
                        None,
                        None,
                        article_number,
                        toestand,
                        opschrift,
                        kop_pad,
                        status,
                        max_chars,
                    )
                )
            elif rendered := _render_block(node):
                chunks.append(
                    _make_chunk(
                        toestand,
                        article_number,
                        None,
                        None,
                        opschrift,
                        kop_pad,
                        _join_text(current_prefix, rendered),
                        status,
                    )
                )
                current_prefix = _join_text(current_prefix, rendered)
        return chunks

    # Articles without lids or lists may still have independent paragraph or
    # table blocks. Keep those blocks intact instead of cutting their text.
    return [
        _make_chunk(
            toestand,
            article_number,
            None,
            None,
            opschrift,
            kop_pad,
            rendered,
            status,
        )
        for node in body_nodes
        if (rendered := _render_block(node))
    ]


def _split_lid(
    lid_node: etree._Element,
    prefix: str,
    article_number: str,
    toestand: Toestand,
    opschrift: str | None,
    kop_pad: str,
    status: ChunkStatus,
    max_chars: int,
) -> list[Chunk]:
    lid_number = _normalise_inline(_text_child(lid_node, "lidnr")) or None
    lid_text = _render_block(lid_node)
    text = _join_text(prefix, lid_text)
    if len(text) <= max_chars:
        return [
            _make_chunk(
                toestand,
                article_number,
                lid_number,
                None,
                opschrift,
                kop_pad,
                text,
                status,
            )
        ]

    child_nodes = [child for child in lid_node if _local_name(child) not in {"lidnr", "meta-data"}]
    lists = [child for child in child_nodes if _local_name(child) == "lijst"]
    if not lists:
        return [
            _make_chunk(
                toestand,
                article_number,
                lid_number,
                None,
                opschrift,
                kop_pad,
                text,
                status,
            )
        ]

    first_list_index = next(
        index for index, child in enumerate(child_nodes) if _local_name(child) == "lijst"
    )
    lead_in = _render_lid_prefix(child_nodes[:first_list_index], lid_number)
    nested_prefix = _join_text(prefix, lead_in)
    chunks: list[Chunk] = []
    current_prefix = nested_prefix
    for child in child_nodes[first_list_index:]:
        if _local_name(child) == "lijst":
            chunks.extend(
                _split_list(
                    child,
                    current_prefix,
                    lid_number,
                    None,
                    article_number,
                    toestand,
                    opschrift,
                    kop_pad,
                    status,
                    max_chars,
                )
            )
        elif rendered := _render_block(child):
            current_prefix = _join_text(current_prefix, rendered)
            chunks.append(
                _make_chunk(
                    toestand,
                    article_number,
                    lid_number,
                    None,
                    opschrift,
                    kop_pad,
                    current_prefix,
                    status,
                )
            )
    return chunks or [
        _make_chunk(
            toestand,
            article_number,
            lid_number,
            None,
            opschrift,
            kop_pad,
            text,
            status,
        )
    ]


def _split_list(
    list_node: etree._Element,
    prefix: str,
    lid_number: str | None,
    parent_component: str | None,
    article_number: str,
    toestand: Toestand,
    opschrift: str | None,
    kop_pad: str,
    status: ChunkStatus,
    max_chars: int,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for item in list_node.findall("li"):
        chunks.extend(
            _split_list_item(
                item,
                prefix,
                lid_number,
                parent_component,
                article_number,
                toestand,
                opschrift,
                kop_pad,
                status,
                max_chars,
            )
        )
    return chunks


def _split_list_item(
    item: etree._Element,
    prefix: str,
    lid_number: str | None,
    parent_component: str | None,
    article_number: str,
    toestand: Toestand,
    opschrift: str | None,
    kop_pad: str,
    status: ChunkStatus,
    max_chars: int,
) -> list[Chunk]:
    label = _normalise_inline(_text_child(item, "li.nr"))
    component = _join_component(parent_component, label)
    item_text = _render_list_item(item)
    text = _join_text(prefix, item_text)
    if len(text) <= max_chars:
        return [
            _make_chunk(
                toestand,
                article_number,
                lid_number,
                component,
                opschrift,
                kop_pad,
                text,
                status,
            )
        ]

    child_nodes = [child for child in item if _local_name(child) not in {"li.nr", "meta-data"}]
    nested_lists = [child for child in child_nodes if _local_name(child) == "lijst"]
    if not nested_lists:
        return [
            _make_chunk(
                toestand,
                article_number,
                lid_number,
                component,
                opschrift,
                kop_pad,
                text,
                status,
            )
        ]

    first_list_index = next(
        index for index, child in enumerate(child_nodes) if _local_name(child) == "lijst"
    )
    lead_in = _render_list_item_prefix(item, child_nodes[:first_list_index], label)
    nested_prefix = _join_text(prefix, lead_in)
    chunks: list[Chunk] = []
    current_prefix = nested_prefix
    for child in child_nodes[first_list_index:]:
        if _local_name(child) == "lijst":
            chunks.extend(
                _split_list(
                    child,
                    current_prefix,
                    lid_number,
                    component,
                    article_number,
                    toestand,
                    opschrift,
                    kop_pad,
                    status,
                    max_chars,
                )
            )
        elif rendered := _render_block(child):
            current_prefix = _join_text(current_prefix, rendered)
            chunks.append(
                _make_chunk(
                    toestand,
                    article_number,
                    lid_number,
                    component,
                    opschrift,
                    kop_pad,
                    current_prefix,
                    status,
                )
            )
    return chunks or [
        _make_chunk(
            toestand,
            article_number,
            lid_number,
            component,
            opschrift,
            kop_pad,
            text,
            status,
        )
    ]


def _make_chunk(
    toestand: Toestand,
    artikel: str,
    lid: str | None,
    onderdeel: str | None,
    opschrift: str | None,
    kop_pad: str,
    tekst: str,
    status: ChunkStatus,
) -> Chunk:
    return Chunk(
        bwb_id=toestand.bwb_id,
        regeling_titel=toestand.titel,
        artikel=artikel,
        lid=lid,
        onderdeel=onderdeel,
        opschrift=opschrift,
        kop_pad=kop_pad,
        tekst=tekst,
        geldig_vanaf=toestand.geldig_vanaf,
        geldig_tot=toestand.geldig_tot,
        bron_url=(f"https://wetten.overheid.nl/jci1.3:c:{toestand.bwb_id}&artikel={artikel}"),
        toestand_url=toestand.toestand_url,
        status=status,
    )


def _article_status(article: etree._Element) -> ChunkStatus:
    if article.get("status", "").casefold() == "vervallen":
        return "vervallen"
    text = " ".join(
        part.decode() if isinstance(part, bytes) else part for part in article.itertext()
    )
    if _REPEALED_MARKER.search(text):
        return "vervallen"
    return "geldend"


def _render_blocks(nodes: Iterable[etree._Element]) -> str:
    rendered: list[str] = []
    for node in nodes:
        text = _render_block(node)
        if text:
            rendered.append(text)
    return "\n\n".join(rendered)


def _render_block(element: etree._Element) -> str:
    name = _local_name(element)
    if name in _IGNORED_TAGS:
        return ""
    if name == "al":
        return _normalise_inline(_inline_text(element))
    if name == "lid":
        number = _normalise_inline(_text_child(element, "lidnr"))
        body = _render_children(element, excluded={"lidnr", "meta-data"})
        return _join_text(f"{number}." if number else "", body)
    if name == "lijst":
        return "\n".join(
            text for child in element.findall("li") if (text := _render_list_item(child))
        )
    if name == "li":
        return _render_list_item(element)
    if name == "table":
        return _render_table(element)
    return _render_children(element, excluded={"meta-data"})


def _render_list_item(item: etree._Element) -> str:
    label = _normalise_inline(_text_child(item, "li.nr"))
    body = _render_children(item, excluded={"li.nr", "meta-data"})
    return _join_text(label, body)


def _render_list_item_prefix(
    item: etree._Element,
    preceding_nodes: list[etree._Element],
    label: str,
) -> str:
    return _join_text(label, _render_blocks(preceding_nodes))


def _render_lid_prefix(
    preceding_nodes: list[etree._Element],
    number: str | None,
) -> str:
    return _join_text(f"{number}." if number else "", _render_blocks(preceding_nodes))


def _render_children(element: etree._Element, *, excluded: set[str]) -> str:
    sections: list[str] = []
    inline_parts: list[str] = []
    if element.text:
        inline_parts.append(element.text)

    for child in element:
        child_name = _local_name(child)
        if child_name in excluded:
            text = ""
        elif child_name in _BLOCK_TAGS:
            text = _render_block(child)
            inline_text = _normalise_inline("".join(inline_parts))
            if inline_text:
                sections.append(inline_text)
            inline_parts.clear()
            if text:
                sections.append(text)
        else:
            inline_parts.append(_inline_text(child))
        if child.tail:
            inline_parts.append(child.tail)

    inline_text = _normalise_inline("".join(inline_parts))
    if inline_text:
        sections.append(inline_text)
    return _normalise_blocks_text("\n".join(sections))


def _inline_text(element: etree._Element | None) -> str:
    if element is None:
        return ""
    pieces: list[str] = [element.text or ""]
    for child in element:
        if _local_name(child) not in _IGNORED_TAGS:
            if _local_name(child) in _BLOCK_TAGS:
                pieces.append(_render_block(child))
            else:
                pieces.append(_inline_text(child))
        pieces.append(child.tail or "")
    return "".join(pieces)


def _render_table(table: etree._Element) -> str:
    caption = _normalise_inline(_text_child(table, "title"))
    tgroup = table.find("tgroup")
    if tgroup is None:
        return _normalise_inline(_inline_text(table))

    try:
        column_count = int(tgroup.get("cols", "0"))
    except ValueError:
        column_count = 0
    if column_count <= 0:
        column_count = len(tgroup.findall("colspec"))

    header_rows = tgroup.findall("thead/row")
    body_rows = tgroup.findall("tbody/row")
    all_rows = header_rows + body_rows
    if not all_rows:
        return caption
    if column_count <= 0:
        column_count = max((len(row.findall("entry")) for row in all_rows), default=1)

    matrix = [_table_row(row, column_count) for row in all_rows]
    header = matrix[0]
    output = [f"**{caption}**" if caption else "", _markdown_row(header)]
    output.append(_markdown_row(["---"] * column_count))
    output.extend(_markdown_row(row) for row in matrix[1:])
    return "\n".join(part for part in output if part)


def _table_row(row: etree._Element, column_count: int) -> list[str]:
    cells = [""] * column_count
    cursor = 1
    for entry in row.findall("entry"):
        start = _column_number(entry.get("colname") or entry.get("namest")) or cursor
        end = _column_number(entry.get("nameend")) or start
        start = max(1, start)
        end = max(start, end)
        if start > len(cells):
            cells.extend([""] * (start - len(cells)))
        value = _render_children(entry, excluded={"meta-data"})
        cells[start - 1] = _normalise_inline(value).replace("|", "\\|")
        if end > len(cells):
            cells.extend([""] * (end - len(cells)))
        cursor = end + 1
    if len(cells) < column_count:
        cells.extend([""] * (column_count - len(cells)))
    return cells[: max(column_count, len(cells))]


def _markdown_row(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def _column_number(name: str | None) -> int | None:
    if name is None:
        return None
    match = re.search(r"(\d+)\Z", name)
    return int(match.group(1)) if match else None


def _text_child(element: etree._Element, name: str) -> str:
    child = element.find(name)
    return _inline_text(child) if child is not None else ""


def _heading_text(element: etree._Element, kop: etree._Element) -> str:
    label = (element.get("label") or "").strip()
    if not label:
        heading_label = _normalise_inline(_text_child(kop, "label"))
        number = _normalise_inline(_text_child(kop, "nr"))
        label = _join_text(heading_label, number)
    title = _normalise_inline(_text_child(kop, "titel"))
    return _join_text(label, f"— {title}" if title else "")


def _join_component(parent: str | None, label: str) -> str | None:
    current = label.strip().rstrip(".) ")
    if not current:
        return parent
    return f"{parent}.{current}" if parent else current


def _join_text(*parts: str) -> str:
    return " ".join(part.strip() for part in parts if part and part.strip())


def _normalise_inline(text: str) -> str:
    return " ".join(text.split())


def _normalise_blocks_text(text: str) -> str:
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _local_name(element: etree._Element) -> str:
    if not isinstance(element.tag, str):
        return ""
    return etree.QName(element).localname


def _clear_processed(element: etree._Element) -> None:
    tail = element.tail
    element.clear()
    element.tail = tail
    parent = element.getparent()
    if parent is not None:
        while element.getprevious() is not None:
            del parent[0]
