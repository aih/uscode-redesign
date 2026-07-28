"""USLM → HTML rendering.

The renderer is the one place outside the parsers that knows USLM element names
(see `test_architecture.py`), so what matters most is that it degrades rather than
breaks when it meets one it doesn't: USLM 2.x adds elements, and a reader that
silently dropped their text would be worse than one that renders a plain div.
"""

from web.uslm_html import render_fragment

USLM1 = "http://xml.house.gov/schemas/uslm/1.0"

SECTION = f"""<section xmlns="{USLM1}" identifier="/us/usc/t16/s1" id="idaaa"
                       class="section">
  <num value="1">§ 1.</num>
  <heading>Establishment</heading>
  <subsection identifier="/us/usc/t16/s1/a" class="indent1">
    <num value="a">(a)</num>
    <content>The Secretary shall <ref href="/us/usc/t16/s2">act</ref>.</content>
  </subsection>
  <sourceCredit>(Aug. 25, 1916, ch. 408, 39 Stat. 535.)</sourceCredit>
</section>"""


def test_identifiers_become_anchors():
    html = render_fragment(SECTION)

    assert 'id="/us/usc/t16/s1"' in html
    assert 'id="/us/usc/t16/s1/a"' in html


def test_olrc_class_names_are_carried_through():
    """PLAN §4: the XML already carries the classes `usctitle.css` styles, so
    display fidelity is mostly a matter of not discarding them."""
    html = render_fragment(SECTION)

    assert "indent1" in html
    assert "uslm-sourceCredit" in html


def test_the_target_provision_is_marked():
    html = render_fragment(SECTION, target_identifier="/us/usc/t16/s1/a")

    assert "target" in html
    assert html.count("target") == 1


def test_refs_become_links():
    assert '<a class="uslm-ref" href="/us/usc/t16/s2">act</a>' in render_fragment(SECTION)


def test_tails_are_not_dropped():
    """Text after a child element — the period following a <ref> — is easy to lose
    and impossible to notice in a diff."""
    assert "act</a>." in render_fragment(SECTION)


def test_text_is_escaped():
    xml = f'<content xmlns="{USLM1}">a &lt; b &amp; c</content>'

    assert "a &lt; b &amp; c" in render_fragment(xml)


def test_an_unknown_element_renders_as_a_container_keeping_its_text():
    """A USLM 2.x element this renderer has never seen must not swallow its own
    content."""
    xml = f'<transmutation xmlns="{USLM1}" class="odd">kept</transmutation>'
    html = render_fragment(xml)

    assert html.startswith("<div ")
    assert "uslm-transmutation" in html
    assert "odd" in html
    assert "kept" in html


def test_status_is_rendered_as_data_and_class():
    xml = f'<section xmlns="{USLM1}" status="repealed"><num>§ 671.</num></section>'
    html = render_fragment(xml)

    assert 'data-status="repealed"' in html
    assert "status-repealed" in html
