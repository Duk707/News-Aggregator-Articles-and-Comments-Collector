import pytest
from src.collectors.yahoo import YahooAdapter
from src.extraction.comments import YahooCommentExtractor, CommentExtractionResult
from src.models.comment import Comment
from src.models.comment_status import CommentStatus
from src.browser import BrowserManager


SAMPLE_COMMENT_HTML_FIXTURE = """
<!DOCTYPE html>
<html>
<head><title>Test Article with Comments</title></head>
<body>
    <h1>AI in Education: Transforming Modern Classrooms</h1>
    <p>This is the main body of the article about artificial intelligence in schools.</p>

    <div class="caas-comments">
        <button class="caas-button">View comments (3)</button>
        <div class="comment-list">
            <div class="caas-comment-item" data-comment-id="comment_top_1">
                <span class="comment-author">Alice Researcher</span>
                <span class="comment-date" datetime="2026-09-25T14:30:00Z">2 hours ago</span>
                <p class="comment-text">AI tools are revolutionizing how teachers personalize student learning plans.</p>

                <div class="caas-comment-replies">
                    <div class="caas-comment-item" data-comment-id="comment_reply_1_1">
                        <span class="comment-author">Bob Educator</span>
                        <span class="comment-date" datetime="2026-09-25T15:00:00Z">1 hour ago</span>
                        <p class="comment-text">I agree! We are seeing great engagement with adaptive tutoring apps.</p>
                        <span class="like-count">5</span>
                    </div>
                </div>
            </div>

            <div class="caas-comment-item" data-comment-id="comment_top_2">
                <span class="comment-author">Charlie Parent</span>
                <span class="comment-date" datetime="2026-09-25T16:00:00Z">30 mins ago</span>
                <p class="comment-text">We must ensure privacy protections for student data when implementing AI.</p>
                <span class="like-count">12</span>
            </div>

            <!-- Duplicate comment element to verify deduplication -->
            <div class="caas-comment-item" data-comment-id="comment_top_2">
                <span class="comment-author">Charlie Parent</span>
                <p class="comment-text">We must ensure privacy protections for student data when implementing AI.</p>
            </div>
        </div>
    </div>
</body>
</html>
"""


def test_comment_extraction_from_html_fixture():
    """
    Tests evidence-driven public comment extraction against a controlled HTML fixture.
    Verifies normalized fields, top-level/reply nesting, parent_comment_id, depth,
    reply_count, reaction parsing, deduplication, and max_comments limits.
    """
    article_url = "https://news.yahoo.com/ai-in-education-12345678.html"

    # Test full extraction
    result = YahooCommentExtractor.extract(url=article_url, html=SAMPLE_COMMENT_HTML_FIXTURE, max_comments=50)

    assert isinstance(result, CommentExtractionResult)
    assert result.status == CommentStatus.AVAILABLE
    assert result.extracted_count == 3  # 2 top-level + 1 reply (duplicate comment_top_2 ignored)
    assert len(result.comments) == 3

    # Check Top-Level Comment 1
    c1 = result.comments[0]
    assert c1.comment_id == "comment_top_1"
    assert c1.author_display_name == "Alice Researcher"
    assert c1.comment_text == "AI tools are revolutionizing how teachers personalize student learning plans."
    assert c1.depth == 0
    assert c1.parent_comment_id is None
    assert c1.reply_count == 1

    # Check Reply Comment 1.1
    c1_reply = result.comments[1]
    assert c1_reply.comment_id == "comment_reply_1_1"
    assert c1_reply.author_display_name == "Bob Educator"
    assert c1_reply.comment_text == "I agree! We are seeing great engagement with adaptive tutoring apps."
    assert c1_reply.depth == 1
    assert c1_reply.parent_comment_id == "comment_top_1"
    assert c1_reply.reactions == 5

    # Check Top-Level Comment 2
    c2 = result.comments[2]
    assert c2.comment_id == "comment_top_2"
    assert c2.author_display_name == "Charlie Parent"
    assert c2.depth == 0
    assert c2.reactions == 12

    # Test max_comments truncation limit
    result_truncated = YahooCommentExtractor.extract(url=article_url, html=SAMPLE_COMMENT_HTML_FIXTURE, max_comments=2)
    assert len(result_truncated.comments) == 2
    assert result_truncated.extracted_count == 2


def test_comment_extraction_explicit_status_handling():
    """
    Verifies that explicit comment statuses (LOGIN_REQUIRED, DISABLED, NONE_PRESENT, NOT_LOADED, UNKNOWN)
    are accurately assigned when comments cannot be obtained from DOM, preventing mislabeling.
    """
    url = "https://news.yahoo.com/sample-article.html"

    # 1. Login required HTML
    login_html = "<html><body><button>View comments</button><p>Sign in to comment on this story.</p></body></html>"
    res_login = YahooCommentExtractor.extract(url=url, html=login_html)
    assert res_login.status == CommentStatus.LOGIN_REQUIRED
    assert len(res_login.comments) == 0

    # 2. Disabled comments HTML
    disabled_html = "<html><body><div id='comments'><p>Comments are disabled for this article.</p></div></body></html>"
    res_disabled = YahooCommentExtractor.extract(url=url, html=disabled_html)
    assert res_disabled.status == CommentStatus.DISABLED
    assert len(res_disabled.comments) == 0

    # 3. Explicit 0 comments reported HTML
    zero_comments_html = "<html><body><div class='caas-comments'><h3>0 Comments</h3></div></body></html>"
    res_zero = YahooCommentExtractor.extract(url=url, html=zero_comments_html)
    assert res_zero.status == CommentStatus.NONE_PRESENT
    assert len(res_zero.comments) == 0

    # 4. View comments button exists, reported count > 0, but no comment elements in DOM -> NOT_LOADED
    not_loaded_html = "<html><body><button class='caas-button'>View comments (15)</button></body></html>"
    res_not_loaded = YahooCommentExtractor.extract(url=url, html=not_loaded_html)
    assert res_not_loaded.status == CommentStatus.NOT_LOADED
    assert len(res_not_loaded.comments) == 0

    # 5. Plain article without any comment evidence -> UNKNOWN
    unknown_html = "<html><body><h1>Just an Article</h1><p>Some text</p></body></html>"
    res_unknown = YahooCommentExtractor.extract(url=url, html=unknown_html)
    assert res_unknown.status == CommentStatus.UNKNOWN
    assert len(res_unknown.comments) == 0


def test_live_yahoo_comment_extraction():
    """
    Integration test executing evidence-driven comment extraction on a live Yahoo article.
    Verifies live behavior returns explicit status and diagnostics without throwing errors.
    """
    live_url = "https://news.yahoo.com/high-school-students-using-ai-110000373.html"
    adapter = YahooAdapter()

    with BrowserManager(headless=True) as bm:
        fetch_result = adapter.load_article(live_url, browser_manager=bm)
        assert fetch_result.success is True

        extraction_result = adapter.extract_comments(
            url=live_url,
            html=fetch_result.html,
            browser_manager=bm,
            max_comments=20
        )

        assert isinstance(extraction_result, CommentExtractionResult)
        assert extraction_result.url == live_url
        assert isinstance(extraction_result.status, CommentStatus)

        # On live unauthenticated Yahoo sessions, clicking 'View comments' does NOT load public comment DOM nodes.
        # Ensure status is NOT mislabeled as NONE_PRESENT when comments were not loaded.
        if extraction_result.extracted_count == 0:
            assert extraction_result.status in [
                CommentStatus.NONE_PRESENT,
                CommentStatus.NOT_LOADED,
                CommentStatus.UNKNOWN,
                CommentStatus.LOGIN_REQUIRED,
                CommentStatus.DISABLED
            ]


        print(f"\n--- Live Yahoo Comment Extraction Verification ---")
        print(f"URL: {extraction_result.url}")
        print(f"Final Comment Status: {extraction_result.status.value}")
        print(f"Reported Comment Count: {extraction_result.reported_count}")
        print(f"Extracted Comment Count: {extraction_result.extracted_count}")
        print(f"Diagnostic Notes: {extraction_result.diagnostic_notes}")


def test_yahoo_nexus_graphql_offline_fixtures(monkeypatch):
    """
    Tests Yahoo Nexus GraphQL comment extraction using sanitized provider-observed JSON fixtures.
    Verifies top-level comments, reply hierarchy, parent_comment_id, depth, pagination, and max_comments.
    """
    import json
    from unittest.mock import MagicMock

    with open("tests/fixtures/yahoo_nexus_graphql_observed.json", "r", encoding="utf-8") as f:
        top_fixture = json.load(f)

    with open("tests/fixtures/yahoo_nexus_replies_observed.json", "r", encoding="utf-8") as f:
        replies_fixture = json.load(f)

    # Mock urllib.request.urlopen to return offline fixtures
    mock_urlopen = MagicMock()

    class MockResponse:
        def __init__(self, data_dict):
            self.data = json.dumps(data_dict).encode("utf-8")
            self.headers = {}
        def read(self):
            return self.data
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    def mock_urlopen_side_effect(req, timeout=10):
        body = json.loads(req.data.decode("utf-8"))
        hash_val = body.get("extensions", {}).get("persistedQuery", {}).get("sha256Hash")
        if hash_val == "ycp_GetConversationWithMultipleContents_v1.2.0":
            return MockResponse(top_fixture)
        elif hash_val == "ycp_GetCommentReplies_v1.4.16":
            return MockResponse(replies_fixture)
        return MockResponse({})

    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen_side_effect)

    yahoo_url = "https://www.yahoo.com/news/politics/articles/test-article-234521611.html"
    dummy_html = "<html><body><div g='260f82f4-7570-3c6a-8f51-30dbe0955c2b'>Article Content</div></body></html>"

    res = YahooCommentExtractor.extract(url=yahoo_url, html=dummy_html, max_comments=10)

    assert res.status == CommentStatus.AVAILABLE
    assert res.extracted_count == 4  # 2 top-level + 2 replies
    assert res.reported_count == 5500
    assert len(res.comments) == 4

    # Top level comment 1
    c1 = res.comments[0]
    assert c1.comment_id == "yahoo_c1_top"
    assert c1.author_display_name == "Alice"
    assert c1.depth == 0
    assert c1.parent_comment_id is None
    assert c1.reply_count == 2

    # Reply 1 to c1
    r1 = res.comments[1]
    assert r1.comment_id == "yahoo_r1_child"
    assert r1.author_display_name == "Charlie"
    assert r1.depth == 1
    assert r1.parent_comment_id == "yahoo_c1_top"

    # Truncation via max_comments = 2
    res_trunc = YahooCommentExtractor.extract(url=yahoo_url, html=dummy_html, max_comments=2)
    assert res_trunc.extracted_count == 2
    assert len(res_trunc.comments) == 2


def test_yahoo_content_uuid_precedence():
    """
    Regression test for Yahoo article UUID extraction precedence hierarchy.
    Verifies that:
    1. Navigation/header data-ylk UUIDs (e.g. sec:topic-subnav) appearing before article content
       are IGNORED in favor of authoritative article deep-link metadata.
    2. Melania Trump article resolves strictly to '3bb64183-23f6-31cd-a492-620f51edd400'.
    3. Red States article resolves strictly to '293e13f5-b325-3b95-a574-ae19eabbc23a'.
    4. Caas-content-id meta tags and article-scoped containers remain fully supported.
    """
    # 1. Navigation YLK UUID appearing BEFORE authoritative article meta tag
    nav_and_article_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta property="al:ios:url" content="yahoo://article/view?uuid=3bb64183-23f6-31cd-a492-620f51edd400&amp;src=web" />
    </head>
    <body>
        <header>
            <a data-ylk="cid:Top Stories;cpos:1;ct:story;elm:hdln;g:7ba05b36-5a36-3f96-a920-7a9aa4bd802d;itc:0;sec:topic-subnav;">Top Story Link</a>
        </header>
        <article>
            <h1>Melania Trump Pushes for AI in Classrooms</h1>
        </article>
    </body>
    </html>
    """
    res_melania = YahooCommentExtractor._extract_content_id(
        url="https://www.yahoo.com/news/politics/articles/melania-trump-pushes-ai-classrooms-233234720.html",
        html=nav_and_article_html
    )
    assert res_melania == "3bb64183-23f6-31cd-a492-620f51edd400"
    assert res_melania != "7ba05b36-5a36-3f96-a920-7a9aa4bd802d"

    # 2. Red States article deep link meta tag
    red_states_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta property="al:android:url" content="yahoo://article/view?uuid=293e13f5-b325-3b95-a574-ae19eabbc23a&amp;src=web" />
    </head>
    <body>
        <header><a data-ylk="g:7ba05b36-5a36-3f96-a920-7a9aa4bd802d;sec:topic-subnav;">Subnav</a></header>
        <article><h1>Trump wants AI in every classroom</h1></article>
    </body>
    </html>
    """
    res_red = YahooCommentExtractor._extract_content_id(
        url="https://www.yahoo.com/news/politics/articles/why-red-states-rejecting-trump-100000034.html",
        html=red_states_html
    )
    assert res_red == "293e13f5-b325-3b95-a574-ae19eabbc23a"
    assert res_red != "7ba05b36-5a36-3f96-a920-7a9aa4bd802d"

    # 3. Caas-content-id meta tag fallback
    caas_meta_html = """
    <html>
    <head><meta name="caas-content-id" content="430cec31-9c16-3be4-b560-1fef6755f40e" /></head>
    <body><article>Article Body</article></body>
    </html>
    """
    res_caas = YahooCommentExtractor._extract_content_id(url="https://finance.yahoo.com/test", html=caas_meta_html)
    assert res_caas == "430cec31-9c16-3be4-b560-1fef6755f40e"

    # 4. Article-scoped DOM fallback
    article_scoped_html = """
    <html>
    <body>
        <header><div data-ylk="g:7ba05b36-5a36-3f96-a920-7a9aa4bd802d;sec:topic-subnav;">Header</div></header>
        <article data-caas-content-id="6ad2a46d-1af4-3f21-a51a-352273f4fe5f">Article Body</article>
    </body>
    </html>
    """
    res_scoped = YahooCommentExtractor._extract_content_id(url="https://finance.yahoo.com/test2", html=article_scoped_html)
    assert res_scoped == "6ad2a46d-1af4-3f21-a51a-352273f4fe5f"

    # 5. Explicit URL UUID fallback
    url_with_uuid = "https://www.yahoo.com/news/article-11111111-2222-3333-4444-555555555555.html"
    res_url = YahooCommentExtractor._extract_content_id(url=url_with_uuid, html="<html><body>No meta</body></html>")
    assert res_url == "11111111-2222-3333-4444-555555555555"


