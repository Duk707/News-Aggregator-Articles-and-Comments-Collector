import os
import json
import pytest
from bs4 import BeautifulSoup
from src.extraction.comments import YahooCommentDeliveryEvidence, CommentDiagnosticInspector
from src.collectors.yahoo import YahooAdapter
from src.browser import BrowserManager


def test_yahoo_comment_delivery_evidence_model():
    """Verify YahooCommentDeliveryEvidence model instantiation and JSON serialization."""
    evidence = YahooCommentDeliveryEvidence(
        url="https://news.yahoo.com/test-article.html",
        button_found=True,
        button_clicked=True,
        verified_comment_network_activity=[{"url": "https://spot.im/api/v2/comments", "status": 200}],
        unrelated_network_activity_count=12,
        unrelated_network_activity_sample=["doubleclick.net", "googlesyndication.com"],
        verified_comment_dom_changes=[".caas-comments"],
        verified_comment_iframes=["https://spot.im/iframe"],
        unrelated_iframe_changes=["https://safeframe.googlesyndication.com/container.html"],
        visible_comment_text_found=True,
        rendered_comments_count=5,
        login_required_after_click=False,
        observed_delivery_mechanism="SPOT_IM_IFRAME",
        findings_summary="Spot.IM iframe dynamically inserted into DOM.",
        timestamp="2026-09-25T20:00:00Z"
    )

    assert evidence.button_found is True
    assert evidence.observed_delivery_mechanism == "SPOT_IM_IFRAME"
    assert len(evidence.verified_comment_iframes) == 1
    assert len(evidence.unrelated_iframe_changes) == 1

    json_data = evidence.model_dump_json(indent=2)
    assert "SPOT_IM_IFRAME" in json_data


@pytest.mark.integration
def test_live_yahoo_comment_delivery_investigation():
    """
    Live Step 10 Investigation: Interactively tests 'View comments' activation
    on an actual Yahoo News article and documents how comments are delivered.
    """
    adapter = YahooAdapter()

    with BrowserManager(headless=True, navigation_timeout_ms=30000, request_delay_ms=500) as bm:
        # Discover live article link from homepage
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

        print(f"\n[STEP 10 INVESTIGATION] Target Yahoo Article URL: {article_url}")

        evidence: YahooCommentDeliveryEvidence = adapter.investigate_comment_delivery(
            article_url,
            browser_manager=bm
        )

        print("\n=======================================================")
        print("    STEP 10 EMPIRICAL COMMENT DELIVERY MECHANISM REPORT")
        print("=======================================================")
        print(json.dumps(evidence.model_dump(), indent=2))
        print("=======================================================\n")

        # Asserts
        assert evidence.url == article_url
        assert evidence.observed_delivery_mechanism in [
            "SPOT_IM_IFRAME",
            "OPENWEB_IFRAME",
            "VIAFOURA_IFRAME",
            "VERIFIED_COMMENT_IFRAME",
            "DYNAMIC_DOM_COMPONENT",
            "PUBLIC_API_ENDPOINT",
            "LOGIN_RESTRICTED",
            "DISABLED",
            "UNDETERMINED",
            "CONTROL_NOT_FOUND"
        ]

        # Verify saved investigation artifact
        report_path = "data/diagnostics/yahoo_comment_delivery_investigation.json"
        assert os.path.exists(report_path)
