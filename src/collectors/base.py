from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional
from src.models import ExtractionResult, CommentStatus
from src.browser import BrowserManager, BrowserFetchResult


class BaseAdapter(ABC):
    """
    Abstract Base Class for platform-specific source adapters.
    """
    platform_name: str = "Base Platform"
    adapter_name: str = "BaseAdapter"

    @abstractmethod
    def supports(self, url: str) -> bool:
        """
        Determines whether this adapter supports extracting content from the given URL.

        Args:
            url: The URL to evaluate.

        Returns:
            bool: True if the adapter recognizes and supports the domain/URL.
        """
        pass

    def supports_html(self, url: str, html: str) -> bool:
        """
        Optional post-fetch platform detection probe (Step 30A.1).
        Inspects page HTML for characteristic platform meta generator tags, script CDN paths, or DOM elements.
        Default implementation returns False.
        """
        return False

    def load(self, url: str, browser_manager: Optional[BrowserManager] = None) -> BrowserFetchResult:
        """
        Loads the public web page for the specified URL using BrowserManager.

        Args:
            url: The requested URL string.
            browser_manager: Optional existing BrowserManager instance.

        Returns:
            BrowserFetchResult: Containing raw page HTML, final URL, status code, and diagnostics.
        """
        if not self.supports(url):
            return BrowserFetchResult(
                requested_url=url,
                success=False,
                error_type="UNSUPPORTED",
                error_message=f"URL '{url}' is not supported by {self.adapter_name}",
                retrieved_at=datetime.now(timezone.utc).isoformat()
            )

        if browser_manager:
            return browser_manager.fetch_page(url)
        else:
            with BrowserManager(headless=True) as bm:
                return bm.fetch_page(url)

    def extract(self, url: str, **kwargs) -> ExtractionResult:
        """
        Main extraction entry point for this adapter.
        To be implemented in future build steps.
        """
        raise NotImplementedError("Article and comment extraction logic will be built in subsequent steps.")
