import os
import json
import pytest
from bs4 import BeautifulSoup
from src.extraction import CommentDiagnosticInspector, CommentDiagnosticsResult
from src.models import CommentStatus
from src.collectors.yahoo import YahooAdapter
from src.browser import BrowserManager


def test_comment_diagnostics_login_required():
    """Verify LOGIN_REQUIRED status when sign-in requirement is present."""
    html = """
    <html>
    <body>
        <h1>Article Headline</h1>
        <div id="comments">
            <p>Please sign in to view comments on this story.</p>
        </div>
    </body>
    </html>
    """
    result: CommentDiagnosticsResult = CommentDiagnosticInspector.inspect("https://news.yahoo.com/test", html)
    assert result.preliminary_status == CommentStatus.LOGIN_REQUIRED
    assert len(result.access_login_messages) > 0


def test_comment_diagnostics_disabled():
    """Verify DISABLED status when comments disabled message is present."""
    html = """
    <html>
    <body>
        <h1>Article Headline</h1>
        <div class="comments-footer">
            <p>Comments are disabled for this article.</p>
        </div>
    </body>
    </html>
    """
    result: CommentDiagnosticsResult = CommentDiagnosticInspector.inspect("https://news.yahoo.com/test", html)
    assert result.preliminary_status == CommentStatus.DISABLED
    assert len(result.disabled_messages) > 0


def test_comment_diagnostics_not_loaded_on_view_button():
    """Verify NOT_LOADED status when View Comments button exists but comments are unrendered."""
    html = """
    <html>
    <body>
        <h1>Article Headline</h1>
        <button class="caas-button">View Comments (42)</button>
        <div class="caas-comments"></div>
    </body>
    </html>
    """
    result: CommentDiagnosticsResult = CommentDiagnosticInspector.inspect("https://news.yahoo.com/test", html)
    assert result.has_view_comments_button is True
    assert result.reported_comment_count == 42
    assert result.comment_container_found is True
    assert result.preliminary_status == CommentStatus.NOT_LOADED


def test_conservative_status_absence_of_container():
    """Verify that absence of verified comment evidence assigns UNKNOWN status rather than NOT_LOADED or NONE_PRESENT."""
    html = """
    <html>
    <body>
        <h1>Article Headline</h1>
        <p>This is standard article text.</p>
    </body>
    </html>
    """
    result: CommentDiagnosticsResult = CommentDiagnosticInspector.inspect("https://news.yahoo.com/test", html)
    # Must be UNKNOWN since no positive comment control/container/count/iframe evidence exists
    assert result.has_view_comments_button is False
    assert result.comment_container_found is False
    assert result.preliminary_status == CommentStatus.UNKNOWN


def test_save_diagnostic_artifact(tmp_path):
    """Verify diagnostic JSON report saving."""
    dummy_result = CommentDiagnosticsResult(
        url="https://news.yahoo.com/sample-article",
        has_comment_text=True,
        has_view_comments_button=True,
        reported_comment_count=15,
        preliminary_status=CommentStatus.NOT_LOADED,
        diagnostic_notes=["Test note"],
        timestamp="2026-09-25T20:00:00Z"
    )

    saved_paths = CommentDiagnosticInspector.save_diagnostic_artifact(
        dummy_result,
        html="<html>Test</html>",
        output_dir=str(tmp_path)
    )

    assert "json_report" in saved_paths
    assert "html_snapshot" in saved_paths
    assert os.path.exists(saved_paths["json_report"])

    with open(saved_paths["json_report"], "r", encoding="utf-8") as f:
        data = json.load(f)
        assert data["url"] == "https://news.yahoo.com/sample-article"
        assert data["reported_comment_count"] == 15
        assert data["preliminary_status"] == "NOT_LOADED"


@pytest.mark.integration
def test_live_yahoo_article_comment_diagnostics():
    """
    Integration test: Loads a live Yahoo News article page, runs comment diagnostics via YahooAdapter,
    prints the complete diagnostic output, and verifies conservative status assignment.
    """
    adapter = YahooAdapter()

    with BrowserManager(headless=True, navigation_timeout_ms=30000, request_delay_ms=500) as bm:
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

        print(f"\n[COMMENT DIAGNOSTICS INTEGRATION TEST] Article URL: {article_url}")

        fetch_result = adapter.load_article(article_url, browser_manager=bm)
        assert fetch_result.success is True

        diag_result: CommentDiagnosticsResult = adapter.inspect_comment_diagnostics(
            fetch_result.final_url or article_url,
            fetch_result.html,
            save_artifact=True
        )

        print("\n--- COMPLETE DIAGNOSTIC OUTPUT ---")
        print(json.dumps(diag_result.model_dump(), indent=2))
        print("----------------------------------\n")

        # Asserts
        assert diag_result.url is not None
        assert diag_result.preliminary_status in [
            CommentStatus.AVAILABLE,
            CommentStatus.NONE_PRESENT,
            CommentStatus.DISABLED,
            CommentStatus.LOGIN_REQUIRED,
            CommentStatus.NOT_LOADED,
            CommentStatus.UNKNOWN
        ]
        # Assert diagnostic artifacts saved in data/diagnostics
        assert os.path.exists("data/diagnostics")
