"""
Unit tests for CultOfPedagogyAdapter (Step 30B.1).
"""
import pytest
from pathlib import Path
from src.collectors.cult_of_pedagogy import CultOfPedagogyAdapter
from src.models import CommentStatus

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "cult_of_pedagogy_article.html"


def test_cult_of_pedagogy_supports_url():
    adapter = CultOfPedagogyAdapter()
    assert adapter.supports("https://www.cultofpedagogy.com/chatgpt-example-machine/") is True
    assert adapter.supports("https://cultofpedagogy.com/some-post/") is True
    assert adapter.supports("https://wonkhe.com/blogs/some-post/") is False


def test_cult_of_pedagogy_extraction_with_fixture():
    adapter = CultOfPedagogyAdapter()
    html_content = FIXTURE_PATH.read_text(encoding="utf-8")
    
    res = adapter.extract("https://www.cultofpedagogy.com/chatgpt-example-machine/", html=html_content)
    
    assert res.success is True
    article = res.article
    assert article is not None
    assert article.title == "How to Use ChatGPT as an Example Machine"
    assert article.author == "Jennifer Gonzalez"
    assert article.original_publisher == "Cult of Pedagogy"
    assert "ChatGPT can be used by teachers" in article.article_text
    
    assert res.comments_status == CommentStatus.AVAILABLE
    assert article.comment_count_reported == 22
    assert article.comments_collected == 2
    
    # Check parent comment
    c1 = article.comments[0]
    assert c1.author_display_name == "Mike Szczepanik"
    assert "I love the examples" in c1.comment_text
    assert c1.depth == 0
    assert c1.reply_count == 1
    
    # Check nested reply comment
    c2 = article.comments[1]
    assert c2.author_display_name == "Jennifer Gonzalez"
    assert "That is such a great use case" in c2.comment_text
    assert c2.depth == 1
    assert c2.parent_comment_id == c1.comment_id
