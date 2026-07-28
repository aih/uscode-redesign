"""Ingest layer: fetch release points, parse USLM, split titles into sections.

The public surface is schema-agnostic on purpose — callers detect, get a parser,
and consume `SectionRecord`s (CLAUDE.md architecture rule 2).
"""

from ingest.base import UslmParser
from ingest.detect import (
    USLM1_NAMESPACE,
    USLM2_NAMESPACE,
    SchemaInfo,
    UnknownUslmSchemaError,
    UslmVersion,
    detect_uslm_version,
    sniff_schema,
)
from ingest.parser import iter_sections, parse_meta, parser_for
from ingest.records import DocumentMeta, GuidRef, NoteRecord, SectionRecord
from ingest.uslm1 import Uslm1Parser
from ingest.uslm2 import Uslm2Parser

__all__ = [
    "USLM1_NAMESPACE",
    "USLM2_NAMESPACE",
    "DocumentMeta",
    "GuidRef",
    "NoteRecord",
    "SchemaInfo",
    "SectionRecord",
    "UnknownUslmSchemaError",
    "Uslm1Parser",
    "Uslm2Parser",
    "UslmParser",
    "UslmVersion",
    "detect_uslm_version",
    "iter_sections",
    "parse_meta",
    "parser_for",
    "sniff_schema",
]
