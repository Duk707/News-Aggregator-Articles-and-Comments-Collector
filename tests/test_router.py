import pytest
from src.utils.urls import validate_url, normalize_url, extract_domain
from src.collectors import BaseAdapter, YahooAdapter, MSNAdapter, SourceRouter, RoutingResult
from src.models import CommentStatus


def test_url_utils():
    """Test validate_url, normalize_url, and extract_domain."""
    assert validate_url("https://news.yahoo.com/article-123.html") is True
    assert validate_url("http://msn.com/en-us/news") is True
    assert validate_url("not_a_url") is False
    assert validate_url("ftp://example.com/file") is False
    assert validate_url("") is False
    assert validate_url(None) is False

    assert normalize_url("  https://news.yahoo.com/  ") == "https://news.yahoo.com/"
    assert extract_domain("https://NEWS.YAHOO.COM/path") == "news.yahoo.com"
    assert extract_domain("invalid-url") is None


def test_yahoo_adapter_supports():
    """Test YahooAdapter URL recognition."""
    adapter = YahooAdapter()
    assert adapter.supports("https://news.yahoo.com/ai-in-education-12345.html") is True
    assert adapter.supports("https://finance.yahoo.com/news/tech-update.html") is True
    assert adapter.supports("https://yahoo.com/article") is True
    assert adapter.supports("https://msn.com/news") is False
    assert adapter.supports("https://nytimes.com") is False


def test_msn_adapter_supports():
    """Test MSNAdapter URL recognition."""
    adapter = MSNAdapter()
    assert adapter.supports("https://www.msn.com/en-us/news/technology/ai-in-education") is True
    assert adapter.supports("https://msn.com/article") is True
    assert adapter.supports("https://news.yahoo.com/article") is False
    assert adapter.supports("https://cnn.com") is False


def test_source_router_yahoo_routing():
    """Test SourceRouter routing valid Yahoo URLs."""
    router = SourceRouter()
    yahoo_url = "https://news.yahoo.com/ai-in-education-1234.html"
    result, adapter = router.route(yahoo_url)

    assert result.is_valid is True
    assert result.supported is True
    assert result.platform_name == "Yahoo News"
    assert result.adapter_name == "YahooAdapter"
    assert adapter is not None
    assert isinstance(adapter, YahooAdapter)


def test_source_router_msn_routing():
    """Test SourceRouter routing valid MSN URLs."""
    router = SourceRouter()
    msn_url = "https://www.msn.com/en-us/news/article"
    result, adapter = router.route(msn_url)

    assert result.is_valid is True
    assert result.supported is True
    assert result.platform_name == "MSN"
    assert result.adapter_name == "MSNAdapter"
    assert adapter is not None
    assert isinstance(adapter, MSNAdapter)


def test_source_router_unsupported_domain():
    """Test SourceRouter with an unsupported website."""
    router = SourceRouter()
    unsupported_url = "https://www.nytimes.com/2026/09/25/technology/ai.html"
    result, adapter = router.route(unsupported_url)

    assert result.is_valid is True
    assert result.supported is False
    assert result.adapter_name is None
    assert result.platform_name is None
    assert result.status == CommentStatus.UNSUPPORTED
    assert "Unsupported" in result.error_message
    assert adapter is None


def test_source_router_malformed_url():
    """Test SourceRouter with malformed URLs."""
    router = SourceRouter()
    malformed_inputs = [
        "not_a_valid_url",
        "ftp://invalid-scheme.com",
        "http:///missing-host",
        "",
        "   "
    ]

    for bad_url in malformed_inputs:
        result, adapter = router.route(bad_url)
        assert result.is_valid is False
        assert result.supported is False
        assert adapter is None
        assert "Invalid" in result.error_message


def test_custom_adapter_registration():
    """Test dynamically registering a custom adapter."""
    class CustomAdapter(BaseAdapter):
        platform_name = "Custom Platform"
        adapter_name = "CustomAdapter"

        def supports(self, url: str) -> bool:
            return "customnews.org" in url

    router = SourceRouter()
    router.register_adapter(CustomAdapter())

    result, adapter = router.route("https://customnews.org/article-1")
    assert result.is_valid is True
    assert result.supported is True
    assert result.platform_name == "Custom Platform"
    assert isinstance(adapter, CustomAdapter)


def test_source_router_step30_adapters():
    """Test routing for TESL Ontario, HEPI, and EngagementHQ known domains."""
    router = SourceRouter()

    r1, a1 = router.route("https://blog.teslontario.org/post-1")
    assert r1.supported is True
    assert r1.adapter_name == "TESLOntarioAdapter"

    r2, a2 = router.route("https://www.hepi.ac.uk/post-1")
    assert r2.supported is True
    assert r2.adapter_name == "HEPIAdapter"

    r3, a3 = router.route("https://connect.austintexas.gov/projects/ai")
    assert r3.supported is True
    assert r3.adapter_name == "EngagementHQAdapter"


def test_source_router_route_by_html():
    """Test post-fetch route_by_html platform detection."""
    router = SourceRouter()

    # Pre-fetch fails on custom government domain
    r_pre, a_pre = router.route("https://custom-city.gov/consultation/ai")
    assert r_pre.supported is False
    assert a_pre is None

    # Post-fetch probe claims custom domain via HTML fingerprints
    html = """
    <html>
    <head>
        <meta name="generator" content="EngagementHQ 2.0" />
        <script src="https://cdn.engagementhq.com/assets/app.js"></script>
    </head>
    <body><div class="ehq-widget">Content</div></body>
    </html>
    """
    r_post, a_post = router.route_by_html("https://custom-city.gov/consultation/ai", html)
    assert r_post.supported is True
    assert r_post.adapter_name == "EngagementHQAdapter"
    assert a_post is not None

