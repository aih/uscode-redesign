"""Polite single-title downloads from uscode.house.gov.

Scope is deliberately one zip at a time: the resumable full-corpus downloader is
Session 6 / PLAN Day 2-3. What lives here is what the release-point ingest needs
— fetch `xml_usc16@119-99.zip`, keep it, unpack the title XML — plus the etiquette
every fetch in this project owes the source (CLAUDE.md "External source etiquette"):
sequential requests, ~1 req/sec, descriptive User-Agent, and cache on disk so a
re-run never re-downloads.
"""

from __future__ import annotations

import hashlib
import time
import urllib.request
import zipfile
from pathlib import Path

from ingest.inventory import USER_AGENT, title_zip_url

DOWNLOAD_DIR = Path("data/releases")
MIN_REQUEST_INTERVAL = 1.0  # seconds between requests to uscode.house.gov

_last_request_at = 0.0


class DownloadError(RuntimeError):
    """A download or unpack that didn't produce what was asked for."""


def download_title_zip(
    release_label: str,
    title_num: str,
    *,
    dest_dir: Path = DOWNLOAD_DIR,
    force: bool = False,
) -> Path:
    """Fetch one title's XML zip for one release point into `data/releases/{label}/`."""
    url = title_zip_url(release_label, title_num)
    target_dir = dest_dir / release_label
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / url.rsplit("/", 1)[-1]

    if target.exists() and not force:
        return target

    partial = target.with_suffix(target.suffix + ".part")
    _throttle()
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=300) as response:  # noqa: S310 - fixed https host
        with open(partial, "wb") as handle:
            while chunk := response.read(1 << 20):
                handle.write(chunk)
    # Rename only once the body is complete, so an interrupted download can never
    # be mistaken for a cached one on the next run.
    partial.replace(target)
    return target


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


def _throttle() -> None:
    global _last_request_at
    elapsed = time.monotonic() - _last_request_at
    if elapsed < MIN_REQUEST_INTERVAL:
        time.sleep(MIN_REQUEST_INTERVAL - elapsed)
    _last_request_at = time.monotonic()
