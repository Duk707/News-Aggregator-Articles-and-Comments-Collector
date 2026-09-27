import pytest
from unittest.mock import patch, MagicMock
from src.collectors.batch import BatchCollector
from src.config import CollectorConfig
from src.models.comment_status import CommentStatus
from src.browser import BrowserManager, BrowserFetchResult


def test_inter_article_delay_mocked():
    """
    Verifies that inter-article delay is called only between supported article attempts,
    and not for invalid, unsupported, or duplicate URLs.
    Uses mock time.sleep for deterministic, instant test execution.
    """
    collector = BatchCollector(config=CollectorConfig(inter_article_delay=2.5))

    urls = [
        "ht!ps://invalid-url-syntax",                                     # Invalid -> No delay
        "https://example.com/unsupported-article",                       # Unsupported -> No delay
        "https://news.yahoo.com/high-school-students-using-ai-110000373.html",  # Supported #1 -> First attempt, no prior delay
        "https://news.yahoo.com/high-school-students-using-ai-110000373.html",  # Duplicate -> No delay
        "https://news.yahoo.com/news/politics/articles/justice-jackson-says-supreme-court-020112090.html" # Supported #2 -> 2.5s delay BEFORE attempt
    ]

    with patch("time.sleep") as mock_sleep:
        with BrowserManager(headless=True, request_delay_ms=0) as bm:
            results = collector.collect_urls(urls=urls, browser_manager=bm)


    assert len(results) == 5

    # time.sleep should be called EXACTLY ONCE with 2.5 seconds (before the 2nd supported article attempt)
    assert mock_sleep.call_count == 1
    mock_sleep.assert_called_with(2.5)


def test_max_articles_run_limit_enforcement():
    """
    Verifies that max_articles limit stops collection after N supported articles,
    and remaining supported URLs receive structured diagnostic results.
    """
    collector = BatchCollector(config=CollectorConfig(max_articles=1))

    urls = [
        "https://news.yahoo.com/high-school-students-using-ai-110000373.html",
        "https://news.yahoo.com/news/politics/articles/justice-jackson-says-supreme-court-020112090.html"
    ]

    with patch("time.sleep"):
        with BrowserManager(headless=True) as bm:
            results = collector.collect_urls(urls=urls, browser_manager=bm, max_articles=1)

    assert len(results) == 2

    # Article #1: Collected successfully
    assert results[0].success is True
    assert results[0].article is not None

    # Article #2: Skipped due to max_articles limit
    assert results[1].success is False
    assert "Batch article collection limit reached" in (results[1].error_message or "")
    assert "max_articles limit (1) reached" in results[1].diagnostic_notes[0]


def test_invalid_and_unsupported_urls_do_not_consume_max_articles_limit():
    """
    Verifies that invalid, unsupported, and duplicate URLs do NOT consume the max_articles limit.
    """
    collector = BatchCollector(config=CollectorConfig(max_articles=2))

    urls = [
        "ht!ps://invalid-syntax",                                         # Invalid (0 count)
        "https://example.com/unsupported",                                # Unsupported (0 count)
        "https://news.yahoo.com/high-school-students-using-ai-110000373.html",  # Supported #1 (1 count)
        "https://news.yahoo.com/high-school-students-using-ai-110000373.html",  # Duplicate (0 count)
        "https://news.yahoo.com/news/politics/articles/justice-jackson-says-supreme-court-020112090.html" # Supported #2 (2 count)
    ]

    with patch("time.sleep"):
        with BrowserManager(headless=True) as bm:
            results = collector.collect_urls(urls=urls, browser_manager=bm, max_articles=2)

    assert len(results) == 5

    assert results[0].comments_status == CommentStatus.UNSUPPORTED
    assert results[1].comments_status == CommentStatus.UNSUPPORTED
    assert results[2].success is True  # Supported #1
    assert results[3].error_message == "Duplicate URL skipped"
    assert results[4].success is True  # Supported #2 (was NOT blocked because invalid/unsupported didn't consume limit!)


def test_disable_inter_article_delay():
    """
    Verifies that setting inter_article_delay=0.0 disables time.sleep between supported articles.
    """
    collector = BatchCollector()

    urls = [
        "https://news.yahoo.com/high-school-students-using-ai-110000373.html",
        "https://news.yahoo.com/news/politics/articles/justice-jackson-says-supreme-court-020112090.html"
    ]

    with patch("time.sleep") as mock_sleep:
        with BrowserManager(headless=True, request_delay_ms=0) as bm:
            results = collector.collect_urls(urls=urls, browser_manager=bm, inter_article_delay=0.0)


    assert len(results) == 2
    assert results[0].success is True
    assert results[1].success is True
    assert mock_sleep.call_count == 0


def test_navigation_timeout_isolation():
    """
    Verifies navigation timeout handling: when BrowserManager returns a TIMEOUT fetch error,
    it produces a structured failure result and remaining batch items continue.
    """
    collector = BatchCollector()

    urls = [
        "https://news.yahoo.com/high-school-students-using-ai-110000373.html",
        "https://news.yahoo.com/news/politics/articles/justice-jackson-says-supreme-court-020112090.html"
    ]

    # Create mock BrowserManager that returns TIMEOUT error on 1st URL and success on 2nd
    mock_bm = MagicMock()
    mock_bm.fetch_page.side_effect = [
        BrowserFetchResult(
            requested_url=urls[0],
            success=False,
            error_type="TIMEOUT",
            error_message="Navigation timed out after 30000ms",
            retrieved_at="2026-09-26T00:00:00Z"
        ),
        BrowserFetchResult(
            requested_url=urls[1],
            success=True,
            html="<html><head><title>Success Article</title></head><body><article><p>Article body text.</p></article></body></html>",
            retrieved_at="2026-09-26T00:00:00Z"
        )
    ]

    with patch("time.sleep"):
        results = collector.collect_urls(urls=urls, browser_manager=mock_bm, inter_article_delay=0.0)

    assert len(results) == 2

    # 1st URL: Structured navigation timeout failure
    assert results[0].success is False
    assert "TIMED OUT" in results[0].error_message.upper() or "FETCH ERROR" in results[0].diagnostic_notes[0].upper()

    # 2nd URL: Succeeded cleanly despite 1st URL timing out!
    assert results[1].success is True
    assert results[1].article is not None
    assert results[1].article.title == "Success Article"
