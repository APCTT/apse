import tempfile
import unittest
from pathlib import Path

from scripts.crawl_iti_sri_lanka import (
    AVAILABLE_URL,
    PRODUCTION_PATH,
    parse_available_technologies,
    resolve_output,
    sector_for,
    validate_records,
    verify_available_catalogue_link,
)


class ITISriLankaCrawlerTests(unittest.TestCase):
    def test_expected_catalogue_must_be_linked_as_available(self):
        verify_available_catalogue_link(
            f'<a href="{AVAILABLE_URL}">Available Technologies</a>'
        )
        with self.assertRaisesRegex(ValueError, "manual status review"):
            verify_available_catalogue_link(
                f'<a href="{AVAILABLE_URL}">Commercialized Technologies</a>'
            )

    def test_parser_uses_headings_and_only_collects_pdf_links(self):
        html = """
        <section id="defaultPage"><div class="wrap-default-page">
          <a href="/outside.pdf">Ignored before a category</a>
        </div></section>
        """
        with self.assertRaisesRegex(ValueError, "before a recognized"):
            parse_available_technologies(html)

        html = """
        <section id="defaultPage"><div class="wrap-default-page">
          <h4>Food</h4>
          <a href="/wp-content/food.pdf"><strong>Fruit Processing </strong><strong>Technology</strong></a>
          <a href="https://192.248.98.14/retired.pdf">Broken legacy link</a>
          <a href="/not-a-pdf">Ignore me</a>
          <h4>Herbal</h4>
          <a href="/wp-content/cream.pdf">Herbal Burn Cream</a>
          <h4>Environment</h4>
          <a href="/wp-content/water.pdf">Wastewater Treatment</a>
        </div></section>
        """
        records = parse_available_technologies(html)
        self.assertEqual(3, len(records))
        self.assertEqual("Fruit Processing Technology", records[0]["title"])
        self.assertEqual(["67", "11", "13"], [r["sector_code"] for r in records])
        self.assertTrue(all(r["url"].endswith(".pdf") for r in records))
        self.assertIn("confirm current transfer availability", records[0]["summary"])

    def test_herbal_mapping_is_conservative(self):
        self.assertEqual(("67", "medium"), sector_for("Herbal", "Moringa Tea"))
        self.assertEqual(("11", "medium"), sector_for("Herbal", "Pain off spray"))
        self.assertEqual(("71", "medium"), sector_for("Herbal", "Herbal Shampoo"))

    def test_validation_has_minimum_record_guard(self):
        self.assertIn("below safety minimum", validate_records([], minimum=1)[0])

    def test_production_output_requires_explicit_confirmation(self):
        with self.assertRaisesRegex(ValueError, "replace-production"):
            resolve_output(PRODUCTION_PATH, replace_production=False)
        self.assertEqual(
            PRODUCTION_PATH.resolve(),
            resolve_output(PRODUCTION_PATH, replace_production=True),
        )
        with tempfile.TemporaryDirectory() as directory:
            staging = Path(directory) / "iti.staging.json"
            self.assertEqual(staging.resolve(), resolve_output(staging, False))


if __name__ == "__main__":
    unittest.main()
