`dakkapel.docx` is the packaged `docxtpl` template, including a repeating VML
diagonal `CONCEPT` watermark and the exact disclosure in its footer.
`dakkapel.html` is the packaged WeasyPrint template. It has no external CSS,
images, fonts, or URL references; the renderer also rejects all URL fetching.

The DOCX OOXML core-properties schema has no `generator` property. The
renderer records `Wetvia-AI` in the standard core `creator` and
`lastModifiedBy` fields and writes the custom properties `generator=Wetvia-AI`
and `ai_generated=true` in `docProps/custom.xml`. PDF Info metadata uses
`/Producer=Wetvia-AI`; XMP carries `wetvia:generator` and
`wetvia:ai_generated` in the `https://wetvia.ai/ns/1.0/` namespace.
