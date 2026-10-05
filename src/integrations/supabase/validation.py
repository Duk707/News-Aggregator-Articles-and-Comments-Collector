import re
from typing import List, Tuple, Set, Dict
from src.integrations.supabase.models import SupabaseStagingDataset

DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class SupabaseValidator:
    """
    Validator for SupabaseStagingDataset verifying field rules, foreign key constraints,
    and unique index constraints matching public.articles and public.comments schemas.
    """


    @classmethod
    def validate_dataset(cls, dataset: SupabaseStagingDataset) -> Tuple[List[str], List[str]]:
        """
        Validates a staging dataset.

        Returns:
            Tuple[List[str], List[str]]: (errors, warnings)
        """
        errors: List[str] = []
        warnings: List[str] = []

        valid_article_ids: Set[int] = {art.id for art in dataset.articles}
        valid_comment_ids: Set[int] = {comm.id for comm in dataset.comments}

        # 1. Unique index check: articles_url_unique_idx
        seen_urls: Dict[str, int] = {}
        for art in dataset.articles:
            if not art.url or not art.url.strip():
                errors.append(f"Article staging_id {art.id} is missing a required non-empty URL.")
            else:
                url_clean = art.url.strip()
                if url_clean in seen_urls:
                    errors.append(
                        f"Duplicate URL '{url_clean}' detected across articles "
                        f"(staging_ids {seen_urls[url_clean]} and {art.id}). Violates articles_url_unique_idx."
                    )
                else:
                    seen_urls[url_clean] = art.id

        # 2. Unique index check: articles_content_hash_unique_idx
        seen_hashes: Dict[str, int] = {}
        for art in dataset.articles:
            if art.content_hash:
                chash = art.content_hash.strip()
                if chash in seen_hashes:
                    errors.append(
                        f"Duplicate content_hash '{chash}' detected across articles "
                        f"(staging_ids {seen_hashes[chash]} and {art.id}). Violates articles_content_hash_unique_idx."
                    )
                else:
                    seen_hashes[chash] = art.id

        # 3. Article body warnings
        for art in dataset.articles:
            if not art.content or not art.content.strip():
                warnings.append(f"Article staging_id {art.id} ('{art.title or art.url}') has empty content.")

        # 4. Comment validation
        for comm in dataset.comments:
            if not comm.text or not comm.text.strip():
                errors.append(f"Comment staging_id {comm.id} (article_id {comm.article_id}) has empty text.")
            
            if comm.article_id not in valid_article_ids:
                errors.append(
                    f"Comment staging_id {comm.id} references non-existent article_id {comm.article_id}."
                )

            if comm.parent_comment_id is not None:
                if comm.parent_comment_id not in valid_comment_ids:
                    errors.append(
                        f"Comment staging_id {comm.id} references non-existent parent_comment_id {comm.parent_comment_id}."
                    )

        # 5. Article-scoped source comment_id duplicate check from original source models
        for src_art in dataset.source_articles:
            seen_source_ids: Set[str] = set()
            
            def check_comment_source_ids(comments_list):
                for comm in comments_list:
                    if comm.comment_id and comm.comment_id.strip():
                        sid = comm.comment_id.strip()
                        if sid in seen_source_ids:
                            warnings.append(
                                f"Duplicate source comment_id '{sid}' detected within article context '{src_art.requested_url}'."
                            )
                        else:
                            seen_source_ids.add(sid)
                    replies = getattr(comm, "replies", None)
                    if replies:
                        check_comment_source_ids(replies)

            if src_art.comments:
                check_comment_source_ids(src_art.comments)

        # 6. Published date format check (DATE NULL: YYYY-MM-DD)
        for art in dataset.articles:
            if art.published_date and art.published_date.strip():
                if not DATE_PATTERN.match(art.published_date.strip()):
                    errors.append(
                        f"Article staging_id {art.id} has invalid published_date format '{art.published_date}'. Expected YYYY-MM-DD."
                    )

        for comm in dataset.comments:
            if comm.published_date and comm.published_date.strip():
                if not DATE_PATTERN.match(comm.published_date.strip()):
                    errors.append(
                        f"Comment staging_id {comm.id} has invalid published_date format '{comm.published_date}'. Expected YYYY-MM-DD."
                    )

        return errors, warnings

