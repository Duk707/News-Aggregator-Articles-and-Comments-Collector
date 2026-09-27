import os
import csv
import pytest
from datetime import datetime, timezone
from src.models.article import Article
from src.models.comment import Comment
from src.models.comment_status import CommentStatus
from src.export.csv_exporter import CSVExporter


@pytest.fixture
def sample_article_with_comments() -> Article:
    """
    Creates an Article with comments, replies, special UTF-8 characters, quotes, commas, and multiline text.
    """
    now = datetime.now(timezone.utc).isoformat()
    c1 = Comment(
        comment_id="comm_101",
        article_url="https://news.yahoo.com/ai-classroom-2026.html",
        parent_comment_id=None,
        author_display_name="Dr. Marie Curie — Lead Researcher, O'Connor Inst.",
        comment_text="First paragraph of comment.\nSecond paragraph with comma, \"quotes\", and 'apostrophes'.",
        published_datetime="2026-09-25T14:00:00Z",
        reactions=12,
        reply_count=1,
        depth=0,
        retrieved_at=now
    )
    c2 = Comment(
        comment_id="comm_102",
        article_url="https://news.yahoo.com/ai-classroom-2026.html",
        parent_comment_id="comm_101",
        author_display_name="Prof. François Smith",
        comment_text="Reply to Dr. Curie! Adapting curricula for Éducation & IA.",
        published_datetime="2026-09-25T14:30:00Z",
        reactions=4,
        reply_count=0,
        depth=1,
        retrieved_at=now
    )
    return Article(
        platform="Yahoo News",
        source_adapter="YahooAdapter",
        requested_url="https://news.yahoo.com/ai-classroom-2026.html",
        canonical_url="https://www.yahoo.com/news/ai-classroom-2026.html",
        original_publisher="Reuters",
        title="AI in the Classroom: “A New Era” — Full Analysis",
        author="Jane Smith & John O'Brien",
        publication_datetime="2026-09-25T12:00:00Z",
        updated_datetime=None,
        article_text="Paragraph 1 of article body text.\nParagraph 2 with \"quoted text\", commas, and data.",
        language="en-US",
        topic_query="AI in Education",
        retrieved_at=now,
        comments_status=CommentStatus.AVAILABLE,
        comment_count_reported=25,
        comments_collected=2,
        extraction_method="JSON-LD + DOM",
        diagnostic_notes=["Extracted metadata via JSON-LD", "Parsed 2 comments"],
        comments=[c1, c2]
    )


@pytest.fixture
def sample_article_zero_comments_not_loaded() -> Article:
    """
    Creates an Article with 0 collected comments and NOT_LOADED status.
    """
    now = datetime.now(timezone.utc).isoformat()
    return Article(
        platform="Yahoo News",
        source_adapter="YahooAdapter",
        requested_url="https://news.yahoo.com/news/tech/article-888.html",
        canonical_url="https://www.yahoo.com/news/tech/article-888.html",
        original_publisher="Associated Press",
        title="Tech Trends Report 2026",
        author=None,
        publication_datetime="2026-09-25T08:00:00Z",
        updated_datetime=None,
        article_text="Main text of article without comments loaded.",
        language="en-US",
        topic_query=None,
        retrieved_at=now,
        comments_status=CommentStatus.NOT_LOADED,
        comment_count_reported=None,
        comments_collected=0,
        extraction_method="JSON-LD",
        diagnostic_notes=["Clicked View comments", "No rendered comment elements found in DOM"],
        comments=[]
    )


def test_csv_export_single_article_with_comments(sample_article_with_comments, tmp_path):
    """
    Verifies exporting a single article with comments to CSV:
    - articles.csv created with correct fields
    - comments.csv created with matching relational article_id
    - Multiline text, quotes, commas, UTF-8 preserved
    - CSV read-back verifies column/row structure
    """
    output_paths = CSVExporter.export(
        sample_article_with_comments,
        output_dir=str(tmp_path),
        articles_filename="articles.csv",
        comments_filename="comments.csv"
    )

    art_file = output_paths["articles_csv"]
    comm_file = output_paths["comments_csv"]

    assert os.path.exists(art_file)
    assert os.path.exists(comm_file)

    # Read back articles.csv
    articles_rows = CSVExporter.load_articles_csv(art_file)
    assert len(articles_rows) == 1

    art_row = articles_rows[0]
    expected_article_id = "https://www.yahoo.com/news/ai-classroom-2026.html"
    assert art_row["article_id"] == expected_article_id
    assert art_row["platform"] == "Yahoo News"
    assert art_row["title"] == "AI in the Classroom: “A New Era” — Full Analysis"
    assert art_row["comments_status"] == "AVAILABLE"
    assert art_row["comments_collected"] == "2"
    assert art_row["comment_count_reported"] == "25"
    assert "Paragraph 1 of article body text.\nParagraph 2" in art_row["article_text"]

    # Read back comments.csv
    comments_rows = CSVExporter.load_comments_csv(comm_file)
    assert len(comments_rows) == 2

    c1_row = comments_rows[0]
    assert c1_row["comment_id"] == "comm_101"
    assert c1_row["article_id"] == expected_article_id  # Relational join key matches!
    assert c1_row["parent_comment_id"] == ""
    assert c1_row["depth"] == "0"
    assert c1_row["reply_count"] == "1"
    assert "Dr. Marie Curie — Lead Researcher, O'Connor Inst." in c1_row["author_display_name"]
    assert "First paragraph of comment.\nSecond paragraph with comma, \"quotes\", and 'apostrophes'." in c1_row["comment_text"]

    c2_row = comments_rows[1]
    assert c2_row["comment_id"] == "comm_102"
    assert c2_row["article_id"] == expected_article_id
    assert c2_row["parent_comment_id"] == "comm_101"
    assert c2_row["depth"] == "1"
    assert "François" in c2_row["author_display_name"]


def test_csv_export_zero_comments_not_loaded(sample_article_zero_comments_not_loaded, tmp_path):
    """
    Verifies exporting an article with zero collected comments and NOT_LOADED status:
    - articles.csv has 1 row with comments_status=NOT_LOADED and comments_collected=0
    - comments.csv has 0 rows (only header)
    - Distinguishes 0 comments collected from comments status
    """
    output_paths = CSVExporter.export(
        sample_article_zero_comments_not_loaded,
        output_dir=str(tmp_path),
        articles_filename="articles.csv",
        comments_filename="comments.csv"
    )

    art_rows = CSVExporter.load_articles_csv(output_paths["articles_csv"])
    comm_rows = CSVExporter.load_comments_csv(output_paths["comments_csv"])

    assert len(art_rows) == 1
    assert art_rows[0]["comments_status"] == "NOT_LOADED"
    assert art_rows[0]["comments_collected"] == "0"
    assert art_rows[0]["comment_count_reported"] == ""

    assert len(comm_rows) == 0


def test_csv_export_multiple_articles_batch(sample_article_with_comments, sample_article_zero_comments_not_loaded, tmp_path):
    """
    Verifies batch exporting multiple articles to articles.csv and comments.csv:
    - articles.csv contains 2 rows
    - comments.csv contains 2 rows (associated with the first article only)
    - Joining comments.csv to articles.csv via article_id resolves correctly
    """
    articles = [sample_article_with_comments, sample_article_zero_comments_not_loaded]

    output_paths = CSVExporter.export(
        articles,
        output_dir=str(tmp_path),
        articles_filename="articles.csv",
        comments_filename="comments.csv"
    )

    art_rows = CSVExporter.load_articles_csv(output_paths["articles_csv"])
    comm_rows = CSVExporter.load_comments_csv(output_paths["comments_csv"])

    assert len(art_rows) == 2
    assert len(comm_rows) == 2

    # Map comments by article_id to test relational joining
    article_1_id = art_rows[0]["article_id"]
    article_2_id = art_rows[1]["article_id"]

    art1_comments = [c for c in comm_rows if c["article_id"] == article_1_id]
    art2_comments = [c for c in comm_rows if c["article_id"] == article_2_id]

    assert len(art1_comments) == 2
    assert len(art2_comments) == 0
