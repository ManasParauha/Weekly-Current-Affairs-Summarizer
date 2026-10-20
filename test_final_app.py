import hashlib
import unittest
from streamlit.testing.v1 import AppTest
from app import build_pdf

class TestStreamlitApp(unittest.TestCase):
    def test_01_initial_state(self):
        at = AppTest.from_file("app.py", default_timeout=30).run()
        self.assertEqual(at.title[0].value, "Weekly Current Affairs Summarizer")
        self.assertEqual(len(at.file_uploader), 1)
        self.assertEqual(len(at.button), 0)
        self.assertEqual(len(at.download_button), 0)
        print("[PASS] Test 1: Initial state clean, title and uploader present")

    def test_02_short_text_warning_and_no_generate_button(self):
        at = AppTest.from_file("app.py", default_timeout=30).run()
        import pymupdf
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((50, 50), "Short scanned placeholder.")
        short_bytes = doc.tobytes()

        at.file_uploader[0].upload(
            filename="empty_scanned.pdf",
            content=short_bytes,
            mime_type="application/pdf",
        ).run()

        self.assertEqual(len(at.warning), 1)
        self.assertIn("This PDF has almost no readable text", at.warning[0].value)
        self.assertEqual(len(at.button), 0)
        self.assertEqual(len(at.download_button), 0)
        print("[PASS] Test 2: Short text (<200 chars) warning displayed, Generate button hidden")

    def test_03_file_size_limit_check(self):
        at = AppTest.from_file("app.py", default_timeout=30).run()
        large_bytes = b"0" * (26 * 1024 * 1024)

        at.file_uploader[0].upload(
            filename="large_file.pdf",
            content=large_bytes,
            mime_type="application/pdf",
        ).run()

        self.assertEqual(len(at.error), 1)
        self.assertIn("25 MB", at.error[0].value)
        self.assertEqual(len(at.button), 0)
        print("[PASS] Test 3: Large file (>25 MB) shows friendly error")

    def test_04_session_state_caching_and_display(self):
        at = AppTest.from_file("app.py", default_timeout=30).run()
        with open("sample_output.pdf", "rb") as f:
            pdf_bytes = f.read()

        file_hash = hashlib.md5(pdf_bytes).hexdigest()

        mock_summary = {
            "title": "Weekly Current Affairs Summary",
            "week_overview": "Key developments across governance, economy, and space.",
            "topics": [
                {
                    "heading": "Digital Public Infrastructure Expansion",
                    "category": "national",
                    "key_points": ["Expanded coverage to 50,000 villages.", "Enhanced cybersecurity protocols."]
                }
            ],
            "important_dates": [
                {"date": "15 October 2026", "event": "National DPI Mission Launch"}
            ]
        }
        mock_pdf_bytes = build_pdf(mock_summary)

        # Pre-populate cache (simulating prior run of the exact same PDF)
        at.session_state["file_cache"] = {
            file_hash: {
                "summary": mock_summary,
                "pdf_bytes": mock_pdf_bytes,
            }
        }

        # Upload the PDF with the cached hash
        at.file_uploader[0].upload(
            filename="sample_output.pdf",
            content=pdf_bytes,
            mime_type="application/pdf",
        ).run()

        # Generate button should NOT be shown because cached results exist
        self.assertEqual(len(at.button), 0)

        # Download button should be immediately available
        self.assertEqual(len(at.download_button), 1)
        self.assertEqual(at.download_button[0].label, "Download Summary PDF")

        # Summary title and overview rendered in overview card
        self.assertTrue(any("Weekly Current Affairs Summary" in m.value for m in at.markdown))
        self.assertTrue(any("Key developments across governance, economy, and space." in m.value for m in at.markdown))

        # Dates table rendered
        self.assertEqual(len(at.table), 1)
        print("[PASS] Test 4: Hashed file re-upload instantly reuses cached summary and PDF bytes without calling AI")

if __name__ == "__main__":
    unittest.main()
