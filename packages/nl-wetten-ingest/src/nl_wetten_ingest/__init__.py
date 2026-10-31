"""Public clients and models for Dutch legal sources."""

from nl_wetten_ingest.bwb import (
    BwbSRUClient,
    SRUDiagnosticError,
    SRUError,
    SRUProtocolError,
    Toestand,
    ToestandDownloadError,
    ToestandStatus,
    changed_since,
    classify,
    search_toestanden,
    select_toestand,
)
from nl_wetten_ingest.parse_bwb_xml import (
    BWBXMLParseError,
    Chunk,
    ChunkStatus,
)
from nl_wetten_ingest.parse_bwb_xml import (
    parse as parse_bwb_xml,
)

__all__ = [
    "BWBXMLParseError",
    "BwbSRUClient",
    "Chunk",
    "ChunkStatus",
    "SRUDiagnosticError",
    "SRUError",
    "SRUProtocolError",
    "Toestand",
    "ToestandDownloadError",
    "ToestandStatus",
    "changed_since",
    "classify",
    "parse_bwb_xml",
    "search_toestanden",
    "select_toestand",
]
