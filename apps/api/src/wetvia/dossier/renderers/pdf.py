"""PDF renderer with disabled URL fetching and explicit XMP AI metadata."""

from importlib.resources import files
from io import BytesIO
from typing import Any

from jinja2 import Environment, select_autoescape
from pypdf import PdfReader, PdfWriter
from weasyprint import HTML  # type: ignore[import-untyped]

from wetvia.dossier.schema import DossierV1

_XMP_METADATA = b"""<?xpacket begin="\xef\xbb\xbf" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
    <rdf:Description rdf:about=""
      xmlns:pdf="http://ns.adobe.com/pdf/1.3/"
      pdf:Producer="Wetvia-AI" />
    <rdf:Description rdf:about=""
      xmlns:xmp="http://ns.adobe.com/xap/1.0/"
      xmp:CreatorTool="Wetvia-AI" />
    <rdf:Description rdf:about=""
      xmlns:wetvia="https://wetvia.ai/ns/1.0/"
      wetvia:ai_generated="true"
      wetvia:generator="Wetvia-AI" />
  </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>"""


def render_pdf(dossier: DossierV1) -> bytes:
    """Render the packaged HTML template and write PDF Info and XMP metadata."""
    template = (
        files("wetvia.dossier.templates").joinpath("dakkapel.html").read_text(encoding="utf-8")
    )
    environment = Environment(autoescape=select_autoescape(default=True))
    html = environment.from_string(template).render(dossier=dossier.model_dump(mode="json"))
    pdf_content = HTML(
        string=html,
        url_fetcher=_deny_resource_fetch,
    ).write_pdf()

    reader = PdfReader(BytesIO(pdf_content))
    writer = PdfWriter()
    writer.append_pages_from_reader(reader)
    writer.add_metadata(
        {
            "/Title": "Conceptdossier dakkapel",
            "/Author": "Wetvia-AI",
            "/Producer": "Wetvia-AI",
            "/Subject": dossier.disclosure,
            "/ai_generated": "true",
        }
    )
    writer.xmp_metadata = _XMP_METADATA
    result = BytesIO()
    writer.write(result)
    return result.getvalue()


def _deny_resource_fetch(url: str, *args: Any, **kwargs: Any) -> Any:
    raise ValueError(f"External resources are disabled for dossier rendering: {url}")


__all__ = ["render_pdf"]
