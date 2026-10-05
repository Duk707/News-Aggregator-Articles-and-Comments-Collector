"""
Unit tests for SupabaseMapper (Step 27).
Includes tests for article mapping, comment ID uniqueness, nested replies,
timezone-aware timestamp preservation, and missing timestamp provenance warnings.
"""
import pytest
from src.models.article import Article
from src.models.comment import Comment
from src.models.comment_status import CommentStatus
from src.integrations.supabase.mapper import SupabaseMapper
from src.integrations.supabase.validation import SupabaseValidator


def test_map_article_basic():
    article = Article(
        platform="Yahoo News",
        source_adapter="YahooAdapter",
        requested_url="https://news.yahoo.com/test-article-123.html",
        canonical_url="https://news.yahoo.com/test-article-123.html",
        original_publisher="Reuters",
        title="Test Article Title",
        author="John Doe",
        publication_datetime="2026-09-30T10:00:00Z",
        article_text="This is a test article body paragraph 1.\nThis is paragraph 2.",
        retrieved_at="2026-09-30T12:00:00Z",
        comments_status=CommentStatus.AVAILABLE
    )

    staged = SupabaseMapper.map_article(article, staging_id=-1)

    assert staged.id == -1
    assert staged.title == "Test Article Title"
    assert staged.content == "This is a test article body paragraph 1.\nThis is paragraph 2."
    assert staged.source == "Reuters"
    assert staged.created_at is None
    assert staged.url == "https://news.yahoo.com/test-article-123.html"
    assert staged.author == "John Doe"
    assert staged.published_date == "2026-09-30"
    assert staged.content_hash is not None
    assert len(staged.content_hash) == 64
    assert staged.clean_content == article.article_text
    assert staged.processing_status is None
    assert staged.processing_note is None
    assert staged.processed_at is None
    assert staged.is_relevant is None


def test_global_comment_id_uniqueness_across_articles():
    art1 = Article(
        platform="Yahoo News",
        source_adapter="YahooAdapter",
        requested_url="https://news.yahoo.com/article1.html",
        retrieved_at="2026-09-30T12:00:00Z",
        comments=[
            Comment(
                comment_id="c1_art1",
                article_url="https://news.yahoo.com/article1.html",
                comment_text="Article 1 Comment 1",
                retrieved_at="2026-09-30T12:00:00Z"
            ),
            Comment(
                comment_id="c2_art1",
                article_url="https://news.yahoo.com/article1.html",
                comment_text="Article 1 Comment 2",
                retrieved_at="2026-09-30T12:00:00Z"
            )
        ]
    )

    art2 = Article(
        platform="MSN",
        source_adapter="MSNAdapter",
        requested_url="https://msn.com/article2.html",
        retrieved_at="2026-09-30T12:00:00Z",
        comments=[
            Comment(
                comment_id="c1_art2",
                article_url="https://msn.com/article2.html",
                comment_text="Article 2 Comment 1",
                retrieved_at="2026-09-30T12:00:00Z"
            )
        ]
    )

    dataset = SupabaseMapper.build_staging_dataset([art1, art2])

    assert len(dataset.articles) == 2
    assert dataset.articles[0].id == -1
    assert dataset.articles[1].id == -2

    assert len(dataset.comments) == 3
    comment_ids = [c.id for c in dataset.comments]
    assert comment_ids == [-1, -2, -3]
    assert len(set(comment_ids)) == 3  # Absolutely no ID collisions across articles!

    # Verify article_id links
    assert dataset.comments[0].article_id == -1
    assert dataset.comments[1].article_id == -1
    assert dataset.comments[2].article_id == -2


def test_article_scoped_source_id_collision_warning():
    art = Article(
        platform="Yahoo News",
        source_adapter="YahooAdapter",
        requested_url="https://news.yahoo.com/article-dup.html",
        retrieved_at="2026-09-30T12:00:00Z",
        comments=[
            Comment(
                comment_id="same_id",
                article_url="https://news.yahoo.com/article-dup.html",
                comment_text="First comment with same_id",
                retrieved_at="2026-09-30T12:00:00Z"
            ),
            Comment(
                comment_id="same_id",
                article_url="https://news.yahoo.com/article-dup.html",
                comment_text="Second comment with same_id",
                retrieved_at="2026-09-30T12:00:00Z"
            )
        ]
    )

    dataset = SupabaseMapper.build_staging_dataset([art])

    assert len(dataset.comments) == 2
    assert dataset.comments[0].id != dataset.comments[1].id
    assert any("Duplicate source comment_id 'same_id'" in w for w in dataset.validation_warnings)


def test_nested_reply_missing_parent_comment_id():
    # Structural hierarchy via flat depth ordering where reply has parent_comment_id=None
    root_comm = Comment(
        comment_id="root_1",
        article_url="https://news.yahoo.com/article.html",
        comment_text="Root comment text",
        depth=0,
        retrieved_at="2026-09-30T12:00:00Z"
    )
    reply_comm = Comment(
        comment_id="reply_1",
        article_url="https://news.yahoo.com/article.html",
        parent_comment_id=None,  # Missing explicit parent ID!
        comment_text="Nested reply text",
        depth=1,
        retrieved_at="2026-09-30T12:00:00Z"
    )

    art = Article(
        platform="Yahoo News",
        source_adapter="YahooAdapter",
        requested_url="https://news.yahoo.com/article.html",
        retrieved_at="2026-09-30T12:00:00Z",
        comments=[root_comm, reply_comm]
    )

    dataset = SupabaseMapper.build_staging_dataset([art])

    assert len(dataset.comments) == 2
    root_staged = dataset.comments[0]
    reply_staged = dataset.comments[1]

    assert root_staged.id == -1
    assert root_staged.parent_comment_id is None

    assert reply_staged.id == -2
    # Must fallback to structural parent staging ID (-1)
    assert reply_staged.parent_comment_id == -1


def test_deeply_nested_replies():
    level0 = Comment(
        comment_id="l0",
        article_url="https://news.yahoo.com/art.html",
        comment_text="Level 0 root",
        depth=0,
        retrieved_at="2026-09-30T12:00:00Z"
    )
    level1 = Comment(
        comment_id="l1",
        article_url="https://news.yahoo.com/art.html",
        parent_comment_id="l0",
        comment_text="Level 1 reply",
        depth=1,
        retrieved_at="2026-09-30T12:00:00Z"
    )
    level2 = Comment(
        comment_id="l2",
        article_url="https://news.yahoo.com/art.html",
        parent_comment_id="l1",
        comment_text="Level 2 reply",
        depth=2,
        retrieved_at="2026-09-30T12:00:00Z"
    )

    art = Article(
        platform="Yahoo News",
        source_adapter="YahooAdapter",
        requested_url="https://news.yahoo.com/art.html",
        retrieved_at="2026-09-30T12:00:00Z",
        comments=[level0, level1, level2]
    )

    dataset = SupabaseMapper.build_staging_dataset([art])

    assert len(dataset.comments) == 3
    l0_row, l1_row, l2_row = dataset.comments[0], dataset.comments[1], dataset.comments[2]

    assert l0_row.id == -1
    assert l0_row.parent_comment_id is None

    assert l1_row.id == -2
    assert l1_row.parent_comment_id == -1

    assert l2_row.id == -3
    assert l2_row.parent_comment_id == -2


def test_missing_source_comment_id():
    comm = Comment(
        comment_id="",  # Missing source comment_id
        article_url="https://news.yahoo.com/art.html",
        comment_text="Comment with no source ID",
        retrieved_at="2026-09-30T12:00:00Z"
    )

    art = Article(
        platform="Yahoo News",
        source_adapter="YahooAdapter",
        requested_url="https://news.yahoo.com/art.html",
        retrieved_at="2026-09-30T12:00:00Z",
        comments=[comm]
    )

    dataset = SupabaseMapper.build_staging_dataset([art])

    assert len(dataset.comments) == 1
    assert dataset.comments[0].id == -1
    assert dataset.comments[0].text == "Comment with no source ID"


def test_internal_model_retention():
    art = Article(
        platform="Yahoo News",
        source_adapter="YahooAdapter",
        requested_url="https://news.yahoo.com/art.html",
        retrieved_at="2026-09-30T12:00:00Z",
        comments_status=CommentStatus.AVAILABLE,
        diagnostic_notes=["Note 1", "Note 2"]
    )

    dataset = SupabaseMapper.build_staging_dataset([art])

    assert len(dataset.source_articles) == 1
    assert dataset.source_articles[0].platform == "Yahoo News"
    assert dataset.source_articles[0].comments_status == CommentStatus.AVAILABLE
    assert dataset.source_articles[0].diagnostic_notes == ["Note 1", "Note 2"]


def test_map_comments_exact_date_and_created_at_none():
    """
    Tests mapping of exact ISO timestamp into SupabaseCommentRow.published_date (YYYY-MM-DD)
    and created_at = None so DB default now() applies.
    """
    comm = Comment(
        comment_id="tz_comm_1",
        article_url="https://ousd.granicusideas.com/item/1",
        comment_text="Comment with PDT timezone",
        published_datetime="2026-10-03T00:38:00-07:00",
        retrieved_at="2026-10-04T12:00:00Z"
    )

    art = Article(
        platform="Granicus Ideas",
        source_adapter="GranicusIdeasAdapter",
        requested_url="https://ousd.granicusideas.com/item/1",
        publication_datetime="2026-08-12T16:00:00-07:00",
        retrieved_at="2026-10-04T12:00:00Z",
        comments=[comm]
    )

    dataset = SupabaseMapper.build_staging_dataset([art])

    assert dataset.articles[0].published_date == "2026-08-12"
    assert dataset.articles[0].created_at is None

    assert len(dataset.comments) == 1
    assert dataset.comments[0].published_date == "2026-10-03"
    assert dataset.comments[0].created_at is None

    errors, warnings = SupabaseValidator.validate_dataset(dataset)
    assert len(errors) == 0


def test_map_comments_relative_and_missing_timestamps():
    """
    Tests mapping of relative-only timestamp (published_datetime = None) and missing timestamps.
    Verifies SupabaseCommentRow.published_date is None and created_at is None.
    """
    comm_relative = Comment(
        comment_id="rel_comm",
        article_url="https://ousd.granicusideas.com/item/2",
        comment_text="Relative timestamp comment",
        published_datetime=None,
        retrieved_at="2026-10-04T12:00:00Z"
    )

    comm_missing = Comment(
        comment_id="missing_comm",
        article_url="https://ousd.granicusideas.com/item/2",
        comment_text="Missing timestamp comment",
        published_datetime=None,
        retrieved_at="2026-10-04T12:00:00Z"
    )

    art = Article(
        platform="Granicus Ideas",
        source_adapter="GranicusIdeasAdapter",
        requested_url="https://ousd.granicusideas.com/item/2",
        retrieved_at="2026-10-04T12:00:00Z",
        comments=[comm_relative, comm_missing]
    )

    dataset = SupabaseMapper.build_staging_dataset([art])

    assert len(dataset.comments) == 2
    assert dataset.comments[0].published_date is None
    assert dataset.comments[0].created_at is None
    assert dataset.comments[1].published_date is None
    assert dataset.comments[1].created_at is None

    errors, warnings = SupabaseValidator.validate_dataset(dataset)
    assert len(errors) == 0

