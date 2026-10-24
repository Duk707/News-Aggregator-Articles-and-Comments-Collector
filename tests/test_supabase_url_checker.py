"""
tests/test_supabase_url_checker.py

Offline unit tests for SupabaseUrlChecker (Gate 3B.1).
Uses strictly mocked SupabaseClient responses. Zero live database or network access.

Verification Coverage:
1. Invalid input and unsupported URL schemes (rejected to empty string).
2. Missing hostname (rejected to empty string).
3. Malformed URL after Bing redirect unwrapping (rejected to empty string).
4. Missing 'url' field in a Supabase record (MALFORMED_RESPONSE).
5. Non-string, non-null 'url' field (MALFORMED_RESPONSE).
6. Malformed response occurring after one or more successful pages (MALFORMED_RESPONSE, not complete).
7. Meaningful trailing-slash preservation (/story vs /story/).
8. Root URL path handling.
9. Tracking-only query parameter differences.
10. Host capitalization vs meaningful path capitalization.
11. Empty articles table (EMPTY status, verified accessible).
12. Single-page URL retrieval (< page_size).
13. Multiple pages containing more than 1,000 records.
14. Exact page-size boundaries.
15. Server-side page-size limits or shortened responses.
16. Null and empty URL fields skipped gracefully.
17. Unauthorized responses (401/403).
18. Network and server errors (connection drop, 500).
19. Incomplete pagination and non-advancing cursor safety checks.
20. Confirmation that NO write operations (POST, PATCH, DELETE) occur.
"""

from unittest.mock import MagicMock
import pytest
import requests

from src.integrations.supabase.client import SupabaseClient
from src.integrations.supabase.url_checker import (
    StoredUrlRecord,
    SupabaseUrlChecker,
    UrlCheckerSnapshot,
    UrlRetrievalStatus,
    canonicalize_url_key
)


# ==============================================================================
# URL Canonicalization Tests (Corrections 1 & 2)
# ==============================================================================

def test_canonicalize_url_key_invalid_inputs():
    """Verify malformed, non-HTTP, and non-absolute URLs are rejected to empty key."""
    assert canonicalize_url_key("not a url") == ""
    assert canonicalize_url_key("https://") == ""
    assert canonicalize_url_key("http://") == ""
    assert canonicalize_url_key("ftp://example.com/story") == ""
    assert canonicalize_url_key("file:///local/path") == ""
    assert canonicalize_url_key("https:///missing-host/path") == ""
    assert canonicalize_url_key("https://?only=query") == ""
    assert canonicalize_url_key("") == ""
    assert canonicalize_url_key("   ") == ""
    assert canonicalize_url_key(None) == ""


def test_canonicalize_url_key_bing_wrapper_unwrapping():
    """Verify Bing apiclick.aspx redirect unwrapping, rejecting malformed targets."""
    valid_wrap = "https://www.bing.com/news/apiclick.aspx?url=https%3A%2F%2Fnews.yahoo.com%2Fstory-99.html%3Futm_source%3Dfeed"
    assert canonicalize_url_key(valid_wrap) == "https://news.yahoo.com/story-99.html"

    # Bing redirect unwrapping with malformed target must return empty string
    invalid_wrap = "https://www.bing.com/news/apiclick.aspx?url=not_a_valid_url"
    assert canonicalize_url_key(invalid_wrap) == ""

    missing_host_wrap = "https://www.bing.com/news/apiclick.aspx?url=https%3A%2F%2F"
    assert canonicalize_url_key(missing_host_wrap) == ""


def test_canonicalize_url_key_trailing_slash_preservation():
    """Correction 2: Verify /story and /story/ remain distinguishable."""
    k_no_slash = canonicalize_url_key("https://news.yahoo.com/story")
    k_with_slash = canonicalize_url_key("https://news.yahoo.com/story/")

    assert k_no_slash == "https://news.yahoo.com/story"
    assert k_with_slash == "https://news.yahoo.com/story/"
    assert k_no_slash != k_with_slash


def test_canonicalize_url_key_root_path_handling():
    """Verify root URL paths are handled cleanly."""
    assert canonicalize_url_key("https://news.yahoo.com/") == "https://news.yahoo.com/"
    assert canonicalize_url_key("https://news.yahoo.com") == "https://news.yahoo.com"
    assert canonicalize_url_key("http://Example.Com:80/") == "http://example.com/"
    assert canonicalize_url_key("https://Example.Com:443/path") == "https://example.com/path"


def test_canonicalize_url_key_tracking_differences_still_match():
    """Verify tracking parameters are stripped so tracking-only variants match."""
    k_clean = canonicalize_url_key("https://news.yahoo.com/story-123.html")
    k_dirty1 = canonicalize_url_key("https://news.yahoo.com/story-123.html?utm_source=twitter&utm_medium=social")
    k_dirty2 = canonicalize_url_key("https://news.yahoo.com/story-123.html?ncid=123&gclid=xyz")

    assert k_clean == "https://news.yahoo.com/story-123.html"
    assert k_clean == k_dirty1
    assert k_clean == k_dirty2

    # Functional query parameters preserved and sorted deterministically
    raw_func1 = "https://www.msn.com/article?b=2&a=1&utm_campaign=daily"
    raw_func2 = "https://www.msn.com/article?a=1&b=2"
    assert canonicalize_url_key(raw_func1) == canonicalize_url_key(raw_func2)
    assert canonicalize_url_key(raw_func1) == "https://www.msn.com/article?a=1&b=2"


def test_canonicalize_url_key_host_vs_path_case_sensitivity():
    """Verify host capitalization does not affect matching, but path capitalization does."""
    k_lower_host = canonicalize_url_key("https://news.yahoo.com/Story-ABC")
    k_upper_host = canonicalize_url_key("https://NEWS.YAHOO.COM/Story-ABC")
    k_lower_path = canonicalize_url_key("https://news.yahoo.com/story-abc")

    # Host capitalization normalized
    assert k_lower_host == k_upper_host
    # Path capitalization preserved
    assert k_lower_host != k_lower_path


# ==============================================================================
# Supabase Response Validation Tests (Strengthened Error Checking)
# ==============================================================================

def test_missing_url_field_returns_malformed_response():
    """Verify record missing the explicitly requested 'url' field causes MALFORMED_RESPONSE."""
    mock_client = MagicMock(spec=SupabaseClient)
    mock_client.get.return_value = (200, [
        {"id": 1, "title": "Article missing URL"}
    ])

    checker = SupabaseUrlChecker(client=mock_client)
    snapshot = checker.fetch_accessible_snapshot()

    assert snapshot.status == UrlRetrievalStatus.MALFORMED_RESPONSE
    assert snapshot.is_verified_accessible is False
    assert "Missing explicitly requested 'url' field" in snapshot.error_message


def test_non_string_non_null_url_returns_malformed_response():
    """Verify non-string and non-null url value causes MALFORMED_RESPONSE."""
    mock_client = MagicMock(spec=SupabaseClient)
    mock_client.get.return_value = (200, [
        {"id": 1, "url": 12345}  # Integer instead of string
    ])

    checker = SupabaseUrlChecker(client=mock_client)
    snapshot = checker.fetch_accessible_snapshot()

    assert snapshot.status == UrlRetrievalStatus.MALFORMED_RESPONSE
    assert snapshot.is_verified_accessible is False
    assert "Expected string or null for 'url'" in snapshot.error_message


def test_malformed_response_on_later_page_not_treated_as_complete():
    """Verify error on page 2 aborts and is NOT treated as complete even if page 1 succeeded."""
    mock_client = MagicMock(spec=SupabaseClient)
    page_1 = [{"id": i, "url": f"https://news.yahoo.com/story-{i}"} for i in range(1, 11)]
    page_2_bad = [{"id": 11}]  # Missing 'url' field

    mock_client.get.side_effect = [
        (200, page_1),
        (200, page_2_bad)
    ]

    checker = SupabaseUrlChecker(client=mock_client, page_size=10)
    snapshot = checker.fetch_accessible_snapshot()

    assert snapshot.status == UrlRetrievalStatus.MALFORMED_RESPONSE
    assert snapshot.is_verified_accessible is False
    assert "Missing explicitly requested 'url' field" in snapshot.error_message


# ==============================================================================
# Keyset Pagination & Normal Retrieval Tests
# ==============================================================================

def test_empty_articles_table():
    """Requirement: Empty table returns EMPTY status and is verified accessible."""
    mock_client = MagicMock(spec=SupabaseClient)
    mock_client.get.return_value = (200, [])

    checker = SupabaseUrlChecker(client=mock_client, page_size=1000)
    snapshot = checker.fetch_accessible_snapshot()

    assert snapshot.status == UrlRetrievalStatus.EMPTY
    assert snapshot.is_verified_accessible is True
    assert snapshot.total_records_read == 0
    assert snapshot.valid_urls_loaded == 0
    assert snapshot.null_or_empty_urls_skipped == 0
    assert snapshot.is_duplicate("https://news.yahoo.com/any.html") is False
    assert mock_client.get.call_count == 1


def test_single_page_url_retrieval():
    """Single-page URL retrieval (< page_size) with trailing slash and duplicate checking."""
    mock_client = MagicMock(spec=SupabaseClient)
    mock_client.get.side_effect = [
        (200, [
            {"id": 10, "url": "https://news.yahoo.com/story-1.html"},
            {"id": 20, "url": "https://www.msn.com/story-2/"}
        ]),
        (200, [])
    ]

    checker = SupabaseUrlChecker(client=mock_client, page_size=1000)
    snapshot = checker.fetch_accessible_snapshot()

    assert snapshot.status == UrlRetrievalStatus.COMPLETE
    assert snapshot.is_verified_accessible is True
    assert snapshot.total_records_read == 2
    assert snapshot.valid_urls_loaded == 2
    assert snapshot.pages_fetched == 1

    # Exact matching
    assert snapshot.is_duplicate("https://news.yahoo.com/story-1.html") is True
    assert snapshot.is_duplicate("https://NEWS.YAHOO.COM/story-1.html?utm_source=rss") is True
    assert snapshot.is_duplicate("https://www.msn.com/story-2/") is True

    # Trailing slash distinction preserved
    assert snapshot.is_duplicate("https://www.msn.com/story-2") is False
    assert snapshot.is_duplicate("https://news.yahoo.com/not-present.html") is False

    match = snapshot.get_match("https://news.yahoo.com/story-1.html")
    assert match is not None
    assert match.id == 10
    assert match.original_url == "https://news.yahoo.com/story-1.html"


def test_multiple_pages_over_1000_records():
    """Multiple pages containing more than 1,000 records using keyset pagination."""
    mock_client = MagicMock(spec=SupabaseClient)

    page_1 = [{"id": i, "url": f"https://news.yahoo.com/story-{i}.html"} for i in range(1, 1001)]
    page_2 = [{"id": i, "url": f"https://www.msn.com/story-{i}.html"} for i in range(1001, 1501)]
    page_3 = []

    mock_client.get.side_effect = [
        (200, page_1),
        (200, page_2),
        (200, page_3)
    ]

    checker = SupabaseUrlChecker(client=mock_client, page_size=1000)
    snapshot = checker.fetch_accessible_snapshot()

    assert snapshot.status == UrlRetrievalStatus.COMPLETE
    assert snapshot.is_verified_accessible is True
    assert snapshot.total_records_read == 1500
    assert snapshot.valid_urls_loaded == 1500
    assert snapshot.pages_fetched == 2

    # Keyset query parameter assertions
    calls = mock_client.get.call_args_list
    assert len(calls) == 3
    assert "id" not in calls[0][1]["params"]
    assert calls[1][1]["params"]["id"] == "gt.1000"
    assert calls[2][1]["params"]["id"] == "gt.1500"

    assert snapshot.is_duplicate("https://news.yahoo.com/story-1.html") is True
    assert snapshot.is_duplicate("https://news.yahoo.com/story-1000.html") is True
    assert snapshot.is_duplicate("https://www.msn.com/story-1001.html") is True
    assert snapshot.is_duplicate("https://www.msn.com/story-1500.html") is True
    assert snapshot.is_duplicate("https://www.msn.com/story-1501.html") is False


def test_exact_page_size_boundary():
    """Exact page-size boundaries (e.g. exactly 1,000 records)."""
    mock_client = MagicMock(spec=SupabaseClient)
    page_1 = [{"id": i, "url": f"https://news.yahoo.com/story-{i}.html"} for i in range(1, 1001)]
    page_2 = []

    mock_client.get.side_effect = [
        (200, page_1),
        (200, page_2)
    ]

    checker = SupabaseUrlChecker(client=mock_client, page_size=1000)
    snapshot = checker.fetch_accessible_snapshot()

    assert snapshot.status == UrlRetrievalStatus.COMPLETE
    assert snapshot.is_verified_accessible is True
    assert snapshot.total_records_read == 1000
    assert snapshot.valid_urls_loaded == 1000
    assert snapshot.pages_fetched == 1


def test_server_side_page_size_limits_shortened_responses():
    """
    Server-side page-size caps (e.g., client requests 1000, server caps at 50).
    The keyset pagination continues across all shortened batches until empty.
    """
    mock_client = MagicMock(spec=SupabaseClient)

    p1 = [{"id": i, "url": f"https://news.yahoo.com/art-{i}.html"} for i in range(1, 51)]
    p2 = [{"id": i, "url": f"https://news.yahoo.com/art-{i}.html"} for i in range(51, 101)]
    p3 = [{"id": i, "url": f"https://news.yahoo.com/art-{i}.html"} for i in range(101, 126)]
    p4 = []

    mock_client.get.side_effect = [
        (200, p1),
        (200, p2),
        (200, p3),
        (200, p4)
    ]

    checker = SupabaseUrlChecker(client=mock_client, page_size=1000)
    snapshot = checker.fetch_accessible_snapshot()

    assert snapshot.status == UrlRetrievalStatus.COMPLETE
    assert snapshot.is_verified_accessible is True
    assert snapshot.total_records_read == 125
    assert snapshot.valid_urls_loaded == 125
    assert snapshot.pages_fetched == 3
    assert mock_client.get.call_count == 4


def test_null_and_empty_url_fields_skipped():
    """Null, empty, and invalid URL strings in DB are skipped gracefully without error."""
    mock_client = MagicMock(spec=SupabaseClient)
    mock_client.get.side_effect = [
        (200, [
            {"id": 1, "url": None},
            {"id": 2, "url": ""},
            {"id": 3, "url": "   "},
            {"id": 4, "url": "not a url"},
            {"id": 5, "url": "https://news.yahoo.com/valid-story.html"},
            {"id": 6, "url": "https://"}
        ]),
        (200, [])
    ]

    checker = SupabaseUrlChecker(client=mock_client, page_size=1000)
    snapshot = checker.fetch_accessible_snapshot()

    assert snapshot.status == UrlRetrievalStatus.COMPLETE
    assert snapshot.is_verified_accessible is True
    assert snapshot.total_records_read == 6
    assert snapshot.null_or_empty_urls_skipped == 5
    assert snapshot.valid_urls_loaded == 1
    assert snapshot.is_duplicate("https://news.yahoo.com/valid-story.html") is True


def test_unauthorized_responses_401_403():
    """Unauthorized responses (401/403) return AUTH_ERROR."""
    mock_client = MagicMock(spec=SupabaseClient)

    # 401 Unauthorized
    mock_client.get.return_value = (401, {"message": "Invalid API key"})
    checker = SupabaseUrlChecker(client=mock_client)
    snap401 = checker.fetch_accessible_snapshot()
    assert snap401.status == UrlRetrievalStatus.AUTH_ERROR
    assert snap401.is_verified_accessible is False
    assert "Access denied" in snap401.error_message

    # 403 Forbidden
    mock_client.get.return_value = (403, {"message": "RLS policy restricts access"})
    snap403 = checker.fetch_accessible_snapshot()
    assert snap403.status == UrlRetrievalStatus.AUTH_ERROR
    assert snap403.is_verified_accessible is False


def test_network_and_server_errors():
    """Network exceptions and HTTP 500 errors."""
    mock_client = MagicMock(spec=SupabaseClient)

    # Network Exception
    mock_client.get.side_effect = requests.exceptions.ConnectTimeout("Connection timed out")
    checker = SupabaseUrlChecker(client=mock_client)
    snap_net = checker.fetch_accessible_snapshot()
    assert snap_net.status == UrlRetrievalStatus.NETWORK_ERROR
    assert snap_net.is_verified_accessible is False
    assert "Network exception" in snap_net.error_message

    # HTTP 500
    mock_client.get.side_effect = None
    mock_client.get.return_value = (500, "Internal Server Error")
    snap_http = checker.fetch_accessible_snapshot()
    assert snap_http.status == UrlRetrievalStatus.HTTP_ERROR
    assert snap_http.is_verified_accessible is False
    assert "HTTP 500" in snap_http.error_message


def test_incomplete_pagination_and_non_advancing_cursor():
    """Incomplete pagination and non-advancing cursor safety stops."""
    mock_client = MagicMock(spec=SupabaseClient)

    # Non-advancing cursor (server returns duplicate or smaller ID)
    mock_client.get.side_effect = [
        (200, [{"id": 10, "url": "https://news.yahoo.com/story-10.html"}]),
        (200, [{"id": 10, "url": "https://news.yahoo.com/story-10-duplicate.html"}])
    ]
    checker = SupabaseUrlChecker(client=mock_client, page_size=10)
    snap_cursor = checker.fetch_accessible_snapshot()
    assert snap_cursor.status == UrlRetrievalStatus.INCOMPLETE_PAGINATION
    assert snap_cursor.is_verified_accessible is False
    assert "failed to advance" in snap_cursor.error_message

    # Safety limit exceeded (max_pages reached)
    mock_client.get.side_effect = [
        (200, [{"id": 1, "url": "https://news.yahoo.com/1"}]),
        (200, [{"id": 2, "url": "https://news.yahoo.com/2"}]),
        (200, [{"id": 3, "url": "https://news.yahoo.com/3"}])
    ]
    checker_limit = SupabaseUrlChecker(client=mock_client, page_size=1, max_pages=2)
    snap_limit = checker_limit.fetch_accessible_snapshot()
    assert snap_limit.status == UrlRetrievalStatus.INCOMPLETE_PAGINATION
    assert snap_limit.is_verified_accessible is False
    assert "Reached safety limit of 2 pages" in snap_limit.error_message


def test_zero_write_operations_performed():
    """Confirmation that NO write requests occur."""
    mock_client = MagicMock(spec=SupabaseClient)
    mock_client.get.return_value = (200, [])

    checker = SupabaseUrlChecker(client=mock_client)
    checker.fetch_accessible_snapshot()

    # Assert get was called for articles table
    assert mock_client.get.call_count == 1
    call_args = mock_client.get.call_args
    assert call_args[0][0] == "articles"
    assert call_args[1]["params"]["select"] == "id,url"

    # Assert write methods were never called
    if hasattr(mock_client, "post"):
        assert mock_client.post.call_count == 0
    if hasattr(mock_client, "put"):
        assert mock_client.put.call_count == 0
    if hasattr(mock_client, "delete"):
        assert mock_client.delete.call_count == 0
    if hasattr(mock_client, "patch"):
        assert mock_client.patch.call_count == 0
