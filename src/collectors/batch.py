import os
import time
from datetime import datetime, timezone
from typing import List, Optional, Set, Any
from src.collectors.router import SourceRouter, RoutingResult
from src.models.extraction import ExtractionResult
from src.models.article import Article
from src.models.comment_status import CommentStatus
from src.utils.urls import normalize_url, validate_url
from src.browser import BrowserManager
from src.config import CollectorConfig
from src.models.summary import CollectionSummary


class BatchCollector:
    """
    Orchestrates batch collection across multiple URLs from lists or input files,
    using SourceRouter for adapter selection, enforcing operational safety controls
    (inter-article delays, max articles run limits, navigation timeouts), fault isolation,
    and deterministic duplicate handling.
    """

    def __init__(
        self,
        router: Optional[SourceRouter] = None,
        config: Optional[CollectorConfig] = None
    ):
        """
        Initializes BatchCollector with a SourceRouter and optional CollectorConfig.
        """
        self.router = router or SourceRouter()
        self.config = config or CollectorConfig()

    @staticmethod
    def create_summary(
        results: List[ExtractionResult],
        output_files: Optional[dict] = None,
        topic_query: Optional[str] = None
    ) -> CollectionSummary:
        """
        Derives a structured CollectionSummary immutably from batch ExtractionResult records.
        """
        return CollectionSummary.from_results(results, output_files=output_files, topic_query=topic_query)


    def collect_urls(
        self,
        urls: List[str],
        browser_manager: Optional[BrowserManager] = None,
        max_comments: Optional[int] = None,
        max_articles: Optional[int] = None,
        inter_article_delay: Optional[float] = None,
        navigation_timeout_ms: Optional[int] = None,
        topic_query: Optional[str] = None,
        progress_callback: Optional[Any] = None
    ) -> List[ExtractionResult]:
        """
        Processes a list of URL strings sequentially through the source router and adapters.
        Guarantees isolated error handling and enforces operational rate limits and run limits.

        Args:
            urls: List of raw URL strings.
            browser_manager: Optional BrowserManager instance.
            max_comments: Max comments to extract per article (overrides config).
            max_articles: Maximum supported articles allowed in this batch run (overrides config).
            inter_article_delay: Delay in seconds between supported articles (overrides config).
            navigation_timeout_ms: Browser navigation timeout in ms (overrides config).
            topic_query: Optional research topic or query term.
            progress_callback: Optional callable(index: int, total: int, result: ExtractionResult).

        Returns:
            List[ExtractionResult]: Collection results for every requested URL in original order.
        """
        results: List[ExtractionResult] = []
        seen_urls: Set[str] = set()

        effective_max_comments = max_comments if max_comments is not None else self.config.max_comments_per_article
        effective_max_articles = max_articles if max_articles is not None else self.config.max_articles
        effective_delay = inter_article_delay if inter_article_delay is not None else self.config.inter_article_delay
        effective_timeout = navigation_timeout_ms if navigation_timeout_ms is not None else self.config.navigation_timeout_ms

        supported_attempts_count = 0

        bm_instance = browser_manager
        bm_owner = False

        if not bm_instance:
            bm_instance = BrowserManager(
                headless=True,
                navigation_timeout_ms=effective_timeout,
                request_delay_ms=self.config.request_delay_ms
            )
            bm_instance.__enter__()
            bm_owner = True

        try:
            for raw_url in urls:
                clean_url = normalize_url(raw_url)

                if not clean_url:
                    continue

                timestamp = datetime.now(timezone.utc).isoformat()

                # Helper to append and notify callback
                def _add_result(res: ExtractionResult):
                    results.append(res)
                    if progress_callback:
                        try:
                            progress_callback(len(results), len(urls), res)
                        except Exception:
                            pass

                # 1. Handle duplicate URLs deterministically
                if clean_url in seen_urls:
                    _add_result(ExtractionResult(
                        requested_url=clean_url,
                        success=False,
                        comments_status=CommentStatus.UNKNOWN,
                        error_message="Duplicate URL skipped",
                        diagnostic_notes=["Duplicate URL skipped during batch collection"],
                        retrieved_at=timestamp
                    ))
                    continue

                seen_urls.add(clean_url)

                # 2. Route URL to adapter
                routing_result, adapter = self.router.route(clean_url)

                if not routing_result.is_valid:
                    _add_result(ExtractionResult(
                        requested_url=clean_url,
                        success=False,
                        comments_status=CommentStatus.UNSUPPORTED,
                        error_message=routing_result.error_message or "Invalid URL syntax",
                        diagnostic_notes=["URL validation failed"],
                        retrieved_at=timestamp
                    ))
                    continue

                if not routing_result.supported or not adapter:
                    _add_result(ExtractionResult(
                        requested_url=clean_url,
                        success=False,
                        comments_status=CommentStatus.UNSUPPORTED,
                        error_message=routing_result.error_message or "Unsupported domain",
                        diagnostic_notes=[f"No registered adapter supported domain for {clean_url}"],
                        retrieved_at=timestamp
                    ))
                    continue

                # 3. Check maximum supported articles run limit
                if effective_max_articles is not None and supported_attempts_count >= effective_max_articles:
                    _add_result(ExtractionResult(
                        requested_url=clean_url,
                        success=False,
                        comments_status=CommentStatus.UNKNOWN,
                        error_message=f"Batch article collection limit reached ({effective_max_articles} articles)",
                        diagnostic_notes=[f"Skipped: max_articles limit ({effective_max_articles}) reached for batch run"],
                        retrieved_at=timestamp
                    ))
                    continue

                # 4. Apply inter-article delay BEFORE processing subsequent supported articles
                if supported_attempts_count > 0 and effective_delay > 0:
                    time.sleep(effective_delay)

                supported_attempts_count += 1

                # 5. Perform collection with complete exception isolation
                result = self._collect_single(
                    clean_url=clean_url,
                    adapter=adapter,
                    browser_manager=bm_instance,
                    max_comments=effective_max_comments,
                    topic_query=topic_query,
                    timestamp=timestamp
                )
                _add_result(result)

        finally:
            if bm_owner and bm_instance:
                bm_instance.__exit__(None, None, None)

        return results

    def collect_from_file(
        self,
        file_path: str = "data/input/urls.txt",
        browser_manager: Optional[BrowserManager] = None,
        max_comments: Optional[int] = None,
        max_articles: Optional[int] = None,
        inter_article_delay: Optional[float] = None,
        navigation_timeout_ms: Optional[int] = None,
        topic_query: Optional[str] = None
    ) -> List[ExtractionResult]:
        """
        Reads URLs line by line from a text file, ignoring empty lines and comments (#),
        and executes batch collection.
        """
        if not os.path.exists(file_path):
            timestamp = datetime.now(timezone.utc).isoformat()
            return [ExtractionResult(
                requested_url=file_path,
                success=False,
                comments_status=CommentStatus.EXTRACTION_ERROR,
                error_message=f"Input URL file not found: {file_path}",
                diagnostic_notes=[f"File path does not exist: {file_path}"],
                retrieved_at=timestamp
            )]

        urls: List[str] = []
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if line_str and not line_str.startswith("#"):
                    urls.append(line_str)

        return self.collect_urls(
            urls=urls,
            browser_manager=browser_manager,
            max_comments=max_comments,
            max_articles=max_articles,
            inter_article_delay=inter_article_delay,
            navigation_timeout_ms=navigation_timeout_ms,
            topic_query=topic_query
        )

    @staticmethod
    def _collect_single(
        clean_url: str,
        adapter: Any,
        browser_manager: BrowserManager,
        max_comments: int,
        topic_query: Optional[str],
        timestamp: str
    ) -> ExtractionResult:
        """
        Executes article loading, metadata extraction, body extraction, and comment extraction
        for a single URL with error isolation.
        """
        try:
            fetch_result = adapter.load_article(clean_url, browser_manager=browser_manager)
            if not fetch_result.success:
                return ExtractionResult(
                    requested_url=clean_url,
                    success=False,
                    comments_status=CommentStatus.UNKNOWN,
                    error_message=fetch_result.error_message or "Failed to load page content",
                    diagnostic_notes=[f"Fetch error: {fetch_result.error_type} - {fetch_result.error_message}"],
                    retrieved_at=fetch_result.retrieved_at or timestamp
                )

            metadata = adapter.extract_metadata(fetch_result.html, fallback_url=fetch_result.final_url)
            body_result = adapter.extract_article_body(fetch_result.html)
            comment_result = adapter.extract_comments(
                url=clean_url,
                html=fetch_result.html,
                browser_manager=browser_manager,
                max_comments=max_comments
            )

            article = Article(
                platform=adapter.platform_name,
                source_adapter=adapter.adapter_name,
                requested_url=clean_url,
                canonical_url=metadata.canonical_url or fetch_result.final_url,
                original_publisher=metadata.original_publisher,
                title=metadata.title,
                author=metadata.author,
                publication_datetime=metadata.publication_datetime,
                updated_datetime=metadata.updated_datetime,
                article_text=body_result.text,
                language=metadata.language,
                topic_query=topic_query,
                retrieved_at=fetch_result.retrieved_at or timestamp,
                comments_status=comment_result.status,
                comment_count_reported=comment_result.reported_count,
                comments_collected=comment_result.extracted_count,
                extraction_method=body_result.extraction_method,
                diagnostic_notes=comment_result.diagnostic_notes,
                comments=comment_result.comments
            )

            return ExtractionResult(
                requested_url=clean_url,
                success=True,
                article=article,
                comments_status=comment_result.status,
                diagnostic_notes=comment_result.diagnostic_notes,
                retrieved_at=fetch_result.retrieved_at or timestamp
            )

        except Exception as e:
            return ExtractionResult(
                requested_url=clean_url,
                success=False,
                comments_status=CommentStatus.EXTRACTION_ERROR,
                error_message=f"Unhandled collection error: {str(e)}",
                diagnostic_notes=[f"Exception raised during collection: {str(e)}"],
                retrieved_at=timestamp
            )
