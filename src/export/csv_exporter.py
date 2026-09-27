import os
import csv
from typing import Optional, List, Dict, Any, Union
from src.models.article import Article
from src.models.comment import Comment


class CSVExporter:
    """
    Handles UTF-8 CSV export for articles and comments into tabular articles.csv
    and comments.csv files, preserving stable relational article IDs and metadata.
    """

    ARTICLE_FIELDNAMES = [
        "article_id",
        "platform",
        "source_adapter",
        "requested_url",
        "canonical_url",
        "original_publisher",
        "title",
        "author",
        "publication_datetime",
        "updated_datetime",
        "article_text",
        "language",
        "topic_query",
        "retrieved_at",
        "comments_status",
        "comment_count_reported",
        "comments_collected",
        "extraction_method",
        "diagnostic_notes"
    ]

    COMMENT_FIELDNAMES = [
        "comment_id",
        "article_id",
        "article_url",
        "parent_comment_id",
        "author_display_name",
        "comment_text",
        "published_datetime",
        "reactions",
        "reply_count",
        "depth",
        "retrieved_at"
    ]

    @classmethod
    def export(
        cls,
        articles: Union[Article, List[Article]],
        output_dir: str = "data/output",
        articles_filename: str = "articles.csv",
        comments_filename: str = "comments.csv"
    ) -> Dict[str, str]:
        """
        Exports article(s) and their associated public comments into articles.csv and comments.csv.

        Args:
            articles: Single Article instance or list of Article instances.
            output_dir: Directory where CSV files will be written.
            articles_filename: Filename for the articles CSV table.
            comments_filename: Filename for the comments CSV table.

        Returns:
            Dict[str, str]: Paths of the created articles.csv and comments.csv files.
        """
        os.makedirs(output_dir, exist_ok=True)

        if isinstance(articles, Article):
            article_list = [articles]
        else:
            article_list = articles

        articles_path = os.path.join(output_dir, articles_filename)
        comments_path = os.path.join(output_dir, comments_filename)

        # Write articles.csv
        with open(articles_path, "w", encoding="utf-8-sig", newline="") as f_art:
            writer_art = csv.DictWriter(
                f_art,
                fieldnames=cls.ARTICLE_FIELDNAMES,
                quoting=csv.QUOTE_MINIMAL
            )
            writer_art.writeheader()

            for art in article_list:
                article_id = art.canonical_url or art.requested_url
                row = {
                    "article_id": article_id,
                    "platform": art.platform,
                    "source_adapter": art.source_adapter,
                    "requested_url": art.requested_url,
                    "canonical_url": art.canonical_url or "",
                    "original_publisher": art.original_publisher or "",
                    "title": art.title or "",
                    "author": art.author or "",
                    "publication_datetime": art.publication_datetime or "",
                    "updated_datetime": art.updated_datetime or "",
                    "article_text": art.article_text or "",
                    "language": art.language or "",
                    "topic_query": art.topic_query or "",
                    "retrieved_at": art.retrieved_at,
                    "comments_status": art.comments_status.value if hasattr(art.comments_status, "value") else str(art.comments_status),
                    "comment_count_reported": str(art.comment_count_reported) if art.comment_count_reported is not None else "",
                    "comments_collected": str(art.comments_collected),
                    "extraction_method": art.extraction_method or "",
                    "diagnostic_notes": " | ".join(art.diagnostic_notes) if art.diagnostic_notes else ""
                }
                writer_art.writerow(row)

        # Write comments.csv
        with open(comments_path, "w", encoding="utf-8-sig", newline="") as f_comm:
            writer_comm = csv.DictWriter(
                f_comm,
                fieldnames=cls.COMMENT_FIELDNAMES,
                quoting=csv.QUOTE_MINIMAL
            )
            writer_comm.writeheader()

            for art in article_list:
                article_id = art.canonical_url or art.requested_url
                for comm in art.comments:
                    row = {
                        "comment_id": comm.comment_id,
                        "article_id": article_id,
                        "article_url": comm.article_url,
                        "parent_comment_id": comm.parent_comment_id or "",
                        "author_display_name": comm.author_display_name or "",
                        "comment_text": comm.comment_text,
                        "published_datetime": comm.published_datetime or "",
                        "reactions": str(comm.reactions) if comm.reactions is not None else "",
                        "reply_count": str(comm.reply_count),
                        "depth": str(comm.depth),
                        "retrieved_at": comm.retrieved_at
                    }
                    writer_comm.writerow(row)

        return {
            "articles_csv": articles_path,
            "comments_csv": comments_path
        }

    @classmethod
    def load_articles_csv(cls, file_path: str) -> List[Dict[str, str]]:
        """
        Reads articles.csv and returns a list of row dictionaries.
        """
        with open(file_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            return list(reader)

    @classmethod
    def load_comments_csv(cls, file_path: str) -> List[Dict[str, str]]:
        """
        Reads comments.csv and returns a list of row dictionaries.
        """
        with open(file_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            return list(reader)
