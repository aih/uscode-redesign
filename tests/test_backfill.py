"""The bulk downloader: planning, resumability, and hash-dedupe verification.

Nothing here touches the network. `fetch_zip` takes an `opener`, and every test
serves bytes built in-process by `_zip_bytes`, so the suite exercises the real
streaming, hashing, validation and retry paths against a fake transport rather
than mocking them out.
"""

from __future__ import annotations

import hashlib
import io
import json
import urllib.error
import zipfile
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import pytest

from ingest.backfill import (
    DownloadLedger,
    LedgerEntry,
    baseline_titles,
    plan_backfill,
    run_backfill,
    verify_ledger,
    write_verification,
)
from ingest.download import FetchStatus, fetch_zip
from ingest.inventory import ReleasePointEntry


# --------------------------------------------------------------------------
# Fake transport
# --------------------------------------------------------------------------


def _zip_bytes(payload: bytes = b"<uscDoc/>", name: str = "usc16.xml") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, payload)
    return buffer.getvalue()


class _Response(io.BytesIO):
    status = 200


class FakeServer:
    """Serves canned bodies by URL and counts requests."""

    def __init__(self, bodies: dict[str, bytes] | None = None, default: bytes | None = None):
        self.bodies = bodies or {}
        self.default = default
        self.requests: list[str] = []
        self.raise_times: dict[str, int] = {}

    def opener(self, request, timeout):  # `timeout` unused; the signature is the contract
        return self._open(request.full_url)

    @contextmanager
    def _open(self, url: str):
        self.requests.append(url)
        remaining = self.raise_times.get(url, 0)
        if remaining:
            self.raise_times[url] = remaining - 1
            raise urllib.error.URLError("connection reset")
        if url in self.bodies:
            yield _Response(self.bodies[url])
            return
        if self.default is not None:
            yield _Response(self.default)
            return
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)


@pytest.fixture(autouse=True)
def _no_throttle(monkeypatch):
    """The 1 req/sec pacing is real in production and pointless in tests."""
    monkeypatch.setattr("ingest.download._throttle", lambda: None)


@pytest.fixture
def entries() -> list[ReleasePointEntry]:
    return [
        ReleasePointEntry("113-21", date(2013, 7, 18), ("16", "18"), "u", "", seq=0),
        ReleasePointEntry("113-31", date(2013, 8, 9), ("16",), "u", "", seq=1),
        ReleasePointEntry("113-36", date(2013, 9, 18), ("18", "50a"), "u", "", seq=2),
    ]


# --------------------------------------------------------------------------
# fetch_zip
# --------------------------------------------------------------------------


def test_fetch_streams_hashes_and_validates(tmp_path):
    body = _zip_bytes()
    server = FakeServer(default=body)
    target = tmp_path / "usc16.zip"

    result = fetch_zip("https://example/usc16.zip", target, opener=server.opener)

    assert result.status is FetchStatus.OK
    assert result.bytes == len(body)
    assert target.read_bytes() == body
    # Hashed during the stream, not in a second pass over the file.
    assert result.sha256 == hashlib.sha256(body).hexdigest()


def test_fetch_leaves_no_part_file_behind(tmp_path):
    server = FakeServer(default=_zip_bytes())
    target = tmp_path / "usc16.zip"

    fetch_zip("https://example/usc16.zip", target, opener=server.opener)

    assert list(tmp_path.glob("*.part")) == []


def test_404_is_unavailable_and_is_not_retried(tmp_path):
    """A 404 is a settled answer. The original retried it up to 20 times."""
    server = FakeServer()

    result = fetch_zip(
        "https://example/missing.zip", tmp_path / "m.zip", opener=server.opener, attempts=4
    )

    assert result.status is FetchStatus.UNAVAILABLE
    assert result.http_status == 404
    assert len(server.requests) == 1


def test_html_error_page_with_status_200_is_unavailable(tmp_path):
    """uscode.house.gov answers 200 with an HTML page for a missing zip, so the
    status code alone never settles it — the body has to be a real zip."""
    server = FakeServer(default=b"<html><body>Not found</body></html>")

    result = fetch_zip(
        "https://example/nope.zip", tmp_path / "n.zip", opener=server.opener, attempts=4, sleep=lambda _: None
    )

    assert result.status is FetchStatus.UNAVAILABLE
    assert "not a zip" in result.detail
    # One confirming retry for a truncated transfer, then it stops.
    assert len(server.requests) == 2
    assert not (tmp_path / "n.zip").exists()


def test_transport_error_retries_then_succeeds(tmp_path):
    body = _zip_bytes()
    server = FakeServer(default=body)
    server.raise_times["https://example/usc16.zip"] = 2

    result = fetch_zip(
        "https://example/usc16.zip",
        tmp_path / "usc16.zip",
        opener=server.opener,
        sleep=lambda _: None,
    )

    assert result.status is FetchStatus.OK
    assert result.attempts == 3


def test_exhausted_retries_is_failed_not_unavailable(tmp_path):
    """`failed` and `unavailable` must stay distinct: only the latter is a
    statement about what OLRC publishes, and only the former is retried freely."""
    server = FakeServer(default=_zip_bytes())
    server.raise_times["https://example/usc16.zip"] = 99

    result = fetch_zip(
        "https://example/usc16.zip",
        tmp_path / "usc16.zip",
        opener=server.opener,
        attempts=3,
        sleep=lambda _: None,
    )

    assert result.status is FetchStatus.FAILED
    assert result.attempts == 3


def test_existing_file_is_not_refetched(tmp_path):
    target = tmp_path / "usc16.zip"
    target.write_bytes(_zip_bytes())
    server = FakeServer(default=_zip_bytes())

    result = fetch_zip("https://example/usc16.zip", target, opener=server.opener)

    assert result.cached and result.ok
    assert server.requests == []


# --------------------------------------------------------------------------
# Planning
# --------------------------------------------------------------------------


def test_baseline_titles_is_the_union_of_the_inventory(entries):
    assert baseline_titles(entries) == ("16", "18", "50a")


def test_plan_fetches_the_oldest_release_in_full(entries):
    tasks = plan_backfill(entries)
    baseline = [t for t in tasks if t.baseline]

    # The oldest RP lists only titles 16 and 18, but a delta needs something to
    # apply to — so it is fetched in full.
    assert {t.title_num for t in baseline} == {"16", "18", "50a"}
    assert {t.release_label for t in baseline} == {"113-21"}


def test_plan_follows_titles_affected_for_later_releases(entries):
    tasks = plan_backfill(entries)
    by_release = {}
    for task in tasks:
        by_release.setdefault(task.release_label, set()).add(task.title_num)

    assert by_release["113-31"] == {"16"}
    assert by_release["113-36"] == {"18", "50a"}


def test_plan_is_oldest_first(entries):
    tasks = plan_backfill(entries)
    assert [t.seq for t in tasks] == sorted(t.seq for t in tasks)


def test_plan_is_far_smaller_than_a_full_crawl(entries):
    """The whole point of driving from titlesAffected (gotcha 10)."""
    tasks = plan_backfill(entries)
    naive = len(entries) * len(baseline_titles(entries))
    assert len(tasks) == 3 + 1 + 2  # baseline 3, then 1, then 2
    assert len(tasks) < naive


def test_plan_can_be_restricted_to_a_title(entries):
    tasks = plan_backfill(entries, titles={"16"})
    assert {t.title_num for t in tasks} == {"16"}


def test_plan_normalizes_title_numbers(entries):
    """`--title 5` must match the inventory's `05`."""
    entries = [ReleasePointEntry("113-21", date(2013, 7, 18), ("05",), "u", "", seq=0)]
    tasks = plan_backfill(entries, titles={"5"})
    assert [t.title_num for t in tasks] == ["05"]


# --------------------------------------------------------------------------
# Running and resuming
# --------------------------------------------------------------------------


def test_run_downloads_and_records(tmp_path, entries):
    server = FakeServer(default=_zip_bytes())
    ledger = DownloadLedger(tmp_path / "ledger.json")

    report = run_backfill(
        plan_backfill(entries), ledger, dest_dir=tmp_path, opener=server.opener
    )

    assert report.downloaded == 6
    assert report.failed == 0
    assert len(ledger.entries) == 6
    assert all(e.ok for e in ledger.entries.values())


def test_rerun_skips_everything_already_done(tmp_path, entries):
    server = FakeServer(default=_zip_bytes())
    tasks = plan_backfill(entries)
    ledger = DownloadLedger(tmp_path / "ledger.json")
    run_backfill(tasks, ledger, dest_dir=tmp_path, opener=server.opener)
    before = len(server.requests)

    reloaded = DownloadLedger.load(tmp_path / "ledger.json")
    report = run_backfill(tasks, reloaded, dest_dir=tmp_path, opener=server.opener)

    assert report.skipped == 6
    assert report.downloaded == 0
    assert len(server.requests) == before  # not one extra request


def test_interrupted_run_resumes_from_the_ledger(tmp_path, entries):
    """A partial run leaves a prefix of history done; the next run continues it."""
    server = FakeServer(default=_zip_bytes())
    tasks = plan_backfill(entries)
    ledger = DownloadLedger(tmp_path / "ledger.json")

    first = run_backfill(tasks, ledger, dest_dir=tmp_path, opener=server.opener, limit=2)
    assert first.downloaded == 2

    resumed = DownloadLedger.load(tmp_path / "ledger.json")
    second = run_backfill(tasks, resumed, dest_dir=tmp_path, opener=server.opener)

    assert second.downloaded == 4
    assert len(resumed.entries) == 6


def test_lost_ledger_adopts_files_from_disk(tmp_path, entries):
    """The ledger is a cache; the disk is the truth. Deleting it must cost a
    hashing pass, not a re-download of tens of gigabytes."""
    server = FakeServer(default=_zip_bytes())
    tasks = plan_backfill(entries)
    ledger = DownloadLedger(tmp_path / "ledger.json")
    run_backfill(tasks, ledger, dest_dir=tmp_path, opener=server.opener)
    requests_before = len(server.requests)

    (tmp_path / "ledger.json").unlink()
    rebuilt = DownloadLedger.load(tmp_path / "ledger.json")
    report = run_backfill(tasks, rebuilt, dest_dir=tmp_path, opener=server.opener)

    assert report.adopted == 6
    assert report.downloaded == 0
    assert len(server.requests) == requests_before
    assert all(e.sha256 for e in rebuilt.entries.values())


def test_moved_corpus_resumes_without_redownloading(tmp_path, entries):
    """The mirror scenario: corpus + ledger downloaded on one machine, pulled to a
    different path on another. Paths in the ledger are relative, so the run must
    skip everything and verification must still find every file."""
    tasks = plan_backfill(entries)
    server = FakeServer(bodies={t.url: _zip_bytes(t.key.encode()) for t in tasks})
    machine_a = tmp_path / "machine-a" / "releases"
    ledger = DownloadLedger(machine_a / "ledger.json")
    run_backfill(tasks, ledger, dest_dir=machine_a, opener=server.opener)
    requests_before = len(server.requests)

    machine_b = tmp_path / "machine-b" / "somewhere-else" / "releases"
    machine_b.parent.mkdir(parents=True)
    (tmp_path / "machine-a" / "releases").rename(machine_b)

    moved = DownloadLedger.load(machine_b / "ledger.json")
    report = run_backfill(tasks, moved, dest_dir=machine_b, opener=server.opener)
    assert report.skipped == 6
    assert report.downloaded == 0
    assert len(server.requests) == requests_before

    verification = verify_ledger(moved, deep=True)
    assert verification.sound
    assert not verification.missing_files


def test_unavailable_is_recorded_and_not_re_asked(tmp_path, entries):
    server = FakeServer()  # everything 404s
    tasks = plan_backfill(entries)
    ledger = DownloadLedger(tmp_path / "ledger.json")

    run_backfill(tasks, ledger, dest_dir=tmp_path, opener=server.opener)
    requests_before = len(server.requests)

    reloaded = DownloadLedger.load(tmp_path / "ledger.json")
    report = run_backfill(tasks, reloaded, dest_dir=tmp_path, opener=server.opener)

    assert report.unavailable == 6
    assert len(server.requests) == requests_before


def test_retry_unavailable_re_asks(tmp_path, entries):
    server = FakeServer()
    tasks = plan_backfill(entries)
    ledger = DownloadLedger(tmp_path / "ledger.json")
    run_backfill(tasks, ledger, dest_dir=tmp_path, opener=server.opener)
    before = len(server.requests)

    run_backfill(
        tasks, ledger, dest_dir=tmp_path, opener=server.opener, retry_unavailable=True
    )

    assert len(server.requests) > before


def test_failed_entries_are_retried_on_the_next_run(tmp_path, entries):
    body = _zip_bytes()
    server = FakeServer(default=body)
    tasks = plan_backfill(entries, titles={"16"})
    url = tasks[0].url
    server.raise_times[url] = 99
    ledger = DownloadLedger(tmp_path / "ledger.json")

    first = run_backfill(
        tasks, ledger, dest_dir=tmp_path, opener=server.opener, attempts=2
    )
    assert first.failed == 1

    server.raise_times[url] = 0
    second = run_backfill(tasks, ledger, dest_dir=tmp_path, opener=server.opener)
    assert second.downloaded == 1


def test_ledger_survives_a_round_trip(tmp_path):
    ledger = DownloadLedger(tmp_path / "ledger.json")
    ledger.record(
        LedgerEntry(
            release_label="119-99",
            title_num="16",
            status=str(FetchStatus.OK),
            url="https://example/x.zip",
            path=str(tmp_path / "x.zip"),
            sha256="a" * 64,
            bytes=1234,
        )
    )
    ledger.save()

    reloaded = DownloadLedger.load(tmp_path / "ledger.json")
    entry = reloaded.entries["119-99/16"]
    assert entry.sha256 == "a" * 64
    assert entry.bytes == 1234
    assert entry.recorded_at  # stamped on record()


@pytest.mark.parametrize(
    "recorded",
    [
        # Another machine's absolute path.
        "/Users/someone-else/repo/data/releases/119-99/xml_usc16@119-99.zip",
        # Relative, but already carrying the corpus prefix — re-prefixing this one
        # produced data/releases/data/releases/… and silently hid the whole corpus.
        "data/releases/119-99/xml_usc16@119-99.zip",
        # Already in the contract form.
        "119-99/xml_usc16@119-99.zip",
    ],
)
def test_paths_normalize_to_the_layout_contract_on_load(tmp_path, recorded):
    """Whatever a writer recorded, a reader resolves it to {label}/{file} under
    its own corpus directory. Anything else makes a pulled ledger unusable."""
    ledger = DownloadLedger(tmp_path / "ledger.json")
    ledger.record(
        LedgerEntry(
            release_label="119-99",
            title_num="16",
            status=str(FetchStatus.OK),
            url="https://example/x.zip",
            path=recorded,
            sha256="a" * 64,
        )
    )
    ledger.save()

    reloaded = DownloadLedger.load(tmp_path / "ledger.json")
    entry = reloaded.entries["119-99/16"]
    assert entry.path == "119-99/xml_usc16@119-99.zip"
    assert reloaded.resolve_path(entry) == tmp_path / "119-99" / "xml_usc16@119-99.zip"


def test_ledger_save_is_atomic(tmp_path, entries):
    """No `.tmp` left behind, and the file is always complete JSON."""
    server = FakeServer(default=_zip_bytes())
    ledger = DownloadLedger(tmp_path / "ledger.json")
    run_backfill(plan_backfill(entries), ledger, dest_dir=tmp_path, opener=server.opener)

    assert list(tmp_path.glob("*.tmp")) == []
    json.loads((tmp_path / "ledger.json").read_text())


# --------------------------------------------------------------------------
# Hash-dedupe verification
# --------------------------------------------------------------------------


def _ledger_with(tmp_path: Path, members: dict[str, bytes]) -> DownloadLedger:
    ledger = DownloadLedger(tmp_path / "ledger.json")
    for key, body in members.items():
        release, title = key.split("/")
        path = tmp_path / release / f"xml_usc{title}@{release}.zip"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        ledger.record(
            LedgerEntry(
                release_label=release,
                title_num=title,
                status=str(FetchStatus.OK),
                url=f"https://example/{key}",
                path=str(path),
                sha256=hashlib.sha256(body).hexdigest(),
                bytes=len(body),
            )
        )
    return ledger


def test_verify_reports_identical_republication_of_a_title(tmp_path):
    """Same title, two release points, identical bytes: OLRC said it changed and
    it did not. A finding about the source, not a defect in the downloader."""
    same = _zip_bytes(b"unchanged")
    ledger = _ledger_with(tmp_path, {"113-21/16": same, "113-31/16": same})

    report = verify_ledger(ledger)

    assert len(report.same_title_duplicates) == 1
    assert report.same_title_duplicates[0].members == ["113-21/16", "113-31/16"]
    assert not report.cross_title_duplicates
    assert report.sound  # informative, not a failure


def test_verify_flags_the_u1_substitution_hazard(tmp_path):
    """`118-22` and `118-22u1` are different release points. If their files ever
    hash alike, one label is being served the other's content — which is exactly
    what the original's silent `u1` → non-`u1` fallback would produce."""
    same = _zip_bytes(b"same file")
    ledger = _ledger_with(tmp_path, {"118-22/16": same, "118-22u1/16": same})

    report = verify_ledger(ledger)

    assert report.same_title_duplicates[0].members == ["118-22/16", "118-22u1/16"]


def test_verify_fails_when_two_titles_share_a_zip(tmp_path):
    """Distinct titles cannot have the same zip. This is URL construction
    collapsing two addresses into one — the way this downloader most plausibly
    breaks, since every URL is built by substitution on a label."""
    same = _zip_bytes(b"collapsed")
    ledger = _ledger_with(tmp_path, {"113-21/16": same, "113-21/18": same})

    report = verify_ledger(ledger)

    assert report.cross_title_duplicates
    assert not report.sound


def test_verify_distinct_files_are_sound(tmp_path):
    ledger = _ledger_with(
        tmp_path, {"113-21/16": _zip_bytes(b"a"), "113-21/18": _zip_bytes(b"b")}
    )

    report = verify_ledger(ledger)

    assert report.distinct_hashes == 2
    assert not report.same_title_duplicates
    assert report.sound


def test_deep_verify_catches_a_file_changed_underneath_the_ledger(tmp_path):
    ledger = _ledger_with(tmp_path, {"113-21/16": _zip_bytes(b"original")})
    entry = ledger.entries["113-21/16"]
    Path(entry.path).write_bytes(_zip_bytes(b"tampered"))

    shallow = verify_ledger(ledger, deep=False)
    deep = verify_ledger(ledger, deep=True)

    assert shallow.sound  # trusts the ledger
    assert not deep.sound  # re-hashes and catches it
    assert deep.integrity_failures


def test_verify_notices_a_recorded_file_that_is_gone(tmp_path):
    ledger = _ledger_with(tmp_path, {"113-21/16": _zip_bytes()})
    Path(ledger.entries["113-21/16"].path).unlink()

    report = verify_ledger(ledger)

    assert report.missing_files == ["113-21/16"]


def test_verification_report_is_written_as_an_artifact(tmp_path):
    ledger = _ledger_with(tmp_path, {"113-21/16": _zip_bytes()})
    report = verify_ledger(ledger)

    path = write_verification(report, directory=tmp_path / "verification")

    document = json.loads(path.read_text())
    assert document["sound"] is True
    assert document["ok"] == 1


def test_unavailable_entries_do_not_count_as_downloaded(tmp_path):
    ledger = DownloadLedger(tmp_path / "ledger.json")
    ledger.record(
        LedgerEntry(
            release_label="118-22u1",
            title_num="16",
            status=str(FetchStatus.UNAVAILABLE),
            url="https://example/x.zip",
            http_status=404,
        )
    )

    report = verify_ledger(ledger)

    assert report.unavailable == 1
    assert report.ok == 0
    assert report.total_bytes == 0
