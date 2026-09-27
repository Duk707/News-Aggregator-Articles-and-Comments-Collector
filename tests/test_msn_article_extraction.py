import os
import pytest
from bs4 import BeautifulSoup

from src.collectors.msn import MSNAdapter
from src.extraction.metadata import MetadataExtractor, ExtractedMetadata
from src.extraction.article_text import ExtractedArticleText
from src.browser import BrowserManager
from src.collectors.batch import BatchCollector


def test_msn_metadata_parsing_and_epoch_timestamp_normalization():
    """
    Unit test: Verifies OpenGraph metadata extraction, epoch timestamp normalization,
    and extraction method tracking for MSN articles.
    """
    sample_msn_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta property="og:title" content="Dates to know for the 2026 midterm elections" />
        <meta property="article:author" content="Claire Carter, Washington Examiner" />
        <meta property="article:published_time" content="1771445945" />
        <meta property="article:modified_time" content="1788204506" />
        <meta property="og:locale" content="en-us" />
        <link rel="canonical" href="https://www.washingtonexaminer.com/news/123" />
    </head>
    <body></body>
    </html>
    """
    adapter = MSNAdapter()
    meta: ExtractedMetadata = adapter.extract_metadata(sample_msn_html)

    assert meta.title == "Dates to know for the 2026 midterm elections"
    assert meta.author == "Claire Carter"
    assert meta.original_publisher == "Washington Examiner"
    assert meta.publication_datetime == "2026-02-18T20:19:05Z"
    assert meta.updated_datetime == "2026-08-31T19:28:26Z"
    assert meta.canonical_url == "https://www.washingtonexaminer.com/news/123"
    assert meta.language == "en-us"
    assert meta.field_methods["title"] == "OpenGraph/Meta"
    assert meta.field_methods["publication_datetime"] == "OpenGraph/Meta"


def test_msn_original_publisher_secregation_and_domain_fallback():
    """
    Unit test: Ensures MSN platform is preserved separately from original_publisher,
    and verifies byline/canonical domain attribution logic.
    """
    adapter = MSNAdapter()
    assert adapter.platform_name == "MSN"

    # Byline attribution
    meta1 = adapter.extract_metadata("""
    <meta property="og:title" content="Sample News" />
    <meta property="article:author" content="Jane Doe, Reuters" />
    """)
    assert meta1.author == "Jane Doe"
    assert meta1.original_publisher == "Reuters"

    # Canonical domain fallback when publisher tag is generic MSN
    meta2 = adapter.extract_metadata("""
    <meta property="og:title" content="Sample News" />
    <meta property="og:site_name" content="MSN" />
    <link rel="canonical" href="https://www.apnews.com/article/12345" />
    """)
    assert meta2.original_publisher == "Apnews"


def test_msn_shadow_dom_hydrated_body_extraction():
    """
    Unit test: Verifies targeted MSN body extraction strategy on hydrated Shadow DOM content.
    """
    sample_hydrated_html = """
    <html>
    <body>
        <nav><a href="#">Home</a></nav>
        <div class="ad-banner">Ad content</div>
        <article class="msn-hydrated-body">
            <p>The general elections will be held on Nov. 3 across all 50 states.</p>
            <p>Voters nationwide will decide all 435 House seats and 33 Senate seats.</p>
        </article>
        <footer>Copyright 2026</footer>
    </body>
    </html>
    """
    adapter = MSNAdapter()
    body: ExtractedArticleText = adapter.extract_article_body(sample_hydrated_html)

    assert body.success is True
    assert body.extraction_method == "MSN Shadow DOM Hydration"
    assert body.paragraph_count == 2
    assert "general elections will be held on Nov. 3" in body.text
    assert "House seats and 33 Senate seats" in body.text
    assert "Ad content" not in body.text
    assert "Copyright" not in body.text


def test_msn_adapter_empty_and_failure_handling():
    """
    Unit test: Verifies adapter behavior for empty HTML and unsupported URLs.
    """
    adapter = MSNAdapter()

    empty_meta = adapter.extract_metadata("")
    assert empty_meta.title is None
    assert empty_meta.extraction_summary == "Empty HTML"

    empty_body = adapter.extract_article_body("")
    assert empty_body.success is False

    unsupported_fetch = adapter.load_article("https://example.com/not-msn")
    assert unsupported_fetch.success is False
    assert unsupported_fetch.error_type == "UNSUPPORTED"


def test_msn_hydrated_body_extraction_deduplication_and_noise_exclusion():
    """
    Regression test for MSN Shadow DOM hydration:
    Verifies that:
    1. Duplicate article paragraphs in hydrated HTML are deduplicated without repetition.
    2. Legitimate distinct paragraphs containing repeated keywords/wording are preserved.
    3. Non-article recommendation containers (e.g. recommended articles, feed cards) are excluded.
    """
    sample_noisy_html = """
    <!DOCTYPE html>
    <html>
    <body>
        <main>
            <article class="msn-hydrated-body">
                <p>UC Berkeley is breaking traditional boundaries by integrating AI across all academic disciplines.</p>
                <p>Students from humanities to computer science now utilize adaptive learning algorithms in course projects.</p>
                <!-- Duplicate paragraph artifact from nested Shadow DOM traversal -->
                <p>UC Berkeley is breaking traditional boundaries by integrating AI across all academic disciplines.</p>
                <!-- Legitimate distinct paragraph with similar wording -->
                <p>The university announced that AI ethics will also be mandatory across all academic disciplines.</p>
            </article>
            <div class="recommended-articles">
                <p>In today's hyper-competitive job market, staying ahead requires continuous skill development.</p>
                <p>In today's hyper-competitive job market, staying ahead requires continuous skill development.</p>
            </div>
        </main>
    </body>
    </html>
    """
    adapter = MSNAdapter()
    body = adapter.extract_article_body(sample_noisy_html)

    assert body.success is True
    assert body.paragraph_count == 3
    assert "UC Berkeley is breaking traditional boundaries" in body.text
    assert "Students from humanities to computer science" in body.text
    assert "mandatory across all academic disciplines" in body.text

    # Verify duplicate paragraph artifact was deduplicated (should appear only once)
    assert body.text.count("UC Berkeley is breaking traditional boundaries") == 1

def test_msn_article_shadow_dom_modal_exclusion():
    """
    Unit test: Verifies that legitimate news paragraphs are preserved while modal dialog 
    overlay boilerplate strings ("This is a modal window.", "Beginning of dialog window.", etc.)
    are excluded from extracted MSN article body text.
    """
    with open("tests/fixtures/msn_article_shadow_dom_modal_observed.html", "r", encoding="utf-8") as f:
        fixture_html = f.read()

    adapter = MSNAdapter()
    body = adapter.extract_article_body(fixture_html)

    assert body.success is True
    assert body.paragraph_count == 5
    assert "Donald Trump has branded the Strait of Hormuz" in body.text
    assert "Araghchi told reporters at the United Nations" in body.text
    assert "British Foreign Secretary Ed Miliband" in body.text
    assert "trade snapshot report showed that food and drink exports" in body.text

    # Verify modal dialog boilerplate strings are excluded
    assert "This is a modal window" not in body.text
    assert "Beginning of dialog window" not in body.text
    assert "End of dialog window" not in body.text
    assert "Escape will cancel and close" not in body.text
    assert "Select a valid image file" not in body.text


def test_msn_article_boilerplate_and_subheading_preservation():
    """
    Unit test: Verifies that MSN canonical source headers, provider app links, and wire service disclaimers
    are removed while subheadings, author biography sentences, and legitimate comma-separated lists are preserved.
    """
    sample_html = """
    <html>
    <body>
        <article class="msn-hydrated-body">
            <p>UC Berkeley is breaking traditional boundaries by integrating AI across humanities, science, and law.</p>
            <p>"The More AI Advances, the More We Must Meet"</p>
            <p>Students, faculty, and industry researchers collaborate daily in open campus laboratories.</p>
            <p>Leora Hessen is an AI pioneer, educational technology advocate, and founder of HelloAida.ai, a multilingual, curriculum-aligned AI tutoring platform built for South African learners.</p>
            <div class="source-link">
                <p>Original article source: UC Berkeley breaks walls in AI education</p>
            </div>
            <p>READ ON THE FOX BUSINESS APP</p>
            <p>Provided by SyndiGate Media Inc.</p>
        </article>
    </body>
    </html>
    """
    adapter = MSNAdapter()
    body = adapter.extract_article_body(sample_html)

    assert body.success is True
    assert body.paragraph_count == 4
    assert "UC Berkeley is breaking traditional boundaries" in body.text
    assert "The More AI Advances, the More We Must Meet" in body.text
    assert "Students, faculty, and industry researchers" in body.text
    assert "Leora Hessen is an AI pioneer" in body.text

    # Positive removals
    assert "Original article source:" not in body.text
    assert "READ ON THE FOX BUSINESS APP" not in body.text
    assert "Provided by SyndiGate Media" not in body.text




@pytest.mark.integration
def test_live_msn_article_extraction():
    """
    Live Integration Test: Fetches a live MSN article using MSNAdapter and BrowserManager,
    extracts metadata and body, and verifies complete normalized Article data output.
    """
    target_url = "https://www.msn.com/en-us/news/politics/here-are-the-dates-to-know-for-the-2026-midterm-elections/ar-AA1WCoGY"
    collector = BatchCollector()

    with BrowserManager(headless=True, navigation_timeout_ms=45000, request_delay_ms=1000) as bm:
        results = collector.collect_urls([target_url], browser_manager=bm)
        assert len(results) == 1
        res = results[0]

        print("\n=======================================================")
        print("         LIVE MSN ARTICLE EXTRACTION VERIFICATION       ")
        print("=======================================================")
        print(f"Requested URL:       {res.requested_url}")
        print(f"Extraction Success:  {res.success}")
        assert res.success is True
        assert res.article is not None

        art = res.article
        print(f"Platform:            {art.platform}")
        print(f"Source Adapter:      {art.source_adapter}")
        print(f"Canonical URL:       {art.canonical_url}")
        print(f"Title:               {art.title}")
        print(f"Author:              {art.author}")
        print(f"Original Publisher:  {art.original_publisher}")
        print(f"Publication Date:    {art.publication_datetime}")
        print(f"Updated Date:        {art.updated_datetime}")
        print(f"Language:            {art.language}")
        print(f"Extraction Method:   {art.extraction_method}")
        print(f"Body Text Length:    {len(art.article_text) if art.article_text else 0} chars")

        if art.article_text:
            preview = art.article_text[:150].replace('\n', ' ').encode('ascii', errors='replace').decode('ascii')
            print(f"Body Preview:        {preview}...")

        print("=======================================================\n")

        # Asserts
        assert art.platform == "MSN"
        assert art.source_adapter == "MSNAdapter"
        assert art.title == "Here are the dates to know for the 2026 midterm elections"
        assert art.author == "Claire Carter"
        assert art.original_publisher == "Washington Examiner"
        assert art.publication_datetime == "2026-02-18T20:19:05Z"
        assert art.language == "en-us"
        assert art.article_text is not None
        assert len(art.article_text) > 500
