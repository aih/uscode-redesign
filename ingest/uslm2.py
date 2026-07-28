"""USLM 2.x parser — partial (PLAN.md Day 1 item 2: "stub passing detection and
basic section extraction on repo samples"; parity is Day 7).

All USLM 2.x element knowledge lives in this file. Verified against
`samples/uslm2/USLM2/{usc01,usc16,usc49}.xml` (uslm-2.0.12.xsd).

What works: detection, `<meta>`, and section extraction — 2.x keeps the same
`<section>`/`<num>`/`<heading>`/`<sourceCredit>`/`<notes>`/`<quotedContent>`
vocabulary for the fields `SectionRecord` carries, so records from either schema
are directly comparable.

What is NOT done, and why nothing here pretends otherwise (OLRC's migration note
lists these as the substantive 1.x -> 2.x differences):
  * **TOC** — 2.x replaces `<tocItem>`/`<column>` with `<referenceItem>`/
    `<designator>`/`<label>`/`<target>`. Nothing here reads a TOC yet; when the
    TOC pass lands it needs a per-schema implementation.
  * **Tables** and the **indent model** — 2.x uses `<list>`/`<listItem>`/
    `<listContent>` and `indentUp*`/`depth*` classes where 1.x used `indent*`.
    Only rendering cares, and the raw XML is stored verbatim, so extraction is
    unaffected.
  * **MathML 3** — 2.0.17+ only; absent from these samples.

Also observed and worth carrying forward: Title 49 uses `@status="renumbered"`,
a value Title 16 never shows — status stays a free string, never an enum.
"""

from __future__ import annotations

from typing import ClassVar

from lxml import etree

from ingest.base import DC_NAMESPACE, ElementNames, StreamingSectionParser
from ingest.detect import USLM2_NAMESPACE, UslmVersion


class Uslm2Parser(StreamingSectionParser):
    uslm_version: ClassVar[UslmVersion] = UslmVersion.V2
    namespace: ClassVar[str] = USLM2_NAMESPACE
    elements: ClassVar[ElementNames] = ElementNames(
        section="section",
        num="num",
        heading="heading",
        source_credit="sourceCredit",
        notes="notes",
        note="note",
        quoted_content="quotedContent",
        meta="meta",
        doc_number="docNumber",
        doc_publication_name="docPublicationName",
        # Same structural vocabulary as 1.x — which is the whole reason the TOC pass
        # reads structural elements instead of <toc> (ADR-0006). Verified against
        # usc49.xml (subtitle/chapter/subchapter/part/subpart) and usc01.xml.
        structure=(
            "title",
            "subtitle",
            "chapter",
            "subchapter",
            "part",
            "subpart",
            "division",
            "subdivision",
            "article",
            "subarticle",
        ),
    )

    def _meta_extras(self, meta: etree._Element | None) -> dict[str, object]:
        if meta is None:
            return {}
        # 2.x drops <property role="is-positive-law"> and renames the 1.x
        # dcterms:created / dc:creator pair to processedDate / processedBy.
        return {
            "created": self._text(meta, "processedDate"),
            "converter": self._text(meta, "processedBy"),
            "extra": {
                key: value
                for key, value in (
                    ("dc:publisher", self._text(meta, "publisher", DC_NAMESPACE)),
                    ("dc:creator", self._text(meta, "creator", DC_NAMESPACE)),
                )
                if value
            },
        }
