import hashlib
from typing import List, Optional, Tuple, Dict, Any
from src.models.article import Article
from src.models.comment import Comment
from src.integrations.supabase.models import (
    SupabaseArticleRow,
    SupabaseCommentRow,
    SupabaseStagingDataset
)


class SupabaseMapper:
    """
    Handles translation of internal Article and Comment models into Supabase-shaped table rows.
    """

    @staticmethod
    def compute_content_hash(text: Optional[str]) -> Optional[str]:
        """
        Calculates SHA-256 hexadecimal digest from normalized article body text.
        Returns None if text is None or contains only whitespace.
        """
        if not text or not text.strip():
            return None
        
        normalized = text.strip().replace("\r\n", "\n")
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @classmethod
    def map_article(cls, article: Article, staging_id: int) -> SupabaseArticleRow:
        """
        Maps an internal Article dataclass/Pydantic model to a SupabaseArticleRow.
        """
        source = (article.original_publisher.strip() 
                  if article.original_publisher and article.original_publisher.strip() 
                  else article.platform)
        
        url = (article.canonical_url.strip() 
               if article.canonical_url and article.canonical_url.strip() 
               else article.requested_url)
        
        content_hash = cls.compute_content_hash(article.article_text)

        return SupabaseArticleRow(
            id=staging_id,
            title=article.title,
            content=article.article_text,
            source=source,
            created_at=None,  # DB default now()
            url=url,
            author=article.author,
            published_date=article.publication_datetime,
            content_hash=content_hash,
            clean_content=article.article_text,
            processing_status=None,  # Intentionally nullable/unset
            processing_note=None,    # Intentionally nullable/unset
            processed_at=None,       # Intentionally nullable/unset
            is_relevant=None         # DB default true
        )

    @classmethod
    def map_comments(
        cls,
        comments: List[Comment],
        article_staging_id: int,
        start_id: int = -1
    ) -> Tuple[List[SupabaseCommentRow], int, List[str]]:
        """
        Flattens comments for a single article into SupabaseCommentRow objects using a two-pass strategy.

        Args:
            comments: List of root or flat Comment objects.
            article_staging_id: Temporary negative staging ID of the parent article.
            start_id: Next negative staging ID counter to use.

        Returns:
            Tuple[List[SupabaseCommentRow], int, List[str]]:
                - List of mapped SupabaseCommentRow objects.
                - Updated next negative staging ID counter.
                - List of mapping-generated warnings.
        """
        curr_id = start_id
        warnings: List[str] = []
        article_local_source_map: Dict[str, int] = {}
        intermediate_records: List[Tuple[Comment, int, Optional[int]]] = []
        synthetic_counter = 0
        depth_stack: Dict[int, int] = {}

        def traverse_tree(comment_list: List[Comment], structural_parent: Optional[int]) -> None:
            nonlocal curr_id, synthetic_counter
            for comm in comment_list:
                comment_staging_id = curr_id
                curr_id -= 1

                # Determine structural parent from explicit parameter or depth hierarchy
                inferred_struct_parent = structural_parent
                if inferred_struct_parent is None and comm.depth > 0:
                    inferred_struct_parent = depth_stack.get(comm.depth - 1)

                depth_stack[comm.depth] = comment_staging_id

                source_id = comm.comment_id.strip() if comm.comment_id else ""
                if not source_id:
                    synthetic_counter += 1
                    source_id = f"__synthetic_comment_{synthetic_counter}__"

                if source_id in article_local_source_map:
                    msg = (
                        f"Duplicate source comment_id '{source_id}' detected in article "
                        f"staging_id {article_staging_id}. Preserving unique comment staging_id {comment_staging_id}."
                    )
                    warnings.append(msg)
                    article_local_source_map[f"{source_id}__dup_{comment_staging_id}"] = comment_staging_id
                else:
                    article_local_source_map[source_id] = comment_staging_id

                intermediate_records.append((comm, comment_staging_id, inferred_struct_parent))

                replies = getattr(comm, "replies", None)
                if replies:
                    traverse_tree(replies, comment_staging_id)

        traverse_tree(comments, None)

        staged_comments: List[SupabaseCommentRow] = []
        for comm, staging_id, structural_parent_id in intermediate_records:
            parent_staging_id: Optional[int] = None
            
            # Try explicit parent_comment_id lookup first
            explicit_parent = comm.parent_comment_id.strip() if comm.parent_comment_id else None
            if explicit_parent and explicit_parent in article_local_source_map:
                parent_staging_id = article_local_source_map[explicit_parent]
            else:
                # Fall back to structural parent derived from nested tree or depth hierarchy
                parent_staging_id = structural_parent_id

            staged_row = SupabaseCommentRow(
                id=staging_id,
                article_id=article_staging_id,
                text=comm.comment_text or "",
                created_at=comm.published_datetime,
                parent_comment_id=parent_staging_id
            )
            staged_comments.append(staged_row)

        return staged_comments, curr_id, warnings

    @classmethod
    def build_staging_dataset(cls, articles: List[Article]) -> SupabaseStagingDataset:
        """
        Constructs a complete SupabaseStagingDataset from a list of Article models.
        Maintains globally unique continuous negative ID sequences across articles and comments.
        """
        staged_articles: List[SupabaseArticleRow] = []
        staged_comments: List[SupabaseCommentRow] = []
        all_warnings: List[str] = []

        article_id_counter = -1
        comment_id_counter = -1

        for art in articles:
            art_staging_id = article_id_counter
            article_id_counter -= 1

            staged_art = cls.map_article(art, art_staging_id)
            staged_articles.append(staged_art)

            if art.comments:
                art_staged_comments, comment_id_counter, mapping_warns = cls.map_comments(
                    art.comments,
                    art_staging_id,
                    start_id=comment_id_counter
                )
                staged_comments.extend(art_staged_comments)
                all_warnings.extend(mapping_warns)

        dataset = SupabaseStagingDataset(
            articles=staged_articles,
            comments=staged_comments,
            source_articles=articles,
            validation_errors=[],
            validation_warnings=all_warnings
        )

        from src.integrations.supabase.validation import SupabaseValidator
        errors, validation_warns = SupabaseValidator.validate_dataset(dataset)

        dataset.validation_errors.extend(errors)
        dataset.validation_warnings.extend(validation_warns)

        return dataset
