"""
Unit tests for shared WordPress comment parsing and reply tree extraction module (Step 30A).
"""
import unittest
from bs4 import BeautifulSoup
from src.extraction.wordpress import parse_wordpress_comments


class TestWordPressExtraction(unittest.TestCase):

    def test_parse_wordpress_comments_nested_replies_and_trackback_filter(self):
        html = """
        <div id="comments">
            <ol class="comment-list">
                <li id="comment-1" class="comment depth-1">
                    <div class="comment-body">
                        <cite class="fn">Alice</cite>
                        <time datetime="2026-03-01T10:00:00Z">March 1, 2026</time>
                        <div class="comment-content"><p>Great article!</p></div>
                    </div>
                    <ul class="children">
                        <li id="comment-2" class="comment depth-2">
                            <div class="comment-body">
                                <cite class="fn">Bob</cite>
                                <time datetime="2026-03-01T11:00:00Z">March 1, 2026</time>
                                <div class="comment-content"><p>I agree with Alice.</p></div>
                            </div>
                        </li>
                    </ul>
                </li>
                <li id="comment-3" class="pingback">
                    <div class="comment-body">Pingback: External Link</div>
                </li>
            </ol>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        comments, trackback_count = parse_wordpress_comments(
            soup=soup,
            article_url="https://example.com/post",
            retrieved_at="2026-03-31T12:00:00Z"
        )

        self.assertEqual(len(comments), 2)
        self.assertEqual(trackback_count, 1)

        c1 = comments[0]
        self.assertEqual(c1.comment_id, "comment-1")
        self.assertEqual(c1.author_display_name, "Alice")
        self.assertEqual(c1.comment_text, "Great article!")
        self.assertIsNone(c1.parent_comment_id)
        self.assertEqual(c1.depth, 0)
        self.assertEqual(c1.reply_count, 1)

        c2 = comments[1]
        self.assertEqual(c2.comment_id, "comment-2")
        self.assertEqual(c2.author_display_name, "Bob")
        self.assertEqual(c2.comment_text, "I agree with Alice.")
        self.assertEqual(c2.parent_comment_id, "comment-1")
        self.assertEqual(c2.depth, 1)
        self.assertEqual(c2.reply_count, 0)


if __name__ == "__main__":
    unittest.main()
