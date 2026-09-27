import os
import pytest
from src.collectors.batch import BatchCollector
from src.collectors.router import SourceRouter
from src.models.extraction import ExtractionResult
from src.models.comment_status import CommentStatus
from src.browser import BrowserManager


def test_batch_collector_mixture_and_duplicates(tmp_path):
    """
    Tests batch collection with a mixture of valid Yahoo URLs, malformed URLs,
    unsupported domain URLs, and duplicate URLs.
    Verifies error isolation, URL normalization, and duplicate handling.
    """
    collector = BatchCollector()

    urls_input = [
        "https://news.yahoo.com/high-school-students-using-ai-110000373.html",  # Valid Yahoo URL
        "ht!ps://invalid-url-string-syntax",                                      # Malformed URL syntax
        "https://example.com/unsupported-news-article.html",                     # Unsupported domain
        "https://news.yahoo.com/high-school-students-using-ai-110000373.html",  # Duplicate URL
    ]

    with BrowserManager(headless=True) as bm:
        results = collector.collect_urls(
            urls=urls_input,
            browser_manager=bm,
            max_comments=10,
            topic_query="AI in Education"
        )

    assert len(results) == 4

    # 1. Valid Yahoo URL
    r1 = results[0]
    assert r1.requested_url == "https://news.yahoo.com/high-school-students-using-ai-110000373.html"
    assert r1.success is True
    assert r1.article is not None
    assert r1.article.platform == "Yahoo News"
    assert r1.article.topic_query == "AI in Education"

    # 2. Malformed URL syntax
    r2 = results[1]
    assert r2.success is False
    assert r2.comments_status == CommentStatus.UNSUPPORTED
    assert "Invalid" in (r2.error_message or "")

    # 3. Unsupported domain URL
    r3 = results[2]
    assert r3.requested_url == "https://example.com/unsupported-news-article.html"
    assert r3.success is False
    assert r3.comments_status == CommentStatus.UNSUPPORTED
    assert "Unsupported" in (r3.error_message or "")

    # 4. Duplicate URL
    r4 = results[3]
    assert r4.requested_url == "https://news.yahoo.com/high-school-students-using-ai-110000373.html"
    assert r4.success is False
    assert r4.error_message == "Duplicate URL skipped"
    assert "Duplicate URL skipped" in r4.diagnostic_notes[0]


def test_batch_collector_from_file(tmp_path):
    """
    Tests reading batch input URLs from a text file with comments (#) and blank lines.
    Verifies that file parsing correctly ignores comments and empty lines.
    """
    file_path = os.path.join(tmp_path, "sample_urls.txt")
    file_content = """# Research Target URLs for AI in Education

https://news.yahoo.com/high-school-students-using-ai-110000373.html
  
# Malformed URL test line
ht@tp://bad-syntax-url

# Unsupported domain
https://wikipedia.org/wiki/Artificial_intelligence

"""
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(file_content)

    collector = BatchCollector()
    with BrowserManager(headless=True) as bm:
        results = collector.collect_from_file(
            file_path=file_path,
            browser_manager=bm,
            max_comments=10
        )

    assert len(results) == 3
    assert results[0].success is True
    assert results[1].success is False
    assert results[2].comments_status == CommentStatus.UNSUPPORTED


def test_batch_collector_failure_isolation():
    """
    Verifies failure isolation: when one URL fails due to a network error or 404 non-existent page,
    the failure is captured as an ExtractionResult and subsequent URLs are still processed.
    """
    collector = BatchCollector()

    # Non-existent Yahoo article URL (returns 404 or empty content) + Valid Yahoo article URL
    urls = [
        "https://news.yahoo.com/nonexistent-article-page-404-999999999.html",
        "https://news.yahoo.com/high-school-students-using-ai-110000373.html"
    ]

    with BrowserManager(headless=True) as bm:
        results = collector.collect_urls(urls=urls, browser_manager=bm)

    assert len(results) == 2

    # Second valid URL MUST still succeed even if the first URL failed
    assert results[1].success is True
    assert results[1].article is not None
    assert results[1].article.platform == "Yahoo News"
