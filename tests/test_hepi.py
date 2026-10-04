"""
Unit tests for Higher Education Policy Institute (HEPI) Source Adapter (Step 30A).
Uses offline HTML fixtures — 0 live network calls.
"""
import os
import unittest
from src.collectors.hepi import HEPIAdapter
from src.models.comment_status import CommentStatus


class TestHEPIAdapter(unittest.TestCase):

    def setUp(self):
        self.adapter = HEPIAdapter()
        self.fixture_path = os.path.join(os.path.dirname(__file__), "fixtures", "hepi_article.html")
        with open(self.fixture_path, "r", encoding="utf-8") as f:
            self.fixture_html = f.read()

    def test_supports_routing(self):
        self.assertTrue(self.adapter.supports("https://www.hepi.ac.uk/2026/02/10/generative-ai/"))
        self.assertTrue(self.adapter.supports("https://hepi.ac.uk/post"))
        self.assertFalse(self.adapter.supports("https://blog.teslontario.org/post"))

    def test_extraction_from_fixture(self):
        result = self.adapter.extract("https://www.hepi.ac.uk/2026/02/10/generative-ai/", html=self.fixture_html)

        self.assertTrue(result.success)
        article = result.article
        self.assertEqual(article.platform, "Higher Education Policy Institute")
        self.assertEqual(article.source_adapter, "HEPIAdapter")
        self.assertEqual(article.original_publisher, "Higher Education Policy Institute")
        self.assertEqual(article.title, "Generative AI in UK Higher Education")
        self.assertEqual(article.author, "Dr. John Policy")
        self.assertEqual(article.publication_datetime, "2026-02-10T08:00:00+00:00")
        self.assertIn("The Higher Education Policy Institute (HEPI) explores", article.article_text)
        self.assertEqual(article.comments_status, CommentStatus.AVAILABLE)
        self.assertEqual(article.comment_count_reported, 1)
        self.assertEqual(article.comments_collected, 1)

        c1 = article.comments[0]
        self.assertEqual(c1.author_display_name, "Prof. Sarah Dean")
        self.assertEqual(c1.comment_text, "Assessment reform must keep pace with these generative AI tools.")


if __name__ == "__main__":
    unittest.main()
