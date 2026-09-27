import json
from datetime import datetime, timezone
from src.models import CommentStatus, Comment, Article, ExtractionResult


def test_comment_status_enum_values():
    """Verify all mandatory CommentStatus enum values exist and are strings."""
    expected_statuses = [
        "AVAILABLE",
        "NONE_PRESENT",
        "DISABLED",
        "LOGIN_REQUIRED",
        "NOT_LOADED",
        "BLOCKED",
        "UNSUPPORTED",
        "UNKNOWN",
        "EXTRACTION_ERROR"
    ]
    for status_str in expected_statuses:
        status_enum = CommentStatus(status_str)
        assert status_enum.value == status_str


def test_comment_model_instantiation_and_serialization():
    """Verify Comment model instantiates correctly and serializes to/from JSON."""
    now_iso = datetime.now(timezone.utc).isoformat()
    comment = Comment(
        comment_id="c123",
        article_url="https://news.yahoo.com/sample-article",
        parent_comment_id=None,
        author_display_name="ResearchUser",
        comment_text="This is a public comment on AI in education.",
        published_datetime=now_iso,
        reactions={"upvotes": 10, "downvotes": 2},
        reply_count=3,
        depth=0,
        retrieved_at=now_iso
    )

    assert comment.comment_id == "c123"
    assert comment.reply_count == 3
    assert comment.depth == 0

    # JSON round trip
    json_data = comment.model_dump_json()
    parsed_dict = json.loads(json_data)
    assert parsed_dict["comment_id"] == "c123"
    assert parsed_dict["author_display_name"] == "ResearchUser"

    reconstructed = Comment.model_validate_json(json_data)
    assert reconstructed == comment


def test_article_model_instantiation_and_serialization():
    """Verify Article model with nested Comments instantiates and serializes cleanly."""
    now_iso = datetime.now(timezone.utc).isoformat()
    comment1 = Comment(
        comment_id="c1",
        article_url="https://news.yahoo.com/sample-article",
        comment_text="First comment",
        retrieved_at=now_iso
    )
    comment2 = Comment(
        comment_id="c2",
        article_url="https://news.yahoo.com/sample-article",
        parent_comment_id="c1",
        comment_text="Reply to first comment",
        depth=1,
        retrieved_at=now_iso
    )

    article = Article(
        platform="Yahoo News",
        source_adapter="YahooAdapter",
        requested_url="https://news.yahoo.com/sample-article",
        canonical_url="https://news.yahoo.com/sample-article-canonical",
        original_publisher="Associated Press",
        title="AI Tools Transforming Modern Classrooms",
        author="Jane Doe",
        publication_datetime="2026-09-25T10:00:00Z",
        article_text="Artificial intelligence is playing an increasing role in education...",
        language="en-US",
        topic_query="AI in Education",
        retrieved_at=now_iso,
        comments_status=CommentStatus.AVAILABLE,
        comment_count_reported=2,
        comments_collected=2,
        extraction_method="JSON-LD + DOM",
        diagnostic_notes=["JSON-LD metadata found", "Comments expanded successfully"],
        comments=[comment1, comment2]
    )

    assert article.platform == "Yahoo News"
    assert article.comments_status == CommentStatus.AVAILABLE
    assert len(article.comments) == 2
    assert article.comments[1].parent_comment_id == "c1"

    # Test JSON serialization & deserialization
    json_str = article.model_dump_json(by_alias=True)
    assert "topic/query" in json_str or "topic_query" in json_str

    reconstructed_article = Article.model_validate_json(json_str)
    assert reconstructed_article.title == "AI Tools Transforming Modern Classrooms"
    assert reconstructed_article.comments_status == CommentStatus.AVAILABLE
    assert len(reconstructed_article.comments) == 2


def test_extraction_result_model():
    """Verify ExtractionResult model handles success and failure cases correctly."""
    now_iso = datetime.now(timezone.utc).isoformat()

    result_fail = ExtractionResult(
        requested_url="https://unsupported.com/article",
        success=False,
        comments_status=CommentStatus.UNSUPPORTED,
        error_message="Unsupported domain",
        diagnostic_notes=["Domain unsupported.com has no configured adapter"],
        retrieved_at=now_iso
    )

    assert not result_fail.success
    assert result_fail.comments_status == CommentStatus.UNSUPPORTED
    assert result_fail.article is None

    json_data = result_fail.model_dump_json()
    reconstructed = ExtractionResult.model_validate_json(json_data)
    assert reconstructed.success is False
    assert reconstructed.error_message == "Unsupported domain"
