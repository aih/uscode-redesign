"""Version-transition classification and attribution (ADR-0074).

Three layers, each answerable without the one above it:

  * Pure rules — the incorporated-law-set window (`excluded_laws` honored: the
    text change between `116-344not283u1` and `116-344` is Pub. L. 116-283
    entering, a law below both labels), the whitespace-insensitive hashes, and
    the source-credit citation reader (EN DASH, gotcha 17).
  * The committed `tbl119pl_2nd_slice.htm` fixture, parsed through the
    classification parser: the table that classifies Pub. L. 119-102 to
    16 U.S.C. 2201 and 2206 — the only two sections whose content differs
    between the CI corpus's release points (ADR-0007's measurement).
  * The database: `compute_for_sections` against the loaded corpus (CI's
    two-release fixture corpus or a full development corpus — the assertions
    hold on both), and the migration round trip on a scratch database.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from ingest import version_changes as vc
from ingest.classification import parse_classification_file
from ingest.records import NoteText, notes_hash_of, text_hash_of
from ingest.release_label import parse_label
from tests.conftest import FIXTURES, REPO_ROOT, _unavailable

SLICE_119 = FIXTURES / "tbl119pl_2nd_slice.htm"


def _facts(label: str, *, id: int = 0, seq: int = 0) -> vc.ReleaseFacts:
    parsed = parse_label(label)
    return vc.ReleaseFacts(
        id=id,
        seq=seq,
        label=label,
        congress=parsed.congress,
        law_num=parsed.law_num,
        excluded=frozenset(parsed.excluded_laws),
    )


# ------------------------------------------------------------------ the window


def test_a_not_law_entering_is_in_the_window():
    """Finding 1: label-interval matching misses every `not`-law incorporation."""
    departing = _facts("116-344not283u1")
    arriving = _facts("116-344")
    assert vc.law_in_window(departing, arriving, 116, 283)


def test_a_law_incorporated_at_both_ends_is_not_in_the_window():
    departing = _facts("116-344not283u1")
    arriving = _facts("116-344")
    assert not vc.law_in_window(departing, arriving, 116, 344)
    assert not vc.law_in_window(departing, arriving, 115, 1)


def test_a_law_beyond_the_arriving_release_is_not_in_the_window():
    assert not vc.law_in_window(_facts("119-99"), _facts("119-102not101"), 119, 103)


def test_the_arriving_releases_own_exclusion_is_honored():
    """119-101 is below 119-102 but excluded at `119-102not101`."""
    assert not vc.law_in_window(_facts("119-99"), _facts("119-102not101"), 119, 101)
    assert vc.law_in_window(_facts("119-99"), _facts("119-102not101"), 119, 102)
    assert vc.law_in_window(_facts("119-99"), _facts("119-102not101"), 119, 100)


def test_no_departing_release_means_no_window():
    """An unbounded window would attribute every law ever enacted."""
    assert not vc.law_in_window(None, _facts("119-102not101"), 119, 102)


def test_incorporated_compares_across_congresses():
    rp = _facts("119-99")
    assert vc.incorporated(rp, 118, 500)
    assert not vc.incorporated(rp, 120, 1)


# ------------------------------------------------------------------- the hashes


def test_text_hash_ignores_all_whitespace():
    """Finding 3: element-boundary whitespace from the 2013–2015 converter is
    converter noise, not a text change."""
    assert text_hash_of("In general In") == text_hash_of("In generalIn")
    assert text_hash_of("a b\nc") == text_hash_of("abc")
    assert text_hash_of("a") != text_hash_of("b")


def test_notes_hash_keeps_fields_and_notes_apart():
    one = NoteText(topic="t", role="r", heading="h", text="x")
    assert notes_hash_of((one,)) == notes_hash_of(
        (NoteText(topic="t", role="r", heading="h", text=" x "),)
    )
    # A value may not bleed into its neighbour…
    assert notes_hash_of((one,)) != notes_hash_of(
        (NoteText(topic="tr", role="", heading="h", text="x"),)
    )
    # …and two notes are not one note with concatenated text.
    two = (NoteText(None, None, None, "a"), NoteText(None, None, None, "b"))
    assert notes_hash_of(two) != notes_hash_of((NoteText(None, None, None, "ab"),))


def test_parsed_records_carry_the_hashes(slice_path):
    from ingest import iter_sections

    for record in iter_sections(slice_path):
        assert len(record.text_hash) == 32
        assert len(record.notes_hash) == 32
        break


def test_the_hashes_are_stable_across_parses(slice_path):
    from ingest import iter_sections

    def first_three(path):
        out = []
        for record in iter_sections(path):
            out.append((record.identifier, record.text_hash, record.notes_hash))
            if len(out) == 3:
                break
        return out

    assert first_three(slice_path) == first_three(slice_path)


# ------------------------------------------------------------ the credit reader


def test_credit_laws_reads_the_en_dash_the_corpus_writes():
    credit = "(Pub. L. 92–463, § 1, Oct. 6, 1972, 86 Stat. 770; Pub. L. 119-102, § 2.)"
    assert vc.credit_laws(credit) == {(92, 463), (119, 102)}


def test_credit_laws_of_nothing_is_empty():
    assert vc.credit_laws(None) == frozenset()
    assert vc.credit_laws("Aug. 25, 1916, ch. 408, § 1, 39 Stat. 535") == frozenset()


# ------------------------------------------------------------------ the fixture


def test_the_119_2_slice_parses_to_its_title_16_rows():
    parsed = parse_classification_file(
        SLICE_119.read_text(), filename="tbl119pl_2nd.htm"
    )
    assert parsed.congress == 119 and parsed.session == 2
    assert parsed.covered_ranges == ("70-70", "74-102")
    assert parsed.row_count == 19
    assert not parsed.skipped_lines
    assert all(entry.title_num == "16" for entry in parsed.entries)


def test_the_slice_classifies_119_102_to_s2201_and_s2206():
    """The rows the CI corpus's one real transition window must match."""
    parsed = parse_classification_file(
        SLICE_119.read_text(), filename="tbl119pl_2nd.htm"
    )
    by_law = [
        (e.usc_identifier, e.is_note, e.action)
        for e in parsed.entries
        if (e.pl_congress, e.pl_num) == (119, 102)
    ]
    assert by_law == [
        ("/us/usc/t16/s2201", True, "new"),
        ("/us/usc/t16/s2201", False, None),
        ("/us/usc/t16/s2206", False, None),
    ]


# ------------------------------------------------------- the concurrent rule


def _group(version_id: int, first_seq: int, last_seq: int) -> vc._Group:
    return vc._Group(
        version_id=version_id,
        text_hash=b"",
        notes_hash=b"",
        heading=None,
        status=None,
        source_credit=None,
        first_seq=first_seq,
        last_seq=last_seq,
        first_release_id=first_seq,
        last_release_id=last_seq,
    )


def test_a_plain_chain_of_versions_is_never_concurrent():
    groups = [_group(1, 1, 5), _group(2, 6, 10), _group(3, 11, 15)]
    assert not vc._window_is_unreliable(groups, 1, groups[0])
    assert not vc._window_is_unreliable(groups, 2, groups[1])


def test_two_groups_mapped_at_one_release_are_concurrent():
    """ADR-0021: the source published several elements under one identifier."""
    groups = [_group(1, 1, 6), _group(2, 6, 10)]
    assert vc._window_is_unreliable(groups, 1, groups[0])


def test_the_transition_after_a_recurrence_is_concurrent_too():
    """Content that comes back — group 1 is mapped again at 9-10 — leaves the
    window into group 3 running straight across an era group 1 held."""
    recurring = _group(1, 1, 10)
    groups = [recurring, _group(2, 4, 8), _group(3, 11, 15)]
    assert vc._window_is_unreliable(groups, 1, groups[0])
    assert vc._window_is_unreliable(groups, 2, groups[1])


# ----------------------------------------------------------------- the corpus


@pytest.fixture(scope="session")
def corpus_with_119_2_table(loaded_database) -> None:
    """Skip unless the 119-2 classification table is loaded beside the corpus —
    `make ci-data` loads both; a dev box holds the full versions of each."""
    from sqlalchemy import select

    from db.base import SessionLocal
    from db.models import ClassificationEntry

    with SessionLocal() as session:
        rows = session.scalar(
            select(ClassificationEntry.id)
            .where(
                ClassificationEntry.pl_congress == 119,
                ClassificationEntry.pl_num == 102,
            )
            .limit(1)
        )
    if rows is None:  # pragma: no cover - environment-dependent
        _unavailable(
            "the 119th/2nd classification table is not loaded — run `make ci-data` "
            "(or `python -m ingest classification` for the real one)"
        )


def _compute(session, identifiers):
    from sqlalchemy import select

    from db.models import Section, Title

    ids = {}
    for identifier in identifiers:
        ids[identifier] = session.execute(
            select(Section.id)
            .join(Title, Title.id == Section.title_id)
            .where(Section.identifier == identifier, Title.num == "16")
        ).scalar_one()
    vc.compute_for_sections(session, list(ids.values()))
    return ids


def _changes_for(session, section_id):
    from sqlalchemy import select

    from db.models import ReleasePoint, SectionVersionChange

    labels = dict(session.execute(select(ReleasePoint.id, ReleasePoint.label)).all())
    rows = session.scalars(
        select(SectionVersionChange).where(
            SectionVersionChange.section_id == section_id
        )
    ).all()
    return rows, labels


def test_the_amended_sections_get_a_classified_text_transition(corpus_with_119_2_table):
    """s2201 and s2206 — the CI corpus's only two content-differing sections —
    must classify as `text`, attributed to Pub. L. 119-102 with both signals."""
    from sqlalchemy import select

    from db.base import SessionLocal
    from db.models import SectionVersionChangeLaw

    with SessionLocal() as session:
        ids = _compute(session, ["/us/usc/t16/s2201", "/us/usc/t16/s2206"])
        for identifier, section_id in ids.items():
            rows, labels = _changes_for(session, section_id)
            arriving = [
                row for row in rows if labels[row.window_to_release_id] == "119-102not101"
            ]
            assert len(arriving) == 1, identifier
            change = arriving[0]
            assert change.change_kind == "text"
            assert change.text_changed is True
            assert change.attribution == "classified"
            assert labels[change.window_from_release_id] == "119-99"
            assert change.concurrent is False
            laws = session.scalars(
                select(SectionVersionChangeLaw).where(
                    SectionVersionChangeLaw.change_id == change.id
                )
            ).all()
            assert [(law.pl_congress, law.pl_num) for law in laws] == [(119, 102)]
            assert laws[0].in_classification is True
            assert laws[0].in_source_credit is True
            assert laws[0].is_note_classification is False
            assert "" in laws[0].classification_actions  # the plain amendment row
        session.rollback()


def test_an_unchanged_section_gets_one_initial_row(corpus_with_119_2_table):
    """A section whose content deduped across every loaded release has exactly
    one version group, so exactly one change row: `initial`, no departure."""
    from db.base import SessionLocal
    from db.models import SectionVersion
    from sqlalchemy import func, select

    with SessionLocal() as session:
        ids = _compute(session, ["/us/usc/t16/s45f"])
        section_id = ids["/us/usc/t16/s45f"]
        rows, _labels = _changes_for(session, section_id)
        groups = session.scalar(
            select(func.count()).where(SectionVersion.section_id == section_id)
        )
        assert len(rows) == groups
        first = min(rows, key=lambda r: r.id)
        assert first.change_kind == "initial"
        assert first.from_version_id is None
        assert first.window_from_release_id is None
        if groups == 1:  # the two-release CI corpus
            assert [row.change_kind for row in rows] == ["initial"]
        session.rollback()


def test_every_transition_kind_is_from_the_vocabulary(corpus_with_119_2_table):
    from db.base import SessionLocal
    from sqlalchemy import select

    from db.models import SectionVersionChange

    with SessionLocal() as session:
        _compute(session, ["/us/usc/t16/s2201", "/us/usc/t16/s45f"])
        kinds = set(
            session.scalars(select(SectionVersionChange.change_kind).distinct())
        )
        assert kinds <= {"initial", "text", "notes", "structure"}
        session.rollback()


def test_reattribute_rebuilds_the_laws_without_touching_the_flags(
    corpus_with_119_2_table,
):
    from sqlalchemy import delete, select

    from db.base import SessionLocal
    from db.models import SectionVersionChangeLaw

    with SessionLocal() as session:
        ids = _compute(session, ["/us/usc/t16/s2201"])
        section_id = ids["/us/usc/t16/s2201"]
        rows, labels = _changes_for(session, section_id)
        target = next(
            row for row in rows if labels[row.window_to_release_id] == "119-102not101"
        )
        before = (target.change_kind, target.text_changed, target.notes_changed)
        # Sabotage what reattribution owns; leave what it must not touch.
        target.attribution = "none"
        session.execute(
            delete(SectionVersionChangeLaw).where(
                SectionVersionChangeLaw.change_id == target.id
            )
        )
        session.flush()

        releases = vc._release_facts(session)
        vc._reattribute_sections(session, [section_id], releases)

        session.refresh(target)
        assert target.attribution == "classified"
        assert (target.change_kind, target.text_changed, target.notes_changed) == before
        laws = session.scalars(
            select(SectionVersionChangeLaw).where(
                SectionVersionChangeLaw.change_id == target.id
            )
        ).all()
        assert [(law.pl_congress, law.pl_num) for law in laws] == [(119, 102)]
        session.rollback()


def test_the_backfilled_hashes_equal_the_ones_the_load_wrote(corpus_with_119_2_table):
    """`_build_record` hashes the element the parser has in hand; the backfill
    re-parses the stored fragment. The two paths must agree byte for byte, or a
    back-filled corpus and a freshly loaded one classify the same transition
    differently."""
    from sqlalchemy import select, update

    from db.base import SessionLocal
    from db.models import SectionVersion

    with SessionLocal() as session:
        ids = _compute(session, ["/us/usc/t16/s2201", "/us/usc/t16/s2206"])
        rows = session.execute(
            select(
                SectionVersion.id, SectionVersion.text_hash, SectionVersion.notes_hash
            ).where(SectionVersion.section_id.in_(list(ids.values())))
        ).all()
        at_load = {row.id: (row.text_hash, row.notes_hash) for row in rows}
        assert at_load and all(
            text and notes for text, notes in at_load.values()
        ), "the load wrote no hashes — reload the corpus"

        session.execute(
            update(SectionVersion)
            .where(SectionVersion.id.in_(list(at_load)))
            .values(text_hash=None, notes_hash=None)
        )
        session.flush()
        assert vc._ensure_hashes(session, list(at_load)) == len(at_load)

        after = session.execute(
            select(
                SectionVersion.id, SectionVersion.text_hash, SectionVersion.notes_hash
            ).where(SectionVersion.id.in_(list(at_load)))
        ).all()
        assert {row.id: (row.text_hash, row.notes_hash) for row in after} == at_load
        session.rollback()


def test_only_the_sections_a_release_can_have_moved_are_recomputed(
    corpus_with_119_2_table,
):
    """The incremental hook's set: the two sections 119-102not101 amended are
    in it, and a load does not recompute every section it maps."""
    from sqlalchemy import select

    from db.base import SessionLocal
    from db.models import (
        ReleasePoint,
        Section,
        SectionReleaseMap,
        SectionVersion,
        Title,
    )

    with SessionLocal() as session:
        title_id = session.scalar(select(Title.id).where(Title.num == "16"))
        release_id = session.scalar(
            select(ReleasePoint.id).where(ReleasePoint.label == "119-102not101")
        )
        wanted = ["/us/usc/t16/s2201", "/us/usc/t16/s2206"]
        ids = _compute(session, wanted)
        others = [
            section_id
            for section_id in session.scalars(
                select(Section.id)
                .where(Section.title_id == title_id, Section.id.not_in(list(ids.values())))
                .order_by(Section.id)
                .limit(48)
            )
        ]
        vc.compute_for_sections(session, others)

        every = list(ids.values()) + others
        mapped: dict[int, set[int]] = {}
        for section_id, version_id in session.execute(
            select(SectionVersion.section_id, SectionReleaseMap.section_version_id)
            .join(
                SectionVersion,
                SectionVersion.id == SectionReleaseMap.section_version_id,
            )
            .where(
                SectionVersion.section_id.in_(every),
                SectionReleaseMap.release_id == release_id,
            )
        ):
            mapped.setdefault(section_id, set()).add(version_id)

        need = vc.sections_needing_recompute(
            session,
            title_id=title_id,
            release_id=release_id,
            mapped_versions=mapped,
            new_version_sections=set(),
        )
        assert set(ids.values()) <= need, "an amended section must be recomputed"
        assert need < set(mapped), "a load must not recompute everything it maps"

        # A section with no change rows at all is in the set whatever else is
        # true of it — the interrupted-load case, and a corpus never computed.
        spare = others[0]
        vc.clear_change_rows(session, [spare])
        assert spare in vc.sections_needing_recompute(
            session,
            title_id=title_id,
            release_id=release_id,
            mapped_versions=mapped,
            new_version_sections=set(),
        )
        session.rollback()


def test_clearing_a_sections_rows_is_what_the_resume_skip_can_see(
    corpus_with_119_2_table,
):
    """Both the failed hook and `load-all --defer-version-changes` record
    themselves by deleting change rows, because `_complete_section_ids` — the
    resume skip a plain `version-changes` run uses — counts rows against version
    groups and cannot see a row whose window went stale."""
    from sqlalchemy import select

    from db.base import SessionLocal
    from db.models import Title

    with SessionLocal() as session:
        title_id = session.scalar(select(Title.id).where(Title.num == "16"))
        section_id = _compute(session, ["/us/usc/t16/s2201"])["/us/usc/t16/s2201"]
        assert section_id in vc._complete_section_ids(session, title_id)

        vc.clear_change_rows(session, [section_id])
        assert section_id not in vc._complete_section_ids(session, title_id)
        session.rollback()


def test_an_unknown_title_is_an_error_not_an_empty_run(corpus_with_119_2_table):
    from db.base import SessionLocal

    with SessionLocal() as session:
        assert vc._title_ids(session, ["16"])
        with pytest.raises(vc.UnknownTitleError):
            vc._title_ids(session, ["16", "notatitle"])


def test_the_report_counts_what_was_computed(corpus_with_119_2_table):
    from db.base import SessionLocal

    with SessionLocal() as session:
        _compute(session, ["/us/usc/t16/s2201", "/us/usc/t16/s45f"])
        report = vc.build_report(session)
        assert report["change_rows"] >= 2
        assert "initial" in report["by_kind"]
        assert "16" in report["per_title"]
        assert report["version_groups_total"] >= report["version_groups_hashed"] > 0
        session.rollback()


# -------------------------------------------------------------- the migration


SCRATCH_DB = f"uscode_migration_roundtrip_{os.getpid()}"
"""Named for the process that creates it. A fixed name races: two worktree
agents running `make test` against the one local Postgres would drop each
other's scratch database mid-run, and the loser's alembic run fails on a
database that no longer exists."""


def _alembic(url: str, *args: str) -> None:
    env = dict(os.environ, DATABASE_URL=url)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def _table_names(url: str) -> set[str]:
    from sqlalchemy import create_engine, inspect

    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def _column_names(url: str, table: str) -> set[str]:
    from sqlalchemy import create_engine, inspect

    engine = create_engine(url)
    try:
        return {column["name"] for column in inspect(engine).get_columns(table)}
    finally:
        engine.dispose()


def test_the_migration_round_trips():
    """Upgrade → downgrade → upgrade on a scratch database: the new tables and
    columns appear, disappear cleanly, and come back.

    Deliberately not `@pytest.mark.slow`, though it runs every migration in the
    project three times through a subprocess: measured at 2.4s, and CI runs
    `make test` alone (`-m 'not slow'`), so marking it would take the only
    migration round-trip in the suite out of every push."""
    from sqlalchemy import create_engine, text

    from db.config import settings

    admin = create_engine(settings.database_url, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}"'))
            conn.execute(text(f'CREATE DATABASE "{SCRATCH_DB}"'))
    except Exception as exc:  # pragma: no cover - environment-dependent
        _unavailable(f"cannot create a scratch database: {exc}")
    finally:
        admin.dispose()

    scratch_url = settings.database_url.rsplit("/", 1)[0] + f"/{SCRATCH_DB}"
    try:
        _alembic(scratch_url, "upgrade", "head")
        tables = _table_names(scratch_url)
        assert {"section_version_changes", "section_version_change_laws"} <= tables
        assert {"text_hash", "notes_hash"} <= _column_names(scratch_url, "section_versions")

        _alembic(scratch_url, "downgrade", "-1")
        tables = _table_names(scratch_url)
        assert "section_version_changes" not in tables
        assert "section_version_change_laws" not in tables
        assert not (
            {"text_hash", "notes_hash"} & _column_names(scratch_url, "section_versions")
        )

        _alembic(scratch_url, "upgrade", "head")
        assert {"section_version_changes", "section_version_change_laws"} <= _table_names(
            scratch_url
        )
    finally:
        admin = create_engine(settings.database_url, isolation_level="AUTOCOMMIT")
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{SCRATCH_DB}" WITH (FORCE)'))
        admin.dispose()


# ------------------------------------------------------------------ full sample


@pytest.mark.slow
def test_full_sample_hashes_separate_the_two_amended_sections(tmp_path):
    """ADR-0007's measurement, restated over the hashes: between 119-99 and
    119-102not101 only s2201 and s2206 changed text, so their `text_hash`
    differs while an untouched section's is identical — across two files whose
    guids all differ."""
    import zipfile

    from ingest import iter_sections
    from tests.conftest import USLM1_USC16, require

    newer = require(USLM1_USC16)
    zip_path = REPO_ROOT / "samples" / "uslm1" / "xml_usc16@119-99.zip"
    require(zip_path)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extract("usc16.xml", tmp_path)
    older = tmp_path / "usc16.xml"

    targets = {"/us/usc/t16/s2201", "/us/usc/t16/s2206", "/us/usc/t16/s45f"}

    def hashes(path: Path) -> dict[str, tuple[bytes, bytes]]:
        collected = {}
        for record in iter_sections(path):
            assert len(record.text_hash) == 32 and len(record.notes_hash) == 32
            if record.identifier in targets:
                collected[record.identifier] = (record.text_hash, record.notes_hash)
        return collected

    old, new = hashes(older), hashes(newer)
    assert set(old) == set(new) == targets
    assert old["/us/usc/t16/s45f"] == new["/us/usc/t16/s45f"]
    assert old["/us/usc/t16/s2201"][0] != new["/us/usc/t16/s2201"][0]
    assert old["/us/usc/t16/s2206"][0] != new["/us/usc/t16/s2206"][0]
    # s2201's amendment also added a note (the classification table's `nt new`).
    assert old["/us/usc/t16/s2201"][1] != new["/us/usc/t16/s2201"][1]
