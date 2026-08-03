#!/usr/bin/env python3
"""Build or incrementally refresh the local Gemini semantic-search index."""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.search.semantic import semantic_search
from backend.sources.registry import SOURCES


async def build(source_ids: set[str], batch_size: int) -> None:
    indexed_sources = [
        source
        for source in SOURCES
        if hasattr(source, "semantic_records")
        and (not source_ids or source.id in source_ids)
    ]
    if not indexed_sources:
        raise SystemExit("No matching locally indexed sources were found.")

    total_updated = 0
    total_records = 0
    for source in indexed_sources:
        updated, records = await semantic_search.index_source(
            source.id,
            source.semantic_records(),
            batch_size=batch_size,
        )
        total_updated += updated
        total_records += records
        print(f"{source.id}: {updated} updated, {records} total")

    print(
        f"Semantic index ready: {total_updated} updated across "
        f"{total_records} catalogue records."
    )


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
        default=50,
        choices=range(1, 101),
        metavar="1-100",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(build(set(args.source), args.batch_size))


if __name__ == "__main__":
    main()
