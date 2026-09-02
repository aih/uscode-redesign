"""The version timeline's change annotations and ordering (Phase V2, ADR-0074).

Two layers under test:

  * `VersionOut` — the additive API shape, including the all-`None` degradation
    a corpus without computed change rows serializes to. No database.
  * `PostgresRepository.versions()` — the change annotations joined in, and the
    ordering fix: groups sort by the earliest release each is *mapped* to,
    never by `first_release_id`'s seq (ADR-0066). These need the loaded
    database and skip without it, like every other integration test.

Fixture facts (BUILDLOG 006, ADR-0074): /us/usc/t16/s2201 is one of the two
sections whose content differs between 119-99 and 119-102not101, and the
committed 119-2 classification slice attributes that change to Pub. L. 119-102.
Both hold on a `make dev-data` database and on the full corpus.
"""

import datetime

import pytest
from sqlalchemy import select

from api.schemas import VersionOut
from storage.repository import ReleaseRef, SectionVersionInfo, VersionLawRef

AMENDED = "/us/usc/t16/s2201"
UNCHANGED = "/us/usc/t16/s45f"
PRIOR = "119-99"
CURRENT = "119-102not101"

_REF = ReleaseRef(
    label=PRIOR,
    currency_date=datetime.date(2026, 6, 12),
    seq=379,
    congress=119,
    law_num=99,
)


# ------------------------------------------------------------- response shape


def test_version_out_degrades_to_nulls_without_change_rows():
    """A corpus loaded but never back-filled answers with every annotation
    null and no laws — the additive fields never invent a change kind."""
    out = VersionOut.of(
        SectionVersionInfo(
            content_hash="ab" * 32,
            first_seen=_REF,
            releases=(PRIOR,),
            num="45f",
            heading="Mineral King Valley addition authorized",
            status=None,
        )
    ).model_dump()

    for field in (
        "change_kind",
        "text_changed",
        "notes_changed",
        "status_changed",
        "concurrent",
        "attribution",
    ):
        assert out[field] is None
    assert out["laws"] == []


def test_version_out_carries_the_annotations_and_laws():
    out = VersionOut.of(
        SectionVersionInfo(
            content_hash="cd" * 32,
            first_seen=_REF,
            releases=(PRIOR, CURRENT),
            num="2201",
            heading="Definitions",
            status=None,
            change_kind="text",
            text_changed=True,
            notes_changed=True,
            status_changed=False,
            concurrent=False,
            attribution="classified",
            laws=(
                VersionLawRef(
                    pl_congress=119,
                    pl_num=102,
                    in_classification=True,
                    is_note_classification=False,
                    in_source_credit=True,
                    classification_actions=("", "new"),
                ),
            ),
        )
    ).model_dump()

    assert out["change_kind"] == "text"
    assert out["attribution"] == "classified"
    assert out["laws"] == [
        {
            "pl_congress": 119,
            "pl_num": 102,
            "in_classification": True,
            "is_note_classification": False,
            "in_source_credit": True,
            "classification_actions": ["", "new"],
            "in_ecct": False,
            "ecct_move": None,
        }
    ]


# ---------------------------------------------------------------- integration


@pytest.fixture()
def repository(loaded_database):
    """A `PostgresRepository` over a session of this test's own, never
    committed — mutations stay invisible to every other test."""
    from db.base import SessionLocal
    from storage.postgres import PostgresRepository

    with SessionLocal() as session:
        yield PostgresRepository(session), session
        session.rollback()


@pytest.mark.integration
def test_versions_carry_change_annotations(repository):
    repo, _session = repository
    entries = repo.versions(AMENDED)

    assert entries[0].change_kind == "initial"
    arriving = next(e for e in entries if e.releases[0] == CURRENT)
    assert arriving.change_kind == "text"
    assert arriving.text_changed is True
    assert arriving.attribution == "classified"
    law = next(
        law
        for law in arriving.laws
        if (law.pl_congress, law.pl_num) == (119, 102)
    )
    assert law.in_classification is True
    assert law.in_source_credit is True
    assert "new" in law.classification_actions


@pytest.mark.integration
def test_versions_annotations_reach_the_api(client):
    body = client.get(f"/api/v1/sections{AMENDED}/versions").json()

    arriving = next(
        v for v in body["versions"] if v["releases"][0] == CURRENT
    )
    assert arriving["change_kind"] == "text"
    assert arriving["attribution"] == "classified"
    assert {
        "pl_congress": 119,
        "pl_num": 102,
        "in_classification": True,
    }.items() <= next(
        law
        for law in arriving["laws"]
        if (law["pl_congress"], law["pl_num"]) == (119, 102)
    ).items()


@pytest.mark.integration
def test_versions_without_change_rows_answer_all_none(repository):
    """The degradation the spec demands: a section whose change rows do not
    exist (a corpus loaded but not back-filled) answers with every annotation
    `None` and no laws. Constructed by deleting the rows inside this test's
    never-committed session."""
    from db.models import Section, SectionVersionChange

    repo, session = repository
    section_id = session.execute(
        select(Section.id).where(Section.identifier == UNCHANGED)
    ).scalar_one()
    for change in session.scalars(
        select(SectionVersionChange).where(
            SectionVersionChange.section_id == section_id
        )
    ):
        session.delete(change)
    session.flush()

    entries = repo.versions(UNCHANGED)
    assert entries
    for entry in entries:
        assert entry.change_kind is None
        assert entry.text_changed is None
        assert entry.notes_changed is None
        assert entry.status_changed is None
        assert entry.concurrent is None
        assert entry.attribution is None
        assert entry.laws == ()


@pytest.mark.integration
def test_versions_order_by_earliest_mapped_release_not_first_release_id(repository):
    """ADR-0066: an incremental load attaches earlier releases to a group
    without lowering `first_release_id`, so ordering by that column's seq is
    wrong. Constructed here by swapping the first two groups' `first_release_id`
    inside a never-committed session: ordering by `first_release_id`'s seq
    would flip them; ordering by the earliest mapped release must not."""
    from db.models import ReleasePoint, Section, SectionVersion

    repo, session = repository
    before = repo.versions(AMENDED)
    if len(before) < 2:
        pytest.skip(f"{AMENDED} has one version group")

    section_id = session.execute(
        select(Section.id).where(Section.identifier == AMENDED)
    ).scalar_one()
    by_hash = {
        version.content_hash.hex(): version
        for version in session.scalars(
            select(SectionVersion).where(SectionVersion.section_id == section_id)
        )
    }
    first = by_hash[before[0].content_hash]
    second = by_hash[before[1].content_hash]
    seq_of = dict(
        session.execute(
            select(ReleasePoint.id, ReleasePoint.seq).where(
                ReleasePoint.id.in_([first.first_release_id, second.first_release_id])
            )
        ).all()
    )
    if seq_of[first.first_release_id] == seq_of[second.first_release_id]:
        pytest.skip("the two groups share a first_release seq")
    first.first_release_id, second.first_release_id = (
        second.first_release_id,
        first.first_release_id,
    )
    session.flush()

    after = repo.versions(AMENDED)
    assert [entry.content_hash for entry in after] == [
        entry.content_hash for entry in before
    ]
    # The swap is visible in `first_seen` — the order just did not follow it.
    assert after[0].first_seen.label == before[1].first_seen.label


@pytest.mark.integration
def test_the_adr_0066_measured_case_sorts_by_its_mapped_start(repository):
    """t16 § 45f's newest group carries `first_seen` 119-99 while its own
    releases run from 117-80 (ADR-0066's measurement). Full corpus only —
    the CI fixture corpus holds two release points and cannot show it."""
    repo, _session = repository
    entries = repo.versions(UNCHANGED)
    newest = entries[-1]
    if "117-80" not in newest.releases:
        pytest.skip("full corpus not loaded (needs 117-80 through 119-99 for t16)")

    assert newest.first_seen.label == PRIOR
    assert newest.releases[0] == "117-80"
    # It still sorts last: every other group's earliest mapped release is older.
    assert all(
        entry.releases[0] != newest.releases[0] for entry in entries[:-1]
    )
