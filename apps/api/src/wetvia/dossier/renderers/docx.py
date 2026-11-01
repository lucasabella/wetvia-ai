"""DOCX renderer with visible watermark and OOXML AI provenance properties."""

from importlib.resources import files
from io import BytesIO
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

from docxtpl import DocxTemplate  # type: ignore[import-untyped]
from jinja2 import Environment

from wetvia.dossier.schema import DossierV1

_CUSTOM_PROPERTIES_REL = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/custom-properties"
)
_CUSTOM_PROPERTIES_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.custom-properties+xml"
)
_CUSTOM_PROPERTY_FORMAT_ID = "{D5CDD505-2E9C-101B-9397-08002B2CF9AE}"


def render_docx(dossier: DossierV1) -> bytes:
    """Render the packaged docxtpl template and stamp valid OOXML properties."""
    template = files("wetvia.dossier.templates").joinpath("dakkapel.docx")
    with template.open("rb") as handle:
        document = DocxTemplate(BytesIO(handle.read()))
    document.render(
        {"dossier": dossier.model_dump(mode="json")},
        jinja_env=Environment(autoescape=True),
    )
    properties = document.docx.core_properties
    properties.author = "Wetvia-AI"
    properties.last_modified_by = "Wetvia-AI"
    properties.title = "Conceptdossier dakkapel"
    properties.subject = dossier.disclosure
    rendered = BytesIO()
    document.save(rendered)
    return _add_custom_properties(rendered.getvalue())


def _add_custom_properties(content: bytes) -> bytes:
    """Add standard OOXML custom properties without claiming a core generator field."""
    content_types_ns = "http://schemas.openxmlformats.org/package/2006/content-types"
    rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    props_ns = "http://schemas.openxmlformats.org/officeDocument/2006/custom-properties"
    variants_ns = "http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"
    ET.register_namespace("ct", content_types_ns)
    ET.register_namespace("rel", rel_ns)
    ET.register_namespace("cp", props_ns)
    ET.register_namespace("vt", variants_ns)

    with ZipFile(BytesIO(content)) as source:
        files_by_name = {name: source.read(name) for name in source.namelist()}

    content_types = ET.fromstring(files_by_name["[Content_Types].xml"])
    if not any(element.get("PartName") == "/docProps/custom.xml" for element in content_types):
        ET.SubElement(
            content_types,
            f"{{{content_types_ns}}}Override",
            {
                "PartName": "/docProps/custom.xml",
                "ContentType": _CUSTOM_PROPERTIES_CONTENT_TYPE,
            },
        )
    files_by_name["[Content_Types].xml"] = ET.tostring(
        content_types,
        encoding="utf-8",
        xml_declaration=True,
    )

    package_relationships = ET.fromstring(files_by_name["_rels/.rels"])
    if not any(element.get("Type") == _CUSTOM_PROPERTIES_REL for element in package_relationships):
        used_ids = {element.get("Id") for element in package_relationships}
        index = 1
        relationship_id = f"rId{index}"
        while relationship_id in used_ids:
            index += 1
            relationship_id = f"rId{index}"
        ET.SubElement(
            package_relationships,
            f"{{{rel_ns}}}Relationship",
            {
                "Id": relationship_id,
                "Type": _CUSTOM_PROPERTIES_REL,
                "Target": "docProps/custom.xml",
            },
        )
    files_by_name["_rels/.rels"] = ET.tostring(
        package_relationships,
        encoding="utf-8",
        xml_declaration=True,
    )

    custom_properties = ET.Element(f"{{{props_ns}}}Properties")
    _add_custom_property(
        custom_properties,
        props_ns,
        variants_ns,
        pid="2",
        name="ai_generated",
        value="true",
        value_type="bool",
    )
    _add_custom_property(
        custom_properties,
        props_ns,
        variants_ns,
        pid="3",
        name="generator",
        value="Wetvia-AI",
        value_type="lpwstr",
    )
    files_by_name["docProps/custom.xml"] = ET.tostring(
        custom_properties,
        encoding="utf-8",
        xml_declaration=True,
    )

    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as destination:
        for name, data in files_by_name.items():
            destination.writestr(name, data)
    return output.getvalue()


def _add_custom_property(
    properties: ET.Element,
    props_ns: str,
    variants_ns: str,
    *,
    pid: str,
    name: str,
    value: str,
    value_type: str,
) -> None:
    element = ET.SubElement(
        properties,
        f"{{{props_ns}}}property",
        {"fmtid": _CUSTOM_PROPERTY_FORMAT_ID, "pid": pid, "name": name},
    )
    value_element = ET.SubElement(element, f"{{{variants_ns}}}{value_type}")
    value_element.text = value


__all__ = ["render_docx"]
