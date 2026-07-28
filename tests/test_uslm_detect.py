"""Schema detection (ADR-0004): namespace decides, schemaLocation labels."""

import io

import pytest

from ingest import (
    USLM1_NAMESPACE,
    USLM2_NAMESPACE,
    UnknownUslmSchemaError,
    Uslm1Parser,
    Uslm2Parser,
    UslmVersion,
    detect_uslm_version,
    parser_for,
    sniff_schema,
)

USLM1_ROOT = (
    '<uscDoc xsi:schemaLocation="http://xml.house.gov/schemas/uslm/1.0 USLM-1.0.15.xsd"'
    ' identifier="/us/usc/t16" xmlns="http://xml.house.gov/schemas/uslm/1.0"'
    ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"/>'
)
USLM2_ROOT = (
    '<uscDoc xsi:schemaLocation="http://schemas.gpo.gov/xml/uslm'
    ' https://www.govinfo.gov/schemas/xml/uslm/uslm-2.0.12.xsd"'
    ' identifier="/us/usc/t1" xmlns="http://schemas.gpo.gov/xml/uslm"'
    ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"/>'
)


def source(xml: str) -> io.BytesIO:
    return io.BytesIO(xml.encode("utf-8"))


def test_detects_uslm1_from_repo_slice(slice_path):
    assert detect_uslm_version(slice_path) is UslmVersion.V1


def test_detects_uslm2_from_repo_sample(uslm2_usc01):
    assert detect_uslm_version(uslm2_usc01) is UslmVersion.V2


def test_schema_info_reports_point_version(slice_path, uslm2_usc01):
    one = sniff_schema(slice_path)
    assert (one.namespace, one.schema_version) == (USLM1_NAMESPACE, "uslm-1.0.15")
    assert (one.root_tag, one.identifier) == ("uscDoc", "/us/usc/t16")

    two = sniff_schema(uslm2_usc01)
    assert (two.namespace, two.schema_version) == (USLM2_NAMESPACE, "uslm-2.0.12")
    assert two.identifier == "/us/usc/t1"


def test_namespace_decides_even_without_schema_location():
    """schemaLocation is advisory; the namespace alone must select the parser."""
    xml = USLM1_ROOT.replace(
        'xsi:schemaLocation="http://xml.house.gov/schemas/uslm/1.0 USLM-1.0.15.xsd" ', ""
    )
    info = sniff_schema(source(xml))
    assert info.version is UslmVersion.V1
    assert info.schema_version == "uslm-1.x"


def test_unknown_namespace_is_an_error():
    xml = '<uscDoc xmlns="http://example.invalid/uslm/9"/>'
    with pytest.raises(UnknownUslmSchemaError, match="unrecognized USLM namespace"):
        detect_uslm_version(source(xml))


def test_sniffing_reads_only_the_root_start_tag():
    """A 32 MB title must cost one buffer to detect, so nothing after the root
    element may be required — here, the body is never closed."""
    truncated = USLM2_ROOT.replace("/>", "><main><title>")
    assert detect_uslm_version(source(truncated)) is UslmVersion.V2


@pytest.mark.parametrize(
    "xml,expected",
    [(USLM1_ROOT, Uslm1Parser), (USLM2_ROOT, Uslm2Parser)],
)
def test_parser_for_selects_by_version(xml, expected):
    assert isinstance(parser_for(source(xml)), expected)


def test_parsers_declare_matching_namespaces():
    assert Uslm1Parser.namespace == USLM1_NAMESPACE
    assert Uslm2Parser.namespace == USLM2_NAMESPACE
    assert Uslm1Parser.uslm_version is UslmVersion.V1
    assert Uslm2Parser.uslm_version is UslmVersion.V2
