"""The reader: server-rendered pages over the same `Repository` the API uses.

`web/reader.py` builds the pages, `web/templates/` holds the Jinja, `web/static/`
the one stylesheet, and `web/uslm_html.py` turns USLM into HTML while keeping
OLRC's class names. `web/routes.py` adds the pages that aren't identifier
lookups — the identifier URLs themselves are served by `api/routes.py`, which
negotiates format and hands the HTML case here, so a citation is one URL whether
a person or a program is asking.
"""

from web.reader import render_error, render_home, render_section, render_toc, section_url

__all__ = [
    "render_error",
    "render_home",
    "render_section",
    "render_toc",
    "section_url",
]
