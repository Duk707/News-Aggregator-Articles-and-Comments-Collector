import pytest
from datetime import datetime, timezone
from src.models.summary import CollectionSummary
from src.models.extraction import ExtractionResult
from src.models.article import Article
from src.models.comment import Comment
from src.models.comment_status import CommentStatus
from src.collectors.batch import BatchCollector


@pytest.fixture
def mixed_batch_results() -> list[ExtractionResult]:
    """
    Constructs a mixed batch containing:
    1. Successful article with comments (AVAILABLE, 2 comments)
    2. Successful article with no comments (NONE_PRESENT, 0 comments)
    3. Actual fetch failure (404 Not Found)
    4. Invalid URL syntax
    5. Unsupported domain
    6. Duplicate URL skipped
    7. Run-limit skipped (max_articles limit reached)
    """
    now = datetime.now(timezone.utc).isoformat()

    c1 = Comment(
        comment_id="c1",
        article_url="https://news.yahoo.com/article-1.html",
        parent_comment_id=None,
        comment_text="Great article!",
        retrieved_at=now
    )
    c2 = Comment(
        comment_id="c2",
        article_url="https://news.yahoo.com/article-1.html",
        parent_comment_id="c1",
        comment_text="I agree!",
        depth=1,
        retrieved_at=now
    )

    # 1. Successful article with comments
    art1 = Article(
        platform="Yahoo News",
        source_adapter="YahooAdapter",
        requested_url="https://news.yahoo.com/article-1.html",
        title="Article One",
        article_text="Body text one",
        retrieved_at=now,
        comments_status=CommentStatus.AVAILABLE,
        comment_count_reported=2,
        comments_collected=2,
        comments=[c1, c2]
    )
    r1 = ExtractionResult(
        requested_url="https://news.yahoo.com/article-1.html",
        success=True,
        article=art1,
        comments_status=CommentStatus.AVAILABLE,
        retrieved_at=now
    )

    # 2. Successful article with no comments (NONE_PRESENT)
    art2 = Article(
        platform="Yahoo News",
        source_adapter="YahooAdapter",
        requested_url="https://news.yahoo.com/article-2.html",
        title="Article Two",
        article_text="Body text two",
        retrieved_at=now,
        comments_status=CommentStatus.NONE_PRESENT,
        comment_count_reported=0,
        comments_collected=0,
        comments=[]
    )
    r2 = ExtractionResult(
        requested_url="https://news.yahoo.com/article-2.html",
        success=True,
        article=art2,
        comments_status=CommentStatus.NONE_PRESENT,
        retrieved_at=now
    )

    # 3. Actual fetch failure (HTTP 404 error on supported Yahoo URL)
    r3 = ExtractionResult(
        requested_url="https://news.yahoo.com/article-404.html",
        success=False,
        comments_status=CommentStatus.EXTRACTION_ERROR,
        error_message="HTTP 404 Not Found",
        diagnostic_notes=["Page fetch failed: HTTP_404"],
        retrieved_at=now
    )

    # 4. Invalid URL syntax
    r4 = ExtractionResult(
        requested_url="ht!ps://invalid-syntax",
        success=False,
        comments_status=CommentStatus.UNSUPPORTED,
        error_message="Invalid or malformed URL syntax",
        diagnostic_notes=["URL validation failed"],
        retrieved_at=now
    )

    # 5. Unsupported domain URL
    r5 = ExtractionResult(
        requested_url="https://example.com/some-article.html",
        success=False,
        comments_status=CommentStatus.UNSUPPORTED,
        error_message="Unsupported news website domain",
        diagnostic_notes=["No registered adapter supported domain"],
        retrieved_at=now
    )

    # 6. Duplicate URL skipped
    r6 = ExtractionResult(
        requested_url="https://news.yahoo.com/article-1.html",
        success=False,
        comments_status=CommentStatus.UNKNOWN,
        error_message="Duplicate URL skipped",
        diagnostic_notes=["Duplicate URL skipped during batch collection"],
        retrieved_at=now
    )

    # 7. Run-limit skipped (max_articles limit reached)
    r7 = ExtractionResult(
        requested_url="https://news.yahoo.com/article-3.html",
        success=False,
        comments_status=CommentStatus.UNKNOWN,
        error_message="Batch article collection limit reached (2 articles)",
        diagnostic_notes=["Skipped: max_articles limit (2) reached for batch run"],
        retrieved_at=now
    )

    return [r1, r2, r3, r4, r5, r6, r7]


def test_collection_summary_calculation(mixed_batch_results):
    """
    Verifies that CollectionSummary accurately categorizes all records without double-counting.
    """
    summary = CollectionSummary.from_results(mixed_batch_results)

    assert summary.total_requested == 7
    assert summary.articles_attempted == 3       # r1, r2, r3
    assert summary.articles_successful == 2      # r1, r2
    assert summary.articles_failed == 1          # r3 (actual 404 fetch failure)

    # Verify non-attempted URL categories
    assert summary.invalid_urls == 1             # r4
    assert summary.unsupported_sources == 1      # r5
    assert summary.duplicates_skipped == 1       # r6
    assert summary.run_limit_skipped == 1        # r7

    # Verify mathematical mutual exclusivity (no double counting!)
    non_attempted_sum = (
        summary.invalid_urls +
        summary.unsupported_sources +
        summary.duplicates_skipped +
        summary.run_limit_skipped
    )
    assert non_attempted_sum + summary.articles_attempted == summary.total_requested
    assert summary.articles_successful + summary.articles_failed == summary.articles_attempted

    # Verify comment metrics
    assert summary.articles_with_comments_available == 1  # r1
    assert summary.articles_with_no_comments == 1          # r2
    assert summary.articles_with_inaccessible_comments == 1 # r3 (failed attempt)
    assert summary.total_comments_collected == 2


def test_collection_summary_terminal_formatting(mixed_batch_results):
    """
    Verifies human-readable terminal text formatting of CollectionSummary.
    """
    output_files = {
        "json": "data/output/batch_articles.json",
        "articles_csv": "data/output/articles.csv",
        "comments_csv": "data/output/comments.csv"
    }

    summary = CollectionSummary.from_results(mixed_batch_results, output_files=output_files)
    text_output = summary.format_terminal_summary()

    assert "BATCH COLLECTION SUMMARY" in text_output
    assert "Articles requested:                          7" in text_output
    assert "Articles attempted:                          3" in text_output
    assert "Articles successfully extracted:             2" in text_output
    assert "Articles failed:                             1" in text_output
    assert "Invalid URLs:                                1" in text_output
    assert "Unsupported sources:                         1" in text_output
    assert "Duplicate URLs skipped:                      1" in text_output
    assert "Run limit skipped (max_articles):            1" in text_output
    assert "Articles with comments available:            1" in text_output
    assert "Articles with no comments (NONE_PRESENT):    1" in text_output
    assert "Total comments collected:                    2" in text_output
    assert "data/output/articles.csv" in text_output


def test_batch_collector_summary_integration(mixed_batch_results):
    """
    Verifies that BatchCollector.create_summary() seamlessly integrates with CollectionSummary.
    """
    summary = BatchCollector.create_summary(mixed_batch_results)
    assert isinstance(summary, CollectionSummary)
    assert summary.total_requested == 7
    assert summary.articles_successful == 2


def test_attempted_fetch_failure_with_unsupported_comments_status():
    """
    Regression Test:
    Verifies that a supported Yahoo URL whose collection was attempted and failed
    while comments_status == CommentStatus.UNSUPPORTED is classified as an ATTEMPTED & FAILED article,
    and NOT conflated with an unsupported source domain.
    """
    now = datetime.now(timezone.utc).isoformat()
    failed_yahoo_result = ExtractionResult(
        requested_url="https://news.yahoo.com/news/politics/articles/failed-article-999.html",
        success=False,
        comments_status=CommentStatus.UNSUPPORTED,
        error_message="HTTP 404 Not Found",
        diagnostic_notes=["Page fetch failed: HTTP 404"],
        retrieved_at=now
    )

    summary = CollectionSummary.from_results([failed_yahoo_result])

    assert summary.total_requested == 1
    assert summary.articles_attempted == 1
    assert summary.articles_failed == 1
    assert summary.articles_successful == 0
    assert summary.unsupported_sources == 0  # Must NOT be counted as an unsupported source domain!
    assert summary.invalid_urls == 0
    assert summary.duplicates_skipped == 0
    assert summary.run_limit_skipped == 0


def test_genuinely_unsupported_domain_classification():
    """
    Verifies that a genuinely unsupported domain (e.g. example.com) is correctly
    classified as unsupported_sources and NOT counted as an attempted article fetch.
    """
    now = datetime.now(timezone.utc).isoformat()
    unsupported_domain_result = ExtractionResult(
        requested_url="https://example.com/some-unsupported-news.html",
        success=False,
        comments_status=CommentStatus.UNSUPPORTED,
        error_message="Unsupported news website domain",
        diagnostic_notes=["No registered adapter supported domain for https://example.com/some-unsupported-news.html"],
        retrieved_at=now
    )

    summary = CollectionSummary.from_results([unsupported_domain_result])

    assert summary.total_requested == 1
    assert summary.articles_attempted == 0   # No fetch attempted!
    assert summary.articles_failed == 0
    assert summary.unsupported_sources == 1  # Correctly classified as unsupported source domain!

