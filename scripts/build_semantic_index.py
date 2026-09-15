#!/usr/bin/env python3
"""Build or incrementally refresh the deployable semantic-search index."""

import argparse
import asyncio
import logging
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.config import settings
from backend.search.semantic import SemanticStore, semantic_search
from backend.sources.registry import SOURCES


async def build(
    source_ids: set[str],
    batch_size: int,
    pause_seconds: float,
    output_path: Path,
) -> None:
    indexed_sources = [
        source
        for source in SOURCES
        if hasattr(source, "semantic_records")
        and (not source_ids or source.id in source_ids)
    ]
    if not indexed_sources:
        raise SystemExit("No matching locally indexed sources were found.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging_path = output_path.with_suffix(output_path.suffix + ".building")
    if not staging_path.exists() and source_ids and output_path.exists():
        shutil.copy2(output_path, staging_path)

    builder_store = SemanticStore(staging_path)
    semantic_search.store = builder_store

    try:
        total_updated = 0
        total_records = 0
        for source in indexed_sources:
            updated, records = await semantic_search.index_source(
                source.id,
                source.semantic_records(),
                batch_size=batch_size,
                pause_seconds=pause_seconds,
            )
            total_updated += updated
            total_records += records
            print(f"{source.id}: {updated} updated, {records} total")

        indexed_count = builder_store.document_count(
            semantic_search.model,
            semantic_search.dimensions,
        )
        os.replace(staging_path, output_path)
        print(
            f"Semantic index ready: {total_updated} updated across "
            f"{total_records} selected records; {indexed_count} total "
            f"documents written to {output_path}."
        )
    except BaseException:
        print(
            f"Build interrupted; partial progress is preserved at "
            f"{staging_path}. Run the same command to resume."
        )
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        help="Index only this source id; repeat for multiple sources.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        choices=range(1, 101),
        metavar="1-100",
    )
    parser.add_argument(
        "--pause-seconds",
        type=float,
        default=59.0,
        help="Delay between batches to respect the free embedding RPM limit.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(settings.SEMANTIC_SEARCH_INDEX_PATH),
        help="Path for the deployable SQLite document-vector index.",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(
        build(
            set(args.source),
            args.batch_size,
            max(0.0, min(args.pause_seconds, 59.0)),
            args.output,
        )
    )


if __name__ == "__main__":
    main()
