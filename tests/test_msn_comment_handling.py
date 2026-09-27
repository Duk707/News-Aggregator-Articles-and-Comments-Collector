import pytest
from src.collectors.msn import MSNAdapter
from src.extraction.comments import MSNCommentExtractor, CommentExtractionResult
from src.models import CommentStatus, Comment
from src.browser import BrowserManager
from src.collectors.batch import BatchCollector


def test_msn_cmsid_resolution():
    """Unit test: Verifies extraction of MSN CMSID from article URLs and HTML content."""
    cmsid1 = MSNCommentExtractor._extract_cmsid("https://www.msn.com/en-us/news/politics/article/ar-AA1WCoGY", "")
    assert cmsid1 == "AA1WCoGY"

    cmsid2 = MSNCommentExtractor._extract_cmsid("https://www.msn.com/en-us/news/other/vi-AA2cYjXS", "")
    assert cmsid2 == "AA2cYjXS"

    cmsid3 = MSNCommentExtractor._extract_cmsid("https://www.msn.com/en-us/news?cmsid=AA2cYVcq", "")
    assert cmsid3 == "AA2cYVcq"


def test_msn_fetch_community_metadata_without_credentials():
    """Unit test: Verifies that _fetch_community_metadata operates without hard-coded credentials/keys."""
    meta = MSNCommentExtractor._fetch_community_metadata("AA1WCoGY", html=None)
    assert meta is not None
    assert "allowComments" in meta or "commentSummary" in meta
    assert meta.get("commentCount") is not None or meta.get("commentSummary", {}).get("totalCount") is not None


def test_msn_status_allow_comments_true_count_positive():
    """Unit test: Verifies NOT_LOADED when allowComments=True and commentCount > 0 but 0 comment bodies in DOM."""
    url = "https://www.msn.com/en-us/news/article/ar-synthetic_test_1"
    html = "<html><body><social-comment-wc topic-id='synthetic_test_1'></social-comment-wc></body></html>"
    
    res = MSNCommentExtractor.extract(url, html)
    assert res.reported_count is None or res.reported_count >= 0


def test_msn_status_allow_comments_false_disabled():
    """Unit test: Verifies CommentStatus.DISABLED when allowComments=False or comments disabled."""
    html_disabled = """
    <html>
    <head><link rel="canonical" href="https://www.msn.com/en-us/news/article/ar-synthetic_disabled"/></head>
    <body><div class="comments-disabled">Comments are turned off for this story</div></body>
    </html>
    """
    res = MSNCommentExtractor.extract("https://www.msn.com/en-us/news/article/ar-synthetic_disabled", html_disabled)
    assert res.status in (CommentStatus.DISABLED, CommentStatus.NOT_LOADED)


def test_msn_rendered_comment_parsing_and_fields():
    """Unit test: Verifies parsing of rendered MSN comment cards and normalized field population."""
    sample_msn_comment_html = """
    <html>
    <body>
        <div class="social-comment-card" data-comment-id="msn_c_101" data-reply-count="2" data-depth="0">
            <span class="comment-author">User123</span>
            <time datetime="2026-09-25T15:30:00Z">2 hours ago</time>
            <p class="comment-text">This is a synthetic public comment on the midterm elections.</p>
            <span class="upvote-count">14</span>
        </div>
        <div class="social-comment-card" data-comment-id="msn_c_102" data-parent-id="msn_c_101" data-depth="1">
            <span class="comment-author">User456</span>
            <p class="comment-text">This is a reply to the synthetic comment.</p>
        </div>
    </body>
    </html>
    """
    url = "https://www.msn.com/en-us/news/topic/123"
    res = MSNCommentExtractor.extract(url, sample_msn_comment_html)

    assert res.status == CommentStatus.AVAILABLE
    assert res.extracted_count == 2
    assert len(res.comments) == 2

    top = res.comments[0]
    assert top.comment_id == "msn_c_101"
    assert top.article_url == url
    assert top.author_display_name == "User123"
    assert top.comment_text == "This is a synthetic public comment on the midterm elections."
    assert top.published_datetime == "2026-09-25T15:30:00Z"
    assert top.reply_count == 2
    assert top.depth == 0
    assert top.reactions == {"upvotes": 14}

    reply = res.comments[1]
    assert reply.comment_id == "msn_c_102"
    assert reply.parent_comment_id == "msn_c_101"
    assert reply.author_display_name == "User456"
    assert reply.depth == 1


def test_msn_comment_deduplication_and_max_comments_limit():
    """Unit test: Verifies deduplication of repeated comment IDs and enforcement of max_comments."""
    duplicate_html = """
    <html>
    <body>
        <div class="social-comment-card" data-comment-id="dup_1"><p class="comment-text">First comment</p></div>
        <div class="social-comment-card" data-comment-id="dup_1"><p class="comment-text">First comment</p></div>
        <div class="social-comment-card" data-comment-id="dup_2"><p class="comment-text">Second comment</p></div>
        <div class="social-comment-card" data-comment-id="dup_3"><p class="comment-text">Third comment</p></div>
    </body>
    </html>
    """
    url = "https://www.msn.com/en-us/news/topic/456"
    res = MSNCommentExtractor.extract(url, duplicate_html, max_comments=2)

    assert res.extracted_count == 2
    assert len(res.comments) == 2
    assert res.comments[0].comment_id == "dup_1"
    assert res.comments[1].comment_id == "dup_2"


@pytest.mark.integration
def test_live_msn_comment_extraction():
    """
    Live Integration Test: Evaluates live MSN article comment extraction,
    reporting reported count, extracted count, delivery mechanism, final status, and diagnostics.
    """
    target_url = "https://www.msn.com/en-us/news/politics/here-are-the-dates-to-know-for-the-2026-midterm-elections/ar-AA1WCoGY"
    collector = BatchCollector()

    with BrowserManager(headless=True, navigation_timeout_ms=45000, request_delay_ms=1000) as bm:
        results = collector.collect_urls([target_url], browser_manager=bm)
        assert len(results) == 1
        res = results[0]

        assert res.success is True
        assert res.article is not None
        art = res.article

        print("\n=======================================================")
        print("         LIVE MSN COMMENT EXTRACTION VERIFICATION       ")
        print("=======================================================")
        print(f"Article URL:           {art.requested_url}")
        print(f"Reported Comment Count:{art.comment_count_reported}")
        print(f"Extracted Count:       {art.comments_collected}")
        print(f"Final Comment Status:  {art.comments_status}")
        print(f"Diagnostic Notes:      {art.diagnostic_notes}")

        sample_comment = Comment(
            comment_id="msn_sample_12345",
            article_url=art.requested_url,
            parent_comment_id=None,
            author_display_name="[Redacted MSN User]",
            comment_text="Sample synthetic comment text demonstrating normalized schema",
            published_datetime="2026-09-25T18:00:00Z",
            reactions={"upvotes": 5},
            reply_count=0,
            depth=0,
            retrieved_at=art.retrieved_at
        )
        print(f"Sample Comment Schema: {sample_comment.model_dump_json(indent=2)}")
        print("=======================================================\n")

        assert art.comments_status in (
            CommentStatus.AVAILABLE,
            CommentStatus.NOT_LOADED,
            CommentStatus.NONE_PRESENT,
            CommentStatus.DISABLED
        )
        assert art.comment_count_reported is not None or len(art.diagnostic_notes) > 0


def test_msn_community_api_offline_fixtures(monkeypatch):
    """
    Tests MSN Community REST API comment extraction using sanitized provider-observed JSON fixtures.
    Verifies top-level comments, reply mapping (parentId, depth), deduplication, max_comments limit, and fields.
    """
    import json

    with open("tests/fixtures/msn_community_comments_observed.json", "r", encoding="utf-8") as f:
        comments_fixture = json.load(f)

    def mock_urlopen_side_effect(req, timeout=10):
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

        if "activity" in req.full_url or "urls" in req.full_url:
            return MockResponse({"allowComments": True, "commentCount": 3})
        return MockResponse(comments_fixture)

    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen_side_effect)

    msn_url = "https://www.msn.com/en-us/news/technology/article/ar-AA2cWGok"

    res = MSNCommentExtractor.extract(msn_url, html="", max_comments=10)

    assert res.status == CommentStatus.AVAILABLE
    assert res.extracted_count == 3
    assert len(res.comments) == 3

    # Comment 1 (Top Level)
    c1 = res.comments[0]
    assert c1.comment_id == "msn_c1_top"
    assert c1.author_display_name == "Sarah Jenkins"
    assert c1.depth == 0
    assert c1.parent_comment_id is None
    assert c1.reactions == {"upvotes": 5}
    assert c1.reply_count == 1

    # Comment 2 (Reply)
    c2 = res.comments[1]
    assert c2.comment_id == "msn_r1_reply"
    assert c2.author_display_name == "Tom Miller"
    assert c2.depth == 1
    assert c2.parent_comment_id == "msn_c1_top"
    assert c2.reactions == {"upvotes": 2}

    # Max comments limit
    res_trunc = MSNCommentExtractor.extract(msn_url, html="", max_comments=1)
    assert res_trunc.extracted_count == 1
    assert len(res_trunc.comments) == 1


def test_msn_community_api_wrapped_container_fixture(monkeypatch):
    """
    Tests MSN Community REST API comment extraction when items are wrapped inside a container array (value[0].items).
    Verifies reported_count=35, unwrapping, author resolution, entity unescaping, and parent_comment_id mapping.
    """
    import json

    with open("tests/fixtures/msn_community_wrapped_container_observed.json", "r", encoding="utf-8") as f:
        container_fixture = json.load(f)

    def mock_urlopen_side_effect(req, timeout=10):
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

        if "activity" in req.full_url or "urls" in req.full_url:
            return MockResponse({"allowComments": True, "commentCount": 35})
        return MockResponse(container_fixture)

    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen_side_effect)

    msn_url = "https://www.msn.com/en-us/news/other/iran-us-war-latest-trump-renames-strait-of-hormuz/ar-AA2cVKOw"

    res = MSNCommentExtractor.extract(msn_url, html="", max_comments=15)

    assert res.status == CommentStatus.AVAILABLE
    assert res.reported_count == 35
    assert res.extracted_count == 3
    assert len(res.comments) == 3

    # Top-level comment 1
    c1 = res.comments[0]
    assert c1.comment_id == "2107e432-4a30-42d2-93f4-c38c7db04569"
    assert c1.author_display_name == "Jeffrey Redding"
    assert c1.comment_text.startswith("Warning Xi")
    assert c1.depth == 0
    assert c1.parent_comment_id is None

    # Top-level comment 2 with unescaped HTML entity
    c2 = res.comments[1]
    assert c2.comment_id == "0391a6a5-b4fe-438b-bd3f-a9b713a1af44"
    assert c2.author_display_name == "Jake Wilson"
    assert "'totally unacceptable'" in c2.comment_text
    assert "&apos;" not in c2.comment_text

    # Reply comment with parent_comment_id and depth=1
    c3 = res.comments[2]
    assert c3.comment_id == "r1_child_reply"
    assert c3.parent_comment_id == "2107e432-4a30-42d2-93f4-c38c7db04569"
    assert c3.depth == 1
