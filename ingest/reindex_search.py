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
from sqlalchemy import select
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
        )
        .select_from(SectionVersion)
        .join(Section, Section.id == SectionVersion.section_id)
        .join(FirstRelease, FirstRelease.id == SectionVersion.first_release_id)
    )


def _index_structure(session, batch_size: int) -> int:
    print("Indexing StructureNodes...")
    buffer: list[dict] = []
    total = 0
    for node in session.execute(select(StructureNode)).scalars().yield_per(batch_size):
        buffer.append({
            "identifier": node.identifier,
            "level": node.level,
            "num_value": node.num_value,
            "heading": node.heading,
        })
        if len(buffer) >= batch_size:
            search_sync.sync_structure_nodes(buffer)
            total += len(buffer)
            buffer.clear()
            print(f"  Indexed {total} nodes", flush=True)
    if buffer:
        search_sync.sync_structure_nodes(buffer)
        total += len(buffer)
    print(f"Finished StructureNodes ({total}).")
    return total


def _index_sections(session, batch_size: int, limit, all_versions: bool) -> int:
    current_ids: set[int] | None = None
    if all_versions:
        # Which versions are in force, so the superseded ones can be indexed with
        # is_current=False rather than left to the default search to trip over.
        print("Collecting current versions...")
        current_ids = {
            row[1] for row in session.execute(_current_version_query()).yield_per(5000)
        }
        print(f"  {len(current_ids)} sections have a current version.")
        stmt = _all_version_query()
    else:
        stmt = _current_version_query()

    if limit is not None:
        stmt = stmt.limit(limit)

    print("Indexing SectionVersions...")
    buffer: list[dict] = []
    total = 0
    rows = session.execute(stmt).yield_per(batch_size)
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
    ) in rows:
        buffer.append({
            "identifier": identifier,
            "version_id": version_id,
            "num": num,
            "heading": heading,
            "xml": xml,
            "status": status,
            "first_release_id": first_release_id,
            "first_release_seq": first_release_seq,
            "first_release_label": first_release_label,
            "is_current": True if current_ids is None else version_id in current_ids,
        })
        if len(buffer) >= batch_size:
            search_sync.sync_sections(buffer)
            total += len(buffer)
            buffer.clear()
            print(f"  Indexed {total} sections", flush=True)
    if buffer:
        search_sync.sync_sections(buffer)
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
        help="Drop both indices first. Required after a mapping change.",
    )
    args = parser.parse_args()

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


if __name__ == "__main__":
    sys.exit(main())
