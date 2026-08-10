import json
import tempfile
import unittest
from pathlib import Path

from backend.sources.crawler_safety import (
    resolve_output,
    snapshot_diff,
    validate_snapshot,
    write_json_atomic,
)


def record(number: int) -> dict:
    return {
        "id": f"source_{number}",
        "title": f"Technology {number}",
        "url": f"https://example.org/technology/{number}",
    }


class CrawlerSafetyTests(unittest.TestCase):
    def test_production_requires_explicit_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            production = Path(directory) / "source.json"
            with self.assertRaisesRegex(ValueError, "replace-production"):
                resolve_output(production, production, False)

    def test_rejects_excessive_failures_and_count_drop(self):
        with tempfile.TemporaryDirectory() as directory:
            production = Path(directory) / "source.json"
            production.write_text(json.dumps([record(i) for i in range(100)]))
            errors = validate_snapshot(
                [record(i) for i in range(70)],
                minimum_records=50,
                discovered_count=100,
                failed_count=30,
                production_path=production,
                max_failure_rate=0.05,
                max_drop_fraction=0.15,
            )
        self.assertTrue(any("failure rate" in error for error in errors))
        self.assertTrue(any("dropped" in error for error in errors))

    def test_atomic_write_and_diff(self):
        with tempfile.TemporaryDirectory() as directory:
            production = Path(directory) / "source.json"
            write_json_atomic([record(1)], production)
            diff = snapshot_diff([record(1), record(2)], production)
            self.assertEqual(1, diff["added"])
            self.assertEqual(0, diff["removed"])
            self.assertFalse(production.with_suffix(".json.tmp").exists())


if __name__ == "__main__":
    unittest.main()
