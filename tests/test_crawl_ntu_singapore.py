import unittest

from scripts.crawl_ntu_singapore import parse_detail, parse_listing


class NTUSingaporeCrawlerTests(unittest.TestCase):
    def test_listing_parser_reads_public_pagination_metadata(self):
        items, total, pages = parse_listing({
            "totalItems": 217,
            "totalPages": 22,
            "items": [{"title": "Example", "url": "https://www.ntu.edu.sg/example"}],
        })

        self.assertEqual((total, pages), (217, 22))
        self.assertEqual(len(items), 1)

    def test_detail_parser_uses_source_fields_and_omits_contact_data(self):
        html = """
        <div class="techportal-detail">
          <h1 class="detail-header__title">Solar membrane reactor</h1>
          <h3 class="techportal-detail__overview">A clean-energy reactor for industry.</h3>
          <input id="gaugeValueDesktop" value="6">
          <div class="az-listing__group">
            <h2 class="az-listing__group-title">Inventor</h2>
            <h3 class="contact-widget__title">Prof Example Researcher</h3>
          </div>
          <div class="article-detail__tags">
            <a>Energy Efficiency and Storage Systems</a>
            <a>Sustainability and Clean Environment</a>
          </div>
          <a href="mailto:private@example.test">Enquire</a>
        </div>
        """
        listing = {
            "title": "Fallback title",
            "description": "Fallback description",
            "date": "08 Oct 2026",
            "url": "https://www.ntu.edu.sg/innovates/tech-portal/tech-offers/detail/example",
        }

        record = parse_detail(html, listing)

        self.assertEqual(record["title"], "Solar membrane reactor")
        self.assertEqual(record["trl"], "TRL 6")
        self.assertEqual(record["sector_codes"], ["27", "13"])
        self.assertEqual(record["inventors"], ["Prof Example Researcher"])
        self.assertNotIn("private@example.test", str(record))


if __name__ == "__main__":
    unittest.main()
