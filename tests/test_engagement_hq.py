"""
Unit & Integration Tests for EngagementHQ Civic Platform Adapter & Fallback Probing (Step 30A / 30A.1).
Uses offline HTML fixtures — 0 live network calls.
"""
import os
import unittest
from unittest.mock import MagicMock
from src.collectors.engagement_hq import EngagementHQAdapter
from src.collectors.router import SourceRouter
from src.collectors.batch import BatchCollector, is_eligible_for_civic_fallback
from src.models.comment_status import CommentStatus


class TestEngagementHQAdapter(unittest.TestCase):

    def setUp(self):
        self.adapter = EngagementHQAdapter()
        self.fixture_path = os.path.join(os.path.dirname(__file__), "fixtures", "engagement_hq_page.html")
        with open(self.fixture_path, "r", encoding="utf-8") as f:
            self.fixture_html = f.read()

    def test_supports_routing(self):
        self.assertTrue(self.adapter.supports("https://connect.austintexas.gov/projects/ai-in-schools"))
        self.assertTrue(self.adapter.supports("https://engage.vic.gov.au/projects/digital-education"))
        self.assertTrue(self.adapter.supports("https://sample.engagementhq.com/consultation"))
        self.assertFalse(self.adapter.supports("https://blog.teslontario.org/post"))

    def test_supports_html_two_strong_vendor_fingerprints(self):
        # HTML with meta generator + CDN script, but NO ehq-widget DOM elements
        html = """
        <html>
        <head>
            <meta name="generator" content="EngagementHQ 2.0" />
            <script src="https://cdn.engagementhq.com/assets/app.js"></script>
        </head>
        <body><div>Custom HTML layout without standard DOM widgets</div></body>
        </html>
        """
        self.assertTrue(self.adapter.supports_html("https://custom-gov.gov/consultation/test", html))

    def test_supports_html_weak_generic_indicator_rejected(self):
        # Generic text containing "engage" but zero EngagementHQ generator/CDN fingerprints
        html = """
        <html>
        <head><title>General Community Portal</title></head>
        <body>
            <p>Welcome! Please engage with our town discussion forum below.</p>
        </body>
        </html>
        """
        self.assertFalse(self.adapter.supports_html("https://example-blog.com/post", html))

    def test_civic_fallback_eligibility_rules(self):
        # Valid civic path URLs
        self.assertTrue(is_eligible_for_civic_fallback("https://custom-gov.gov/projects/ai-initiative"))
        self.assertTrue(is_eligible_for_civic_fallback("https://custom-gov.gov/consultation/budget-2026"))
        self.assertTrue(is_eligible_for_civic_fallback("https://custom-gov.gov/public-input/schools"))
        self.assertTrue(is_eligible_for_civic_fallback("https://engage.custom-gov.gov/topics/tech"))

        # Non-civic path URLs (unsupported arbitrary URLs)
        self.assertFalse(is_eligible_for_civic_fallback("https://random-news.com/article/123"))
        self.assertFalse(is_eligible_for_civic_fallback("https://example-store.com/product/xyz"))

        # Private / Localhost / Loopback Exclusions
        self.assertFalse(is_eligible_for_civic_fallback("http://localhost/projects/test"))
        self.assertFalse(is_eligible_for_civic_fallback("http://127.0.0.1/consultation/test"))
        self.assertFalse(is_eligible_for_civic_fallback("http://10.0.0.1/projects/test"))
        self.assertFalse(is_eligible_for_civic_fallback("http://192.168.1.50/projects/test"))

    def test_router_post_fetch_probe(self):
        router = SourceRouter()
        # Fast path fails on custom domain
        routing_res, adapter = router.route("https://custom-city.gov/consultation/ai-policy")
        self.assertFalse(routing_res.supported)
        self.assertIsNone(adapter)

        # Post-fetch probe claims custom domain via HTML fingerprints
        probe_res, claimed_adapter = router.route_by_html("https://custom-city.gov/consultation/ai-policy", self.fixture_html)
        self.assertTrue(probe_res.supported)
        self.assertEqual(probe_res.adapter_name, "EngagementHQAdapter")
        self.assertIsInstance(claimed_adapter, EngagementHQAdapter)

    def test_batch_collector_fallback_probe_single_fetch_html_reuse(self):
        router = SourceRouter()
        collector = BatchCollector(router=router)

        # Mock BrowserManager to verify fetch_page is called EXACTLY ONCE
        mock_bm = MagicMock()
        mock_fetch_res = MagicMock()
        mock_fetch_res.success = True
        mock_fetch_res.html = self.fixture_html
        mock_fetch_res.error_type = None
        mock_fetch_res.error_message = None
        mock_fetch_res.final_url = "https://custom-city.gov/projects/ai-in-schools"
        mock_fetch_res.retrieved_at = "2026-03-31T12:00:00Z"
        mock_bm.fetch_page.return_value = mock_fetch_res

        urls = ["https://custom-city.gov/projects/ai-in-schools"]
        results = collector.collect_urls(urls=urls, browser_manager=mock_bm)

        # Verify fetch_page was called exactly once
        self.assertEqual(mock_bm.fetch_page.call_count, 1)

        self.assertEqual(len(results), 1)
        res = results[0]
        self.assertTrue(res.success)
        self.assertEqual(res.article.platform, "EngagementHQ Civic Portal")
        self.assertEqual(res.article.title, "AI Guidelines for Municipal Schools")
        self.assertEqual(res.comments_status, CommentStatus.AVAILABLE)

    def test_fallback_fetch_failure_status_mapping(self):
        router = SourceRouter()
        collector = BatchCollector(router=router)

        mock_bm = MagicMock()
        mock_fetch_res = MagicMock()
        mock_fetch_res.success = False
        mock_fetch_res.html = ""
        mock_fetch_res.error_type = "BLOCKED"
        mock_fetch_res.error_message = "Access Denied (HTTP 403)"
        mock_fetch_res.retrieved_at = "2026-03-31T12:00:00Z"
        mock_bm.fetch_page.return_value = mock_fetch_res

        urls = ["https://custom-city.gov/projects/blocked-consultation"]
        results = collector.collect_urls(urls=urls, browser_manager=mock_bm)

        self.assertEqual(len(results), 1)
        res = results[0]
        self.assertFalse(res.success)
        self.assertEqual(res.comments_status, CommentStatus.BLOCKED)


if __name__ == "__main__":
    unittest.main()

