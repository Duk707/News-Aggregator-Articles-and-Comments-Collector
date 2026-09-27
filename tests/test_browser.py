import pytest
from src.browser import BrowserManager, BrowserFetchResult


def test_browser_manager_context_manager():
    """Verify context manager protocol starts and closes browser cleanly."""
    with BrowserManager(headless=True) as manager:
        assert manager._is_started is True
        assert manager._browser is not None

    assert manager._is_started is False
    assert manager._browser is None


def test_browser_fetch_page_success():
    """Acceptance test: opens a public test page, returns rendered HTML, closes browser cleanly."""
    with BrowserManager(headless=True, request_delay_ms=0) as manager:
        test_url = "data:text/html,<html><head><title>Test Page</title></head><body><h1>Hello World</h1></body></html>"
        result: BrowserFetchResult = manager.fetch_page(test_url)

        assert result.success is True
        assert result.requested_url == test_url
        assert result.html is not None
        assert "<h1>Hello World</h1>" in result.html
        assert "<title>Test Page</title>" in result.html
        assert result.error_type is None


def test_browser_fetch_timeout_detection():
    """Verify timeout is caught and reported cleanly."""
    with BrowserManager(headless=True, navigation_timeout_ms=100, request_delay_ms=0) as manager:
        # Non-routable IP that will trigger timeout
        result = manager.fetch_page("http://10.255.255.1/")

        assert result.success is False
        assert result.error_type in ("TIMEOUT", "NAVIGATION_ERROR")
        assert result.error_message is not None


def test_captcha_and_access_denied_detection():
    """Verify signature detection for CAPTCHA and Access Denial."""
    manager = BrowserManager()

    # 403 status code
    assert manager._check_access_or_captcha(403, "<html>Forbidden</html>") == "ACCESS_DENIED"
    # 429 status code
    assert manager._check_access_or_captcha(429, "<html>Too Many Requests</html>") == "ACCESS_DENIED"

    # HTML containing captcha signature
    assert manager._check_access_or_captcha(200, "<html>Please complete the CAPTCHA to continue</html>") == "CAPTCHA_DETECTED"
    # HTML containing Cloudflare turnstile
    assert manager._check_access_or_captcha(200, "<html><div class='cf-turnstile'></div></html>") == "CAPTCHA_DETECTED"

    # HTML containing Access Denied signature
    assert manager._check_access_or_captcha(200, "<html>Access Denied on this server</html>") == "ACCESS_DENIED"

    # Clean HTML
    assert manager._check_access_or_captcha(200, "<html><h1>Welcome to Yahoo News</h1></html>") is None
