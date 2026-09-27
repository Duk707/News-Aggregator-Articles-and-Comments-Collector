import os
import json
import pytest
from datetime import datetime, timezone
from src.models.article import Article
from src.models.comment import Comment
from src.models.comment_status import CommentStatus
from src.export.json_exporter import JSONExporter


@pytest.fixture
def sample_article_with_comments() -> Article:
    """
    Creates a sample normalized Article with comments, special UTF-8 characters,
    and preserved null fields.
    """
    now = datetime.now(timezone.utc).isoformat()
    c1 = Comment(
        comment_id="comm_001",
        article_url="https://news.yahoo.com/ai-education-123.html",
        parent_comment_id=None,
        author_display_name="Dr. Marie Curie — Éducatrice",
        comment_text="L'intelligence artificielle transforme l'éducation moderna! “Adaptive learning is key.”",
        published_datetime="2026-09-25T14:00:00Z",
        reactions=15,
        reply_count=1,
        depth=0,
        retrieved_at=now
    )
    c2 = Comment(
        comment_id="comm_002",
        article_url="https://news.yahoo.com/ai-education-123.html",
        parent_comment_id="comm_001",
        author_display_name="Prof. John Doe",
        comment_text="I agree, Dr. Curie! It allows personalized feedback for every student.",
        published_datetime="2026-09-25T14:30:00Z",
        reactions=3,
        reply_count=0,
        depth=1,
        retrieved_at=now
    )
    return Article(
        platform="Yahoo News",
        source_adapter="YahooAdapter",
        requested_url="https://news.yahoo.com/ai-education-123.html",
        canonical_url="https://www.yahoo.com/news/ai-education-123.html",
        original_publisher="Reuters & USA TODAY",
        title="AI in Education: “Revolutionizing Classrooms in 2026” — Special Report",
        author="Jane Smith",
        publication_datetime="2026-09-25T12:00:00Z",
        updated_datetime=None,  # Genuinely unavailable -> preserve null
        article_text="Artificial Intelligence tools are enabling personalized learning pathways. “Students learn at their own pace,” explained researchers.",
        language="en-US",
        topic_query="AI in Education",
        retrieved_at=now,
        comments_status=CommentStatus.AVAILABLE,
        comment_count_reported=42,
        comments_collected=2,
        extraction_method="JSON-LD + OpenGraph + Rendered HTML DOM",
        diagnostic_notes=["Extracted title via JSON-LD", "Comments loaded and parsed successfully"],
        comments=[c1, c2]
    )


@pytest.fixture
def sample_article_zero_comments_not_loaded() -> Article:
    """
    Creates a sample normalized Article with 0 collected comments and a non-AVAILABLE status (NOT_LOADED).
    """
    now = datetime.now(timezone.utc).isoformat()
    return Article(
        platform="Yahoo News",
        source_adapter="YahooAdapter",
        requested_url="https://news.yahoo.com/news/politics/article-999.html",
        canonical_url="https://www.yahoo.com/news/politics/article-999.html",
        original_publisher="Associated Press",
        title="Supreme Court Issues New Ruling",
        author=None,  # Unavailable -> null
        publication_datetime="2026-09-25T10:00:00Z",
        updated_datetime=None,
        article_text="The Supreme Court delivered an opinion today...",
        language="en-US",
        topic_query=None,
        retrieved_at=now,
        comments_status=CommentStatus.NOT_LOADED,
        comment_count_reported=None,  # Unavailable -> null
        comments_collected=0,
        extraction_method="JSON-LD",
        diagnostic_notes=["Found 'View comments' button", "No comment DOM elements loaded after activation"],
        comments=[]
    )


def test_json_export_article_with_comments(sample_article_with_comments, tmp_path):
    """
    Verifies exporting an article with comments to JSON:
    - File created cleanly
    - Null values preserved
    - UTF-8 characters (smart quotes, em-dashes, non-English characters) preserved without escape corruption
    - Read back successfully into validated Article model
    """
    target_file = os.path.join(tmp_path, "article_with_comments.json")
    saved_path = JSONExporter.export_article(sample_article_with_comments, output_path=target_file)

    assert os.path.exists(saved_path)

    # Inspect raw file text for UTF-8 preservation & null fields
    with open(saved_path, "r", encoding="utf-8") as f:
        raw_json_str = f.read()

    # UTF-8 assertions: raw Unicode chars should be present, not escape codes like \u00e9
    assert "Éducatrice" in raw_json_str
    assert "“Revolutionizing Classrooms in 2026”" in raw_json_str
    assert "— Special Report" in raw_json_str
    assert '"updated_datetime": null' in raw_json_str

    # Read back and validate model integrity
    reloaded_article = JSONExporter.load_article(saved_path)
    assert isinstance(reloaded_article, Article)
    assert reloaded_article.platform == "Yahoo News"
    assert reloaded_article.title == sample_article_with_comments.title
    assert reloaded_article.updated_datetime is None
    assert reloaded_article.comments_status == CommentStatus.AVAILABLE
    assert reloaded_article.comments_collected == 2
    assert len(reloaded_article.comments) == 2

    c1 = reloaded_article.comments[0]
    assert c1.author_display_name == "Dr. Marie Curie — Éducatrice"
    assert c1.depth == 0
    assert c1.reply_count == 1

    c2 = reloaded_article.comments[1]
    assert c2.parent_comment_id == "comm_001"
    assert c2.depth == 1


def test_json_export_zero_comments_non_available_status(sample_article_zero_comments_not_loaded, tmp_path):
    """
    Verifies exporting an article with zero collected comments and NOT_LOADED status:
    - Status NOT_LOADED preserved
    - comments array is empty []
    - comments_collected is 0
    - null preserved for missing author and reported count
    - Read back succeeds
    """
    target_file = os.path.join(tmp_path, "article_not_loaded.json")
    saved_path = JSONExporter.export_article(sample_article_zero_comments_not_loaded, output_path=target_file)

    assert os.path.exists(saved_path)

    with open(saved_path, "r", encoding="utf-8") as f:
        raw_json_str = f.read()

    assert '"comments_status": "NOT_LOADED"' in raw_json_str
    assert '"author": null' in raw_json_str
    assert '"comment_count_reported": null' in raw_json_str
    assert '"comments_collected": 0' in raw_json_str
    assert '"comments": []' in raw_json_str

    reloaded = JSONExporter.load_article(saved_path)
    assert reloaded.comments_status == CommentStatus.NOT_LOADED
    assert reloaded.comments_collected == 0
    assert reloaded.comments == []
    assert reloaded.author is None


def test_json_export_batch(sample_article_with_comments, sample_article_zero_comments_not_loaded, tmp_path):
    """
    Verifies batch exporting multiple articles to a JSON array file and loading them back.
    """
    batch_file = os.path.join(tmp_path, "batch_test.json")
    articles = [sample_article_with_comments, sample_article_zero_comments_not_loaded]

    saved_path = JSONExporter.export_batch(articles, output_path=batch_file)
    assert os.path.exists(saved_path)

    reloaded_batch = JSONExporter.load_batch(saved_path)
    assert len(reloaded_batch) == 2
    assert reloaded_batch[0].title == sample_article_with_comments.title
    assert reloaded_batch[1].comments_status == CommentStatus.NOT_LOADED
