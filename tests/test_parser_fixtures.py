import pytest
from src.extraction.metadata import MetadataExtractor
from src.extraction.article_text import ArticleTextExtractor
from src.extraction.comments import CommentDiagnosticInspector, MSNCommentExtractor
from src.models.comment_status import CommentStatus
from tests.fixtures import load_fixture, load_json_fixture


# -----------------------------------------------------------------------------
# 1. Metadata Extraction Tests (Observed & Synthetic Fixtures)
# -----------------------------------------------------------------------------

def test_metadata_extractor_yahoo_observed_fixture():
    """
    Tests MetadataExtractor.extract() on observed Yahoo article HTML fixture.
    Verifies ordered fallback extraction of title, author, date, publisher, and canonical URL.
    """
    html = load_fixture("yahoo_article_observed.html")
    metadata = MetadataExtractor.extract(html)

    assert metadata.title == "AI Tools Transform K-12 Classrooms"
    assert metadata.author == "Jane Doe"
    assert metadata.publication_datetime == "2026-09-25T14:30:00Z"
    assert metadata.original_publisher == "Associated Press"
    assert metadata.canonical_url == "https://news.yahoo.com/ai-tools-transform-k12-classrooms-12345.html"
    assert metadata.language == "en-US"
    assert "JSON-LD" in metadata.extraction_summary


def test_metadata_extractor_msn_observed_fixture():
    """
    Tests MetadataExtractor.extract() on observed MSN article HTML fixture.
    Verifies extraction of JSON-LD @graph, author byline separation, and canonical URL.
    """
    html = load_fixture("msn_article_observed.html")
    metadata = MetadataExtractor.extract(html)

    assert metadata.title == "MSN Digital Learning Software Advances"
    assert metadata.author == "Claire Carter"
    assert metadata.original_publisher == "Washington Examiner"
    assert metadata.publication_datetime == "2026-09-24T10:00:00Z"
    assert metadata.canonical_url == "https://www.msn.com/en-us/news/technology/classroom-tech-advances/ar-AA1WCoGY"


def test_metadata_extractor_synthetic_missing_metadata():
    """
    Tests MetadataExtractor.extract() on synthetic fixture with missing byline/timestamp.
    Verifies that missing fields are retained as None without fabrication.
    """
    html = load_fixture("synthetic_article_missing_metadata.html")
    metadata = MetadataExtractor.extract(html)

    assert metadata.title == "Article Headline Without Byline or Timestamp"
    assert metadata.author is None
    assert metadata.publication_datetime is None
    assert metadata.original_publisher is None


def test_metadata_extractor_synthetic_changed_selectors():
    """
    Tests MetadataExtractor.extract() on synthetic fixture with altered CSS selectors.
    Verifies fallback to semantic HTML tags (<h1>, <time>, <address>).
    """
    html = load_fixture("synthetic_article_changed_selectors.html")
    metadata = MetadataExtractor.extract(html)

    assert metadata.title == "Semantic Title Heading"
    assert metadata.author == "Reporter Alex Smith"
    assert metadata.publication_datetime == "2026-09-23T08:00:00Z"
    assert "Semantic HTML" in metadata.extraction_summary


# -----------------------------------------------------------------------------
# 2. Article Body Text Extraction Tests (Observed & Synthetic Fixtures)
# -----------------------------------------------------------------------------

def test_article_text_extractor_yahoo_observed_fixture():
    """
    Tests ArticleTextExtractor.extract() on observed Yahoo body HTML fixture.
    Verifies body paragraph extraction and automatic removal of sponsored ads and share buttons.
    """
    html = load_fixture("yahoo_article_observed.html")
    result = ArticleTextExtractor.extract(html)

    assert result.success is True
    assert result.paragraph_count == 3
    assert "Artificial intelligence software" in result.text
    assert "Sponsored Content Box" not in result.text
    assert "Social Share Buttons" not in result.text


def test_article_text_extractor_synthetic_noise_only():
    """
    Tests ArticleTextExtractor.extract() on synthetic fixture containing only ads and footers.
    Verifies success=False and appropriate warning generation.
    """
    html = load_fixture("synthetic_body_noise_only.html")
    result = ArticleTextExtractor.extract(html)

    assert result.success is False
    assert result.text is None


# -----------------------------------------------------------------------------
# 3. Comment Diagnostics & Evidence Tests (Observed & Synthetic Fixtures)
# -----------------------------------------------------------------------------

def test_comment_diagnostics_synthetic_unloaded_button():
    """
    Tests CommentDiagnosticInspector.inspect() on synthetic fixture with 'View Comments' button.
    Verifies conservative preliminary status inference of NOT_LOADED.
    """
    html = load_fixture("synthetic_comment_diagnostics_button.html")
    url = "https://news.yahoo.com/test-article.html"
    diag = CommentDiagnosticInspector.inspect(url, html)

    assert diag.has_view_comments_button is True
    assert diag.reported_comment_count == 42
    assert diag.comment_container_found is True
    assert diag.preliminary_status == CommentStatus.NOT_LOADED


def test_comment_diagnostics_synthetic_disabled():
    """
    Tests CommentDiagnosticInspector.inspect() on synthetic fixture with disabled text.
    Verifies preliminary status inference of DISABLED.
    """
    html = load_fixture("synthetic_comment_diagnostics_disabled.html")
    url = "https://news.yahoo.com/disabled-comments.html"
    diag = CommentDiagnosticInspector.inspect(url, html)

    assert diag.preliminary_status == CommentStatus.DISABLED
    assert len(diag.disabled_messages) > 0


def test_comment_diagnostics_synthetic_login_required():
    """
    Tests CommentDiagnosticInspector.inspect() on synthetic fixture with login text.
    Verifies preliminary status inference of LOGIN_REQUIRED.
    """
    html = load_fixture("synthetic_comment_diagnostics_login.html")
    url = "https://news.yahoo.com/login-comments.html"
    diag = CommentDiagnosticInspector.inspect(url, html)

    assert diag.preliminary_status == CommentStatus.LOGIN_REQUIRED
    assert len(diag.access_login_messages) > 0


def test_msn_peregrine_community_observed_json():
    """
    Tests parsing of observed MSN Peregrine Community API JSON response fixture.
    Verifies extraction of options.allowComments=False.
    """
    data = load_json_fixture("msn_peregrine_community_observed.json")

    assert "value" in data
    assert len(data["value"]) == 1
    community = data["value"][0]
    assert community["cmsid"] == "AA1WCoGY"
    assert community["options"]["allowComments"] is False


# -----------------------------------------------------------------------------
# 4. Comment Parsing & Deduplication Tests (Synthetic Fixture)
# -----------------------------------------------------------------------------

def test_comment_parser_synthetic_tree_and_deduplication():
    """
    Tests MSNCommentExtractor._parse_rendered_comments() on synthetic comment tree fixture.
    Verifies comment card parsing, parent ID mapping, depth calculation, reactions, and ID deduplication.
    """
    html = load_fixture("synthetic_comment_tree.html")
    url = "https://www.msn.com/en-us/news/article/ar-AA1WCoGY"
    comments, notes = MSNCommentExtractor._parse_rendered_comments(url, html, max_comments=10)

    # Must contain exactly 2 unique comments (the duplicate 'c1' is stripped!)
    assert len(comments) == 2

    c1 = comments[0]
    assert c1.comment_id == "c1"
    assert c1.author_display_name == "UserAlpha"
    assert "top-level public comment" in c1.comment_text
    assert c1.depth == 0
    assert c1.reactions == {"upvotes": 15}

    c2 = comments[1]
    assert c2.comment_id == "c2"
    assert c2.parent_comment_id == "c1"
    assert c2.depth == 1
    assert c2.reactions == {"upvotes": 4}


def test_msn_adapter_cmsid_resolution_offline():
    """
    Tests MSNCommentExtractor._extract_cmsid() offline logic using URL patterns.
    """
    url = "https://www.msn.com/en-us/news/technology/classroom-tech-advances/ar-AA1WCoGY"
    cmsid = MSNCommentExtractor._extract_cmsid(url, None)
    assert cmsid == "AA1WCoGY"
