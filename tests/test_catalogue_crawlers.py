import unittest

from scripts.crawl_csir import parse_tech_page as parse_csir
from scripts.crawl_dost_tapi import parse_tech_page as parse_dost
from backend.sources.crawl_nrdc import list_category


class _Response:
    status_code = 200

    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self):
        return None


class _Client:
    def __init__(self, text: str):
        self.text = text

    def get(self, *args, **kwargs):
        return _Response(self.text)


class CatalogueCrawlerParserTests(unittest.TestCase):
    def test_dost_uses_official_category_and_profile_institution(self):
        html = """
        <h1 class="page-title">Semen Extender for Goat</h1>
        <div class="field--name-body"><p>A processing aid for goat breeding.</p></div>
        <div class="field--name-field-profile-of-technologist">
          <p>Researcher Name</p><p>Isabela State University</p>
          <p>For inquiries, please contact DOST-PCAARRD</p>
        </div>
        """
        result = parse_dost(
            html,
            "https://tapitechtransfer.dost.gov.ph/technologies/"
            "agricultural-productivity/semen-extender-goat",
        )
        self.assertEqual("65", result["sector_code"])
        self.assertEqual("Agricultural productivity", result["sector"])
        self.assertEqual("Isabela State University", result["institute"])

    def test_dost_does_not_treat_msme_theme_as_manufacturing_sector(self):
        html = """
        <h1 class="page-title">Instant Spiced Beverage</h1>
        <div class="field--name-body"><p>A shelf-stable food and beverage product.</p></div>
        """
        result = parse_dost(
            html,
            "https://tapitechtransfer.dost.gov.ph/technologies/"
            "msme-competitiveness/instant-spiced-beverage",
        )
        self.assertEqual("MSME competitiveness", result["sector"])
        self.assertEqual("67", result["sector_code"])
        self.assertEqual("dost_content_fallback", result["classification_method"])

    def test_dost_reviewed_theme_record_beats_incidental_health_words(self):
        html = """
        <h1 class="page-title">Nipa Sugar</h1>
        <div class="field--name-body"><p>A sweetener marketed to health-conscious consumers.</p></div>
        """
        result = parse_dost(
            html,
            "https://tapitechtransfer.dost.gov.ph/technologies/"
            "msme-competitiveness/nipa-sugar",
        )
        self.assertEqual("67", result["sector_code"])
        self.assertEqual("dost_reviewed_record_mapping", result["classification_method"])

    def test_csir_uses_profile_table_lab_and_gauge(self):
        html = """
        <table class="table">
          <tr><td><small class="tech_caption">Title:</small></td>
              <td class="tech_data">Annatto Seed Separator</td></tr>
          <tr><td><small class="tech_caption">Value Proposition:</small></td>
              <td class="tech_data">A machine for natural food processing with health benefits.</td></tr>
          <tr><td><small class="tech_caption">Summary Application:</small></td>
              <td class="tech_data">Used by food manufacturers.</td></tr>
        </table>
        <div class="box-info"><div><img src="img/lab/cftri.jpg"
          alt="CSIR-Central Food Technological Research Institute"></div>
          <div>CSIR-Central Food Technological Research Institute[CSIR-CFTRI]</div></div>
        <div class="box-info"><span class="label-primary">Industrial Applications:</span>
          <span class="label-default">Food Processes [Food, Beverages, Tobacco]</span></div>
        <script>renderTo: 'TRIGaugeDiv', series: [{data: [6]}]</script>
        """
        result = parse_csir(
            html,
            "https://techindiacsir.anusandhan.net/online/"
            "annatto-seed-separator-T-2062-tech.htm",
        )
        self.assertEqual("Annatto Seed Separator", result["title"])
        self.assertEqual("CSIR-CFTRI", result["institute"])
        self.assertEqual("TRL-6", result["trl"])
        self.assertEqual("67", result["sector_code"])

    def test_nrdc_encodes_special_characters_in_detail_urls(self):
        client = _Client(
            '<a href="https://nrdcindia.com/technologyDetals/512/'
            'FREEZE DRIED BEVERAGES (MANGO & RABRI)">Technology</a>'
        )
        items = list_category(client, 1)
        self.assertEqual(1, len(items))
        self.assertIn("%20", items[0]["href"])
        self.assertIn("%26", items[0]["href"])
        self.assertIn("%28", items[0]["href"])


if __name__ == "__main__":
    unittest.main()
