import os
import csv
from typing import Dict
from src.integrations.supabase.models import SupabaseStagingDataset


class SupabaseCSVExporter:
    """
    Exports SupabaseStagingDataset into Supabase-shaped staging CSV files:
    articles_supabase.csv and comments_supabase.csv.

    Note: Because these CSV files contain temporary negative staging IDs (-1, -2, ...),
    they are Supabase-shaped staging/export files used for staging, relationship inspection,
    and previewing, rather than direct raw database imports.
    """

    ARTICLE_FIELDNAMES = [
        "id",
        "title",
        "content",
        "source",
        "created_at",
        "url",
        "author",
        "published_date",
        "content_hash",
        "clean_content",
        "processing_status",
        "processing_note",
        "processed_at",
        "is_relevant"
    ]

    COMMENT_FIELDNAMES = [
        "id",
        "article_id",
        "text",
        "created_at",
        "parent_comment_id"
    ]

    @classmethod
    def export(
        cls,
        dataset: SupabaseStagingDataset,
        output_dir: str = "data/output",
        articles_filename: str = "articles_supabase.csv",
        comments_filename: str = "comments_supabase.csv"
    ) -> Dict[str, str]:
        """
        Exports staging dataset to articles_supabase.csv and comments_supabase.csv.

        Args:
            dataset: SupabaseStagingDataset instance.
            output_dir: Output directory path.
            articles_filename: Filename for staged articles CSV.
            comments_filename: Filename for staged comments CSV.

        Returns:
            Dict[str, str]: Dictionary containing paths to the generated CSV files.
        """
        os.makedirs(output_dir, exist_ok=True)

        articles_path = os.path.join(output_dir, articles_filename)
        comments_path = os.path.join(output_dir, comments_filename)

        # Write articles_supabase.csv
        with open(articles_path, "w", encoding="utf-8-sig", newline="") as f_art:
            writer_art = csv.DictWriter(
                f_art,
                fieldnames=cls.ARTICLE_FIELDNAMES,
                quoting=csv.QUOTE_MINIMAL
            )
            writer_art.writeheader()

            for art in dataset.articles:
                row = {
                    "id": str(art.id),
                    "title": art.title or "",
                    "content": art.content or "",
                    "source": art.source or "",
                    "created_at": art.created_at or "",
                    "url": art.url or "",
                    "author": art.author or "",
                    "published_date": art.published_date or "",
                    "content_hash": art.content_hash or "",
                    "clean_content": art.clean_content or "",
                    "processing_status": art.processing_status or "",
                    "processing_note": art.processing_note or "",
                    "processed_at": art.processed_at or "",
                    "is_relevant": str(art.is_relevant) if art.is_relevant is not None else ""
                }
                writer_art.writerow(row)

        # Write comments_supabase.csv
        with open(comments_path, "w", encoding="utf-8-sig", newline="") as f_comm:
            writer_comm = csv.DictWriter(
                f_comm,
                fieldnames=cls.COMMENT_FIELDNAMES,
                quoting=csv.QUOTE_MINIMAL
            )
            writer_comm.writeheader()

            for comm in dataset.comments:
                row = {
                    "id": str(comm.id),
                    "article_id": str(comm.article_id),
                    "text": comm.text,
                    "created_at": comm.created_at or "",
                    "parent_comment_id": str(comm.parent_comment_id) if comm.parent_comment_id is not None else ""
                }
                writer_comm.writerow(row)

        return {
            "articles_csv": articles_path,
            "comments_csv": comments_path
        }
