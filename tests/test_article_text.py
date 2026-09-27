import pytest
from bs4 import BeautifulSoup
from src.extraction import ArticleTextExtractor, ExtractedArticleText
from src.collectors.yahoo import YahooAdapter
from src.browser import BrowserManager


def test_article_text_extraction_strips_unwanted_elements():
    """
    Verify that ArticleTextExtractor extracts article body paragraphs while cleanly
    excluding navigation, ads, recommendations, footers, and comments.
    """
    sample_html = """
    <html>
    <head><style>.ad { color: red; }</style></head>
    <body>
        <nav>
            <a href="#">Home</a> <a href="#">Politics</a>
        </nav>
        <header>
            <h1>Main Article Headline</h1>
        </header>
        <article class="caas-body">
            <p>First paragraph of the main news article discussing AI in education.</p>
            <div class="caas-sponsored">
                <p>Sponsored Advertisement Content - Buy Now!</p>
            </div>
            <p>Second paragraph explaining how machine learning models assist teachers in grading.</p>
            <div class="caas-related-articles">
                <h3>Recommended Stories</h3>
                <p>Unrelated recommended story summary.</p>
            </div>
            <p>Third paragraph providing research statistics on student engagement.</p>
            <div id="comments" class="comments-container">
                <div class="comment">User Comment Text: This is a public comment.</div>
            </div>
        </article>
        <footer>
            <p>Copyright 2026 Yahoo News. All rights reserved.</p>
        </footer>
    </body>
    </html>
    """

    result: ExtractedArticleText = ArticleTextExtractor.extract(sample_html)

    assert result.success is True
    assert result.paragraph_count == 3
    assert "First paragraph of the main news article" in result.text
    assert "Second paragraph explaining how machine learning" in result.text
    assert "Third paragraph providing research statistics" in result.text

    # Verify unwanted content is COMPLETELY excluded
    assert "Sponsored Advertisement" not in result.text
    assert "Recommended Stories" not in result.text
    assert "Unrelated recommended story" not in result.text
    assert "User Comment Text" not in result.text
    assert "Copyright 2026" not in result.text
    assert "Home" not in result.text


def test_article_text_extraction_empty_handling():
    """Verify empty or non-article HTML returns success=False without crashing."""
    empty_html = "<html><body><div class='caas-sponsored'>Sponsored Only</div></body></html>"
    result: ExtractedArticleText = ArticleTextExtractor.extract(empty_html)

    assert result.success is False
    assert result.text is None
    assert result.paragraph_count == 0
    assert result.warning is not None


@pytest.mark.integration
def test_live_yahoo_article_body_extraction():
    """
    Integration test: Fetches a live Yahoo News article page, extracts the body text
    using YahooAdapter, and verifies that body text is extracted, paragraph count > 0,
    and no navigation, ad, or comment containers are included.
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

        print(f"\n[BODY INTEGRATION TEST] Article URL: {article_url}")

        fetch_result = adapter.load_article(article_url, browser_manager=bm)
        assert fetch_result.success is True

        body_result: ExtractedArticleText = adapter.extract_article_body(fetch_result.html)

        print(f"[BODY INTEGRATION TEST] Body Extraction Success: {body_result.success}")
        print(f"[BODY INTEGRATION TEST] Extraction Method: {body_result.extraction_method}")
        print(f"[BODY INTEGRATION TEST] Paragraph Count: {body_result.paragraph_count}")
        if body_result.text:
            first_150_chars = body_result.text[:150].replace('\n', ' ')
            safe_preview = first_150_chars.encode('ascii', errors='replace').decode('ascii')
            print(f"[BODY INTEGRATION TEST] Preview (First 150 chars): {safe_preview}...")

        # Asserts
        assert body_result.success is True
        assert body_result.paragraph_count > 0
        assert body_result.char_count > 200
        assert body_result.text is not None

        # Verify unwanted text exclusions in live extraction
        text_lower = body_result.text.lower()
        assert "privacy policy" not in text_lower
        assert "terms of service" not in text_lower
        assert "all rights reserved" not in text_lower


def test_yahoo_article_text_boilerplate_and_comma_list_preservation():
    """
    Unit test: Verifies that trailing copyright disclaimers, affiliate app download prompts,
    and link-only related article headers are cleanly excluded, while legitimate prose
    containing comma-separated lists, quotes, and research citations are preserved.
    """
    html = """
    <html>
    <body>
        <article class="caas-body">
            <p>School districts nationwide are evaluating generative AI platforms, balancing educational innovation against academic integrity.</p>
            <p>The curriculum committee evaluated several tools, including ChatGPT, Claude, Gemini, and Copilot, for classroom use.</p>
            <p>"We want to ensure AI empowers students without replacing critical reasoning," said Dr. Jane Smith.</p>
            <div class="col-footer">
                <p><a data-ylk="elm:context_link;sec:content-canvas;" href="https://example.com/related1">Map Shows Senate Seats Most Likely to Flip</a></p>
                <p><a data-ylk="elm:context_link;sec:content-canvas;" href="https://example.com/related2">Start your unlimited Newsweek trial</a></p>
            </div>
            <p>Copyright 2026 Nexstar Media, Inc. All rights reserved. This material may not be published, broadcast, rewritten, or redistributed. For the latest news, weather, sports, and streaming video, head to The Hill.</p>
            <p><a data-yga="article_link" href="https://example.com/app">Click here</a> to download our free news, weather and smart TV apps. And <a href="#">click here</a> to stream Channel 9 Eyewitness News live.</p>
        </article>
    </body>
    </html>
    """
    result = ArticleTextExtractor.extract(html)

    assert result.success is True
    assert result.paragraph_count == 3
    assert "School districts nationwide are evaluating generative AI" in result.text
    assert "ChatGPT, Claude, Gemini, and Copilot" in result.text
    assert "empowers students without replacing critical reasoning" in result.text

    # Positive removals
    assert "Map Shows Senate Seats" not in result.text
    assert "Start your unlimited Newsweek trial" not in result.text
    assert "Copyright 2026 Nexstar Media" not in result.text
    assert "download our free news, weather" not in result.text

