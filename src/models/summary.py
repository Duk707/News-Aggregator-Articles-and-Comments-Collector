from typing import Optional, Dict, List, Any
from pydantic import BaseModel, Field
from src.models.comment_status import CommentStatus
from src.models.extraction import ExtractionResult


class CollectionSummary(BaseModel):
    """
    Structured summary model representing the complete outcome of a batch collection run,
    computed immutably from batch ExtractionResult records without double-counting.
    """
    total_requested: int = Field(description="Total input URL records evaluated")
    articles_attempted: int = Field(description="Total supported article URLs where fetch was attempted")
    articles_successful: int = Field(description="Count of successfully extracted articles")
    articles_failed: int = Field(description="Count of supported articles attempted but failed to load/extract")
    
    invalid_urls: int = Field(description="Count of URLs with invalid/malformed syntax")
    unsupported_sources: int = Field(description="Count of URLs from unsupported news domains")
    duplicates_skipped: int = Field(description="Count of duplicate URLs skipped after first occurrence")
    run_limit_skipped: int = Field(description="Count of supported URLs skipped because max_articles limit was reached")

    articles_with_comments_available: int = Field(description="Count of articles with CommentStatus.AVAILABLE")
    articles_with_no_comments: int = Field(description="Count of articles with CommentStatus.NONE_PRESENT")
    articles_with_inaccessible_comments: int = Field(description="Count of articles with NOT_LOADED, LOGIN_REQUIRED, DISABLED, UNKNOWN, etc.")
    
    comment_status_counts: Dict[str, int] = Field(default_factory=dict, description="Breakdown of comment statuses across attempted/extracted articles")
    total_comments_collected: int = Field(default=0, description="Total normalized comments extracted across all articles")
    topic_query: Optional[str] = Field(default=None, description="Associated topic or search query label for this collection run")
    output_files: Dict[str, str] = Field(default_factory=dict, description="Paths of exported JSON and CSV files if generated")

    @classmethod
    def from_results(
        cls,
        results: List[ExtractionResult],
        output_files: Optional[Dict[str, str]] = None,
        topic_query: Optional[str] = None
    ) -> "CollectionSummary":
        """
        Calculates a CollectionSummary immutably from a list of batch ExtractionResult records.
        Ensures strict mutual exclusivity between non-attempted URLs and actual fetch failures.
        """
        total_requested = len(results)
        articles_attempted = 0
        articles_successful = 0
        articles_failed = 0
        invalid_urls = 0
        unsupported_sources = 0
        duplicates_skipped = 0
        run_limit_skipped = 0
        articles_with_comments_available = 0
        articles_with_no_comments = 0
        articles_with_inaccessible_comments = 0
        total_comments_collected = 0
        status_counts: Dict[str, int] = {st.value: 0 for st in CommentStatus}

        for r in results:
            msg = (r.error_message or "").lower()
            notes_str = " ".join(r.diagnostic_notes).lower()

            # Categorize non-attempted URLs
            if not r.success and "invalid or malformed url syntax" in msg:
                invalid_urls += 1
            elif not r.success and ("unsupported news website domain" in msg or "unsupported domain" in msg or "no registered adapter supported domain" in notes_str):
                unsupported_sources += 1
            elif not r.success and ("duplicate url skipped" in msg or "duplicate url" in notes_str):
                duplicates_skipped += 1

            elif not r.success and ("batch article collection limit reached" in msg or "max_articles limit" in notes_str):
                run_limit_skipped += 1
            elif r.success and r.article:
                # Supported article attempt succeeded
                articles_attempted += 1
                articles_successful += 1

                status_val = r.comments_status.value if hasattr(r.comments_status, "value") else str(r.comments_status)
                status_counts[status_val] = status_counts.get(status_val, 0) + 1

                if r.comments_status == CommentStatus.AVAILABLE:
                    articles_with_comments_available += 1
                elif r.comments_status == CommentStatus.NONE_PRESENT:
                    articles_with_no_comments += 1
                else:
                    articles_with_inaccessible_comments += 1

                total_comments_collected += r.article.comments_collected
            else:
                # Supported article attempt failed (e.g., HTTP error, 404, network error)
                articles_attempted += 1
                articles_failed += 1

                status_val = r.comments_status.value if hasattr(r.comments_status, "value") else str(r.comments_status)
                status_counts[status_val] = status_counts.get(status_val, 0) + 1
                articles_with_inaccessible_comments += 1

        # Derive topic_query from results if not explicitly provided
        derived_topic = topic_query
        if not derived_topic:
            for r in results:
                if r.article and r.article.topic_query:
                    derived_topic = r.article.topic_query
                    break

        return cls(
            total_requested=total_requested,
            articles_attempted=articles_attempted,
            articles_successful=articles_successful,
            articles_failed=articles_failed,
            invalid_urls=invalid_urls,
            unsupported_sources=unsupported_sources,
            duplicates_skipped=duplicates_skipped,
            run_limit_skipped=run_limit_skipped,
            articles_with_comments_available=articles_with_comments_available,
            articles_with_no_comments=articles_with_no_comments,
            articles_with_inaccessible_comments=articles_with_inaccessible_comments,
            comment_status_counts=status_counts,
            total_comments_collected=total_comments_collected,
            topic_query=derived_topic,
            output_files=output_files or {}
        )

    def format_terminal_summary(self) -> str:
        """
        Formats a human-readable text summary for terminal/CLI output matching BUILD_STEPS.md.
        """
        lines = [
            "=======================================================",
            "              BATCH COLLECTION SUMMARY                 ",
            "=======================================================",
            f"Topic / Research Label:                      {self.topic_query or 'None'}",
            f"Articles requested:                          {self.total_requested}",
            f"Articles attempted:                          {self.articles_attempted}",
            f"Articles successfully extracted:             {self.articles_successful}",
            f"Articles failed:                             {self.articles_failed}",
            "-------------------------------------------------------",
            f"Invalid URLs:                                {self.invalid_urls}",
            f"Unsupported sources:                         {self.unsupported_sources}",
            f"Duplicate URLs skipped:                      {self.duplicates_skipped}",
            f"Run limit skipped (max_articles):            {self.run_limit_skipped}",
            "-------------------------------------------------------",
            f"Articles with comments available:            {self.articles_with_comments_available}",
            f"Articles with no comments (NONE_PRESENT):    {self.articles_with_no_comments}",
            f"Articles with unknown/inaccessible comments: {self.articles_with_inaccessible_comments}",
            f"Total comments collected:                    {self.total_comments_collected}",
            "-------------------------------------------------------"
        ]

        if self.output_files:
            lines.append("Output locations:")
            for key, path in self.output_files.items():
                lines.append(f"  - {key}: {path}")
        else:
            lines.append("Output locations: None (No files exported yet)")

        lines.append("=======================================================")
        return "\n".join(lines)
