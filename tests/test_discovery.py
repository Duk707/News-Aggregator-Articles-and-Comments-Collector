import pytest
from datetime import datetime, timezone
from src.discovery.models import CandidateArticle
from src.discovery.search import (
    CandidateDiscoverer,
    clean_tracking_params,
    parse_rfc822_date,
    parse_date_filter_boundary
)
from src.collectors.router import SourceRouter


# Sanitized XML string fixture for offline discovery testing
SAMPLE_RSS_XML = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <title>Bing News Search Results</title>
    <item>
      <title>AI Tools Revolutionize Education Systems</title>
      <link>https://news.yahoo.com/ai-tools-education-12345.html?utm_source=rssfeed&amp;utm_medium=referral&amp;ncid=123</link>
      <description>Teachers and researchers explore how artificial intelligence changes classrooms.</description>
      <pubDate>Fri, 25 Sep 2026 14:30:00 GMT</pubDate>
    </item>
    <item>
      <title>MSN Report on Classroom Technology Advances</title>
      <link>https://www.msn.com/en-us/news/technology/classroom-tech-advances/ar-AA1WCoGY?utm_campaign=newsfeed</link>
      <description>A comprehensive study on K-12 digital learning software.</description>
      <pubDate>Thu, 24 Sep 2026 10:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Unsupported Site Article About AI</title>
      <link>https://www.example.com/unsupported-news-article.html</link>
      <description>This site is not a supported Yahoo or MSN domain.</description>
      <pubDate>Wed, 23 Sep 2026 08:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Crypto and Gaming Trends in Tech</title>
      <link>https://news.yahoo.com/crypto-gaming-trends-67890.html</link>
      <description>Discussing cryptocurrency and Web3 gaming market movements.</description>
      <pubDate>Tue, 22 Sep 2026 12:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Yahoo Article With Missing Publication Date</title>
      <link>https://news.yahoo.com/missing-date-article-99999.html</link>
      <description>Educational research summary without explicit date tag.</description>
    </item>
    <item>
      <title>Duplicate Yahoo Article Title</title>
      <link>https://news.yahoo.com/ai-tools-education-12345.html?utm_source=duplicate</link>
      <description>Duplicate article link with different tracking params.</description>
      <pubDate>Fri, 25 Sep 2026 14:30:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


def test_candidate_article_model_instantiation():
    """Verifies CandidateArticle model instantiation and default provenance fields."""
    cand = CandidateArticle(
        title="Test Headline Title",
        url="https://news.yahoo.com/test-article.html",
        platform="Yahoo News",
        source_domain="news.yahoo.com",
        discovery_query="AI in Education",
        discovered_at="2026-09-26T00:00:00Z"
    )
    assert cand.title == "Test Headline Title"
    assert cand.url == "https://news.yahoo.com/test-article.html"
    assert cand.platform == "Yahoo News"
    assert cand.discovery_provider == "Bing News RSS"
    assert cand.discovery_method == "public_rss_feed"


def test_clean_tracking_params():
    """Verifies that tracking parameters are stripped while functional parameters are preserved."""
    url1 = "https://news.yahoo.com/item.html?utm_source=rss&utm_medium=feed&ncid=123"
    cleaned1 = clean_tracking_params(url1)
    assert "utm_source" not in cleaned1
    assert "ncid" not in cleaned1
    assert cleaned1 == "https://news.yahoo.com/item.html"

    # Functional parameter 'ar' for MSN should be preserved
    url2 = "https://www.msn.com/en-us/news/article/ar-AA1WCoGY?utm_campaign=test&ar=AA1WCoGY"
    cleaned2 = clean_tracking_params(url2)
    assert "utm_campaign" not in cleaned2
    assert "ar=AA1WCoGY" in cleaned2


def test_candidate_discoverer_xml_parsing_and_routing():
    """Verifies XML candidate parsing and SourceRouter validation filtering out unsupported domains."""
    discoverer = CandidateDiscoverer()
    candidates = discoverer.parse_xml_candidates(
        xml_content=SAMPLE_RSS_XML,
        query="AI in Education",
        max_candidates=10
    )

    # 4 valid candidate Yahoo/MSN articles (example.com is filtered out!)
    assert len(candidates) == 4
    urls = [c.url for c in candidates]
    assert "https://www.example.com/unsupported-news-article.html" not in urls
    assert "https://news.yahoo.com/ai-tools-education-12345.html" in urls
    assert "https://www.msn.com/en-us/news/technology/classroom-tech-advances/ar-AA1WCoGY" in urls


def test_candidate_discoverer_keyword_filtering():
    """Verifies post-discovery include and exclude keyword filtering."""
    discoverer = CandidateDiscoverer()

    # Include filter: requires 'classroom' or 'k-12'
    candidates_inc = discoverer.parse_xml_candidates(
        xml_content=SAMPLE_RSS_XML,
        query="AI in Education",
        include_keywords=["classroom", "K-12"]
    )
    assert len(candidates_inc) == 2
    titles = [c.title for c in candidates_inc]
    assert "AI Tools Revolutionize Education Systems" in titles
    assert "MSN Report on Classroom Technology Advances" in titles

    # Exclude filter: forbids 'crypto'
    candidates_exc = discoverer.parse_xml_candidates(
        xml_content=SAMPLE_RSS_XML,
        query="AI in Education",
        exclude_keywords=["crypto"]
    )
    titles_exc = [c.title for c in candidates_exc]
    assert "Crypto and Gaming Trends in Tech" not in titles_exc


def test_candidate_discoverer_include_keyword_match_modes():
    """
    Verifies ANY vs ALL include keyword match modes:
    - ANY: candidate containing at least one keyword (e.g. 'education') passes.
    - ALL: candidate must contain every keyword (e.g. both 'education' and 'AI'). An article with only 'education' fails ALL mode.
    """
    discoverer = CandidateDiscoverer()
    keywords = ["education", "AI"]

    # 1. Mode ANY -> Candidate with ONLY 'education' passes ANY mode
    cands_any = discoverer.parse_xml_candidates(
        xml_content=SAMPLE_RSS_XML,
        query="AI in Education",
        include_keywords=keywords,
        include_keyword_mode="ANY"
    )
    titles_any = [c.title for c in cands_any]
    assert "AI Tools Revolutionize Education Systems" in titles_any      # Has both AI and Education
    assert "Yahoo Article With Missing Publication Date" in titles_any  # Has Educational in snippet (matches 'education')

    # 2. Mode ALL -> Candidate with ONLY 'education' FAILS ALL mode; candidate with both passes
    cands_all = discoverer.parse_xml_candidates(
        xml_content=SAMPLE_RSS_XML,
        query="AI in Education",
        include_keywords=keywords,
        include_keyword_mode="ALL"
    )
    titles_all = [c.title for c in cands_all]
    assert "AI Tools Revolutionize Education Systems" in titles_all      # Has both -> PASSES ALL
    assert "Yahoo Article With Missing Publication Date" not in titles_all # Has only education -> FAILS ALL!



def test_candidate_discoverer_conservative_date_filtering():
    """
    Verifies Rule 1 requirement:
    - When no date filter is active, candidates with missing dates are retained (publication_date=None).
    - When user explicitly supplies start/end date, candidates with missing dates are EXCLUDED conservatively.
    - Out-of-range dates are EXCLUDED, while in-range dates are INCLUDED.
    """
    discoverer = CandidateDiscoverer()

    # Case A: No date filter active -> missing date item IS retained with publication_date=None
    cands_no_filter = discoverer.parse_xml_candidates(
        xml_content=SAMPLE_RSS_XML,
        query="AI in Education",
        start_date=None,
        end_date=None
    )
    missing_date_items = [c for c in cands_no_filter if "Missing Publication Date" in c.title]
    assert len(missing_date_items) == 1
    assert missing_date_items[0].publication_date is None

    # Case B: Date filter IS active ('2026-09-24' to '2026-09-25') -> missing date item MUST BE EXCLUDED!
    cands_date_filter = discoverer.parse_xml_candidates(
        xml_content=SAMPLE_RSS_XML,
        query="AI in Education",
        start_date="2026-09-24",
        end_date="2026-09-25"
    )
    missing_date_filtered = [c for c in cands_date_filter if "Missing Publication Date" in c.title]
    assert len(missing_date_filtered) == 0  # Conservative exclusion verified!

    # Verify only in-range dates ('2026-09-24' and '2026-09-25') are retained
    titles = [c.title for c in cands_date_filter]
    assert "AI Tools Revolutionize Education Systems" in titles       # 2026-09-25
    assert "MSN Report on Classroom Technology Advances" in titles   # 2026-09-24
    assert "Crypto and Gaming Trends in Tech" not in titles            # 2026-09-22 (Excluded)


def test_candidate_discoverer_deduplication_and_limit():
    """Verifies duplicate URL stripping and max_candidates limit enforcement."""
    discoverer = CandidateDiscoverer()

    # Limit = 2
    candidates = discoverer.parse_xml_candidates(
        xml_content=SAMPLE_RSS_XML,
        query="AI in Education",
        max_candidates=2
    )
    assert len(candidates) == 2


def test_candidate_discoverer_trump_exclusion():
    """
    Verifies that when exclude_keywords=['Trump'] is passed, candidate items containing 'Trump'
    in their title or description are strictly excluded regardless of case or punctuation.
    """
    trump_xml = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Melania Trump Slammed for Gifting Elementary School Kids AI Literacy Training</title>
      <link>https://www.msn.com/en-us/news/other/melania-trump-slammed/ar-AA2d17L2</link>
      <description>Concerns grow over AI in education.</description>
    </item>
    <item>
      <title>Why Red States Are Rejecting Trump's AI Vision for Schools</title>
      <link>https://www.msn.com/en-us/money/general/why-red-states-rejecting-trump-vision/ar-AA2cWGok</link>
      <description>State officials raise concerns over federal AI directives.</description>
    </item>
    <item>
      <title>Schools Hedge Their Bets on AI as Concerns Grow Among Parents</title>
      <link>https://www.yahoo.com/news/politics/articles/schools-hedge-bets-ai-concerns-220000076.html</link>
      <description>School districts struggle to adopt generative AI guidelines.</description>
    </item>
  </channel>
</rss>
"""
    discoverer = CandidateDiscoverer()

    # Test without exclude keywords -> 3 items
    cands_no_exc = discoverer.parse_xml_candidates(trump_xml, query="AI schools")
    assert len(cands_no_exc) == 3

    # Test with exclude_keywords=['Trump'] -> drops both Trump items, retains 1 non-Trump item!
    cands_exc = discoverer.parse_xml_candidates(trump_xml, query="AI schools", exclude_keywords=["Trump"])
    assert len(cands_exc) == 1
    assert cands_exc[0].title == "Schools Hedge Their Bets on AI as Concerns Grow Among Parents"


def test_candidate_discoverer_blank_query_with_include_keywords(monkeypatch):
    """
    Verifies that a blank Discovery Search Query with Include Keywords constructs
    source-specific sub-queries and accumulates candidates.
    """
    requested_urls = []

    class DummyResponse:
        status_code = 200
        text = SAMPLE_RSS_XML

    def mock_get(url, params=None, headers=None, timeout=None):
        requested_urls.append(params.get("q"))
        return DummyResponse()

    monkeypatch.setattr("requests.get", mock_get)

    discoverer = CandidateDiscoverer()
    # Blank query, include_keywords=['AI', 'Education'], mode='ALL'
    cands = discoverer.discover(
        query="",
        include_yahoo=True,
        include_msn=True,
        include_keywords=["AI", "Education"],
        include_keyword_mode="ALL",
        max_candidates=10
    )

    assert len(requested_urls) > 0
    # Verify source-specific sub-queries were issued: 'AI Education site:yahoo.com' and 'AI Education site:msn.com'
    assert any("site:yahoo.com" in q for q in requested_urls)
    assert any("site:msn.com" in q for q in requested_urls)
    assert any("AI Education" in q for q in requested_urls)
    assert len(cands) > 0


def test_candidate_discoverer_source_balancing(monkeypatch):
    """
    Verifies round-robin interleaving when both Yahoo and MSN have qualifying candidates.
    Ensures that Yahoo does NOT consume the entire max_candidates limit before MSN is queried.
    """
    yahoo_xml = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Yahoo Article 1</title>
      <link>https://news.yahoo.com/article-1.html</link>
      <pubDate>Fri, 25 Sep 2026 14:30:00 GMT</pubDate>
    </item>
    <item>
      <title>Yahoo Article 2</title>
      <link>https://news.yahoo.com/article-2.html</link>
      <pubDate>Fri, 25 Sep 2026 14:30:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""
    msn_xml = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>MSN Article 1</title>
      <link>https://www.msn.com/en-us/news/article-1/ar-1</link>
      <pubDate>Fri, 25 Sep 2026 14:30:00 GMT</pubDate>
    </item>
    <item>
      <title>MSN Article 2</title>
      <link>https://www.msn.com/en-us/news/article-2/ar-2</link>
      <pubDate>Fri, 25 Sep 2026 14:30:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""
    class DummyResponse:
        def __init__(self, text):
            self.status_code = 200
            self.text = text

    def mock_get(url, params=None, headers=None, timeout=None):
        q = params.get("q", "")
        if "site:yahoo.com" in q:
            return DummyResponse(yahoo_xml)
        elif "site:msn.com" in q:
            return DummyResponse(msn_xml)
        return DummyResponse("")

    monkeypatch.setattr("requests.get", mock_get)

    discoverer = CandidateDiscoverer()
    cands = discoverer.discover(
        query="AI Education",
        include_yahoo=True,
        include_msn=True,
        max_candidates=4
    )

    assert len(cands) == 4
    # Round-robin interleaving verified: Yahoo 1, MSN 1, Yahoo 2, MSN 2
    assert cands[0].platform == "Yahoo News"
    assert cands[1].platform == "MSN"
    assert cands[2].platform == "Yahoo News"
    assert cands[3].platform == "MSN"


def test_candidate_discoverer_unbalanced_source_fill(monkeypatch):
    """
    Verifies that if one source has fewer candidates (e.g. 1 MSN item) than requested max_candidates (4),
    all available candidates from that source are retained and the remaining slots are filled by the other source (3 Yahoo items).
    """
    yahoo_xml = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <item><title>Yahoo 1</title><link>https://news.yahoo.com/y1.html</link></item>
    <item><title>Yahoo 2</title><link>https://news.yahoo.com/y2.html</link></item>
    <item><title>Yahoo 3</title><link>https://news.yahoo.com/y3.html</link></item>
    <item><title>Yahoo 4</title><link>https://news.yahoo.com/y4.html</link></item>
  </channel>
</rss>
"""
    msn_xml = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <item><title>MSN 1</title><link>https://www.msn.com/en-us/news/m1/ar-1</link></item>
  </channel>
</rss>
"""
    class DummyResponse:
        def __init__(self, text):
            self.status_code = 200
            self.text = text

    def mock_get(url, params=None, headers=None, timeout=None):
        q = params.get("q", "")
        if "site:yahoo.com" in q:
            return DummyResponse(yahoo_xml)
        elif "site:msn.com" in q:
            return DummyResponse(msn_xml)
        return DummyResponse("")

    monkeypatch.setattr("requests.get", mock_get)

    discoverer = CandidateDiscoverer()
    cands = discoverer.discover(
        query="AI Education",
        include_yahoo=True,
        include_msn=True,
        max_candidates=4
    )

    assert len(cands) == 4
    platforms = [c.platform for c in cands]
    assert platforms.count("MSN") == 1
    assert platforms.count("Yahoo News") == 3


def test_candidate_discoverer_adaptive_depth_max_30(monkeypatch):
    """
    Verifies that when max_candidates=30 is requested, discovery scales target offset pages
    beyond page 2 (first=21, 31) up to the target request budget.
    """
    requested_offsets = []

    def mock_get(url, params=None, headers=None, timeout=None):
        offset = params.get("first", 1)
        requested_offsets.append(offset)

        # Generate RSS XML with unique URLs per offset page
        xml_page = f"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Article Offset {offset}</title>
      <link>https://news.yahoo.com/article-offset-{offset}.html</link>
      <pubDate>Fri, 25 Sep 2026 14:30:00 GMT</pubDate>
    </item>
  </channel>
</rss>"""
        class DummyResponse:
            status_code = 200
            text = xml_page

        return DummyResponse()

    monkeypatch.setattr("requests.get", mock_get)

    discoverer = CandidateDiscoverer()
    cands = discoverer.discover(
        query="AI Education",
        include_yahoo=True,
        include_msn=False,
        max_candidates=30
    )

    # Offset 21 should be requested for max_candidates=30
    assert 21 in requested_offsets


def test_discovery_diagnostics_accounting(monkeypatch):
    """
    Verifies that discovery diagnostics track:
    - Multiple pages with repeated URLs
    - Unsupported URLs
    - Keyword rejections
    - Separate Yahoo / MSN counters
    - Zero-yield early termination
    - Accurate unique counts without regression
    """
    # Page 1 for Yahoo: 1 valid Yahoo, 1 unsupported URL, 1 keyword reject (contains 'sports')
    yahoo_p1 = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>AI in Education Yahoo Article 1</title>
      <link>https://news.yahoo.com/article-1.html</link>
      <pubDate>Fri, 25 Sep 2026 14:30:00 GMT</pubDate>
    </item>
    <item>
      <title>Unsupported Domain Link</title>
      <link>https://www.random-blog.com/post.html</link>
      <pubDate>Fri, 25 Sep 2026 14:30:00 GMT</pubDate>
    </item>
    <item>
      <title>Sports and Gaming Education</title>
      <link>https://news.yahoo.com/sports-article.html</link>
      <pubDate>Fri, 25 Sep 2026 14:30:00 GMT</pubDate>
    </item>
  </channel>
</rss>"""

    # Page 2 for Yahoo: 1 repeat of Article 1, 1 new valid Yahoo
    yahoo_p2 = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>AI in Education Yahoo Article 1 Duplicate</title>
      <link>https://news.yahoo.com/article-1.html?utm_source=feed</link>
      <pubDate>Fri, 25 Sep 2026 14:30:00 GMT</pubDate>
    </item>
    <item>
      <title>AI in Education Yahoo Article 2</title>
      <link>https://news.yahoo.com/article-2.html</link>
      <pubDate>Fri, 25 Sep 2026 15:30:00 GMT</pubDate>
    </item>
  </channel>
</rss>"""

    # Page 3 for Yahoo: empty / zero yield
    yahoo_p3 = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
  </channel>
</rss>"""

    # Page 1 for MSN: 1 valid MSN article
    msn_p1 = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>AI in Education MSN Article 1</title>
      <link>https://www.msn.com/en-us/news/article/ar-MSN111</link>
      <pubDate>Fri, 25 Sep 2026 16:30:00 GMT</pubDate>
    </item>
  </channel>
</rss>"""

    # Page 2 for MSN: 0 new items (zero yield)
    msn_p2 = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
  </channel>
</rss>"""

    class DummyResponse:
        def __init__(self, text):
            self.status_code = 200
            self.text = text

    def mock_get(url, params=None, headers=None, timeout=None):
        q = params.get("q", "")
        offset = params.get("first", 1)

        if "site:yahoo.com" in q:
            if offset == 1:
                return DummyResponse(yahoo_p1)
            elif offset == 11:
                return DummyResponse(yahoo_p2)
            else:
                return DummyResponse(yahoo_p3)
        elif "site:msn.com" in q:
            if offset == 1:
                return DummyResponse(msn_p1)
            else:
                return DummyResponse(msn_p2)
        return DummyResponse("")

    monkeypatch.setattr("requests.get", mock_get)

    discoverer = CandidateDiscoverer()
    cands = discoverer.discover(
        query="AI Education",
        include_yahoo=True,
        include_msn=True,
        max_candidates=20,
        exclude_keywords=["sports"]
    )

    diag = discoverer.last_diagnostics
    assert diag is not None

    # Yahoo Diagnostics Assertions
    assert diag.yahoo.source_name == "Yahoo News"
    assert diag.yahoo.pages_attempted == 3
    assert diag.yahoo.requests_made == 3
    assert diag.yahoo.raw_items_in_responses == 5  # 3 on p1 + 2 on p2 + 0 on p3
    assert diag.yahoo.items_processed == 5
    assert diag.yahoo.unique_candidates_pooled == 2  # article-1 and article-2
    assert diag.yahoo.candidates_returned == 2
    assert diag.yahoo.repeated_urls_in_search == 1  # duplicate of article-1 on p2
    assert diag.yahoo.rejected_unsupported_urls == 1  # random-blog.com
    assert diag.yahoo.rejected_keywords == 1  # sports-article.html
    assert diag.yahoo.platform_breakdown.get("Yahoo News") == 2
    assert diag.yahoo.termination_reason == "zero_yield_page"

    # MSN Diagnostics Assertions
    assert diag.msn.source_name == "MSN"
    assert diag.msn.pages_attempted == 2
    assert diag.msn.requests_made == 2
    assert diag.msn.raw_items_in_responses == 1
    assert diag.msn.items_processed == 1
    assert diag.msn.unique_candidates_pooled == 1
    assert diag.msn.candidates_returned == 1
    assert diag.msn.repeated_urls_in_search == 0
    assert diag.msn.rejected_unsupported_urls == 0
    assert diag.msn.rejected_keywords == 0
    assert diag.msn.platform_breakdown.get("MSN") == 1
    assert diag.msn.termination_reason == "zero_yield_page"

    # Total and Candidate Verification
    assert diag.total_candidates_returned == 3  # 2 Yahoo + 1 MSN
    assert len(cands) == 3
    urls = [c.url for c in cands]
    assert "https://news.yahoo.com/article-1.html" in urls
    assert "https://news.yahoo.com/article-2.html" in urls
    assert "https://www.msn.com/en-us/news/article/ar-MSN111" in urls

    # Summary Line & Multiline Report Checks
    summary_line = diag.format_summary_line()
    assert "Yahoo News: 2 ret / 2 pooled" in summary_line
    assert "MSN: 1 ret / 1 pooled" in summary_line
    assert "term: zero_yield_page" in summary_line

    report = diag.format_multiline_report()
    assert "Discovery Run Summary" in report
    assert "Yahoo News Query (Terminated: zero_yield_page)" in report
    assert "MSN Query (Terminated: zero_yield_page)" in report
    assert "Yield: 2 pooled -> 2 returned to GUI" in report


def test_discovery_diagnostics_corrections_regression(monkeypatch):
    """
    Focused regression test covering:
    1. raw_items_in_responses vs items_processed when candidate limit cuts processing early.
    2. Network error and xml parse error distinguishing from zero_yield_page.
    3. Separate pooled vs returned counts when global max_candidates cuts source pool.
    4. Platform breakdown tracking actual router-validated platform.
    """
    # 5 raw items in RSS XML
    xml_with_5_items = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Article 1</title>
      <link>https://news.yahoo.com/article-1.html</link>
      <pubDate>Fri, 25 Sep 2026 14:30:00 GMT</pubDate>
    </item>
    <item>
      <title>Article 2</title>
      <link>https://news.yahoo.com/article-2.html</link>
      <pubDate>Fri, 25 Sep 2026 14:30:00 GMT</pubDate>
    </item>
    <item>
      <title>Article 3</title>
      <link>https://news.yahoo.com/article-3.html</link>
      <pubDate>Fri, 25 Sep 2026 14:30:00 GMT</pubDate>
    </item>
    <item>
      <title>Article 4</title>
      <link>https://news.yahoo.com/article-4.html</link>
      <pubDate>Fri, 25 Sep 2026 14:30:00 GMT</pubDate>
    </item>
    <item>
      <title>Article 5</title>
      <link>https://news.yahoo.com/article-5.html</link>
      <pubDate>Fri, 25 Sep 2026 14:30:00 GMT</pubDate>
    </item>
  </channel>
</rss>"""

    class DummyResponse:
        def __init__(self, text, status_code=200):
            self.status_code = status_code
            self.text = text

    # Case 1: Max candidates = 2 on Yahoo with 5 items in response
    def mock_get_limit(url, params=None, headers=None, timeout=None):
        return DummyResponse(xml_with_5_items)

    monkeypatch.setattr("requests.get", mock_get_limit)

    discoverer = CandidateDiscoverer()
    cands = discoverer.discover(
        query="AI Education",
        include_yahoo=True,
        include_msn=False,
        max_candidates=2
    )

    diag = discoverer.last_diagnostics
    assert len(cands) == 2
    # All 5 raw items in response counted, but only 2 processed before limit reached
    assert diag.yahoo.raw_items_in_responses == 5
    assert diag.yahoo.items_processed == 2
    assert diag.yahoo.unique_candidates_pooled == 2
    assert diag.yahoo.candidates_returned == 2
    assert diag.yahoo.termination_reason == "max_candidates_reached"
    assert diag.yahoo.platform_breakdown.get("Yahoo News") == 2

    # Case 2: Network error returns HTTP 500
    def mock_get_net_err(url, params=None, headers=None, timeout=None):
        return DummyResponse("Server Error", status_code=500)

    monkeypatch.setattr("requests.get", mock_get_net_err)
    discoverer_net = CandidateDiscoverer()
    cands_net = discoverer_net.discover(
        query="AI Education",
        include_yahoo=True,
        include_msn=False,
        max_candidates=10
    )
    assert len(cands_net) == 0
    assert discoverer_net.last_diagnostics.yahoo.network_errors == 1
    assert discoverer_net.last_diagnostics.yahoo.termination_reason == "network_error"

    # Case 3: Invalid XML response
    def mock_get_xml_err(url, params=None, headers=None, timeout=None):
        return DummyResponse("<not-valid-xml<<", status_code=200)

    monkeypatch.setattr("requests.get", mock_get_xml_err)
    discoverer_xml = CandidateDiscoverer()
    cands_xml = discoverer_xml.discover(
        query="AI Education",
        include_yahoo=True,
        include_msn=False,
        max_candidates=10
    )
    assert len(cands_xml) == 0
    assert discoverer_xml.last_diagnostics.yahoo.xml_parse_errors == 1
    assert discoverer_xml.last_diagnostics.yahoo.termination_reason == "xml_parse_error"

    # Case 4: Separate pooled vs returned counts when global max_candidates cuts source pool
    # Yahoo has 2, MSN has 2, but max_candidates = 3
    msn_xml_2_items = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>MSN 1</title>
      <link>https://www.msn.com/en-us/news/article/ar-M1</link>
    </item>
    <item>
      <title>MSN 2</title>
      <link>https://www.msn.com/en-us/news/article/ar-M2</link>
    </item>
  </channel>
</rss>"""

    yahoo_xml_2_items = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Yahoo 1</title>
      <link>https://news.yahoo.com/y1.html</link>
    </item>
    <item>
      <title>Yahoo 2</title>
      <link>https://news.yahoo.com/y2.html</link>
    </item>
  </channel>
</rss>"""

    def mock_get_both(url, params=None, headers=None, timeout=None):
        q = params.get("q", "")
        if "site:yahoo.com" in q:
            return DummyResponse(yahoo_xml_2_items)
        elif "site:msn.com" in q:
            return DummyResponse(msn_xml_2_items)
        return DummyResponse("")

    monkeypatch.setattr("requests.get", mock_get_both)
    discoverer_both = CandidateDiscoverer()
    cands_both = discoverer_both.discover(
        query="AI Education",
        include_yahoo=True,
        include_msn=True,
        max_candidates=3
    )

    diag_both = discoverer_both.last_diagnostics
    assert len(cands_both) == 3
    # Both pools accumulated 2 unique items (4 total pooled)
    assert diag_both.yahoo.unique_candidates_pooled == 2
    assert diag_both.msn.unique_candidates_pooled == 2
    # Round-robin merging yielded 2 from Yahoo, 1 from MSN = 3 total returned to GUI
    assert diag_both.yahoo.candidates_returned == 2
    assert diag_both.msn.candidates_returned == 1
    assert diag_both.total_candidates_returned == 3
    # Check returned platform breakdown
    assert diag_both.yahoo.returned_platform_breakdown.get("Yahoo News") == 2
    assert diag_both.msn.returned_platform_breakdown.get("MSN") == 1
    assert diag_both.overall_termination == "completed"


def test_discovery_diagnostics_overall_status_and_platform_breakdown(monkeypatch):
    """
    Verifies:
    1. No errors results in 'completed'.
    2. An HTTP/network error results in 'completed_with_errors'.
    3. Malformed XML results in 'completed_with_errors'.
    4. Zero-yield pages without errors do not count as network failures and result in 'completed'.
    5. Pooled and returned platform totals differ correctly when global candidate limit truncates.
    6. Cross-platform RSS results are attributed to their actual validated platform.
    7. Existing discovery candidate ordering and limits remain unchanged.
    """
    class DummyResponse:
        def __init__(self, text, status_code=200):
            self.status_code = status_code
            self.text = text

    # XML returning 3 Yahoo articles
    yahoo_xml_3 = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Y1</title>
      <link>https://news.yahoo.com/y1.html</link>
    </item>
    <item>
      <title>Y2</title>
      <link>https://news.yahoo.com/y2.html</link>
    </item>
    <item>
      <title>Y3</title>
      <link>https://news.yahoo.com/y3.html</link>
    </item>
  </channel>
</rss>"""

    # Cross-platform XML: query was site:msn.com, but contains 1 MSN and 1 valid Yahoo link
    msn_xml_cross = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>MSN Article</title>
      <link>https://www.msn.com/en-us/news/article/ar-CROSS1</link>
    </item>
    <item>
      <title>Yahoo Article Found via MSN query</title>
      <link>https://news.yahoo.com/cross-yahoo.html</link>
    </item>
  </channel>
</rss>"""

    # --- Scenario 1: Clean run with truncation (max_candidates=2) and cross-platform attribution ---
    def mock_get_clean(url, params=None, headers=None, timeout=None):
        q = params.get("q", "")
        if "site:yahoo.com" in q:
            return DummyResponse(yahoo_xml_3)
        elif "site:msn.com" in q:
            return DummyResponse(msn_xml_cross)
        return DummyResponse("")

    monkeypatch.setattr("requests.get", mock_get_clean)
    disc = CandidateDiscoverer()
    cands = disc.discover(query="AI Education", include_yahoo=True, include_msn=True, max_candidates=2)

    diag = disc.last_diagnostics
    assert len(cands) == 2
    # Status is 'completed' because zero network or xml errors occurred
    assert diag.overall_termination == "completed"

    # Yahoo query pooled 2 (hit max_candidates=2 for pool), returned 1
    assert diag.yahoo.unique_candidates_pooled == 2
    assert diag.yahoo.candidates_returned == 1
    assert diag.yahoo.platform_breakdown == {"Yahoo News": 2}
    assert diag.yahoo.returned_platform_breakdown == {"Yahoo News": 1}

    # MSN query pooled 2 (1 MSN, 1 Yahoo News cross-platform!), returned 1 (MSN)
    assert diag.msn.unique_candidates_pooled == 2
    assert diag.msn.candidates_returned == 1
    assert diag.msn.platform_breakdown == {"MSN": 1, "Yahoo News": 1}
    assert diag.msn.returned_platform_breakdown == {"MSN": 1}

    # Check candidate ordering (round-robin: first from Yahoo, then first from MSN)
    assert cands[0].url == "https://news.yahoo.com/y1.html"
    assert cands[1].url == "https://www.msn.com/en-us/news/article/ar-CROSS1"

    # Multiline report checks
    report = diag.format_multiline_report()
    assert "Status: completed" in report
    assert "Pooled [Yahoo News: 2] -> Returned [Yahoo News: 1]" in report
    assert "Pooled [MSN: 1, Yahoo News: 1] -> Returned [MSN: 1]" in report

    # --- Scenario 2: Network error causes 'completed_with_errors' ---
    def mock_get_net_fail(url, params=None, headers=None, timeout=None):
        q = params.get("q", "")
        if "site:yahoo.com" in q:
            return DummyResponse(yahoo_xml_3)
        return DummyResponse("Gateway Timeout", status_code=504)

    monkeypatch.setattr("requests.get", mock_get_net_fail)
    disc_net = CandidateDiscoverer()
    cands_net = disc_net.discover(query="AI Education", include_yahoo=True, include_msn=True, max_candidates=5)
    diag_net = disc_net.last_diagnostics
    assert diag_net.overall_termination == "completed_with_errors"
    assert diag_net.msn.network_errors == 1
    assert diag_net.msn.termination_reason == "network_error"
    assert diag_net.yahoo.network_errors == 0
    assert diag_net.yahoo.termination_reason == "zero_yield_page"

    # --- Scenario 3: Malformed XML causes 'completed_with_errors' ---
    def mock_get_xml_fail(url, params=None, headers=None, timeout=None):
        q = params.get("q", "")
        if "site:yahoo.com" in q:
            return DummyResponse(yahoo_xml_3)
        return DummyResponse("<malformed><<", status_code=200)

    monkeypatch.setattr("requests.get", mock_get_xml_fail)
    disc_xml = CandidateDiscoverer()
    cands_xml = disc_xml.discover(query="AI Education", include_yahoo=True, include_msn=True, max_candidates=5)
    diag_xml = disc_xml.last_diagnostics
    assert diag_xml.overall_termination == "completed_with_errors"
    assert diag_xml.msn.xml_parse_errors == 1
    assert diag_xml.msn.termination_reason == "xml_parse_error"

    # --- Scenario 4: Clean zero yield does NOT count as error ---
    def mock_get_empty(url, params=None, headers=None, timeout=None):
        return DummyResponse("<rss><channel></channel></rss>", status_code=200)

    monkeypatch.setattr("requests.get", mock_get_empty)
    disc_empty = CandidateDiscoverer()
    cands_empty = disc_empty.discover(query="AI Education", include_yahoo=True, include_msn=True, max_candidates=5)
    diag_empty = disc_empty.last_diagnostics
    assert len(cands_empty) == 0
    assert diag_empty.overall_termination == "completed"
    assert diag_empty.yahoo.network_errors == 0
    assert diag_empty.yahoo.xml_parse_errors == 0
    assert diag_empty.yahoo.termination_reason == "zero_yield_page"
    assert diag_empty.msn.termination_reason == "zero_yield_page"


