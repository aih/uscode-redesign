"""Full rebuild of the search indices from Postgres (ADR-0028).

`ingest.load` keeps the index in step release by release; this is the "start
over" path — after a mapping change, or to build the index over a corpus that
was loaded before search existed.

Two passes, and the default is the cheap one. `--current-only` indexes the text
in force now: one document per section, 66k of them, which is what the default
search reads. `--all-versions` adds every superseded version (490k documents) so
that `?release=` can reach back — it is a much longer job and buys nothing for
the default query.

Both passes stream. `.all()` over section_versions would pull ~3.5 GB of XML into
memory before indexing a single document.
"""

import sys
import argparse
from sqlalchemy import func, select
from sqlalchemy.orm import aliased
from db.base import SessionLocal
from db.models import (
    ReleasePoint,
    Section,
    SectionReleaseMap,
    SectionVersion,
    StructureNode,
)
from ingest import search_sync
from storage.search import get_search_client

FirstRelease = aliased(ReleasePoint)
MappedRelease = aliased(ReleasePoint)


def _current_version_query():
    """The version of each section published at the newest release point that
    section appears at — DISTINCT ON over the (section, release) map ordered by
    the inventory's global seq, because release labels do not sort (gotcha 4) and
    row ids are creation order, not release order.
    """
    return (
        select(
            Section.identifier,
            SectionVersion.id,
            SectionVersion.num,
            SectionVersion.heading,
            SectionVersion.xml,
            SectionVersion.status,
            SectionVersion.first_release_id,
            FirstRelease.seq,
            FirstRelease.label,
            SectionReleaseMap.parent_identifier,
            SectionReleaseMap.seq_in_title,
        )
        .select_from(SectionReleaseMap)
        .join(SectionVersion, SectionVersion.id == SectionReleaseMap.section_version_id)
        .join(Section, Section.id == SectionVersion.section_id)
        .join(MappedRelease, MappedRelease.id == SectionReleaseMap.release_id)
        .join(FirstRelease, FirstRelease.id == SectionVersion.first_release_id)
        .distinct(SectionVersion.section_id)
        .order_by(SectionVersion.section_id, MappedRelease.seq.desc())
    )


def _all_version_query():
    """Every version, with the placement it had at the release it first appeared.

    Placement is per (version, release) and this pass indexes a version once, so
    it has to pick one: the version's own first release, which is the release
    that put that text where it is. The join is an outer one because a version
    can have no map row at its first release — the source publishing two
    elements under one identifier leaves one of them unmapped (ADR-0021).
    """
    return (
        select(
            Section.identifier,
            SectionVersion.id,
            SectionVersion.num,
            SectionVersion.heading,
            SectionVersion.xml,
            SectionVersion.status,
            SectionVersion.first_release_id,
            FirstRelease.seq,
            FirstRelease.label,
            SectionReleaseMap.parent_identifier,
            SectionReleaseMap.seq_in_title,
        )
        .select_from(SectionVersion)
        .join(Section, Section.id == SectionVersion.section_id)
        .join(FirstRelease, FirstRelease.id == SectionVersion.first_release_id)
        .outerjoin(
            SectionReleaseMap,
            (SectionReleaseMap.section_version_id == SectionVersion.id)
            & (SectionReleaseMap.release_id == SectionVersion.first_release_id),
        )
    )


def _colliding_doc_ids(session) -> set[tuple[str, int]]:
    """(identifier, first_release_id) pairs that more than one version claims.

    `search_sync.doc_id` is built from exactly that pair, so each of these is two
    versions writing to one document and the index keeping whichever was indexed
    last (ADR-0021, ADR-0028's "not solved here"). The documents are flagged
    `id_collision` so a result can say it is one of two rather than pretending to
    be the only one.

    Measured over the loaded corpus: 160 pairs across 49 identifiers in 14
    titles. Re-check with `docs/verification/search-index.json`.
    """
    rows = session.execute(
        select(Section.identifier, SectionVersion.first_release_id)
        .join(Section, Section.id == SectionVersion.section_id)
        .group_by(Section.identifier, SectionVersion.first_release_id)
        .having(func.count() > 1)
    )
    return {(identifier, release_id) for identifier, release_id in rows}


def _index_structure(session, batch_size: int, index: str | None = None) -> int:
    print("Indexing StructureNodes...")
    buffer: list[dict] = []
    total = 0
    stmt = select(StructureNode).execution_options(
        stream_results=True, yield_per=batch_size
    )
    for node in session.execute(stmt).scalars():
        buffer.append({
            "identifier": node.identifier,
            "level": node.level,
            "num_value": node.num_value,
            "heading": node.heading,
            # Title 16's one `reserved` is on a subchapter (gotcha 13), so a
            # status filter that read sections alone would miss it.
            "status": node.status,
        })
        if len(buffer) >= batch_size:
            search_sync.sync_structure_nodes(buffer, index=index)
            total += len(buffer)
            buffer.clear()
            print(f"  Indexed {total} nodes", flush=True)
    if buffer:
        search_sync.sync_structure_nodes(buffer, index=index)
        total += len(buffer)
    print(f"Finished StructureNodes ({total}).")
    return total


def _index_sections(session, batch_size: int, limit, all_versions: bool,
                    index: str | None = None) -> int:
    current_ids: set[int] | None = None
    if all_versions:
        # Which versions are in force, so the superseded ones can be indexed with
        # is_current=False rather than left to the default search to trip over.
        print("Collecting current versions...")
        current_ids = {
            row[1]
            for row in session.execute(
                _current_version_query().execution_options(
                    stream_results=True, yield_per=5000
                )
            )
        }
        print(f"  {len(current_ids)} sections have a current version.")
        stmt = _all_version_query()
    else:
        stmt = _current_version_query()

    if limit is not None:
        stmt = stmt.limit(limit)

    collisions = _colliding_doc_ids(session)
    print(f"  {len(collisions)} documents are shared by two versions (ADR-0021).")

    print("Indexing SectionVersions...")
    buffer: list[dict] = []
    total = 0
    # `yield_per` has to be an execution option on the statement, not a call on
    # the Result: by the time a Result exists the query has run and psycopg has
    # already buffered every row client-side. Selecting SectionVersion.xml
    # across 489,738 rows that way costs ~3.5 GB, which is an OOM kill on an
    # 8 GB box. Measured over the real corpus: 1,020 MB and still climbing at
    # 60k rows the old way, a flat 283 MB this way.
    rows = session.execute(
        stmt.execution_options(stream_results=True, yield_per=batch_size)
    )
    for (
        identifier,
        version_id,
        num,
        heading,
        xml,
        status,
        first_release_id,
        first_release_seq,
        first_release_label,
        parent_identifier,
        seq_in_title,
    ) in rows:
        buffer.append({
            "identifier": identifier,
            "version_id": version_id,
            "num": num,
            "heading": heading,
            "xml": xml,
            "status": status,
            "parent_identifier": parent_identifier,
            "seq_in_title": seq_in_title,
            "id_collision": (identifier, first_release_id) in collisions,
            "first_release_id": first_release_id,
            "first_release_seq": first_release_seq,
            "first_release_label": first_release_label,
            "is_current": True if current_ids is None else version_id in current_ids,
        })
        if len(buffer) >= batch_size:
            search_sync.sync_sections(buffer, index=index)
            total += len(buffer)
            buffer.clear()
            print(f"  Indexed {total} sections", flush=True)
    if buffer:
        search_sync.sync_sections(buffer, index=index)
        total += len(buffer)
    print(f"Finished SectionVersions ({total}).")
    return total


def main():
    parser = argparse.ArgumentParser(
        description="Reindex sections and structure nodes to OpenSearch."
    )
    parser.add_argument("--batch-size", type=int, default=500, help="Batch size for indexing.")
    parser.add_argument(
        "--limit", type=int, default=None, help="Index at most this many section versions."
    )
    parser.add_argument(
        "--all-versions",
        action="store_true",
        help="Index superseded versions too, so ?release= can reach back (490k docs).",
    )
    parser.add_argument("--skip-sections", action="store_true", help="Structure nodes only.")
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Drop both indices first, in place. Search is down while it runs.",
    )
    parser.add_argument(
        "--if-changed",
        action="store_true",
        help=(
            "Rebuild only when the index was built from a different mapping, "
            "and build beside the live one rather than over it. What a deploy runs."
        ),
    )
    args = parser.parse_args()

    if args.if_changed:
        if args.recreate:
            parser.error("--if-changed and --recreate mean opposite things")
        return _rebuild_if_changed(args)

    if args.recreate:
        print("Recreating indices...")
        search_sync.recreate_indices()
    else:
        search_sync.create_indices()

    with SessionLocal() as session:
        _index_structure(session, args.batch_size)
        if not args.skip_sections:
            _index_sections(session, args.batch_size, args.limit, args.all_versions)

    return 0


def _rebuild_if_changed(args) -> int:
    """Rebuild the indices whose mapping has moved, without taking search down.

    The deploy path. A mapping change is not additive (ADR-0028), so the new
    fields are simply **absent** on an index built from the old one — `title:16`
    returns nothing, which reads exactly like a title with nothing in it rather
    than like a broken deployment. That failure is silent, which is why this is
    automatic rather than a line in a runbook.

    Build, then promote. Each index is filled under a name of its own and the
    alias is moved in one call at the end, so a search issued while this runs
    reads the old index throughout and the new one afterwards. A failure
    part-way leaves the alias where it was: the site keeps the index it had,
    which is stale rather than empty.
    """
    client = get_search_client()
    stale = search_sync.stale_aliases(client)
    if not stale:
        print("Search index mapping is current; nothing to rebuild.")
        return 0

    print(f"Rebuilding {', '.join(stale)} — the mapping has changed.")
    built: list[tuple[str, str]] = []
    with SessionLocal() as session:
        for alias in stale:
            physical = search_sync.create_index(client, alias)
            print(f"  building {physical}")
            if alias == search_sync.STRUCTURE_INDEX:
                _index_structure(session, args.batch_size, index=physical)
            else:
                _index_sections(
                    session, args.batch_size, args.limit, args.all_versions, index=physical
                )
            built.append((alias, physical))

    # Nothing is promoted until everything is built, so a failure in the second
    # index does not leave the first one live against a half-migrated pair.
    for alias, physical in built:
        client.indices.refresh(index=physical)
        search_sync.promote(client, alias, physical)
        print(f"  {alias} now points at {physical}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
