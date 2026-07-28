"""USLM 1.x parser — the schema every current release point is published in.

All USLM 1.x element knowledge in this project lives in this file (CLAUDE.md
architecture rule 2). Verified against `samples/uslm1/usc16.xml`
(USLM-1.0.15.xsd, `Online@119-102not101`).

Schema notes that shaped this implementation:
  * `@temporalId` does not appear anywhere in the 1.0.15 converter output, so
    `SectionRecord.temporal_id` is always None for these files.
  * `<section>` also occurs inside `<quotedContent>` — 298 of Title 16's 5,393
    `<section>` elements are quoted text from amending acts, carry no `@identifier`,
    and are not code sections. The base class skips them; see ADR-0004.
  * `@status` is not section-only: Title 16's single `reserved` status sits on a
    `<subchapter>`, which is why section status counts total 643, not 644.
"""

from __future__ import annotations

from typing import ClassVar

from lxml import etree

from ingest.base import DC_NAMESPACE, ElementNames, StreamingSectionParser
from ingest.detect import USLM1_NAMESPACE, UslmVersion

DCTERMS_NAMESPACE = "http://purl.org/dc/terms/"


class Uslm1Parser(StreamingSectionParser):
    uslm_version: ClassVar[UslmVersion] = UslmVersion.V1
    namespace: ClassVar[str] = USLM1_NAMESPACE
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
    )

    def _meta_extras(self, meta: etree._Element | None) -> dict[str, object]:
        if meta is None:
            return {}
        return {
            "is_positive_law": self._is_positive_law(meta),
            "created": self._text(meta, "created", DCTERMS_NAMESPACE),
            "converter": self._text(meta, "creator", DC_NAMESPACE),
        }

    def _is_positive_law(self, meta: etree._Element) -> bool | None:
        for prop in meta.findall(self._q("property")):
            if prop.get("role") == "is-positive-law":
                return (self._normalize(prop) or "").lower() == "yes"
        return None
