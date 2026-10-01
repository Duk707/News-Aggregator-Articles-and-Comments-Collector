import os
import csv
import pytest
from src.integrations.supabase.models import (
    SupabaseArticleRow,
    SupabaseCommentRow,
    SupabaseStagingDataset
)
from src.integrations.supabase.exporter import SupabaseCSVExporter


def test_export_supabase_csv_headers(tmp_path):
    output_dir = str(tmp_path)

    art = SupabaseArticleRow(
        id=-1,
        title="Test Article Title",
        content="Test content body.",
        source="Yahoo News",
        created_at=None,
        url="https://news.yahoo.com/test.html",
        author="Reporter Smith",
        published_date="2026-09-30T10:00:00Z",
        content_hash="a" * 64,
        clean_content="Test content body.",
        processing_status=None,
        processing_note=None,
        processed_at=None,
        is_relevant=None
    )

    comm = SupabaseCommentRow(
        id=-1,
        article_id=-1,
        text="Great article!",
        created_at="2026-09-30T11:00:00Z",
        parent_comment_id=None
    )

    dataset = SupabaseStagingDataset(articles=[art], comments=[comm])

    export_paths = SupabaseCSVExporter.export(
        dataset,
        output_dir=output_dir,
        articles_filename="articles_supabase.csv",
        comments_filename="comments_supabase.csv"
    )

    art_csv_path = export_paths["articles_csv"]
    comm_csv_path = export_paths["comments_csv"]

    assert os.path.exists(art_csv_path)
    assert os.path.exists(comm_csv_path)

    # Verify articles_supabase.csv headers
    with open(art_csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        headers = next(reader)
        assert headers == SupabaseCSVExporter.ARTICLE_FIELDNAMES

    # Verify comments_supabase.csv headers
    with open(comm_csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        headers = next(reader)
        assert headers == SupabaseCSVExporter.COMMENT_FIELDNAMES
