"""Parser selection: sniff the file, hand back the right `UslmParser`.

This is the only place that maps a schema generation to an implementation. Ingest
code calls `parser_for(path)` and then talks to the protocol — it never names
`Uslm1Parser` or `Uslm2Parser`, so the day OLRC flips to USLM 2.x, ingest keeps
working (PLAN.md Day 7).
"""

from __future__ import annotations

from typing import Iterator

from ingest.base import UslmParser
from ingest.detect import UnknownUslmSchemaError, UslmVersion, XmlSource, sniff_schema
from ingest.records import DocumentMeta, SectionRecord, StructureRecord
from ingest.uslm1 import Uslm1Parser
from ingest.uslm2 import Uslm2Parser

PARSERS: dict[UslmVersion, type[UslmParser]] = {
    UslmVersion.V1: Uslm1Parser,
    UslmVersion.V2: Uslm2Parser,
}


def parser_for(source: XmlSource) -> UslmParser:
    """Return a parser for `source`, chosen by its detected USLM version."""
    version = sniff_schema(source).version
    parser_class = PARSERS.get(version)
    if parser_class is None:  # pragma: no cover - unreachable while PARSERS is total
        raise UnknownUslmSchemaError(f"no parser registered for USLM {version}")
    return parser_class()


def iter_sections(source: XmlSource) -> Iterator[SectionRecord]:
    """Stream sections from `source`, schema chosen automatically."""
    return parser_for(source).iter_sections(source)


def iter_structure(source: XmlSource) -> Iterator[StructureRecord]:
    """Stream the hierarchy above the sections, schema chosen automatically."""
    return parser_for(source).iter_structure(source)


def parse_meta(source: XmlSource) -> DocumentMeta:
    """Read document metadata from `source`, schema chosen automatically."""
    return parser_for(source).parse_meta(source)
