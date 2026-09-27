import pytest
from bs4 import BeautifulSoup
from src.extraction import MetadataExtractor, ExtractedMetadata
from src.collectors.yahoo import YahooAdapter
from src.browser import BrowserManager


def test_json_ld_metadata_extraction():
    """Test Level 1: JSON-LD metadata extraction."""
    json_ld_html = """
    <html>
    <head>
        <script type="application/ld+json">
        {
            "@context": "https://schema.org",
            "@type": "NewsArticle",
            "headline": "AI Revolutionizes High School Science Labs",
            "author": {"@type": "Person", "name": "Alice Smith"},
            "datePublished": "2026-09-25T14:30:00Z",
            "dateModified": "2026-09-25T15:00:00Z",
            "publisher": {"@type": "Organization", "name": "Tech Education News"},
            "mainEntityOfPage": "https://news.yahoo.com/articles/ai-labs.html",
            "inLanguage": "en-US"
        }
        </script>
    </head>
    <body></body>
    </html>
    """
    metadata: ExtractedMetadata = MetadataExtractor.extract(json_ld_html)

    assert metadata.title == "AI Revolutionizes High School Science Labs"
    assert metadata.author == "Alice Smith"
    assert metadata.publication_datetime == "2026-09-25T14:30:00Z"
    assert metadata.updated_datetime == "2026-09-25T15:00:00Z"
    assert metadata.original_publisher == "Tech Education News"
    assert metadata.canonical_url == "https://news.yahoo.com/articles/ai-labs.html"
    assert metadata.language == "en-US"
    assert metadata.field_methods["title"] == "JSON-LD"
    assert metadata.field_methods["author"] == "JSON-LD"


def test_opengraph_meta_metadata_extraction():
    """Test Level 2: OpenGraph and Meta tags fallback metadata extraction."""
    og_html = """
    <html lang="en">
    <head>
        <meta property="og:title" content="OpenGraph Article Headline" />
        <meta name="author" content="Bob Johnson" />
        <meta property="article:published_time" content="2026-09-24T08:00:00Z" />
        <meta property="og:site_name" content="Associated Press" />
        <link rel="canonical" href="https://news.yahoo.com/articles/og-test.html" />
    </head>
    <body></body>
    </html>
    """
    metadata: ExtractedMetadata = MetadataExtractor.extract(og_html)

    assert metadata.title == "OpenGraph Article Headline"
    assert metadata.author == "Bob Johnson"
    assert metadata.publication_datetime == "2026-09-24T08:00:00Z"
    assert metadata.original_publisher == "Associated Press"
    assert metadata.canonical_url == "https://news.yahoo.com/articles/og-test.html"
    assert metadata.language == "en"
    assert metadata.field_methods["title"] == "OpenGraph/Meta"


def test_semantic_html_metadata_extraction():
    """Test Level 3: Semantic HTML fallback metadata extraction."""
    semantic_html = """
    <html>
    <body>
        <article>
            <h1>Semantic Heading Title</h1>
            <address>Carol White</address>
            <time datetime="2026-09-23T12:00:00Z">September 23, 2026</time>
        </article>
    </body>
    </html>
    """
    metadata: ExtractedMetadata = MetadataExtractor.extract(semantic_html)

    assert metadata.title == "Semantic Heading Title"
    assert metadata.author == "Carol White"
    assert metadata.publication_datetime == "2026-09-23T12:00:00Z"
    assert metadata.field_methods["title"] == "Semantic HTML"


def test_yahoo_selectors_metadata_extraction():
    """Test Level 4: Yahoo specific selector fallback metadata extraction."""
    yahoo_html = """
    <html>
    <body>
        <div class="caas-title">Yahoo Custom Selector Headline</div>
        <div class="caas-author-name">David Brown</div>
        <div class="caas-attr-provider">Reuters</div>
        <time class="caas-attr-meta-time" datetime="2026-09-22T10:00:00Z">Sept 22, 2026</time>
    </body>
    </html>
    """
    metadata: ExtractedMetadata = MetadataExtractor.extract(yahoo_html)

    assert metadata.title == "Yahoo Custom Selector Headline"
    assert metadata.author == "David Brown"
    assert metadata.original_publisher == "Reuters"
    assert metadata.publication_datetime == "2026-09-22T10:00:00Z"
    assert metadata.field_methods["title"] == "Yahoo Selector"


def test_missing_fields_handling_no_fabrication():
    """Verify missing fields remain None and no values are fabricated."""
    empty_html = "<html><body><p>Just a simple paragraph with no metadata</p></body></html>"
    metadata: ExtractedMetadata = MetadataExtractor.extract(empty_html)

    assert metadata.title is None
    assert metadata.author is None
    assert metadata.publication_datetime is None
    assert metadata.updated_datetime is None
    assert metadata.original_publisher is None
    assert metadata.canonical_url is None
    assert metadata.language is None
    assert metadata.extraction_summary == "None"


@pytest.mark.integration
def test_live_yahoo_article_metadata_extraction():
    """
    Integration test: Fetches a live Yahoo News article and extracts metadata
    using YahooAdapter, asserting that headline/title and canonical URL are extracted.
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

        print(f"\n[METADATA INTEGRATION TEST] Article URL: {article_url}")

        fetch_result = adapter.load_article(article_url, browser_manager=bm)
        assert fetch_result.success is True

        metadata: ExtractedMetadata = adapter.extract_metadata(
            fetch_result.html,
            fallback_url=fetch_result.final_url
        )

        print(f"[METADATA INTEGRATION TEST] Title: {metadata.title}")
        print(f"[METADATA INTEGRATION TEST] Author: {metadata.author}")
        print(f"[METADATA INTEGRATION TEST] Published Date: {metadata.publication_datetime}")
        print(f"[METADATA INTEGRATION TEST] Original Publisher: {metadata.original_publisher}")
        print(f"[METADATA INTEGRATION TEST] Canonical URL: {metadata.canonical_url}")
        print(f"[METADATA INTEGRATION TEST] Language: {metadata.language}")
        print(f"[METADATA INTEGRATION TEST] Field Extraction Methods: {metadata.field_methods}")
        print(f"[METADATA INTEGRATION TEST] Extraction Summary: {metadata.extraction_summary}")

        # Verification asserts
        assert metadata.title is not None and len(metadata.title) > 5
        assert metadata.canonical_url is not None and "yahoo.com" in metadata.canonical_url
        assert metadata.extraction_summary != "None"
