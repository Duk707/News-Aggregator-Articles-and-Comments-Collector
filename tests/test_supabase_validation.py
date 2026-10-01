import pytest
from src.models.article import Article
from src.models.comment import Comment
from src.integrations.supabase.models import (
    SupabaseArticleRow,
    SupabaseCommentRow,
    SupabaseStagingDataset
)
from src.integrations.supabase.validation import SupabaseValidator
from src.integrations.supabase.mapper import SupabaseMapper


def test_duplicate_url_validation():
    art1 = SupabaseArticleRow(
        id=-1,
        title="Article 1",
        url="https://news.yahoo.com/same-url.html",
        content="Unique text 1",
        content_hash="1111111111111111111111111111111111111111111111111111111111111111"
    )
    art2 = SupabaseArticleRow(
        id=-2,
        title="Article 2",
        url="https://news.yahoo.com/same-url.html",  # Duplicate URL!
        content="Unique text 2",
        content_hash="2222222222222222222222222222222222222222222222222222222222222222"
    )

    dataset = SupabaseStagingDataset(articles=[art1, art2])
    errors, warnings = SupabaseValidator.validate_dataset(dataset)

    assert any("Duplicate URL 'https://news.yahoo.com/same-url.html'" in e for e in errors)


def test_duplicate_content_hash_validation():
    art1 = SupabaseArticleRow(
        id=-1,
        title="Article 1",
        url="https://news.yahoo.com/url1.html",
        content="Identical article text body",
        content_hash="abc123hashcode12345678901234567890123456789012345678901234567890"
    )
    art2 = SupabaseArticleRow(
        id=-2,
        title="Article 2",
        url="https://news.yahoo.com/url2.html",
        content="Identical article text body",
        content_hash="abc123hashcode12345678901234567890123456789012345678901234567890"  # Duplicate Hash!
    )

    dataset = SupabaseStagingDataset(articles=[art1, art2])
    errors, warnings = SupabaseValidator.validate_dataset(dataset)

    assert any("Duplicate content_hash 'abc123hashcode12345678901234567890123456789012345678901234567890'" in e for e in errors)


def test_empty_comment_text_validation():
    art = SupabaseArticleRow(
        id=-1,
        url="https://news.yahoo.com/valid.html"
    )
    comm = SupabaseCommentRow(
        id=-1,
        article_id=-1,
        text="   "  # Empty whitespace text!
    )

    dataset = SupabaseStagingDataset(articles=[art], comments=[comm])
    errors, warnings = SupabaseValidator.validate_dataset(dataset)

    assert any("Comment staging_id -1 (article_id -1) has empty text" in e for e in errors)


def test_orphan_parent_comment_id_validation():
    art = SupabaseArticleRow(
        id=-1,
        url="https://news.yahoo.com/valid.html"
    )
    comm = SupabaseCommentRow(
        id=-1,
        article_id=-1,
        text="Valid comment text",
        parent_comment_id=-999  # Orphan parent ID!
    )

    dataset = SupabaseStagingDataset(articles=[art], comments=[comm])
    errors, warnings = SupabaseValidator.validate_dataset(dataset)

    assert any("references non-existent parent_comment_id -999" in e for e in errors)


def test_article_scoped_duplicate_source_comment_id_validation():
    art = Article(
        platform="Yahoo News",
        source_adapter="YahooAdapter",
        requested_url="https://news.yahoo.com/dup-comments.html",
        retrieved_at="2026-09-30T12:00:00Z",
        comments=[
            Comment(
                comment_id="src_123",
                article_url="https://news.yahoo.com/dup-comments.html",
                comment_text="Comment 1",
                retrieved_at="2026-09-30T12:00:00Z"
            ),
            Comment(
                comment_id="src_123",
                article_url="https://news.yahoo.com/dup-comments.html",
                comment_text="Comment 2",
                retrieved_at="2026-09-30T12:00:00Z"
            )
        ]
    )

    dataset = SupabaseMapper.build_staging_dataset([art])
    assert any("Duplicate source comment_id 'src_123'" in w for w in dataset.validation_warnings)
