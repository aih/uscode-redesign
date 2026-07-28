"""Schema sniffing: which USLM version is this file?

The detection rule (ADR-0004), derived from the repo samples:

    root element namespace URI
      http://xml.house.gov/schemas/uslm/1.0  -> USLM 1.x
      http://schemas.gpo.gov/xml/uslm        -> USLM 2.x

The exact point version comes from `xsi:schemaLocation` (`USLM-1.0.15.xsd`,
`uslm-2.0.12.xsd`) and is advisory — it names the release, it does not select the
parser. Only the root start tag is read, so sniffing a 32 MB title costs nothing.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import IO, Iterator

from lxml import etree

USLM1_NAMESPACE = "http://xml.house.gov/schemas/uslm/1.0"
USLM2_NAMESPACE = "http://schemas.gpo.gov/xml/uslm"

XmlSource = str | Path | IO[bytes]


class UslmVersion(StrEnum):
    """Major schema generation. The parser is selected on this and nothing else."""

    V1 = "1"
    V2 = "2"


class UnknownUslmSchemaError(ValueError):
    """Raised when a document's root namespace matches no known USLM generation."""


@dataclass(frozen=True, slots=True)
class SchemaInfo:
    version: UslmVersion
    namespace: str
    schema_version: str
    """Point version for the record, e.g. `uslm-1.0.15`; `uslm-1.x` if unstated."""

    root_tag: str
    """Local name of the root element, e.g. `uscDoc`."""

    identifier: str | None
    """Root `@identifier`, e.g. `/us/usc/t16`."""


_NAMESPACE_VERSIONS = {
    USLM1_NAMESPACE: UslmVersion.V1,
    USLM2_NAMESPACE: UslmVersion.V2,
}

_SCHEMA_LOCATION_XSD = re.compile(r"uslm-?(\d+(?:\.\d+)+)\.xsd", re.IGNORECASE)
_XSI_SCHEMA_LOCATION = "{http://www.w3.org/2001/XMLSchema-instance}schemaLocation"


@contextmanager
def open_source(source: XmlSource) -> Iterator[IO[bytes]]:
    """Yield a binary stream for `source`, rewound and ready to parse.

    Paths are opened and closed here; already-open streams are rewound and left
    open for the caller, so a caller can sniff and then parse the same handle.
    """
    if isinstance(source, (str, Path)):
        with open(source, "rb") as handle:
            yield handle
    else:
        source.seek(0)
        yield source


def sniff_schema(source: XmlSource) -> SchemaInfo:
    """Read only the root start tag and report the document's schema."""
    with open_source(source) as handle:
        for _event, element in etree.iterparse(handle, events=("start",)):
            return _schema_info(element)
    raise UnknownUslmSchemaError("document has no root element")


def detect_uslm_version(source: XmlSource) -> UslmVersion:
    """Return the USLM generation of `source` (the sniffer of PLAN.md §2)."""
    return sniff_schema(source).version


def _schema_info(root: etree._Element) -> SchemaInfo:
    qname = etree.QName(root)
    namespace = qname.namespace or ""
    version = _NAMESPACE_VERSIONS.get(namespace)
    if version is None:
        raise UnknownUslmSchemaError(
            f"unrecognized USLM namespace {namespace!r} on root element "
            f"{qname.localname!r}; known namespaces are "
            f"{USLM1_NAMESPACE!r} (USLM 1.x) and {USLM2_NAMESPACE!r} (USLM 2.x)"
        )
    return SchemaInfo(
        version=version,
        namespace=namespace,
        schema_version=_schema_version(root.get(_XSI_SCHEMA_LOCATION), version),
        root_tag=qname.localname,
        identifier=root.get("identifier"),
    )


def _schema_version(schema_location: str | None, version: UslmVersion) -> str:
    if schema_location:
        match = _SCHEMA_LOCATION_XSD.search(schema_location)
        if match:
            return f"uslm-{match.group(1)}"
    return f"uslm-{version.value}.x"
