import sys
import argparse
from sqlalchemy import select
from db.base import SessionLocal
from db.models import SectionVersion, StructureNode
from ingest import search_sync

def main():
    parser = argparse.ArgumentParser(description="Reindex all sections and structure nodes to OpenSearch.")
    parser.add_argument("--batch-size", type=int, default=500, help="Batch size for indexing.")
    args = parser.parse_args()

    search_sync.create_indices()
    
    with SessionLocal() as session:
        print("Indexing StructureNodes...")
        nodes = session.execute(select(StructureNode)).scalars().all()
        nodes_to_sync = []
        for n in nodes:
            nodes_to_sync.append({
                "identifier": n.identifier,
                "level": n.level,
                "num_value": n.num_value,
                "heading": n.heading
            })
            if len(nodes_to_sync) >= args.batch_size:
                search_sync.sync_structure_nodes(nodes_to_sync)
                nodes_to_sync.clear()
                print(f"  Indexed {args.batch_size} nodes")
        
        if nodes_to_sync:
            search_sync.sync_structure_nodes(nodes_to_sync)
            print(f"  Indexed {len(nodes_to_sync)} nodes")
        print("Finished StructureNodes.")

        print("Indexing SectionVersions...")
        versions = session.execute(select(SectionVersion)).scalars().all()
        versions_to_sync = []
        for v in versions:
            versions_to_sync.append({
                "identifier": v.section.identifier if hasattr(v, 'section') and v.section else "unknown",
                "num": v.num,
                "heading": v.heading,
                "xml": v.xml,
                "status": v.status,
                "release_id": v.first_release_id
            })
            if len(versions_to_sync) >= args.batch_size:
                search_sync.sync_sections(versions_to_sync)
                versions_to_sync.clear()
                print(f"  Indexed {args.batch_size} sections")
        
        if versions_to_sync:
            search_sync.sync_sections(versions_to_sync)
            print(f"  Indexed {len(versions_to_sync)} sections")
        print("Finished SectionVersions.")

if __name__ == "__main__":
    sys.exit(main())
