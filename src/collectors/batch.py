import os
import time
import urllib.parse
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


def is_eligible_for_civic_fallback(clean_url: str) -> bool:
    """
    Evaluates whether an unsupported URL is eligible for post-fetch civic platform probing (Step 30A.1).
    Enforces strict exclusions:
    - Must be a valid public http/https URL.
    - Blocks localhost, loopback, private IP ranges (10.x, 172.16-31.x, 192.168.x, 169.254.x).
    - Requires an explicit civic/public-consultation path pattern (/projects/, /consultation/, /public-input/, /civic/, /discussion/, /topics/, /engage/).
    - Normal research topic_query is NOT sufficient by itself.
    """
    try:
        parsed = urllib.parse.urlparse(clean_url)
    except Exception:
        return False

    if parsed.scheme.lower() not in ("http", "https"):
        return False

    host = (parsed.hostname or "").lower().strip()
    if not host:
        return False

    # Private / Localhost / Loopback / Reserved target exclusions
    if (
        host in ("localhost", "127.0.0.1", "::1") or
        host.startswith("10.") or
        host.startswith("192.168.") or
        host.startswith("169.254.")
    ):
        return False

    if host.startswith("172."):
        parts = host.split(".")
        if len(parts) >= 2 and parts[1].isdigit():
            val = int(parts[1])
            if 16 <= val <= 31:
                return False

    # Explicit civic/public-consultation path pattern requirement
    path = (parsed.path or "").lower()
    civic_path_patterns = [
        "/projects/",
        "/consultation/",
        "/public-input/",
        "/civic/",
        "/discussion/",
        "/topics/",
        "/engage/"
    ]

    return any(pattern in path for pattern in civic_path_patterns) or host.startswith("engage.")


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
        Supports post-fetch platform fallback probing for eligible civic/public-institution URLs.
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

                # 2. Fast-Path Route URL to adapter
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

                # 3. Fallback Post-Fetch Probe Branch for Unsupported Civic Candidate URLs
                if not routing_result.supported or not adapter:
                    if is_eligible_for_civic_fallback(clean_url):
                        # Execute single fallback fetch
                        fetch_res = bm_instance.fetch_page(clean_url)

                        if not fetch_res.success:
                            # Map error type to proper CommentStatus
                            if fetch_res.error_type == "BLOCKED":
                                err_status = CommentStatus.BLOCKED
                            elif fetch_res.error_type in ("NOT_LOADED", "TIMEOUT"):
                                err_status = CommentStatus.NOT_LOADED
                            else:
                                err_status = CommentStatus.UNKNOWN

                            _add_result(ExtractionResult(
                                requested_url=clean_url,
                                success=False,
                                comments_status=err_status,
                                error_message=fetch_res.error_message or "Fallback page fetch failed",
                                diagnostic_notes=[f"Fallback fetch error: {fetch_res.error_type} - {fetch_res.error_message}"],
                                retrieved_at=fetch_res.retrieved_at or timestamp
                            ))
                            continue

                        if fetch_res.html:
                            probe_result, claimed_adapter = self.router.route_by_html(clean_url, fetch_res.html)
                            if probe_result.supported and claimed_adapter:
                                # HTML Reuse: pass already-fetched html directly to extract() — ZERO second fetch
                                if supported_attempts_count > 0 and effective_delay > 0:
                                    time.sleep(effective_delay)
                                supported_attempts_count += 1

                                result = self._extract_with_preloaded_html(
                                    clean_url=clean_url,
                                    adapter=claimed_adapter,
                                    fetch_result=fetch_res,
                                    max_comments=effective_max_comments,
                                    topic_query=topic_query,
                                    timestamp=timestamp
                                )
                                _add_result(result)
                                continue

                    # Unclaimed URL or non-eligible unsupported URL
                    _add_result(ExtractionResult(
                        requested_url=clean_url,
                        success=False,
                        comments_status=CommentStatus.UNSUPPORTED,
                        error_message=routing_result.error_message or "Unsupported domain",
                        diagnostic_notes=[f"No registered adapter supported domain or HTML fingerprints for {clean_url}"],
                        retrieved_at=timestamp
                    ))
                    continue

                # 4. Standard Supported Fast-Path Adapter Execution
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

                if supported_attempts_count > 0 and effective_delay > 0:
                    time.sleep(effective_delay)

                supported_attempts_count += 1

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

    @staticmethod
    def _extract_with_preloaded_html(
        clean_url: str,
        adapter: Any,
        fetch_result: Any,
        max_comments: int,
        topic_query: Optional[str],
        timestamp: str
    ) -> ExtractionResult:
        """
        Executes adapter extraction using already-fetched HTML — guarantees zero duplicate network fetches.
        """
        try:
            return adapter.extract(clean_url, html=fetch_result.html, topic_query=topic_query)
        except Exception as e:
            return ExtractionResult(
                requested_url=clean_url,
                success=False,
                comments_status=CommentStatus.EXTRACTION_ERROR,
                error_message=f"Unhandled collection error: {str(e)}",
                diagnostic_notes=[f"Exception raised during fallback collection: {str(e)}"],
                retrieved_at=timestamp
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
