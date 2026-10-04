"""
Unit tests for SpencerEducationAdapter (Step 30B.1).
"""
import pytest
from pathlib import Path
from src.collectors.spencer_education import SpencerEducationAdapter
from src.models import CommentStatus

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "spencer_education_article.html"


def test_spencer_education_supports_url():
    adapter = SpencerEducationAdapter()
    assert adapter.supports("https://spencereducation.com/creative-constraints/") is True
    assert adapter.supports("https://www.spencereducation.com/post-name/") is True
    assert adapter.supports("https://blog.teslontario.org/some-post/") is False


def test_spencer_education_extraction_with_fixture():
    adapter = SpencerEducationAdapter()
    html_content = FIXTURE_PATH.read_text(encoding="utf-8")
    
    res = adapter.extract("https://spencereducation.com/creative-constraints/", html=html_content)
    
    assert res.success is True
    article = res.article
    assert article is not None
    assert article.title == "Creative Constraints in the Classroom"
    assert article.author == "John Spencer"
    assert article.original_publisher == "Spencer Education"
    assert "Design thinking thrives" in article.article_text
    
    assert res.comments_status == CommentStatus.AVAILABLE
    assert article.comment_count_reported == 1
    assert article.comments_collected == 1
    
    c1 = article.comments[0]
    assert c1.author_display_name == "Marian"
    assert "Excellent article! 💕" in c1.comment_text
    # Verify missing date constraint: date must be None when absent in DOM
    assert c1.published_datetime is None
