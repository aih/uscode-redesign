"""The dedupe key: section XML minus its guids (ADR-0007).

Guids are regenerated at every release point by design, so hashing raw XML
deduplicates nothing across release points — measured, 0 of Title 16's 5,095
sections had identical raw XML between 119-99 and 119-102not101, while 5,093 were
identical once guids were removed.
"""

import hashlib
import re
from io import BytesIO

from ingest import iter_sections

USLM1 = "http://xml.house.gov/schemas/uslm/1.0"


def _document(guid_suffix: str, text: str = "The Secretary shall act.") -> BytesIO:
    """A minimal one-section USLM 1.x document, guids parameterized."""
    return BytesIO(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<uscDoc xmlns="{USLM1}" identifier="/us/usc/t16">
  <main>
    <title identifier="/us/usc/t16">
      <chapter identifier="/us/usc/t16/ch1" id="idchap{guid_suffix}">
        <section identifier="/us/usc/t16/s1" id="idsec{guid_suffix}">
          <num value="1">§ 1.</num>
          <heading>Establishment</heading>
          <subsection identifier="/us/usc/t16/s1/a" id="idsub{guid_suffix}">
            <content>{text}</content>
          </subsection>
        </section>
      </chapter>
    </title>
  </main>
</uscDoc>
""".encode()
    )


def _only_section(guid_suffix: str, text: str = "The Secretary shall act."):
    (section,) = iter_sections(_document(guid_suffix, text))
    return section


def test_content_key_drops_every_guid():
    section = _only_section("aaaa")

    assert 'id="idsec' in section.xml  # the stored XML keeps them, verbatim
    assert not re.search(r'\bid="', section.content_key)


def test_content_key_keeps_everything_else_verbatim():
    section = _only_section("aaaa")

    assert section.content_key == re.sub(r' id="id\w+"', "", section.xml)


def test_regenerated_guids_alone_do_not_make_a_new_version():
    """The whole point: same text, new release point, new guids — one version."""
    old = _only_section("aaaa")
    new = _only_section("bbbb")

    assert old.xml != new.xml
    assert old.guid != new.guid
    assert _hash(old) == _hash(new)


def test_a_real_amendment_still_makes_a_new_version():
    old = _only_section("aaaa")
    amended = _only_section("bbbb", text="The Secretary shall not act.")

    assert _hash(old) != _hash(amended)


def test_guids_survive_content_key_computation(slice_path):
    """`_content_key` strips `@id` off the live tree and puts it back; if the
    restore ever broke, guid_map would silently lose entries."""
    sections = list(iter_sections(slice_path))

    assert all(section.guid for section in sections)
    assert all(section.guid_refs for section in sections)
    assert all('id="' in section.xml for section in sections)


def _hash(section) -> bytes:
    return hashlib.sha256(section.content_key.encode("utf-8")).digest()
