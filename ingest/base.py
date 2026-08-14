"""The `UslmParser` protocol and the streaming machinery its implementations share.

CLAUDE.md architecture rule 2 says USLM element paths never appear outside a parser
implementation. `StreamingSectionParser` honours that by knowing no *USLM* element
names of its own: every one arrives from the subclass as an `ElementNames`
vocabulary, so `Uslm1Parser` and `Uslm2Parser` each own their schema knowledge in
full while sharing one memory-bounded traversal (CLAUDE.md gotcha 6 — Title 42 must
never be loaded as a whole tree). The one name spelled out below, `dc:title`, is
Dublin Core rather than USLM and is identical in both generations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Iterator, Protocol

from lxml import etree

from ingest.detect import UslmVersion, XmlSource, open_source, sniff_schema
from ingest.records import (
    DocumentMeta,
    GuidRef,
    NoteRecord,
    NoteText,
    SectionRecord,
    StructureRecord,
)

DC_NAMESPACE = "http://purl.org/dc/elements/1.1/"


@dataclass(frozen=True, slots=True)
class ElementNames:
    """The local element names one USLM generation uses for the things we extract.

    Supplied by each parser implementation — the streaming base has no defaults, so
    a schema change is a change to that parser's vocabulary and nothing else.
    """

    section: str
    num: str
    heading: str
    source_credit: str
    notes: str
    note: str
    quoted_content: str
    meta: str
    doc_number: str
    doc_publication_name: str
    structure: tuple[str, ...]
    """Structural container levels above the section, outermost first. Not every
    title uses every level (Title 16 has no `subtitle`), and the list is a
    vocabulary to *recognize*, not a hierarchy to enforce — the tree comes from the
    document, not from this order."""

    toc: str
    """The table-of-contents element — excluded from plain text (ADR-0069)."""

    text_blocks: tuple[str, ...]
    """Local names below the section that start a new line of plain text: the
    provision ladder (`subsection` … `subsubitem`), the leaf text carriers
    (`chapeau`, `content`, `continuation`, `proviso`, `p`), and table/list
    machinery. The partition follows the measured inline/block artifact of
    ADR-0040 (`docs/verification/inline-elements.json`): `num` and `heading` are
    deliberately absent so a provision's designator and heading share its first
    line. Matched by local name so USLM's XHTML-namespace table elements are
    covered without a second vocabulary."""

    text_run_on: tuple[str, ...]
    """The subset of `text_blocks` that keeps the printed Code's run-on form
    after a bare designator — the leaf text carriers, so `(1) assure the
    preservation…` stays one line while a sibling *provision* after a bare
    `<num>` still breaks."""

    text_spaced: tuple[str, ...]
    """Local names whose text joins the line with a space on either side:
    `num`, `heading`, table cells. Never the mid-word inline elements —
    `460<i>l</i>–3` must stay one word."""


@dataclass(slots=True)
class _StructureFrame:
    """An open structural element: identity known at `start`, text filled in later."""

    element: etree._Element
    identifier: str
    level: str
    status: str | None
    guid: str | None
    parent_identifier: str | None
    seq: int
    depth: int
    num: str | None = None
    num_value: str | None = None
    heading: str | None = None

    def to_record(self) -> StructureRecord:
        return StructureRecord(
            identifier=self.identifier,
            level=self.level,
            num=self.num,
            num_value=self.num_value,
            heading=self.heading,
            status=self.status,
            guid=self.guid,
            parent_identifier=self.parent_identifier,
            seq=self.seq,
            depth=self.depth,
        )


class UslmParser(Protocol):
    """What every USLM parser must provide. Consumers depend on this, not on 1.x/2.x."""

    uslm_version: ClassVar[UslmVersion]
    namespace: ClassVar[str]

    def parse_meta(self, source: XmlSource) -> DocumentMeta:
        """Read `<meta>` and root attributes without parsing the body."""
        ...

    def iter_sections(self, source: XmlSource) -> Iterator[SectionRecord]:
        """Yield one `SectionRecord` per real section, in document order."""
        ...

    def iter_structure(self, source: XmlSource) -> Iterator[StructureRecord]:
        """Yield the hierarchy above the sections, parents before children."""
        ...

    def count_section_elements(self, source: XmlSource) -> int:
        """Count every `<section>` element, quoted ones included (ADR-0005).

        Provenance manifests (PLAN §11.4) record this alongside the real count
        from `iter_sections`; the gap between them is the quoted-content
        exclusion, worth surfacing rather than only reporting one number.
        """
        ...


class StreamingSectionParser:
    """`iterparse`-based section extraction, parameterized by `ElementNames`."""

    uslm_version: ClassVar[UslmVersion]
    namespace: ClassVar[str]
    elements: ClassVar[ElementNames]

    # ------------------------------------------------------------------ public

    def parse_meta(self, source: XmlSource) -> DocumentMeta:
        schema = sniff_schema(source)
        meta_tag = self._q(self.elements.meta)
        with open_source(source) as handle:
            meta: etree._Element | None = None
            depth = 0
            for event, element in etree.iterparse(handle, events=("start", "end")):
                if event == "start":
                    depth += 1
                    if depth == 2 and element.tag != meta_tag:
                        break  # body reached without a <meta> — stop reading
                elif element.tag == meta_tag:
                    meta = element
                    break

        publication = self._text(meta, self.elements.doc_publication_name)
        return DocumentMeta(
            identifier=schema.identifier or "",
            schema_version=schema.schema_version,
            uslm_version=str(self.uslm_version),
            doc_number=self._text(meta, self.elements.doc_number),
            doc_title=self._text(meta, "title", namespace=DC_NAMESPACE),
            doc_publication_name=publication,
            release_label=self._release_label(publication),
            **self._meta_extras(meta),
        )

    def iter_sections(self, source: XmlSource) -> Iterator[SectionRecord]:
        schema_version = sniff_schema(source).schema_version
        section_tag = self._q(self.elements.section)
        quoted_tag = self._q(self.elements.quoted_content)
        seq = 0

        with open_source(source) as handle:
            for _event, element in etree.iterparse(
                handle, events=("end",), tag=section_tag
            ):
                if not self._is_real_section(element, quoted_tag):
                    # A section quoted inside another section's amendment text, or a
                    # stray section with no identity. Leave the element in place: its
                    # end event fires before the enclosing real section's, and the
                    # enclosing section's XML must stay verbatim.
                    continue
                yield self._build_record(element, seq, schema_version)
                seq += 1
                self._prune(element)

    def iter_structure(self, source: XmlSource) -> Iterator[StructureRecord]:
        """Stream the structural skeleton: title → chapter → subchapter → part → …

        Both events are needed, and for opposite reasons. A node's *identity* is
        known at `start`, which is also where document pre-order is fixed; its
        `<num>`/`<heading>` are only complete at their own `end`. Waiting for the
        structural element's own `end` — the obvious reading of "parse chapters" —
        would buffer an entire chapter of sections in memory, which Title 42 does
        not forgive (CLAUDE.md gotcha 6). So: open a frame at `start`, fill it from
        `num`/`heading` end events, close it at `end`, and prune the finished
        sections as they go by.

        Frames are collected in `start` order, which *is* document pre-order, and
        yielded once the file is exhausted — a node isn't complete until its
        heading arrives, and a tree has to be inserted parents-first. Only the
        skeleton is held (569 nodes for all of Title 16), never section bodies.
        """
        structure_tags = {self._q(name) for name in self.elements.structure}
        num_tag = self._q(self.elements.num)
        heading_tag = self._q(self.elements.heading)
        quoted_tag = self._q(self.elements.quoted_content)
        section_tag = self._q(self.elements.section)
        notes_tag = self._q(self.elements.notes)

        stack: list[_StructureFrame] = []
        frames: list[_StructureFrame] = []
        sibling_seq: dict[str | None, int] = {}
        quoted_depth = 0

        with open_source(source) as handle:
            for event, element in etree.iterparse(handle, events=("start", "end")):
                tag = element.tag
                if event == "start":
                    if tag == quoted_tag:
                        quoted_depth += 1
                    elif (
                        quoted_depth == 0
                        and tag in structure_tags
                        and element.get("identifier")
                    ):
                        parent = stack[-1].identifier if stack else None
                        seq = sibling_seq.get(parent, 0)
                        sibling_seq[parent] = seq + 1
                        frame = _StructureFrame(
                            element=element,
                            identifier=element.get("identifier") or "",
                            level=etree.QName(element).localname,
                            status=element.get("status"),
                            guid=element.get("id"),
                            parent_identifier=parent,
                            seq=seq,
                            depth=len(stack),
                        )
                        stack.append(frame)
                        frames.append(frame)
                    continue

                if tag == quoted_tag:
                    quoted_depth -= 1
                elif quoted_depth:
                    continue
                elif stack and tag in (num_tag, heading_tag):
                    if element.getparent() is stack[-1].element:
                        if tag == num_tag:
                            stack[-1].num = self._normalize(element)
                            stack[-1].num_value = element.get("value")
                        else:
                            stack[-1].heading = self._normalize(element)
                elif tag in (section_tag, notes_tag):
                    self._prune(element)  # the bulk of the document, already read
                elif stack and element is stack[-1].element:
                    self._prune(stack.pop().element)

        for frame in frames:
            yield frame.to_record()

    def count_section_elements(self, source: XmlSource) -> int:
        tag = self._q(self.elements.section)
        count = 0
        with open_source(source) as handle:
            for _event, element in etree.iterparse(handle, events=("end",), tag=tag):
                count += 1
                element.clear()
        return count

    def plain_text(self, fragment: str | etree._Element) -> str:
        """Body text of a stored section fragment, one line per block (ADR-0069).

        Excludes `<notes>`/`<note>`, `<sourceCredit>` and `<toc>`; every
        `text_blocks` element starts a new line; a provision's `<num>` and
        `<heading>` share its first line. `<quotedContent>` text is kept — it is
        body text — as a block of its own unless it sits inside a sentence, the
        same per-occurrence test ADR-0040 measured the partition with. Elements
        are matched by local name, so XHTML-namespace table markup needs no
        second vocabulary. Whitespace collapses within each line and empty lines
        are dropped.

        Accepts the serialized fragment or an already-parsed element, so a
        caller extracting body and notes from one fragment parses it once.
        """
        root = etree.fromstring(fragment) if isinstance(fragment, str) else fragment
        parts: list[str] = []
        self._emit_text(root, parts, self._text_skip_locals(), self._text_block_locals())
        return self._join_text(parts)

    def notes_text(self, fragment: str | etree._Element) -> tuple[NoteText, ...]:
        """Each note of a stored section fragment as plain text (ADR-0069).

        Walks the same containers as `_collect_notes`. A note's own heading is
        reported in `heading` and left out of `text`.
        """
        root = etree.fromstring(fragment) if isinstance(fragment, str) else fragment
        collected: list[NoteText] = []
        note_tag = self._q(self.elements.note)
        notes_tag = self._q(self.elements.notes)
        for child in root:
            if child.tag == note_tag:
                collected.append(self._note_text(child))
            elif child.tag == notes_tag:
                collected.extend(
                    self._note_text(note) for note in child if note.tag == note_tag
                )
        return tuple(collected)

    # ----------------------------------------------------------------- hooks

    def _meta_extras(self, meta: etree._Element | None) -> dict[str, object]:
        """Schema-specific `<meta>` fields. Overridden by each implementation."""
        return {}

    # --------------------------------------------------------------- internals

    def _q(self, local_name: str, namespace: str | None = None) -> str:
        return f"{{{namespace or self.namespace}}}{local_name}"

    def _is_real_section(self, element: etree._Element, quoted_tag: str) -> bool:
        if not element.get("identifier"):
            return False
        return not any(a.tag == quoted_tag for a in element.iterancestors())

    def _build_record(
        self, element: etree._Element, seq: int, schema_version: str
    ) -> SectionRecord:
        identifier = element.get("identifier")
        assert identifier is not None  # guaranteed by _is_real_section
        num = element.find(self._q(self.elements.num))
        return SectionRecord(
            identifier=identifier,
            guid=element.get("id") or "",
            temporal_id=element.get("temporalId"),
            num=self._normalize(num),
            num_value=num.get("value") if num is not None else None,
            heading=self._normalize(element.find(self._q(self.elements.heading))),
            status=element.get("status"),
            seq=seq,
            xml=etree.tostring(element, encoding="unicode", with_tail=False),
            content_key=self._content_key(element),
            source_credit=self._normalize(
                element.find(self._q(self.elements.source_credit))
            ),
            notes=self._collect_notes(element),
            guid_refs=self._collect_guids(element, identifier),
            ancestors=self._collect_ancestors(element),
            schema_version=schema_version,
        )

    def _content_key(self, element: etree._Element) -> str:
        """The section's XML with every `@id` guid removed — the dedupe key.

        Guids are regenerated at every release point *by design* (ADR-0003), so the
        raw XML of an untouched section changes at every one of the ~324 release
        points. Hashing it deduped nothing at all: measured across 119-99 and
        119-102not101, 0 of 5,095 Title 16 sections had identical raw XML, while
        5,093 were identical once guids were dropped and exactly 2 had really been
        amended (ADR-0007).

        Removing the attributes in place and restoring them avoids copying the
        subtree; only `@id` is touched, so everything else — including whitespace —
        still participates in the hash.
        """
        removed = [(node, node.attrib.pop("id")) for node in element.iter() if "id" in node.attrib]
        try:
            return etree.tostring(element, encoding="unicode", with_tail=False)
        finally:
            for node, guid in removed:
                node.set("id", guid)

    def _collect_notes(self, element: etree._Element) -> tuple[NoteRecord, ...]:
        note_tag = self._q(self.elements.note)
        notes_tag = self._q(self.elements.notes)
        collected: list[NoteRecord] = []
        for child in element:
            if child.tag == note_tag:
                collected.append(self._note_record(child))
            elif child.tag == notes_tag:
                collected.extend(
                    self._note_record(note) for note in child if note.tag == note_tag
                )
        return tuple(collected)

    def _note_record(self, note: etree._Element) -> NoteRecord:
        return NoteRecord(
            topic=note.get("topic"),
            role=note.get("role"),
            heading=self._normalize(note.find(self._q(self.elements.heading))),
            xml=etree.tostring(note, encoding="unicode", with_tail=False),
        )

    def _note_text(self, note: etree._Element) -> NoteText:
        skip = frozenset((self.elements.toc,))
        blocks = self._text_block_locals()
        heading_tag = self._q(self.elements.heading)
        parts: list[str] = []
        if note.text:
            parts.append(note.text)
        for child in note:
            if child.tag != heading_tag:
                self._emit_text(child, parts, skip, blocks)
            if child.tail:
                parts.append(child.tail)
        return NoteText(
            topic=note.get("topic"),
            role=note.get("role"),
            heading=self._normalize(note.find(heading_tag)),
            text=self._join_text(parts),
        )

    def _text_skip_locals(self) -> frozenset[str]:
        return frozenset(
            (
                self.elements.notes,
                self.elements.note,
                self.elements.source_credit,
                self.elements.toc,
            )
        )

    def _text_block_locals(self) -> frozenset[str]:
        # Quoted sections and structural levels can appear inside
        # <quotedContent>, so the whole recognized vocabulary breaks lines.
        return frozenset(
            (
                *self.elements.text_blocks,
                *self.elements.structure,
                self.elements.section,
                self.elements.quoted_content,
            )
        )

    def _emit_text(
        self,
        element: etree._Element,
        parts: list[str],
        skip: frozenset[str],
        blocks: frozenset[str],
    ) -> None:
        local = self._local_name(element)
        if local is None or local in skip:
            return  # the subtree; its tail belongs to the parent and stays
        block = local in blocks and not (
            local == self.elements.quoted_content and self._in_running_prose(element)
        )
        spaced = local in self.elements.text_spaced
        if block and not (
            local in self.elements.text_run_on and self._runs_on_from_num(element)
        ):
            parts.append("\n")
        elif spaced:
            parts.append(" ")
        if element.text:
            parts.append(element.text)
        for child in element:
            self._emit_text(child, parts, skip, blocks)
            if child.tail:
                parts.append(child.tail)
        if block:
            parts.append("\n")
        elif spaced:
            parts.append(" ")

    def _runs_on_from_num(self, element: etree._Element) -> bool:
        """True when everything before `element` in its parent is the bare
        `<num>` — the unheaded-provision case, where the printed Code runs the
        designator and the text together (`(1) assure the preservation…`). A
        heading before the block keeps the break, so a headed provision still
        reads `(a) Statement of purpose` with its text below (ADR-0069)."""
        parent = element.getparent()
        if parent is None or (parent.text or "").strip():
            return False
        saw_num = False
        for sibling in element.itersiblings(preceding=True):
            if (sibling.tail or "").strip():
                return False
            local = self._local_name(sibling)
            if local is None:
                continue
            if local != self.elements.num:
                return False
            saw_num = True
        return saw_num

    @staticmethod
    def _local_name(element: etree._Element) -> str | None:
        """Local name, or None for non-elements (comments, PIs)."""
        tag = element.tag
        if not isinstance(tag, str):
            return None
        return etree.QName(tag).localname

    @staticmethod
    def _in_running_prose(element: etree._Element) -> bool:
        """A non-whitespace text node immediately beside the element — the test
        `scripts/inline_elements.py` counts with (ADR-0040)."""
        previous = element.getprevious()
        if previous is not None:
            before = previous.tail
        else:
            parent = element.getparent()
            before = parent.text if parent is not None else None
        return bool((before or "").strip()) or bool((element.tail or "").strip())

    @staticmethod
    def _join_text(parts: list[str]) -> str:
        lines = ("".join(parts)).split("\n")
        collapsed = (" ".join(line.split()) for line in lines)
        return "\n".join(line for line in collapsed if line)

    def _collect_guids(
        self, element: etree._Element, section_identifier: str
    ) -> tuple[GuidRef, ...]:
        refs: list[GuidRef] = []
        stack: list[tuple[etree._Element, str]] = [(element, section_identifier)]
        while stack:
            current, inherited = stack.pop()
            identifier = current.get("identifier") or inherited
            guid = current.get("id")
            if guid:
                refs.append(GuidRef(guid=guid, identifier=identifier))
            stack.extend((child, identifier) for child in reversed(current))
        return tuple(refs)

    def _collect_ancestors(self, element: etree._Element) -> tuple[tuple[str, str], ...]:
        chain: list[tuple[str, str]] = []
        for ancestor in element.iterancestors():
            if ancestor.getparent() is None:
                break  # the document element repeats the title's identifier
            identifier = ancestor.get("identifier")
            if identifier:
                chain.append((etree.QName(ancestor).localname, identifier))
        chain.reverse()
        return tuple(chain)

    @staticmethod
    def _prune(element: etree._Element) -> None:
        """Free the emitted section and everything before it in its parent."""
        element.clear()
        parent = element.getparent()
        if parent is None:
            return
        while element.getprevious() is not None:
            del parent[0]

    def _text(
        self, parent: etree._Element | None, local_name: str, namespace: str | None = None
    ) -> str | None:
        if parent is None:
            return None
        return self._normalize(parent.find(self._q(local_name, namespace)))

    @staticmethod
    def _normalize(element: etree._Element | None) -> str | None:
        """Full text of `element`, whitespace-collapsed; None when absent or empty."""
        if element is None:
            return None
        text = " ".join("".join(element.itertext()).split())
        return text or None

    @staticmethod
    def _release_label(publication_name: str | None) -> str | None:
        if not publication_name or "@" not in publication_name:
            return None
        return publication_name.split("@", 1)[1] or None
