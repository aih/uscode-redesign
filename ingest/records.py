"""Normalized, schema-agnostic records emitted by every `UslmParser`.

Nothing downstream of `ingest/` may know whether a record came from USLM 1.x or
2.x — `schema_version` rides along as metadata so the original XML can always be
returned verbatim (CLAUDE.md architecture rule 2).
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Observed @status values. Not exhaustive and deliberately not an enum: Title 49
# in the USLM 2.x samples carries `renumbered`, which Title 16 never does, and
# early release points are expected to drift (CLAUDE.md gotcha 8).
STATUS_REPEALED = "repealed"
STATUS_OMITTED = "omitted"
STATUS_TRANSFERRED = "transferred"
STATUS_RESERVED = "reserved"
STATUS_RENUMBERED = "renumbered"


@dataclass(frozen=True, slots=True)
class GuidRef:
    """One `@id` guid found anywhere inside a section, with the provision it pins.

    `identifier` is the element's own `@identifier` when it has one, otherwise the
    nearest enclosing identifier (at minimum the section's). Elements such as `<p>`
    carry an `@id` but no `@identifier`, and `GET /us/usc/?id=` still has to resolve
    them to something retrievable — the containing provision is that something.

    A guid pins (provision, release point) and is never a cross-release identity
    (ADR-0003).
    """

    guid: str
    identifier: str


@dataclass(frozen=True, slots=True)
class NoteRecord:
    """A `<note>` attached to a section (directly or via a `<notes>` container)."""

    topic: str | None
    role: str | None
    heading: str | None
    xml: str


@dataclass(frozen=True, slots=True)
class SectionRecord:
    """One US Code section — the storage atom (ADR-0001).

    `xml` is the section element serialized verbatim, so sub-section provisions
    (`/us/usc/t16/s45f/c/5`) are extracted from it by XPath at request time rather
    than being stored separately.
    """

    identifier: str
    """Logical path, e.g. `/us/usc/t16/s45f`. Cross-release identity."""

    guid: str
    """The section's `@id`. Pins (section, release point) — never identity."""

    temporal_id: str | None
    """`@temporalId`, display only, never a key. Absent in USLM 1.0.15 output."""

    num: str | None
    """Rendered designator text, e.g. `§ 45f.`"""

    num_value: str | None
    """`<num @value>`, e.g. `45f` — the machine-readable designator."""

    heading: str | None
    status: str | None
    seq: int
    """0-based position in document order among the emitted sections of one file."""

    xml: str
    source_credit: str | None
    notes: tuple[NoteRecord, ...] = ()
    guid_refs: tuple[GuidRef, ...] = ()
    """Every `@id` in the section, section's own included — feeds `guid_map`."""

    ancestors: tuple[tuple[str, str], ...] = ()
    """(level name, identifier) from title down to the section's parent, e.g.
    `(("title", "/us/usc/t16"), ("chapter", "/us/usc/t16/ch1"), ...)`. Headings are
    deliberately not captured: streaming prunes sibling `<num>`/`<heading>` nodes
    before later sections are reached, so heading text comes from the TOC pass."""

    schema_version: str = ""
    """e.g. `uslm-1.0.15` — carried so ingest can record it per title version."""


@dataclass(frozen=True, slots=True)
class StructureRecord:
    """One structural container above the section — chapter, subchapter, part, …

    Emitted by the TOC pass in document pre-order (parents before their children),
    which is the order a tree can be inserted in. Read off the *structural elements*
    rather than the `<toc>` element: structural markup is near-identical across USLM
    1.x and 2.x, while `<toc>` is one of the three things OLRC changed in 2.x
    (ADR-0006).
    """

    identifier: str
    """`/us/usc/t16/ch1/schVI`. Cross-release identity, same as a section's."""

    level: str
    """The element's local name: `title`, `chapter`, `subchapter`, `part`, `subpart`, …
    Deliberately free text, not an enum — the level vocabulary differs per title
    (Title 49 has `subtitle`, Title 16 does not) and per schema generation."""

    num: str | None
    num_value: str | None
    heading: str | None
    status: str | None
    """`reserved` and friends. Title 16's only `reserved` is on a subchapter, which
    is exactly why status can't be modelled as a section-only field (gotcha 13)."""

    guid: str | None
    """`@id` — pins (node, release point), like any other guid (ADR-0003)."""

    parent_identifier: str | None
    """None for the title root."""

    seq: int
    """Document order among siblings sharing a parent."""

    depth: int
    """0 for the title root; 1 for its children; … Cheap breadcrumb/indent hint."""


@dataclass(frozen=True, slots=True)
class DocumentMeta:
    """`<meta>` plus root attributes of one USLM title document."""

    identifier: str
    """Root `@identifier`, e.g. `/us/usc/t16`."""

    schema_version: str
    uslm_version: str
    doc_number: str | None = None
    doc_title: str | None = None
    doc_publication_name: str | None = None
    release_label: str | None = None
    """Parsed out of `docPublicationName` (`Online@119-102not101` -> `119-102not101`).
    None when the document is not a release-point publication — the USLM 2.x samples
    say only `Online`."""

    is_positive_law: bool | None = None
    created: str | None = None
    converter: str | None = None
    extra: dict[str, str] = field(default_factory=dict)
