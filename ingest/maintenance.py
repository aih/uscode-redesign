"""Recognise uscode.house.gov's maintenance notice.

While OLRC maintains the site it answers its pages with a notice instead of
their content. Every parser that reads one of those pages then finds nothing
it recognises and reports that the markup has probably changed, which is the
wrong diagnosis and sends whoever reads it to fix a parser that is not broken.

`maintenance_notice` is consulted only after a parse has already failed, or
with the body of an HTTP error, so a release-point description or a table row
that happens to mention maintenance can never turn a good page into an error.
The patterns are phrases rather than the bare word for the same reason.
"""

from __future__ import annotations

import html as html_lib
import re
import urllib.error

_SCRIPT_RE = re.compile(r"<(script|style)\b.*?</\1\s*>", re.DOTALL | re.IGNORECASE)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_BLOCK_TAG_RE = re.compile(
    r"</?(?:p|div|h[1-6]|li|ul|ol|br|hr|title|head|body|table|tr|td|th|section|header"
    r"|footer|main|article|nav|center|blockquote|pre)\b[^>]*>",
    re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"[ \t\r\f\v]+")

_NOTICE_RE = re.compile(
    r"\b(?:under|undergoing|scheduled|planned|routine|system|site|website|for|performing"
    r"|perform|to|during)\s+(?:\w+\s+){0,2}?maintenance\b"
    r"|\bmaintenance\s+(?:is|will|in\s+progress|window|period|notice|mode|outage)\b",
    re.IGNORECASE,
)
_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+")

NOTICE_LIMIT = 300
"""Characters of the notice kept in the error, which `record_source_check`
truncates to 500 with the URL in front of it."""


# The exit code `check`, `classification-check`, `inventory` and
# `classification` return when the source answered with its maintenance
# notice: sysexits.h's EX_TEMPFAIL. deploy/update-corpus.sh reads it to skip
# the steps that need the source instead of failing the run.
EXIT_MAINTENANCE = 75


def is_maintenance_error(error: str | None) -> bool:
    """Whether a recorded error string is a SourceUnderMaintenance."""
    return bool(error) and error.startswith("SourceUnderMaintenance:")


class SourceUnderMaintenance(RuntimeError):
    """uscode.house.gov answered with its maintenance notice instead of the page.

    The class name is the prefix of the recorded error
    (`SourceUnderMaintenance: …`), which is how `/api/v1/status` tells this
    failure from the others.
    """

    def __init__(self, url: str, notice: str) -> None:
        self.url = url
        self.notice = notice
        super().__init__(
            f"uscode.house.gov is under maintenance — {url} returned its maintenance "
            f"notice instead of the page: {notice!r}"
        )


def visible_text(html: str) -> list[str]:
    """The page's text as a reader sees it, one entry per block of the page: no
    scripts, styles, comments or tags."""
    text = _COMMENT_RE.sub(" ", _SCRIPT_RE.sub(" ", html))
    text = _TAG_RE.sub(" ", _BLOCK_TAG_RE.sub("\n", text))
    lines = (
        _SPACE_RE.sub(" ", line).strip() for line in html_lib.unescape(text).split("\n")
    )
    return [line for line in lines if line]


def maintenance_notice(html: str) -> str | None:
    """The sentence of `html` that announces maintenance, or None.

    The sentence is returned rather than a flag so the recorded error says what
    OLRC said, often including when the site will be back. Of several, the
    longest is kept, so a "Site Maintenance" heading gives way to the
    paragraph under it.
    """
    found: list[str] = []
    for block in visible_text(html):
        match = _NOTICE_RE.search(block)
        if match is None:
            continue
        start = 0
        for boundary in _SENTENCE_END_RE.finditer(block, 0, match.start()):
            start = boundary.end()
        end_match = _SENTENCE_END_RE.search(block, match.end())
        end = end_match.start() if end_match else len(block)
        found.append(block[start:end].strip())
    if not found:
        return None
    sentence = max(found, key=len)
    if len(sentence) > NOTICE_LIMIT:
        sentence = sentence[: NOTICE_LIMIT - 1].rstrip() + "…"
    return sentence


def raise_if_maintenance(html: str, url: str) -> None:
    """Raise `SourceUnderMaintenance` when `html` is the maintenance notice."""
    notice = maintenance_notice(html)
    if notice is not None:
        raise SourceUnderMaintenance(url, notice)


def raise_if_maintenance_response(error: urllib.error.HTTPError, url: str) -> None:
    """The same check on an HTTP error's body (a 503 carrying the notice).

    Reads the body, so call it once and re-raise `error` if it returns.
    """
    try:
        body = error.read()
    except Exception:  # noqa: BLE001 - a body we cannot read is not a notice
        return
    if not body:
        return
    charset = error.headers.get_content_charset() if error.headers else None
    raise_if_maintenance(body.decode(charset or "utf-8", errors="replace"), url)
