"""Fetching, loading and polling the classification tables (spec §3, ADR-0067).

The parse side is `tests/test_classification_parser.py`. What is here is the half
that has a database and a network on the other side of it:

  * the fetch, with an `Opener` injected so nothing in the suite reaches
    uscode.house.gov (ADR-0013) and `throttle` neutralised so it does not sleep
    a second per request;
  * `load_file`'s wholesale replace — that a re-load of unchanged text touches
    no row, that changed text leaves none of the old ones, and that reloading the
    ECCT cannot double it;
  * `poll_classification`, which must write a check row on the path where the
    page came back *and* the path where it did not, for ADR-0036's reason.

The integration tests bind their sessions to one connection inside a transaction
that is rolled back afterwards, because `run_classification_load` commits per
file by design and this database is the loaded fixture corpus every other
integration test reads from.
"""

from __future__ import annotations

import json
import urllib.error
from contextlib import contextmanager
from email.message import Message
from pathlib import Path

import pytest
from sqlalchemy import delete, func, select

from db.models import ClassificationEntry, ClassificationFile, ClassificationSourceCheck, EcctEntry
from ingest import classification as cls
from tests.conftest import FIXTURES

#: The committed slices under the filenames OLRC publishes them at — the same
#: mapping `make ci-data` copies, and the reason `--from-file` needs no network.
FIXTURE_PAGES = {
    "tables.shtml": "tables_slice.shtml",
    "priortables.shtml": "priortables_slice.shtml",
    "tbl118pl_2nd.htm": "tbl118pl_2nd_slice.htm",
    "tbl110pl_1st.htm": "tbl110pl_1st_slice.htm",
    "tbl104pl.htm": "tbl104pl_slice.htm",
    "ecct.html": "ecct.html",
}


@pytest.fixture(autouse=True)
def no_throttle(monkeypatch):
    """The real throttle sleeps up to a second per request, which is right for a
    backfill and absurd for a test suite."""
    monkeypatch.setattr(cls, "throttle", lambda: None)


@pytest.fixture()
def pages(tmp_path) -> Path:
    """The fixture slices as a directory `--from-file` can read."""
    directory = tmp_path / "classification"
    directory.mkdir()
    for published, slice_name in FIXTURE_PAGES.items():
        (directory / published).write_text((FIXTURES / slice_name).read_text())
    return directory


class _Response:
    """What `urlopen` yields, as far as the fetch is concerned."""

    def __init__(self, text: str, charset: str = "utf-8") -> None:
        self.headers = Message()
        self.headers["Content-Type"] = f"text/html; charset={charset}"
        self._body = text.encode(charset)

    def read(self) -> bytes:
        return self._body


def _opener(available: dict[str, str], *, charset: str = "utf-8"):
    """An `Opener` serving canned pages by filename; anything else is a 404."""

    @contextmanager
    def opener(request, timeout):
        name = cls.page_filename(request.full_url)
        if name not in available:
            raise urllib.error.HTTPError(request.full_url, 404, "Not Found", None, None)  # type: ignore[arg-type]
        yield _Response(available[name], charset=charset)

    return opener


def _served(directory: Path, *names: str) -> dict[str, str]:
    return {name: (directory / name).read_text() for name in names}


def _index_page(*entries: tuple[str, str]) -> str:
    """A `tables.shtml`-shaped page: one cell per document, the covered-law
    sentence above the link and the "Sorted in Public Law order" run between
    them, which is how OLRC writes it (`tests/fixtures/tables_slice.shtml`)."""
    cells = "\n".join(
        f'<td><p>119th Congress, 2nd Session<br />{covered}</p>'
        f'<p>Sorted in Public Law order<br />'
        f'<a href="{filename}">(HTML format)</a></p></td>'
        for filename, covered in entries
    )
    return f"<html><body><table><tr>{cells}</tr></table></body></html>"


COVERED_118 = "Public Laws 118-35 through 118-274"


# ------------------------------------------------------------------- the fetch


def test_the_fetch_keeps_a_copy_under_the_published_filename(tmp_path, pages):
    cache = tmp_path / "cache"
    html = cls.fetch_classification_page(
        cls.CLASSIFICATION_BASE_URL + "tbl118pl_2nd.htm",
        cache_dir=cache,
        opener=_opener(_served(pages, "tbl118pl_2nd.htm")),
    )

    assert "U. S. Code" in html
    assert (cache / "tbl118pl_2nd.htm").read_text() == html
    # The body lands in a .part file and is renamed, so an interrupted fetch
    # cannot leave a truncated page a later --from-file run would parse as real.
    assert list(cache.iterdir()) == [cache / "tbl118pl_2nd.htm"]


def test_the_fetch_decodes_with_the_charset_the_response_declares(tmp_path):
    """The older vintages are Latin-1, and a page decoded as UTF-8 loses a column
    the moment a byte above 0x7f appears in it."""
    page = "<pre>§ 45a-1</pre>"
    html = cls.fetch_classification_page(
        cls.CLASSIFICATION_BASE_URL + "tbl104pl.htm",
        cache_dir=tmp_path,
        opener=_opener({"tbl104pl.htm": page}, charset="iso-8859-1"),
    )
    assert html == page


def test_the_fetch_can_be_told_not_to_cache(tmp_path):
    cls.fetch_classification_page(
        cls.CLASSIFICATION_SOURCE_URL,
        cache_dir=None,
        opener=_opener({"tables.shtml": _index_page(("tbl118pl_2nd.htm", COVERED_118))}),
    )
    assert list(tmp_path.iterdir()) == []


def test_a_page_not_on_disk_reads_as_none(tmp_path):
    assert cls.read_cached_page(tmp_path, "tbl118pl_2nd.htm") is None


# --------------------------------------------------- documents found on disk


def test_a_table_on_disk_is_named_by_its_filename(pages):
    links = {link.filename: link for link in cls.links_on_disk(pages)}

    assert (links["tbl118pl_2nd.htm"].congress, links["tbl118pl_2nd.htm"].session) == (118, 2)
    # The 104th is one file for both sessions, and 0 says so.
    assert (links["tbl104pl.htm"].congress, links["tbl104pl.htm"].session) == (104, 0)
    assert links["tbl118pl_2nd.htm"].kind == "pl"
    # The index pages are not documents, and neither is anything else in there.
    assert "tables.shtml" not in links
    assert "priortables.shtml" not in links


def test_an_unsuffixed_ecct_on_disk_has_no_congress_to_belong_to(pages):
    """The sentence that dates `ecct.html` is on the index page, so a directory
    scan cannot supply it — 0/0 is the registry's "the source did not say"."""
    ecct = next(link for link in cls.links_on_disk(pages) if link.kind == "ecct")
    assert (ecct.congress, ecct.session) == (0, 0)


def test_an_archived_ecct_on_disk_carries_its_own_congress(tmp_path):
    (tmp_path / "ecct_119-1.html").write_text("<table><th>x</th></table>")
    link = cls.links_on_disk(tmp_path)[0]
    assert (link.congress, link.session) == (119, 1)


def test_files_already_linked_are_not_found_twice(pages):
    found = cls.links_on_disk(pages, exclude={"tbl104pl.htm"})
    assert "tbl104pl.htm" not in {link.filename for link in found}


# ------------------------------------------------------------- the artifacts


def _parse(pages: Path, filename: str):
    return cls.parse_classification_file(
        (pages / filename).read_text(), filename=filename
    )


def test_a_verification_artifact_is_the_parse_and_not_the_table(tmp_path, pages):
    parsed = _parse(pages, "tbl118pl_2nd.htm")
    path = cls.write_verification(parsed, directory=tmp_path)
    document = json.loads(path.read_text())

    assert path.name == "classification-118-2.json"
    assert document["rows_parsed"] == parsed.row_count
    assert document["column_offsets"] == [0, 6, 19, 36, 45, 67]
    assert document["content_hash"] == parsed.content_hash
    # No entries: the artifact stays a few kilobytes and a diff between two runs
    # is a diff between two parses.
    assert "entries" not in document


def test_the_verification_artifact_is_where_the_skipped_lines_survive(tmp_path, pages):
    """`classification_files.skipped_lines` is a count, so the lines themselves
    exist in one place only."""
    parsed = _parse(pages, "tbl118pl_2nd.htm")
    document = json.loads(cls.write_verification(parsed, directory=tmp_path).read_text())
    assert document["skipped_line_text"] == list(parsed.skipped_lines)


def test_the_manifest_merges_one_file_at_a_time(tmp_path, pages):
    path = tmp_path / "classification.json"
    cls.write_classification_manifest(_parse(pages, "tbl118pl_2nd.htm"), path=path)
    cls.write_classification_manifest(_parse(pages, "tbl104pl.htm"), path=path)

    manifest = json.loads(path.read_text())
    assert set(manifest["files"]) == {"tbl118pl_2nd.htm", "tbl104pl.htm"}
    assert manifest["files"]["tbl104pl.htm"]["congress"] == 104
    assert manifest["source_url"] == cls.CLASSIFICATION_SOURCE_URL


# --------------------------------------------------------------- parse-only runs


def _no_database():
    raise AssertionError("--no-load must not open a database session")


def test_no_load_writes_the_artifacts_and_opens_no_session(tmp_path, pages):
    report = cls.run_classification_load(
        _no_database,
        from_dir=pages,
        load=False,
        verification_dir=tmp_path / "verification",
        manifest_path=tmp_path / "classification.json",
    )

    assert report.sound
    assert report.rows_written == 0
    assert {path.name for path in (tmp_path / "verification").iterdir()} == {
        "classification-118-2.json",
        "classification-110-1.json",
        "classification-104-0.json",
        "classification-ecct-119-2.json",
    }


def test_a_linked_document_the_directory_does_not_hold_is_skipped(tmp_path, pages):
    """The slices link a dozen files and hold three; a missing one is an answer,
    not a failure."""
    report = cls.run_classification_load(
        _no_database,
        from_dir=pages,
        load=False,
        verification_dir=tmp_path,
        manifest_path=tmp_path / "classification.json",
    )
    assert report.sound
    assert "tbl119pl_2nd.htm" in {filename for filename, _why in report.skipped}


def test_a_table_no_index_page_links_is_loaded_anyway(tmp_path, pages):
    """`tbl110pl_1st.htm` is in neither slice of the index pages. What is in the
    directory is what gets loaded, with the covered range read from its own
    header."""
    report = cls.run_classification_load(
        _no_database,
        from_dir=pages,
        load=False,
        verification_dir=tmp_path,
        manifest_path=tmp_path / "classification.json",
    )
    assert report.sound
    covered = json.loads((tmp_path / "classification-110-1.json").read_text())
    assert covered["covered_laws_text"] == "Public Laws 110-1 through 110-180"


def test_an_index_page_that_will_not_load_is_a_failure_and_not_a_crash(tmp_path, pages):
    """One page failing must not lose the other one's tables.

    Over the network a linked table that 404s is a failure rather than the skip
    `--from-file` reports: the index page says the document exists, so not being
    able to get it is news about the fetch and not about the directory.
    """
    report = cls.run_classification_load(
        _no_database,
        load=False,
        cache_dir=None,
        verification_dir=tmp_path,
        manifest_path=tmp_path / "classification.json",
        opener=_opener(_served(pages, "priortables.shtml", "tbl104pl.htm")),
    )

    failed = {filename for filename, _detail in report.failures}
    assert "tables.shtml" in failed
    assert not report.sound
    assert (tmp_path / "classification-104-0.json").exists()


# --------------------------------------------------------------- the loader
#
# Marked per-test: everything above runs on a fresh clone with no Postgres.


@pytest.fixture()
def factory(loaded_database):
    """Sessions bound to one connection inside a transaction that is rolled back.

    `run_classification_load` commits once per file — that is what makes an
    interrupted backfill resumable — so isolating it takes a real outer
    transaction rather than a session that never commits. The classification
    tables are emptied first so a test's answers do not depend on what a previous
    `make ci-data` left in them.
    """
    from sqlalchemy.orm import Session as SessionType

    from db.base import engine

    connection = engine.connect()
    outer = connection.begin()

    def make() -> SessionType:
        return SessionType(bind=connection, join_transaction_mode="create_savepoint")

    with make() as setup:
        setup.execute(delete(ClassificationFile))
        setup.commit()
    try:
        yield make
    finally:
        outer.rollback()
        connection.close()


def _counts(session) -> tuple[int, int]:
    return (
        session.scalar(select(func.count()).select_from(ClassificationEntry)),
        session.scalar(select(func.count()).select_from(EcctEntry)),
    )


@pytest.mark.integration
def test_loading_a_file_stores_its_registry_row_and_every_row(factory, pages):
    parsed = _parse(pages, "tbl118pl_2nd.htm")
    with factory() as session:
        result = cls.load_file(session, parsed)
        session.commit()

        assert result.action == "inserted"
        assert result.rows_written == parsed.row_count

        row = session.scalars(select(ClassificationFile)).one()
        assert (row.kind, row.congress, row.session) == ("pl", 118, 2)
        assert row.content_hash == parsed.content_hash
        assert row.row_count == parsed.row_count
        assert row.stat_volume == 138
        # The column is an Integer and the parser produces the lines themselves.
        assert row.skipped_lines == len(parsed.skipped_lines)
        assert _counts(session)[0] == parsed.row_count


@pytest.mark.integration
def test_a_re_load_of_identical_text_touches_no_row(factory, pages):
    """The `<PRE>` hash is what gates the rows: the index page can reword its
    covered-law sentence without the table changing."""
    parsed = _parse(pages, "tbl118pl_2nd.htm")
    with factory() as session:
        cls.load_file(session, parsed)
        session.commit()
        before = sorted(session.scalars(select(ClassificationEntry.id)))

        result = cls.load_file(session, parsed)
        session.commit()

        assert result.action == "unchanged"
        assert (result.rows_written, result.rows_deleted) == (0, 0)
        assert sorted(session.scalars(select(ClassificationEntry.id))) == before


@pytest.mark.integration
def test_a_changed_file_replaces_every_row_it_had(factory, pages):
    """No row identity to diff against, so the whole file is re-inserted
    (ADR-0067 decision 3)."""
    first = _parse(pages, "tbl118pl_2nd.htm")
    with factory() as session:
        cls.load_file(session, first)
        session.commit()
        before = set(session.scalars(select(ClassificationEntry.id)))

        # Two rows shorter, and hashing differently, which is what OLRC
        # republishing the current session's file looks like.
        trimmed = _trimmed(pages, "tbl118pl_2nd.htm", drop=2)
        result = cls.load_file(session, trimmed)
        session.commit()

        assert result.action == "replaced"
        assert result.rows_deleted == first.row_count
        assert result.rows_written == first.row_count - 2
        after = set(session.scalars(select(ClassificationEntry.id)))
        assert not after & before
        assert len(after) == first.row_count - 2


@pytest.mark.integration
def test_forcing_a_re_load_replaces_rows_that_hash_the_same(factory, pages):
    parsed = _parse(pages, "tbl118pl_2nd.htm")
    with factory() as session:
        cls.load_file(session, parsed)
        session.commit()
        before = set(session.scalars(select(ClassificationEntry.id)))

        result = cls.load_file(session, parsed, force=True)
        session.commit()

        assert result.action == "replaced"
        assert not set(session.scalars(select(ClassificationEntry.id))) & before


@pytest.mark.integration
def test_reloading_the_ecct_does_not_double_it(factory, pages):
    """`ecct_entries` has its own `(file_id, row_seq)` constraint now, and the
    loader deletes explicitly rather than relying on a cascade that a registry
    row updated in place never fires."""
    ecct = cls.parse_ecct(
        (pages / "ecct.html").read_text(), congress=119, session=2
    )
    with factory() as session:
        cls.load_file(session, ecct)
        session.commit()
        assert _counts(session)[1] == ecct.row_count

        cls.load_file(session, ecct, force=True)
        session.commit()
        assert _counts(session)[1] == ecct.row_count


@pytest.mark.integration
def test_dropping_a_registry_row_takes_its_rows_with_it(factory, pages):
    """Both entry tables cascade, so nothing can be orphaned by a delete that
    reaches the registry (migration 0044883c483c)."""
    with factory() as session:
        cls.load_file(session, _parse(pages, "tbl118pl_2nd.htm"))
        cls.load_file(
            session,
            cls.parse_ecct((pages / "ecct.html").read_text(), congress=119, session=2),
        )
        session.commit()
        assert _counts(session) != (0, 0)

        session.execute(delete(ClassificationFile))
        session.commit()
        assert _counts(session) == (0, 0)


def _trimmed(pages: Path, filename: str, *, drop: int):
    """The same file with its last `drop` data rows gone — a different `<PRE>`
    hash, which is what a republication is."""
    parsed = cls.parse_classification_file((pages / filename).read_text(), filename=filename)
    from dataclasses import replace

    return replace(
        parsed,
        entries=parsed.entries[:-drop],
        content_hash=parsed.content_hash[:-1] + ("0" if parsed.content_hash[-1] != "0" else "1"),
    )


# ------------------------------------------------------------ the whole run


@pytest.mark.integration
def test_a_run_over_a_directory_loads_it_and_a_re_run_is_a_no_op(factory, pages, tmp_path):
    artifacts = tmp_path / "verification"
    manifest = tmp_path / "classification.json"

    first = cls.run_classification_load(
        factory,
        from_dir=pages,
        verification_dir=artifacts,
        manifest_path=manifest,
    )
    assert first.sound
    assert first.loaded == 4
    assert first.rows_written > 100

    again = cls.run_classification_load(
        factory,
        from_dir=pages,
        verification_dir=artifacts,
        manifest_path=manifest,
    )
    assert again.sound
    assert again.rows_written == 0
    assert again.loaded == 0


@pytest.mark.integration
def test_the_covered_law_gate_skips_a_file_without_asking_for_it(factory, pages, tmp_path):
    """A closed congress's table is not re-downloaded, which is what keeps a
    re-run at two requests rather than 33 (ADR-0067 decision 5). The opener here
    serves the index page and 404s the table, so a fetch would fail the run."""
    index = _index_page(("tbl118pl_2nd.htm", COVERED_118))
    everything = _opener({"tables.shtml": index, "tbl118pl_2nd.htm": (pages / "tbl118pl_2nd.htm").read_text()})
    index_only = _opener({"tables.shtml": index})
    common = dict(
        urls=(cls.CLASSIFICATION_SOURCE_URL,),
        cache_dir=None,
        verification_dir=tmp_path,
        manifest_path=tmp_path / "classification.json",
    )

    first = cls.run_classification_load(factory, opener=everything, **common)
    assert first.loaded == 1

    again = cls.run_classification_load(factory, opener=index_only, **common)
    assert again.sound
    assert again.skipped == (("tbl118pl_2nd.htm", "covered laws unchanged"),)


# ---------------------------------------------------------------- the poll


def _poll(factory, page: str | None, *, url: str = cls.CLASSIFICATION_SOURCE_URL):
    with factory() as session:
        available = {} if page is None else {cls.page_filename(url): page}
        result = cls.poll_classification(
            session, url=url, cache_dir=None, opener=_opener(available)
        )
        session.commit()
        check = session.scalars(
            select(ClassificationSourceCheck).order_by(ClassificationSourceCheck.id.desc())
        ).first()
        return result, check


@pytest.mark.integration
def test_a_successful_poll_records_the_check(factory):
    result, check = _poll(factory, _index_page(("tbl118pl_2nd.htm", COVERED_118)))

    assert result.ok
    assert check is not None and check.ok
    assert check.files_seen == 1
    assert check.latest_covered_text == COVERED_118
    # Nothing is loaded, so the one document on the page is news.
    assert result.changed_files == ("tbl118pl_2nd.htm",)
    assert list(check.changed_files) == ["tbl118pl_2nd.htm"]


@pytest.mark.integration
def test_a_poll_after_the_load_reports_nothing_changed(factory, pages, tmp_path):
    page = _index_page(("tbl118pl_2nd.htm", COVERED_118))
    cls.run_classification_load(
        factory,
        urls=(cls.CLASSIFICATION_SOURCE_URL,),
        cache_dir=None,
        verification_dir=tmp_path,
        manifest_path=tmp_path / "classification.json",
        opener=_opener(
            {"tables.shtml": page, "tbl118pl_2nd.htm": (pages / "tbl118pl_2nd.htm").read_text()}
        ),
    )

    result, check = _poll(factory, page)

    assert result.ok
    assert not result.has_changes
    assert list(check.changed_files) == []


@pytest.mark.integration
def test_a_reworded_covered_range_is_what_the_poll_notices(factory, pages, tmp_path):
    """The pages carry no usable Last-Modified and embed a per-request
    jsessionid, so the covered-law sentence is the change-detection key."""
    page = _index_page(("tbl118pl_2nd.htm", COVERED_118))
    cls.run_classification_load(
        factory,
        urls=(cls.CLASSIFICATION_SOURCE_URL,),
        cache_dir=None,
        verification_dir=tmp_path,
        manifest_path=tmp_path / "classification.json",
        opener=_opener(
            {"tables.shtml": page, "tbl118pl_2nd.htm": (pages / "tbl118pl_2nd.htm").read_text()}
        ),
    )

    result, check = _poll(
        factory, _index_page(("tbl118pl_2nd.htm", "Public Laws 118-35 through 118-280"))
    )

    assert result.changed_files == ("tbl118pl_2nd.htm",)
    assert check.latest_covered_text == "Public Laws 118-35 through 118-280"


@pytest.mark.integration
def test_a_failed_poll_still_records_the_attempt(factory):
    """A scraper that stopped running looks exactly like a source with nothing
    new, and only the record of the attempt tells them apart (ADR-0036)."""
    result, check = _poll(factory, None)

    assert not result.ok
    assert "HTTP Error 404" in (result.error or "")
    assert check is not None and not check.ok
    # Not zero: the page never parsed, so nothing was seen.
    assert check.files_seen is None
    assert "404" in (check.error or "")


@pytest.mark.integration
def test_an_unparseable_index_page_is_a_failed_check(factory):
    """OLRC changing its markup must not read as "there are no tables"."""
    result, check = _poll(factory, "<html><body>nothing here</body></html>")

    assert not result.ok
    assert "ClassificationParseError" in (result.error or "")
    assert check is not None and not check.ok


@pytest.mark.integration
def test_a_page_missing_a_document_we_hold_is_refused(factory, pages, tmp_path):
    """A document never leaves OLRC's index, so its absence is a truncated
    response rather than news — the refusal `poll_source` makes for a vanished
    release point."""
    both = _index_page(
        ("tbl118pl_2nd.htm", COVERED_118), ("tbl118pl_1st.htm", "Public Laws 118-1 through 118-34")
    )
    cls.run_classification_load(
        factory,
        urls=(cls.CLASSIFICATION_SOURCE_URL,),
        cache_dir=None,
        verification_dir=tmp_path,
        manifest_path=tmp_path / "classification.json",
        opener=_opener(
            {"tables.shtml": both, "tbl118pl_2nd.htm": (pages / "tbl118pl_2nd.htm").read_text()}
        ),
    )

    result, check = _poll(factory, _index_page(("tbl118pl_1st.htm", "Public Laws 118-1")))

    assert not result.ok
    assert "missing from tables.shtml" in (result.error or "")
    assert "tbl118pl_2nd.htm" in (result.error or "")
    assert check is not None and not check.ok


@pytest.mark.integration
def test_another_congresss_tables_are_not_expected_on_this_page(factory, pages, tmp_path):
    """`tables.shtml` lists the current congress alone, so the thirty files
    `priortables.shtml` links must not read as vanished."""
    with factory() as session:
        cls.load_file(session, _parse(pages, "tbl104pl.htm"))
        session.commit()

    result, _check = _poll(factory, _index_page(("tbl118pl_2nd.htm", COVERED_118)))
    assert result.ok


# ------------------------------------------------------------- the exit codes


@pytest.mark.integration
@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (cls.ClassificationCheckResult(ok=True, links=(), changed_files=()), 0),
        (cls.ClassificationCheckResult(ok=True, links=(), changed_files=("tbl119pl_2nd.htm",)), 10),
        (cls.ClassificationCheckResult(ok=False, links=(), changed_files=(), error="boom"), 1),
    ],
    ids=["nothing-new", "changed", "failed"],
)
def test_the_check_says_what_it_found_in_its_exit_code(monkeypatch, result, expected):
    """`deploy/update-corpus.sh` reads the exit code and nothing else — there is
    no jq guarantee on that box."""
    from ingest.__main__ import main

    monkeypatch.setattr(cls, "poll_classification", lambda session, **kwargs: result)
    assert main(["classification-check"]) == expected
