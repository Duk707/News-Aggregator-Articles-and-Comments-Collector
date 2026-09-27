import os
import re
import json
import hashlib
from typing import Optional, List
from src.models.article import Article


class JSONExporter:
    """
    Handles UTF-8 JSON export and deserialization of normalized Article records
    and associated public comments.
    """

    @classmethod
    def export_article(
        cls,
        article: Article,
        output_path: Optional[str] = None,
        output_dir: str = "data/output"
    ) -> str:
        """
        Exports a normalized Article model instance to a UTF-8 JSON file.

        Args:
            article: The normalized Article instance to export.
            output_path: Explicit file path for the JSON output. If None, auto-generates
                         a safe filename in output_dir.
            output_dir: Directory to save the exported file if output_path is None.

        Returns:
            str: Path of the saved UTF-8 JSON file.
        """
        os.makedirs(output_dir, exist_ok=True)

        if not output_path:
            filename = cls.generate_filename(article)
            output_path = os.path.join(output_dir, filename)

        # Serialize Article preserving null values and UTF-8 encoding
        json_str = article.model_dump_json(indent=2, by_alias=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(json_str)

        return output_path

    @classmethod
    def load_article(cls, file_path: str) -> Article:
        """
        Loads and validates a UTF-8 JSON file back into a normalized Article model instance.

        Args:
            file_path: Path to the exported JSON file.

        Returns:
            Article: Deserialized and validated Article model instance.
        """
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        return Article.model_validate_json(content)

    @classmethod
    def export_batch(
        cls,
        articles: List[Article],
        output_path: str = "data/output/batch_articles.json"
    ) -> str:
        """
        Exports a list of normalized Article instances to a single UTF-8 JSON array file.

        Args:
            articles: List of Article instances.
            output_path: File path for the JSON batch output.

        Returns:
            str: Path of the saved UTF-8 batch JSON file.
        """
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        articles_data = [a.model_dump(by_alias=True) for a in articles]
        json_str = json.dumps(articles_data, indent=2, ensure_ascii=False)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(json_str)

        return output_path

    @classmethod
    def load_batch(cls, file_path: str) -> List[Article]:
        """
        Loads and validates a UTF-8 JSON array file back into a list of Article model instances.

        Args:
            file_path: Path to the exported batch JSON file.

        Returns:
            List[Article]: List of deserialized Article instances.
        """
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return [Article.model_validate(item) for item in data]

    @staticmethod
    def generate_filename(article: Article) -> str:
        """
        Generates a safe, readable, unique filename for an article export.
        """
        platform_slug = re.sub(r"[^a-zA-Z0-9]", "_", article.platform.lower()).strip("_")
        ref_str = article.canonical_url or article.requested_url or article.title or "article"
        url_hash = hashlib.md5(ref_str.encode("utf-8")).hexdigest()[:10]

        return f"{platform_slug}_{url_hash}.json"
