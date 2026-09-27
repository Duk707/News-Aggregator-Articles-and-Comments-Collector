from typing import Optional, Dict, Any
from src.collectors.base import BaseAdapter
from src.utils.urls import extract_domain
from src.browser import BrowserManager, BrowserFetchResult
from src.extraction.metadata import MetadataExtractor, ExtractedMetadata
from src.extraction.article_text import ArticleTextExtractor, ExtractedArticleText
from src.extraction.comments import (
    CommentDiagnosticInspector,
    CommentDiagnosticsResult,
    YahooCommentDeliveryEvidence,
    YahooCommentExtractor,
    CommentExtractionResult
)


class YahooAdapter(BaseAdapter):
    """
    Source adapter for Yahoo News and Yahoo ecosystem article platforms.
    """
    platform_name: str = "Yahoo News"
    adapter_name: str = "YahooAdapter"

    def supports(self, url: str) -> bool:
        """
        Returns True if the URL belongs to Yahoo News or supported Yahoo subdomains.
        """
        domain = extract_domain(url)
        if not domain:
            return False

        # Matches news.yahoo.com, finance.yahoo.com, yahoo.com, etc.
        return domain == "yahoo.com" or domain.endswith(".yahoo.com")

    def load_article(self, url: str, browser_manager: Optional[BrowserManager] = None) -> BrowserFetchResult:
        """
        Loads a Yahoo article URL using BrowserManager, recording navigation outcomes and diagnostic state.

        Args:
            url: The requested Yahoo article URL.
            browser_manager: Optional BrowserManager instance.

        Returns:
            BrowserFetchResult: Containing requested URL, final URL, HTTP status, HTML content, and diagnostics.
        """
        return self.load(url, browser_manager=browser_manager)

    def extract_metadata(self, html: str, fallback_url: Optional[str] = None) -> ExtractedMetadata:
        """
        Extracts structured metadata from Yahoo article HTML using ordered fallbacks.

        Args:
            html: HTML string.
            fallback_url: Optional fallback canonical URL.

        Returns:
            ExtractedMetadata: Extracted title, author, dates, publisher, canonical URL, and language.
        """
        return MetadataExtractor.extract(html, fallback_canonical_url=fallback_url)

    def extract_article_body(self, html: str) -> ExtractedArticleText:
        """
        Extracts clean main body text from Yahoo article HTML while excluding ads,
        recommendations, navigation, footers, and comments.

        Args:
            html: HTML string.

        Returns:
            ExtractedArticleText: Extracted body text and paragraph/character metrics.
        """
        return ArticleTextExtractor.extract(html)

    def inspect_comment_diagnostics(self, url: str, html: str, save_artifact: bool = True) -> CommentDiagnosticsResult:
        """
        Inspects page HTML for comment evidence and generates a diagnostic report
        with conservative preliminary comment status classification.

        Args:
            url: Evaluated article URL.
            html: Rendered page HTML.
            save_artifact: Whether to save JSON/HTML diagnostic artifacts to data/diagnostics.

        Returns:
            CommentDiagnosticsResult: Diagnostic findings and evidence.
        """
        result = CommentDiagnosticInspector.inspect(url, html)
        if save_artifact:
            CommentDiagnosticInspector.save_diagnostic_artifact(result, html=html)
        return result

    def investigate_comment_delivery(self, url: str, browser_manager: BrowserManager) -> YahooCommentDeliveryEvidence:
        """
        Interactively investigates how Yahoo delivers comments upon user activation of the 'View comments' control.

        Args:
            url: Target article URL.
            browser_manager: BrowserManager instance.

        Returns:
            YahooCommentDeliveryEvidence: Detailed investigation findings and observed mechanism.
        """
        return CommentDiagnosticInspector.investigate_comment_delivery_mechanism(url, browser_manager)

    def extract_comments(
        self,
        url: str,
        html: Optional[str] = None,
        browser_manager: Optional[BrowserManager] = None,
        max_comments: int = 50
    ) -> CommentExtractionResult:
        """
        Extracts public comments from Yahoo article HTML or via interactive Playwright rendering.

        Args:
            url: Article URL.
            html: Optional pre-loaded HTML content string.
            browser_manager: Optional BrowserManager instance for live interaction.
            max_comments: Maximum number of comments to extract.

        Returns:
            CommentExtractionResult: Extracted normalized comments, final status, and diagnostic notes.
        """
        return YahooCommentExtractor.extract(
            url=url,
            html=html,
            browser_manager=browser_manager,
            max_comments=max_comments
        )

    def get_loading_diagnostics(self, fetch_result: BrowserFetchResult) -> Dict[str, Any]:

        """
        Generates a diagnostic summary dictionary of the page loading attempt.
        """
        return {
            "platform": self.platform_name,
            "adapter": self.adapter_name,
            "requested_url": fetch_result.requested_url,
            "final_url": fetch_result.final_url,
            "status_code": fetch_result.status_code,
            "success": fetch_result.success,
            "error_type": fetch_result.error_type,
            "error_message": fetch_result.error_message,
            "retrieved_at": fetch_result.retrieved_at,
            "html_bytes": len(fetch_result.html.encode('utf-8')) if fetch_result.html else 0
        }


