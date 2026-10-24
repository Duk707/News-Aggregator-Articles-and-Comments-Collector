"""
tests/test_probe_bing_rss_pagination.py

Offline unit tests for scripts/probe_bing_rss_pagination.py.
Verifies:
1. Exact outbound query string formulation (matching production baseline).
2. Explicit rejection of unsupported query/mode configurations.
3. Global abort behavior on HTTP 403, HTTP 429, and network exceptions (MSN never called).
4. XML / RSS response validation (distinguishing valid empty RSS from malformed XML and HTML).
5. Offset sequencing, deduplication, keyword filtering, and Phase 1 vs Phase 2 reporting.

ALL TESTS ARE STRICTLY OFFLINE (NO LIVE NETWORK REQUESTS).
"""

import pytest
from unittest.mock import MagicMock

from scripts.probe_bing_rss_pagination import (
    PAGE_OFFSETS,
    MAX_REQUEST_BUDGET,
    PageProbeResult,
    PhaseProbeSummary,
    ProbeConfig,
    ProbeRunState,
    SourceProbeResult,
    build_phase_summary,
    build_probe_query,
    format_page_table,
    format_phase_comparison,
    print_full_report,
    probe_source,
    run_probe,
)
from src.discovery.search import CandidateDiscoverer


def make_mock_rss_xml(items: list) -> str:
    """Helper to generate valid RSS XML string containing items."""
    xml_items = []
    for it in items:
        title = it.get("title", "Article Title")
        link = it.get("link", "https://news.yahoo.com/article-123.html")
        desc = it.get("desc", "AI in education article snippet")
        pub = it.get("pubDate", "Mon, 15 Jan 2024 12:00:00 GMT")
        xml_items.append(f"""
        <item>
            <title>{title}</title>
            <link>{link}</link>
            <description>{desc}</description>
            <pubDate>{pub}</pubDate>
        </item>
        """)
    return f"""<?xml version="1.0" encoding="utf-8"?>
    <rss version="2.0">
        <channel>
            <title>Bing News Search</title>
            {''.join(xml_items)}
        </channel>
    </rss>
    """


# ==============================================================================
# ISSUE 1 TESTS: Query construction matching production
# ==============================================================================

def test_baseline_outbound_query_strings():
    """
    Assert exact outbound query strings for verified baseline:
    - Discovery Search Query: blank
    - Include Keywords: AI, education
    - Include mode: ALL
    Matches production queries:
    - 'AI education site:yahoo.com'
    - 'AI education site:msn.com'
    """
    captured_queries = []

    def mock_fetcher(url: str, params: dict):
        captured_queries.append(params.get("q"))
        return 200, make_mock_rss_xml([])

    config = ProbeConfig(
        live=False,
        max_pages=1,
        query="",
        keywords=["AI", "education"],
        keyword_mode="ALL",
        sources=["yahoo", "msn"]
    )
    run_probe(config, fetcher=mock_fetcher)

    assert len(captured_queries) == 2
    assert captured_queries[0] == "AI education site:yahoo.com"
    assert captured_queries[1] == "AI education site:msn.com"


def test_custom_query_outbound_query_strings():
    """Verify that when a non-blank search query is provided, it precedes the site: term."""
    q_yahoo = build_probe_query("AI in Education", "site:yahoo.com", ["AI", "education"], "ALL")
    q_msn = build_probe_query("AI in Education", "site:msn.com", ["AI", "education"], "ALL")
    assert q_yahoo == "AI in Education site:yahoo.com"
    assert q_msn == "AI in Education site:msn.com"


def test_blank_query_any_mode_rejected_with_explanation():
    """
    Verify that blank query with keyword mode 'ANY' is explicitly rejected
    to protect the 20-request budget isolation.
    """
    with pytest.raises(ValueError) as excinfo:
        build_probe_query(
            query="",
            site_query="site:yahoo.com",
            keywords=["AI", "education"],
            keyword_mode="ANY"
        )
    assert "Unsupported configuration" in str(excinfo.value)
    assert "ANY" in str(excinfo.value)


def test_empty_query_and_keywords_rejected():
    """Verify ValueError is raised if both query and keywords are missing."""
    with pytest.raises(ValueError) as excinfo:
        build_probe_query(query="", site_query="site:yahoo.com", keywords=[], keyword_mode="ALL")
    assert "Both search query and include keywords are empty" in str(excinfo.value)


# ==============================================================================
# ISSUE 2 TESTS: Global abort behavior on HTTP 403, 429, network exceptions
# ==============================================================================

def test_global_abort_on_http_429_prevents_subsequent_requests_and_sources():
    """
    Verify that if Yahoo encounters HTTP 429, ALL subsequent requests are prevented,
    and MSN is NEVER requested.
    """
    requested_sources = []

    def mock_fetcher(url: str, params: dict):
        q = params.get("q", "")
        requested_sources.append(q)
        return 429, "Too Many Requests"

    config = ProbeConfig(live=False, max_pages=5, sources=["yahoo", "msn"])
    results = run_probe(config, fetcher=mock_fetcher)

    # Exactly 1 request made across entire experiment
    assert len(requested_sources) == 1
    assert "site:yahoo.com" in requested_sources[0]
    assert not any("site:msn.com" in q for q in requested_sources)

    yahoo_res = results["yahoo"]
    msn_res = results["msn"]

    assert yahoo_res.termination_reason == "http_429_blocked"
    assert len(yahoo_res.pages) == 1
    assert yahoo_res.pages[0].status_code == 429

    assert msn_res.termination_reason == "global_abort_http_429_blocked"
    assert len(msn_res.pages) == 0
    assert "Run aborted globally" in msn_res.error


def test_global_abort_on_http_403_prevents_subsequent_sources():
    """Verify that if Yahoo encounters HTTP 403, MSN is NEVER requested."""
    requested_sources = []

    def mock_fetcher(url: str, params: dict):
        requested_sources.append(params.get("q", ""))
        return 403, "Access Denied"

    config = ProbeConfig(live=False, max_pages=5, sources=["yahoo", "msn"])
    results = run_probe(config, fetcher=mock_fetcher)

    assert len(requested_sources) == 1
    assert "site:yahoo.com" in requested_sources[0]
    assert not any("site:msn.com" in q for q in requested_sources)

    assert results["yahoo"].termination_reason == "http_403_blocked"
    assert results["msn"].termination_reason == "global_abort_http_403_blocked"
    assert len(results["msn"].pages) == 0


def test_global_abort_on_network_exception_prevents_subsequent_sources():
    """Verify that network exception on Yahoo globally aborts and MSN is NEVER requested."""
    call_count = 0

    def mock_fetcher(url: str, params: dict):
        nonlocal call_count
        call_count += 1
        raise ConnectionResetError("Connection dropped by remote host")

    config = ProbeConfig(live=False, max_pages=5, sources=["yahoo", "msn"])
    results = run_probe(config, fetcher=mock_fetcher)

    assert call_count == 1
    assert results["yahoo"].termination_reason == "network_error"
    assert results["msn"].termination_reason == "global_abort_network_error"
    assert len(results["msn"].pages) == 0


# ==============================================================================
# ISSUE 3 TESTS: XML / RSS Response Validation
# ==============================================================================

def test_valid_empty_rss_distinguished_from_errors():
    """
    Verify valid RSS response with 0 items is treated as a valid zero-yield response,
    NOT an error, and does NOT trigger global abort.
    """
    call_count = 0

    def mock_fetcher(url: str, params: dict):
        nonlocal call_count
        call_count += 1
        # Valid empty RSS channel
        xml = """<?xml version="1.0" encoding="utf-8"?>
        <rss version="2.0">
            <channel>
                <title>Bing News Search</title>
                <link>https://www.bing.com/news</link>
                <description>Empty search results</description>
            </channel>
        </rss>
        """
        return 200, xml

    config = ProbeConfig(live=False, max_pages=2, sources=["yahoo", "msn"])
    results = run_probe(config, fetcher=mock_fetcher)

    yahoo = results["yahoo"]
    assert len(yahoo.pages) == 2
    for p in yahoo.pages:
        assert p.status_code == 200
        assert p.raw_items == 0
        assert p.new_unique == 0
        assert p.error is None
    assert yahoo.termination_reason == "completed"

    msn = results["msn"]
    assert len(msn.pages) == 2
    assert msn.termination_reason == "completed"


def test_malformed_xml_detected_and_not_treated_as_zero_yield():
    """
    Verify that malformed/truncated XML is explicitly recorded as an error,
    triggers global abort, and is NOT reported as a valid zero-yield page.
    """
    call_count = 0

    def mock_fetcher(url: str, params: dict):
        nonlocal call_count
        call_count += 1
        return 200, "<?xml version='1.0'?><rss><channel><item><title>Truncated unclosed XML"

    config = ProbeConfig(live=False, max_pages=5, sources=["yahoo", "msn"])
    results = run_probe(config, fetcher=mock_fetcher)

    assert call_count == 1
    yahoo = results["yahoo"]
    assert len(yahoo.pages) == 1
    assert "Malformed XML response" in yahoo.pages[0].error
    assert yahoo.termination_reason == "malformed_xml"
    assert yahoo.pages[0].raw_items == 0

    # MSN was aborted globally
    assert results["msn"].termination_reason == "global_abort_malformed_xml"
    assert len(results["msn"].pages) == 0


def test_unexpected_html_response_detected_and_aborts_run():
    """
    Verify that unexpected HTML (e.g. Cloudflare / Bot challenge with HTTP 200)
    is recorded as unexpected_html_response, not zero yield, and triggers global abort.
    """
    call_count = 0

    def mock_fetcher(url: str, params: dict):
        nonlocal call_count
        call_count += 1
        html_body = """<!DOCTYPE html>
        <html lang="en">
        <head><title>Verify you are human</title></head>
        <body><div id="challenge">Please solve the challenge to proceed</div></body>
        </html>
        """
        return 200, html_body

    config = ProbeConfig(live=False, max_pages=5, sources=["yahoo", "msn"])
    results = run_probe(config, fetcher=mock_fetcher)

    assert call_count == 1
    yahoo = results["yahoo"]
    assert len(yahoo.pages) == 1
    assert "Unexpected HTML response" in yahoo.pages[0].error
    assert yahoo.termination_reason == "unexpected_html_response"

    assert results["msn"].termination_reason == "global_abort_unexpected_html_response"
    assert len(results["msn"].pages) == 0


# ==============================================================================
# EXISTING PAGINATION & ACCOUNTING TESTS
# ==============================================================================

def test_probe_config_defaults():
    config = ProbeConfig()
    assert config.live is False
    assert config.delay_sec >= 2.0
    assert config.max_pages == 10
    assert config.keywords == ["AI", "education"]
    assert config.keyword_mode == "ALL"
    assert config.sources == ["yahoo", "msn"]


def test_dry_run_safety_no_fetcher():
    """Verify that when live is False and no fetcher is supplied, zero requests are made."""
    config = ProbeConfig(live=False)
    results = run_probe(config, fetcher=None)
    assert "yahoo" in results
    assert "msn" in results
    for src_res in results.values():
        for page in src_res.pages:
            assert page.error == "Dry-run mode (no HTTP request made)"
            assert page.raw_items == 0
            assert page.new_unique == 0


def test_offset_progression_up_to_10_pages():
    """Verify that probe calls offsets [1, 11, 21, ..., 91] in exact sequential order."""
    requested_offsets = []

    def mock_fetcher(url: str, params: dict):
        requested_offsets.append(params.get("first"))
        off = params.get("first")
        xml = make_mock_rss_xml([{
            "title": f"AI in education breakthrough offset {off}",
            "link": f"https://news.yahoo.com/story-offset-{off}.html",
            "desc": "AI is transforming education"
        }])
        return 200, xml

    config = ProbeConfig(live=False, max_pages=10, sources=["yahoo"])
    results = run_probe(config, fetcher=mock_fetcher)

    assert requested_offsets == PAGE_OFFSETS
    assert len(requested_offsets) == 10
    yahoo_res = results["yahoo"]
    assert len(yahoo_res.pages) == 10
    for idx, page in enumerate(yahoo_res.pages):
        assert page.page_num == idx + 1
        assert page.offset == PAGE_OFFSETS[idx]
        assert page.status_code == 200
        assert page.new_unique == 1
        assert page.cumulative_unique == idx + 1


def test_phase1_vs_phase2_yield_accounting():
    """
    Verify that Pages 1-5 (Phase 1) and Pages 6-10 (Phase 2) are properly partitioned,
    accounting for duplicates and new unique yield.
    """
    def mock_fetcher(url: str, params: dict):
        off = params.get("first")
        if off <= 41:
            items = [
                {
                    "title": f"AI and education story A at offset {off}",
                    "link": f"https://news.yahoo.com/story-a-{off}.html",
                    "desc": "AI and education"
                },
                {
                    "title": f"AI and education story B at offset {off}",
                    "link": f"https://news.yahoo.com/story-b-{off}.html",
                    "desc": "AI and education"
                }
            ]
        else:
            items = [
                {
                    "title": f"AI and education story C at offset {off}",
                    "link": f"https://news.yahoo.com/story-c-{off}.html",
                    "desc": "AI and education"
                },
                {
                    "title": "Repeated AI and education story from page 1",
                    "link": "https://news.yahoo.com/story-a-1.html",
                    "desc": "AI and education"
                }
            ]
        return 200, make_mock_rss_xml(items)

    config = ProbeConfig(live=False, max_pages=10, sources=["yahoo"])
    results = run_probe(config, fetcher=mock_fetcher)
    yahoo = results["yahoo"]

    assert yahoo.phase1 is not None
    assert yahoo.phase2 is not None

    # Phase 1: 5 pages * 2 items = 10 unique items
    assert yahoo.phase1.requests_attempted == 5
    assert yahoo.phase1.successful_requests == 5
    assert yahoo.phase1.raw_items == 10
    assert yahoo.phase1.new_unique == 10
    assert yahoo.phase1.repeats == 0
    assert yahoo.phase1.cumulative_unique_end == 10

    # Phase 2: 5 pages * 1 new item = 5 new unique items, 5 repeats
    assert yahoo.phase2.requests_attempted == 5
    assert yahoo.phase2.successful_requests == 5
    assert yahoo.phase2.raw_items == 10
    assert yahoo.phase2.new_unique == 5
    assert yahoo.phase2.repeats == 5
    assert yahoo.phase2.cumulative_unique_end == 15

    assert yahoo.total_unique == 15


def test_keyword_and_unsupported_url_rejections():
    """Verify that keyword filtering and invalid URL rejections are tallied accurately."""
    def mock_fetcher(url: str, params: dict):
        items = [
            # 1. Valid: matches AI and education, supported Yahoo
            {
                "title": "AI in education future",
                "link": "https://news.yahoo.com/valid-story.html",
                "desc": "technology in school"
            },
            # 2. Rejection: missing 'education' keyword (mode ALL)
            {
                "title": "AI in finance and banking",
                "link": "https://news.yahoo.com/finance-story.html",
                "desc": "wall street tech"
            },
            # 3. Rejection: unsupported non-Yahoo domain
            {
                "title": "AI in education from external site",
                "link": "https://unknownsite.org/external-story.html",
                "desc": "learning algorithms"
            }
        ]
        return 200, make_mock_rss_xml(items)

    config = ProbeConfig(live=False, max_pages=1, sources=["yahoo"])
    results = run_probe(config, fetcher=mock_fetcher)
    page1 = results["yahoo"].pages[0]

    assert page1.raw_items == 3
    assert page1.new_unique == 1
    assert page1.rejected_keywords == 1
    assert page1.rejected_unsupported == 1
    assert page1.repeats == 0


def test_stop_on_zero_items_flag():
    """Verify that when stop_on_zero_items is True, probe halts on empty RSS response."""
    call_count = 0

    def mock_fetcher(url: str, params: dict):
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            return 200, make_mock_rss_xml([{
                "title": f"AI in education {call_count}",
                "link": f"https://news.yahoo.com/story-{call_count}.html",
                "desc": "AI in education"
            }])
        return 200, make_mock_rss_xml([])

    config = ProbeConfig(live=False, max_pages=10, sources=["yahoo"], stop_on_zero_items=True)
    results = run_probe(config, fetcher=mock_fetcher)
    yahoo = results["yahoo"]

    assert call_count == 3
    assert yahoo.termination_reason == "zero_raw_items"
    assert len(yahoo.pages) == 3


def test_max_request_budget_enforced():
    """Verify total requests across all sources never exceeds MAX_REQUEST_BUDGET."""
    call_count = 0

    def mock_fetcher(url: str, params: dict):
        nonlocal call_count
        call_count += 1
        return 200, make_mock_rss_xml([])

    config = ProbeConfig(live=False, max_pages=10, sources=["yahoo", "msn"])
    results = run_probe(config, fetcher=mock_fetcher)

    assert call_count <= MAX_REQUEST_BUDGET


def test_report_formatting_smoke():
    """Verify formatting functions generate text without crashing."""
    p1 = PageProbeResult(
        page_num=1,
        offset=1,
        status_code=200,
        raw_items=10,
        new_unique=8,
        repeats=1,
        rejected_unsupported=1,
        rejected_keywords=0,
        cumulative_unique=8,
        platform_breakdown={"Yahoo News": 8}
    )
    p6 = PageProbeResult(
        page_num=6,
        offset=51,
        status_code=200,
        raw_items=10,
        new_unique=4,
        repeats=5,
        rejected_unsupported=1,
        rejected_keywords=0,
        cumulative_unique=12,
        platform_breakdown={"Yahoo News": 4}
    )
    src_res = SourceProbeResult(
        source_name="Yahoo News",
        site_query="site:yahoo.com",
        pages=[p1, p6],
        phase1=build_phase_summary("Phase 1", "Pages 1-5", [p1]),
        phase2=build_phase_summary("Phase 2", "Pages 6-10", [p6]),
        total_unique=12,
        termination_reason="completed"
    )

    tbl_text = format_page_table(src_res)
    assert "Yahoo News" in tbl_text
    assert "Offset" in tbl_text

    phase_text = format_phase_comparison(src_res)
    assert "PHASE COMPARISON" in phase_text
    assert "Phase 1 (Pages 1–5)" in phase_text
    assert "Phase 2 (Pages 6–10)" in phase_text
    assert "Capacity Assessment" in phase_text

    config = ProbeConfig(live=False)
    print_full_report({"yahoo": src_res}, config)
