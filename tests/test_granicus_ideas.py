"""
Unit tests for GranicusIdeasAdapter (Step 30C.1).
Includes comprehensive coverage for pagination, max_comments limits, loop guards,
timestamp handling, duplicate ID filtering, mid-pagination failures, and unexplained count mismatches.
"""
import os
import pytest
from src.collectors.granicus_ideas import GranicusIdeasAdapter, parse_granicus_timestamp
from src.models import CommentStatus

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def load_fixture(filename: str) -> str:
    path = os.path.join(FIXTURES_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def test_granicus_ideas_supports():
    adapter = GranicusIdeasAdapter()
    assert adapter.supports("https://ousd.granicusideas.com/meetings/2989/agenda_items/123") is True
    assert adapter.supports("https://browardschools.granicusideas.com/meetings/618/agenda_items/456") is True
    assert adapter.supports("https://example.com/article") is False


def test_granicus_ideas_extract_ousd_multipage():
    adapter = GranicusIdeasAdapter()
    
    p1_html = load_fixture("granicus_ideas_ousd_p1.html")
    p2_html = load_fixture("granicus_ideas_ousd_p2.html")
    p3_html = load_fixture("granicus_ideas_ousd_p3.html")

    pages = {
        "https://ousd.granicusideas.com/meetings/2989/agenda_items/6a7902467d79659707005b5d": p1_html,
        "https://ousd.granicusideas.com/meetings/2989/agenda_items/6a7902467d79659707005b5d?page=2": p2_html,
        "https://ousd.granicusideas.com/meetings/2989/agenda_items/6a7902467d79659707005b5d?page=3": p3_html,
    }

    def mock_fetch(url: str) -> str:
        return pages.get(url, "")

    target_url = "https://ousd.granicusideas.com/meetings/2989/agenda_items/6a7902467d79659707005b5d"
    result = adapter.extract(target_url, html=p1_html, fetch_page_func=mock_fetch)

    assert result.success is True
    assert result.article is not None
    assert result.article.title == "Board Policy 0441 — Artificial Intelligence"
    assert result.article.original_publisher == "Oakland Unified School District"
    assert result.comments_status == CommentStatus.AVAILABLE
    assert result.article.comment_count_reported == 42
    assert result.article.comments_collected == 42
    assert len(result.article.comments) == 42

    # Verify ID deduplication and comment ordering
    assert result.article.comments[0].comment_id == "ousd-comment-1"
    assert result.article.comments[0].author_display_name == "Alice Smith"
    assert result.article.comments[0].published_datetime == "2026-08-12T10:00:00Z"
    assert result.article.comments[-1].comment_id == "ousd-comment-42"


def test_granicus_ideas_magicschool_closed_window():
    adapter = GranicusIdeasAdapter()
    html = load_fixture("granicus_ideas_magicschool.html")

    target_url = "https://browardschools.granicusideas.com/meetings/618/agenda_items/6a39c094442538fd430008ce"
    result = adapter.extract(target_url, html=html)

    assert result.success is True
    assert result.article is not None
    assert result.article.title == "Item 65: Pause Implementation of MagicSchool AI Pending Comprehensive Policy"
    assert result.article.original_publisher == "Broward County Public Schools"
    assert result.comments_status == CommentStatus.AVAILABLE
    assert result.article.comment_count_reported == 14
    assert result.article.comments_collected == 14
    assert len(result.article.comments) == 14


def test_granicus_ideas_max_comments_page1():
    adapter = GranicusIdeasAdapter()
    p1_html = load_fixture("granicus_ideas_ousd_p1.html")
    target_url = "https://ousd.granicusideas.com/meetings/2989/agenda_items/6a7902467d79659707005b5d"

    # Limit to 5 comments on page 1
    result = adapter.extract(target_url, html=p1_html, max_comments=5)

    assert result.success is True
    assert result.article.comments_collected == 5
    assert len(result.article.comments) == 5
    assert any("Reached max_comments limit" in note for note in result.diagnostic_notes)


def test_granicus_ideas_max_comments_later_page_no_extra_fetch():
    adapter = GranicusIdeasAdapter()
    p1_html = load_fixture("granicus_ideas_ousd_p1.html")
    p2_html = load_fixture("granicus_ideas_ousd_p2.html")
    p3_html = load_fixture("granicus_ideas_ousd_p3.html")

    fetched_urls = []

    def mock_fetch(url: str) -> str:
        fetched_urls.append(url)
        if "?page=2" in url:
            return p2_html
        if "?page=3" in url:
            return p3_html
        return ""

    target_url = "https://ousd.granicusideas.com/meetings/2989/agenda_items/6a7902467d79659707005b5d"
    # Limit max_comments to 25 (20 from p1, 5 from p2)
    result = adapter.extract(target_url, html=p1_html, fetch_page_func=mock_fetch, max_comments=25)

    assert result.article.comments_collected == 25
    # Page 3 should NOT have been fetched because max_comments (25) was satisfied on Page 2
    assert not any("?page=3" in u for u in fetched_urls)


def test_granicus_ideas_mid_pagination_fetch_failure():
    adapter = GranicusIdeasAdapter()
    p1_html = load_fixture("granicus_ideas_ousd_p1.html")
    target_url = "https://ousd.granicusideas.com/meetings/2989/agenda_items/6a7902467d79659707005b5d"

    def failing_fetch(url: str) -> str:
        return ""  # Network failure simulation

    result = adapter.extract(target_url, html=p1_html, fetch_page_func=failing_fetch)

    # Page 1 comments (20) should still be successfully preserved
    assert result.success is True
    assert result.article.comments_collected == 20
    assert len(result.article.comments) == 20


def test_granicus_ideas_infinite_pagination_loop_guard():
    adapter = GranicusIdeasAdapter()
    # HTML with next link pointing back to self / visited page
    loop_html = """
    <html><body>
        <h2>5 Comments</h2>
        <div class="comment-item" data-id="c1">
            <span class="author-name">User 1</span>
            <p class="comment-body">Body 1</p>
        </div>
        <div class="pagination">
            <a rel="next" href="https://ousd.granicusideas.com/item/1">Next</a>
        </div>
    </body></html>
    """
    target_url = "https://ousd.granicusideas.com/item/1"

    def mock_fetch(url: str) -> str:
        return loop_html

    result = adapter.extract(target_url, html=loop_html, fetch_page_func=mock_fetch)

    # Should exit cleanly after detecting visited URL without infinite loop
    assert result.success is True
    assert result.article.comments_collected == 1


def test_granicus_ideas_duplicate_comment_ids_across_pages():
    adapter = GranicusIdeasAdapter()
    p1_html = load_fixture("granicus_ideas_ousd_p1.html")
    # p2 repeats comment-20 from p1
    p2_dup_html = """
    <html><body>
        <div class="comment-item" data-id="ousd-comment-20">
            <span class="author-name">Duplicate User</span>
            <p class="comment-body">Duplicate Body</p>
        </div>
        <div class="comment-item" data-id="ousd-comment-21">
            <span class="author-name">User 21</span>
            <p class="comment-body">Unique Body 21</p>
        </div>
    </body></html>
    """
    target_url = "https://ousd.granicusideas.com/meetings/2989/agenda_items/6a7902467d79659707005b5d"

    def mock_fetch(url: str) -> str:
        return p2_dup_html

    result = adapter.extract(target_url, html=p1_html, fetch_page_func=mock_fetch)

    # ousd-comment-20 extracted on p1, ignored on p2 duplicate -> total 21
    assert result.article.comments_collected == 21
    comment_ids = [c.comment_id for c in result.article.comments]
    assert comment_ids.count("ousd-comment-20") == 1


def test_granicus_ideas_unexplained_count_mismatch_diagnostic():
    """
    Tests case where reported count = 42, but completed pagination yields 41 unique collected comments
    (without fetch failure or max_comments truncation).
    Verifies comments_status = AVAILABLE, comments_collected = 41, comment_count_reported = 42,
    and diagnostic_notes contains an explicit unexplained count mismatch note.
    """
    adapter = GranicusIdeasAdapter()
    p1_html = load_fixture("granicus_ideas_ousd_p1.html")  # 20 comments
    p2_html = load_fixture("granicus_ideas_ousd_p2.html")  # 20 comments
    
    # Page 3 HTML containing only 1 comment (making total collected = 41 instead of reported 42)
    p3_single_html = """
    <!DOCTYPE html>
    <html lang="en">
    <body>
        <div id="comments-section">
            <h2>42 Comments</h2>
            <div class="comments-list">
                <div class="comment-item" data-id="ousd-comment-41">
                    <span class="author-name">User 41</span>
                    <time datetime="2026-08-12T16:40:00Z">2026-08-12</time>
                    <div class="comment-body">Single final comment on page 3.</div>
                </div>
            </div>
            <div class="pagination"><span class="current">3</span></div>
        </div>
    </body>
    </html>
    """

    pages = {
        "https://ousd.granicusideas.com/meetings/2989/agenda_items/6a7902467d79659707005b5d": p1_html,
        "https://ousd.granicusideas.com/meetings/2989/agenda_items/6a7902467d79659707005b5d?page=2": p2_html,
        "https://ousd.granicusideas.com/meetings/2989/agenda_items/6a7902467d79659707005b5d?page=3": p3_single_html,
    }

    def mock_fetch(url: str) -> str:
        return pages.get(url, "")

    target_url = "https://ousd.granicusideas.com/meetings/2989/agenda_items/6a7902467d79659707005b5d"
    result = adapter.extract(target_url, html=p1_html, fetch_page_func=mock_fetch)

    assert result.success is True
    assert result.comments_status == CommentStatus.AVAILABLE
    assert result.article.comment_count_reported == 42
    assert result.article.comments_collected == 41
    assert len(result.article.comments) == 41

    # Verify diagnostic notes contain exact unexplained count mismatch note
    expected_note = "Unexplained count mismatch: reported 42, extracted 41 unique public comments."
    assert expected_note in result.diagnostic_notes


def test_granicus_ideas_absolute_timestamp_parsed_iso():
    """
    Tests parsing of real Granicus Ideas absolute timestamp string:
    'October 03, 2026 at 12:38am PDT'
    Verifies that it is normalized into ISO-8601 published_datetime value.
    """
    adapter = GranicusIdeasAdapter()
    html_abs = """
    <html><body>
        <h2>1 Comment</h2>
        <div class="comment-item" data-id="c200">
            <span class="author-name">User Absolute</span>
            <time>October 03, 2026 at 12:38am PDT</time>
            <p class="comment-body">Absolute date comment body</p>
        </div>
    </body></html>
    """
    target_url = "https://ousd.granicusideas.com/item/200"
    result = adapter.extract(target_url, html=html_abs)

    assert result.article.comments[0].published_datetime == "2026-10-03T00:38:00-07:00"


def test_granicus_ideas_relative_timestamp_parsed_none():
    adapter = GranicusIdeasAdapter()
    html_rel = """
    <html><body>
        <h2>1 Comment</h2>
        <div class="comment-item" data-id="c100">
            <span class="author-name">User Rel</span>
            <time>3 months ago</time>
            <p class="comment-body">Relative date body</p>
        </div>
    </body></html>
    """
    target_url = "https://ousd.granicusideas.com/item/100"
    result = adapter.extract(target_url, html=html_rel)

    assert result.article.comments[0].published_datetime is None
