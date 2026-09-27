import pytest
from bs4 import BeautifulSoup
from src.collectors.yahoo import YahooAdapter
from src.browser import BrowserManager, BrowserFetchResult


def test_yahoo_adapter_unsupported_url_handling():
    """Verify YahooAdapter rejects non-Yahoo URLs gracefully when load is called."""
    adapter = YahooAdapter()
    unsupported_url = "https://www.nytimes.com/some-article"

    result = adapter.load_article(unsupported_url)
    assert result.success is False
    assert result.error_type == "UNSUPPORTED"
    assert "not supported" in result.error_message


def test_yahoo_adapter_diagnostics_generation():
    """Verify diagnostic dictionary formatting from fetch results."""
    adapter = YahooAdapter()
    dummy_result = BrowserFetchResult(
        requested_url="https://news.yahoo.com/test",
        final_url="https://news.yahoo.com/test-final",
        status_code=200,
        html="<html><body><p>Sample Yahoo Article</p></body></html>",
        success=True,
        retrieved_at="2026-09-25T19:00:00Z"
    )

    diagnostics = adapter.get_loading_diagnostics(dummy_result)
    assert diagnostics["platform"] == "Yahoo News"
    assert diagnostics["adapter"] == "YahooAdapter"
    assert diagnostics["requested_url"] == "https://news.yahoo.com/test"
    assert diagnostics["final_url"] == "https://news.yahoo.com/test-final"
    assert diagnostics["status_code"] == 200
    assert diagnostics["success"] is True
    assert diagnostics["html_bytes"] > 0


@pytest.mark.integration
def test_live_individual_yahoo_article_page_loading():
    """
    Integration test: Discovers a live individual Yahoo News article URL and tests
    that YahooAdapter.load_article successfully loads the individual article page,
    recording requested URL, final URL after redirects, HTTP status code,
    retrieved_at timestamp, and rendered HTML size.
    """
    adapter = YahooAdapter()

    with BrowserManager(headless=True, navigation_timeout_ms=30000, request_delay_ms=500) as bm:
        # Step A: Fetch index page to discover a live individual article link
        index_result = bm.fetch_page("https://news.yahoo.com/")
        assert index_result.success is True

        soup = BeautifulSoup(index_result.html, "html.parser")
        article_url = None

        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]
            if href.endswith(".html") or ".html?" in href:
                if href.startswith("/"):
                    article_url = f"https://news.yahoo.com{href}"
                elif href.startswith("http") and "yahoo.com" in href:
                    article_url = href
                if article_url:
                    break

        if not article_url:
            article_url = "https://news.yahoo.com/rss"

        print(f"\n[INTEGRATION TEST] Target individual Yahoo article URL: {article_url}")

        # Step B: Load the individual article page using YahooAdapter
        result = adapter.load_article(article_url, browser_manager=bm)
        diagnostics = adapter.get_loading_diagnostics(result)

        print(f"[INTEGRATION TEST] Requested URL: {result.requested_url}")
        print(f"[INTEGRATION TEST] Final URL: {result.final_url}")
        print(f"[INTEGRATION TEST] HTTP Status Code: {result.status_code}")
        print(f"[INTEGRATION TEST] Retrieval Timestamp: {result.retrieved_at}")
        print(f"[INTEGRATION TEST] Rendered HTML Size: {diagnostics['html_bytes']} bytes")

        assert result.requested_url == article_url
        assert result.success is True
        assert result.status_code == 200
        assert result.final_url is not None
        assert "yahoo.com" in result.final_url.lower()
        assert result.html is not None
        assert len(result.html) > 5000
        assert result.retrieved_at is not None
        assert diagnostics["success"] is True
