"""Polite, verifying downloads from uscode.house.gov.

Two layers live here:

  * `fetch_zip` — one HTTP GET of one zip, streamed to disk, hashed while it
    streams, validated as a real zip, with bounded retries and backoff. It
    returns a `FetchResult` rather than raising, because "this title does not
    exist at this release point" is an *answer* the backfill records, not an
    error that should stop a 3,000-file run.
  * `download_title_zip` / `extract_title_xml` — the single-title convenience
    used by `python -m ingest fetch` and `make dev-data`.

The bulk, resumable orchestration on top of this is `ingest.backfill`.

Etiquette (CLAUDE.md "External source etiquette") is enforced here so no caller
can forget it: sequential requests, ~1 req/sec across the whole process,
descriptive User-Agent, and cache on disk so a re-run never re-downloads.

Ported from `loadusc-xcitedb/loadusc/downloadusc.py`; docs/prior-art.md §1
records what was kept and what changed, ADR-0012 why.
"""

from __future__ import annotations

import hashlib
import http.client
import time
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from ingest.inventory import USER_AGENT, title_zip_url

DOWNLOAD_DIR = Path("data/releases")
MIN_REQUEST_INTERVAL = 1.0  # seconds between requests to uscode.house.gov
DEFAULT_ATTEMPTS = 4
BACKOFF_BASE = 2.0  # seconds; doubled per retry
BACKOFF_CAP = 60.0

_last_request_at = 0.0

#: `(request, timeout) -> context manager yielding a file-like response`.
#: Injected by tests so nothing in the suite touches the network.
Opener = Callable[[urllib.request.Request, float], Any]


class DownloadError(RuntimeError):
    """A download or unpack that didn't produce what was asked for."""


class FetchStatus(StrEnum):
    """Outcome of one `fetch_zip`. A closed set we own (unlike USLM `@status`)."""

    OK = "ok"
    """Downloaded, or already on disk, and it is a valid zip."""

    UNAVAILABLE = "unavailable"
    """The server answered, and the answer is that there is no such file — a 404,
    or the HTTP 200 HTML error page uscode.house.gov serves for a missing zip.
    Recorded and never retried on a later run without `--retry-unavailable`."""

    FAILED = "failed"
    """Transport or server-side failure after exhausting retries. Retried freely
    on the next run, because it says nothing about whether the file exists."""


@dataclass(frozen=True, slots=True)
class FetchResult:
    url: str
    status: FetchStatus
    path: Path | None = None
    sha256: str | None = None
    bytes: int = 0
    http_status: int | None = None
    attempts: int = 0
    cached: bool = False
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status is FetchStatus.OK


def fetch_zip(
    url: str,
    target: Path,
    *,
    attempts: int = DEFAULT_ATTEMPTS,
    force: bool = False,
    timeout: float = 300.0,
    opener: Opener | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> FetchResult:
    """GET `url` into `target`, verifying it is a zip. Never raises on a bad fetch.

    The body streams straight to a `.part` file and is hashed on the way through,
    so a 500 MB title costs one pass and a constant amount of memory —
    `downloadusc.py` held each zip in memory twice (`io.BytesIO(r.content)` for
    the validity check, again for the extract).

    `target` is only created by renaming the completed `.part`, so an interrupted
    run can never leave a truncated file that the next run mistakes for a cached
    one.
    """
    if target.exists() and not force:
        return FetchResult(
            url=url,
            status=FetchStatus.OK,
            path=target,
            sha256=sha256_file(target),
            bytes=target.stat().st_size,
            cached=True,
            detail="already on disk",
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    last_detail = ""
    last_http_status: int | None = None

    for attempt in range(1, attempts + 1):
        throttle()
        try:
            digest, size, http_status = _stream_to(url, partial, timeout, opener)
        except urllib.error.HTTPError as exc:
            last_http_status = exc.code
            last_detail = f"HTTP {exc.code} {exc.reason}"
            # A 404 is a settled answer: OLRC does not have this title at this
            # release point. Retrying it 20 times, as the original did, only
            # burns the source's goodwill.
            if exc.code == 404:
                _unlink(partial)
                return FetchResult(
                    url=url,
                    status=FetchStatus.UNAVAILABLE,
                    http_status=exc.code,
                    attempts=attempt,
                    detail=last_detail,
                )
            if exc.code < 500 and exc.code != 429:
                _unlink(partial)
                return FetchResult(
                    url=url,
                    status=FetchStatus.FAILED,
                    http_status=exc.code,
                    attempts=attempt,
                    detail=last_detail,
                )
        except (
            urllib.error.URLError,
            TimeoutError,
            OSError,
            # A truncated chunked response raises http.client.IncompleteRead, which
            # descends from HTTPException — *not* from OSError. Without this it
            # escapes the retry loop and kills an entire multi-hour run; it did,
            # at 1,164 of 3,197 files. It is exactly the transient this loop exists
            # to absorb.
            http.client.HTTPException,
        ) as exc:
            last_detail = f"{type(exc).__name__}: {exc}"
        else:
            last_http_status = http_status
            if zipfile.is_zipfile(partial):
                partial.replace(target)
                return FetchResult(
                    url=url,
                    status=FetchStatus.OK,
                    path=target,
                    sha256=digest,
                    bytes=size,
                    http_status=http_status,
                    attempts=attempt,
                )
            # 200 with a non-zip body is uscode.house.gov's HTML error page. One
            # confirming retry covers a genuinely truncated transfer; beyond that
            # the file is simply not published under this name.
            last_detail = f"HTTP {http_status}: response is not a zip ({size:,} bytes)"
            if attempt >= 2:
                _unlink(partial)
                return FetchResult(
                    url=url,
                    status=FetchStatus.UNAVAILABLE,
                    http_status=http_status,
                    attempts=attempt,
                    detail=last_detail,
                )

        if attempt < attempts:
            sleep(min(BACKOFF_BASE * 2 ** (attempt - 1), BACKOFF_CAP))

    _unlink(partial)
    return FetchResult(
        url=url,
        status=FetchStatus.FAILED,
        http_status=last_http_status,
        attempts=attempts,
        detail=last_detail or "exhausted retries",
    )


def download_title_zip(
    release_label: str,
    title_num: str,
    *,
    dest_dir: Path = DOWNLOAD_DIR,
    force: bool = False,
) -> Path:
    """Fetch one title's XML zip for one release point into `data/releases/{label}/`.

    Raises on failure — this is the interactive single-title path, where a caller
    wants to know immediately. The bulk path uses `fetch_zip` and records instead.
    """
    result = fetch_zip(
        title_zip_url(release_label, title_num),
        zip_target(release_label, title_num, dest_dir=dest_dir),
        force=force,
    )
    if not result.ok or result.path is None:
        raise DownloadError(f"{result.url}: {result.status} — {result.detail}")
    return result.path


def zip_target(release_label: str, title_num: str, *, dest_dir: Path = DOWNLOAD_DIR) -> Path:
    """Where one title's zip for one release point belongs on disk."""
    url = title_zip_url(release_label, title_num)
    return dest_dir / release_label / url.rsplit("/", 1)[-1]


def extract_title_xml(zip_path: Path, *, dest_dir: Path | None = None) -> Path:
    """Unpack the single `.xml` member of a title zip; return its path."""
    dest = dest_dir or zip_path.parent
    with zipfile.ZipFile(zip_path) as archive:
        members = [n for n in archive.namelist() if n.lower().endswith(".xml")]
        if len(members) != 1:
            raise DownloadError(f"{zip_path}: expected one .xml member, found {members}")
        member = members[0]
        extracted = Path(archive.extract(member, path=dest))
    return extracted


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stream_to(
    url: str, partial: Path, timeout: float, opener: Opener | None
) -> tuple[str, int, int | None]:
    """Stream one response to `partial`, hashing as it goes. Returns (sha256, bytes, status)."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    digest = hashlib.sha256()
    size = 0
    with (opener or _default_opener)(request, timeout) as response:
        http_status = getattr(response, "status", None)
        with open(partial, "wb") as handle:
            while chunk := response.read(1 << 20):
                digest.update(chunk)
                handle.write(chunk)
                size += len(chunk)
    return digest.hexdigest(), size, http_status


@contextmanager
def _default_opener(request: urllib.request.Request, timeout: float) -> Iterator[Any]:
    # Certificate verification stays on. loadusc-xcitedb disabled it globally for
    # this host (`verify=False` plus a warning suppressor); the certificate
    # validates, and if it stops we pin a CA rather than stop checking.
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed https host
        yield response


def _unlink(path: Path) -> None:
    path.unlink(missing_ok=True)


def throttle() -> None:
    """Hold every caller to ~1 request/second at uscode.house.gov.

    Public because the budget is per *host*, not per module: `_last_request_at`
    is process-global, so the classification scraper calling this is what keeps
    a run that fetches zips and tables together inside one rate.
    """
    global _last_request_at
    elapsed = time.monotonic() - _last_request_at
    if elapsed < MIN_REQUEST_INTERVAL:
        time.sleep(MIN_REQUEST_INTERVAL - elapsed)
    _last_request_at = time.monotonic()
