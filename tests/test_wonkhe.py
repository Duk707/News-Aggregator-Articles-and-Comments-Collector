"""
Unit tests for WonkheAdapter (Step 30B.2).
"""
import pytest
from pathlib import Path
from src.collectors.wonkhe import WonkheAdapter
from src.models import CommentStatus

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "wonkhe_article.html"


def test_wonkhe_supports_url():
    adapter = WonkheAdapter()
    assert adapter.supports("https://wonkhe.com/blogs/chatgpt-assessment-and-cheating-have-we-tried-trusting-students/") is True
    assert adapter.supports("https://www.wonkhe.com/blogs/some-post/") is True
    assert adapter.supports("https://spencereducation.com/some-post/") is False


def test_wonkhe_extraction_with_fixture():
    adapter = WonkheAdapter()
    html_content = FIXTURE_PATH.read_text(encoding="utf-8")
    
    res = adapter.extract("https://wonkhe.com/blogs/chatgpt-assessment-and-cheating-have-we-tried-trusting-students/", html=html_content)
    
    assert res.success is True
    article = res.article
    assert article is not None
    assert article.title == "ChatGPT, assessment and cheating – have we tried trusting students?"
    assert article.author == "Debbie McVitty"
    assert article.original_publisher == "Wonkhe"
    assert "Generative AI tools raise fundamental questions" in article.article_text
    
    assert res.comments_status == CommentStatus.AVAILABLE
    assert article.comment_count_reported == 8
    assert article.comments_collected == 2
    
    c1 = article.comments[0]
    assert c1.author_display_name == "Andy"
    assert "Great article that recognises" in c1.comment_text
    assert c1.published_datetime == "20 Feb 2023"
    
    c2 = article.comments[1]
    assert c2.author_display_name == "Stephen Powell"
    assert "Students of marketing related subjects" in c2.comment_text
    assert c2.published_datetime == "20 Feb 2023"
