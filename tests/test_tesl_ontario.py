"""
Unit tests for TESL Ontario Blog Source Adapter (Step 30A).
Uses offline HTML fixtures — 0 live network calls.
"""
import os
import unittest
from src.collectors.tesl_ontario import TESLOntarioAdapter
from src.models.comment_status import CommentStatus


class TestTESLOntarioAdapter(unittest.TestCase):

    def setUp(self):
        self.adapter = TESLOntarioAdapter()
        self.fixture_path = os.path.join(os.path.dirname(__file__), "fixtures", "tesl_ontario_article.html")
        with open(self.fixture_path, "r", encoding="utf-8") as f:
            self.fixture_html = f.read()

    def test_supports_routing(self):
        self.assertTrue(self.adapter.supports("https://blog.teslontario.org/ai-in-the-esl-classroom/"))
        self.assertFalse(self.adapter.supports("https://www.hepi.ac.uk/post"))

    def test_extraction_from_fixture(self):
        result = self.adapter.extract("https://blog.teslontario.org/ai-in-the-esl-classroom/", html=self.fixture_html)

        self.assertTrue(result.success)
        article = result.article
        self.assertEqual(article.platform, "TESL Ontario Blog")
        self.assertEqual(article.source_adapter, "TESLOntarioAdapter")
        self.assertEqual(article.original_publisher, "TESL Ontario")
        self.assertEqual(article.title, "AI in the ESL Classroom")
        self.assertEqual(article.author, "Jane Educator")
        self.assertEqual(article.publication_datetime, "2026-03-15T09:00:00+00:00")
        self.assertIn("Artificial intelligence is transforming language learning", article.article_text)
        self.assertEqual(article.comments_status, CommentStatus.AVAILABLE)
        self.assertEqual(article.comment_count_reported, 2)
        self.assertEqual(article.comments_collected, 2)
        self.assertEqual(len(article.comments), 2)

        # First comment
        c1 = article.comments[0]
        self.assertEqual(c1.author_display_name, "Maria Teacher")
        self.assertEqual(c1.comment_text, "Great post! I have been using AI for lesson planning with great success.")
        self.assertIsNone(c1.parent_comment_id)

        # Nested reply
        c2 = article.comments[1]
        self.assertEqual(c2.author_display_name, "Jane Educator")
        self.assertEqual(c2.comment_text, "Thanks Maria! Which prompt structures work best for your classes?")
        self.assertEqual(c2.parent_comment_id, "comment-501")


if __name__ == "__main__":
    unittest.main()
