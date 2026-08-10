import unittest

from scripts.crawl_tech2biz import (
    _translation_from_response,
    parse_tech_page,
    validate_records,
)


class Tech2BizCrawlerTests(unittest.TestCase):
    def test_quota_message_is_never_accepted_as_translation(self):
        original = "ภาษาไทย"
        translated, status = _translation_from_response(original, {
            "responseStatus": 200,
            "responseData": {
                "translatedText": (
                    "MYMEMORY WARNING: YOU USED ALL AVAILABLE FREE TRANSLATIONS "
                    "FOR TODAY"
                ),
            },
        })
        self.assertEqual(original, translated)
        self.assertEqual("quota_exceeded", status)

    def test_non_success_response_preserves_original(self):
        original = "ภาษาไทย"
        translated, status = _translation_from_response(original, {
            "responseStatus": 429,
            "responseDetails": "Quota exceeded",
            "responseData": {"translatedText": ""},
        })
        self.assertEqual(original, translated)
        self.assertEqual("quota_exceeded", status)

    def test_current_page_heading_and_original_content_are_extracted(self):
        html = """
        <div id="page-content">
          <div class="line-bottom">
            <span class="h2 font-weight-bold">ชื่อเทคโนโลยี</span>
          </div>
          <div class="content-detail d-none d-sm-block">
            <div class="d-block font-normal-16px mb-3">
              รายละเอียดเทคโนโลยีที่ยาวเพียงพอสำหรับการทดสอบ
            </div>
          </div>
          <div class="conversation-panel">
            <div class="font-weight-bold">สถาบันทดสอบ</div>
          </div>
          <div class="content-bg-area">
            <div class="font-30px text-center text-success">ระดับต้นแบบ</div>
            <div class="progress-bar"></div>
          </div>
        </div>
        """
        record = parse_tech_page(
            html,
            "https://www.tech2biz.net/content/1234-example",
        )
        self.assertEqual("ชื่อเทคโนโลยี", record["title_th"])
        self.assertIn("รายละเอียดเทคโนโลยี", record["summary_th"])
        self.assertEqual("สถาบันทดสอบ", record["institute"])
        self.assertEqual("Prototype", record["trl"])

    def test_visible_transfer_status_is_not_overridden_by_progress_labels(self):
        html = """
        <div id="page-content">
          <div class="line-bottom">
            <span class="h2 font-weight-bold">ชื่อเทคโนโลยี</span>
          </div>
          <div class="content-detail">
            <p>รายละเอียดเทคโนโลยีที่ยาวเพียงพอสำหรับการทดสอบ</p>
          </div>
          <div class="font-30px text-center text-success">
            ระดับถ่ายทอด (Transfer)
          </div>
          <ul>
            <li>Initial</li><li>Experimental</li>
            <li>Prototype</li><li>Transfer</li>
          </ul>
        </div>
        """
        record = parse_tech_page(
            html,
            "https://www.tech2biz.net/content/1234-example",
        )
        self.assertEqual("Transfer", record["trl"])

    def test_validation_blocks_translation_errors_and_duplicates(self):
        record = {
            "id": "tech2biz_1",
            "url": "https://www.tech2biz.net/content/1-example",
            "title": "MYMEMORY WARNING: quota",
            "summary": "Summary",
            "title_original": "ชื่อ",
            "summary_original": "รายละเอียด",
        }
        errors = validate_records([record, record], minimum=1)
        self.assertIn("duplicate record IDs found", errors)
        self.assertIn("duplicate record URLs found", errors)
        self.assertTrue(any("translation error text" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
