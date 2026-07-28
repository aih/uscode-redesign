"""USLM → HTML, keeping OLRC's own class names.

PLAN §4: the XML already carries the `@class`/`@style` values `usctitle.css` is
written against, so display fidelity is mostly a matter of *not throwing them
away*. This maps USLM elements onto HTML elements, copies `@class` and `@style`
through untouched, and anchors every element that has an `@identifier` so a
provision URL can scroll to it.

Deliberately small: it is the minimum that makes `?format=html` real for the Day-1
demo, not the reader UI (Session 5). It is also schema-agnostic — it matches on
local names shared by USLM 1.x and 2.x and falls back to a `<div>`, so a 2.x
element it has never seen renders as a container rather than vanishing.
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

PAGE_CSS = """
:root { color-scheme: light dark; }
body { font-family: Georgia, 'Times New Roman', serif; line-height: 1.5;
       max-width: 46rem; margin: 2rem auto; padding: 0 1rem; }
h1 { font-size: 1.4rem; } h2 { font-size: 1.15rem; }
.uslm-num { font-weight: bold; margin-right: .35em; }
[class*="indent"] { margin-left: 1.5rem; }
.indent2 { margin-left: 3rem; } .indent3 { margin-left: 4.5rem; }
.indent4 { margin-left: 6rem; }
.uslm-sourceCredit { font-size: .85rem; color: #666; margin-top: 1rem; }
.uslm-note, .uslm-notes { font-size: .85rem; border-left: 3px solid #ccc;
       padding-left: .75rem; margin: 1rem 0; }
.status { display: inline-block; font-family: system-ui, sans-serif;
       font-size: .7rem; text-transform: uppercase; letter-spacing: .04em;
       border: 1px solid currentColor; border-radius: .2rem; padding: 0 .3em;
       vertical-align: .15em; }
.target { background: rgba(255, 235, 59, .35); outline: 2px solid rgba(255, 193, 7, .8);
       scroll-margin-top: 2rem; }
.meta { font-family: system-ui, sans-serif; font-size: .8rem; color: #666;
       border-bottom: 1px solid #ddd; padding-bottom: .5rem; margin-bottom: 1.5rem; }
"""


def render_fragment(xml: str, *, target_identifier: str | None = None) -> str:
    """Render one USLM element (and its children) as an HTML fragment."""
    root = etree.fromstring(xml.encode("utf-8"))
    return _render(root, target_identifier)


def render_page(
    xml: str,
    *,
    title: str,
    subtitle: str = "",
    target_identifier: str | None = None,
) -> str:
    """A standalone page around `render_fragment` — enough to read a section in a
    browser, and no more; the reader UI is Session 5."""
    return (
        "<!doctype html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{escape(title)}</title><style>{PAGE_CSS}</style></head><body>"
        f'<div class="meta">{subtitle}</div>'
        f"{render_fragment(xml, target_identifier=target_identifier)}"
        "</body></html>"
    )


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
