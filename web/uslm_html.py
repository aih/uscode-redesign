"""USLM → HTML, keeping OLRC's own class names.

PLAN §4: the XML already carries the `@class`/`@style` values `usctitle.css` is
written against, so display fidelity is mostly a matter of *not throwing them
away*. This maps USLM elements onto HTML elements, copies `@class` and `@style`
through untouched, and anchors every element that has an `@identifier` so a
provision URL can scroll to it.

It is schema-agnostic — it matches on local names shared by USLM 1.x and 2.x and
falls back to a `<div>`, so a 2.x element it has never seen renders as a container
rather than vanishing. This file and the templates beside it are the presentation
layer; the page *around* a fragment is built in `web/reader.py`.
"""

from __future__ import annotations

from html import escape

from lxml import etree

# Local name → HTML tag. Anything absent renders as <div>, keeping its classes.
_TAGS = {
    "num": "span",
    "heading": "h2",
    "subheading": "h3",
    "chapeau": "p",
    "content": "p",
    "continuation": "p",
    "p": "p",
    "text": "p",
    "sourceCredit": "p",
    "note": "aside",
    "notes": "aside",
    "quotedContent": "blockquote",
    "quotedText": "blockquote",
    "ref": "a",
    "date": "span",
    "term": "em",
    "i": "em",
    "b": "strong",
    "inline": "span",
    "table": "table",
    "tr": "tr",
    "td": "td",
    "th": "th",
    "thead": "thead",
    "tbody": "tbody",
    "list": "ul",
    "listItem": "li",
    "listContent": "div",
}

_VOID = {"br", "img"}


def render_fragment(xml: str, *, target_identifier: str | None = None) -> str:
    """Render one USLM element (and its children) as an HTML fragment."""
    root = etree.fromstring(xml.encode("utf-8"))
    return _render(root, target_identifier)


def _render(element: etree._Element, target: str | None) -> str:
    local = etree.QName(element).localname
    tag = _TAGS.get(local, "div")
    identifier = element.get("identifier")

    classes = [f"uslm-{local}"]
    if element.get("class"):
        classes.append(element.get("class", ""))
    if element.get("status"):
        classes.append(f"status-{element.get('status')}")
    if target and identifier == target:
        classes.append("target")

    attributes = [f'class="{escape(" ".join(classes))}"']
    if identifier:
        attributes.append(f'id="{escape(identifier)}"')
    if element.get("style"):
        attributes.append(f'style="{escape(element.get("style", ""))}"')
    if tag == "a":
        attributes.append(f'href="{escape(element.get("href", "#"))}"')
    if element.get("status"):
        attributes.append(f'data-status="{escape(element.get("status", ""))}"')

    if tag in _VOID:  # pragma: no cover - USLM has no void elements we map
        return f"<{tag} {' '.join(attributes)}>"

    parts = [escape(element.text or "")]
    for child in element:
        parts.append(_render(child, target))
        parts.append(escape(child.tail or ""))
    return f"<{tag} {' '.join(attributes)}>{''.join(parts)}</{tag}>"
