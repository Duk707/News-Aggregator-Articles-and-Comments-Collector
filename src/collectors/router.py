from typing import List, Optional, Tuple
from pydantic import BaseModel, Field, ConfigDict
from src.collectors.base import BaseAdapter
from src.collectors.yahoo import YahooAdapter
from src.collectors.msn import MSNAdapter
from src.collectors.tesl_ontario import TESLOntarioAdapter
from src.collectors.hepi import HEPIAdapter
from src.collectors.engagement_hq import EngagementHQAdapter
from src.collectors.cult_of_pedagogy import CultOfPedagogyAdapter
from src.collectors.spencer_education import SpencerEducationAdapter
from src.collectors.wonkhe import WonkheAdapter
from src.models.comment_status import CommentStatus
from src.utils.urls import validate_url, normalize_url


class RoutingResult(BaseModel):
    """
    Standardized result object returned by SourceRouter.
    """
    url: str = Field(description="Normalized input URL")
    is_valid: bool = Field(description="True if URL is syntactically valid")
    supported: bool = Field(description="True if a registered adapter supports the domain")
    adapter_name: Optional[str] = Field(default=None, description="Name of matching adapter class")
    platform_name: Optional[str] = Field(default=None, description="Name of news platform")
    status: CommentStatus = Field(default=CommentStatus.UNKNOWN, description="Preliminary comment status")
    error_message: Optional[str] = Field(default=None, description="Validation or routing error message")

    model_config = ConfigDict(arbitrary_types_allowed=True)


class SourceRouter:
    """
    Central router that validates input URLs and dispatches them to appropriate source adapters.
    """
    def __init__(self, adapters: Optional[List[BaseAdapter]] = None):
        """
        Initializes SourceRouter with registered platform adapters.
        """
        if adapters is not None:
            self.adapters = adapters
        else:
            self.adapters = [
                YahooAdapter(),
                MSNAdapter(),
                TESLOntarioAdapter(),
                HEPIAdapter(),
                EngagementHQAdapter(),
                CultOfPedagogyAdapter(),
                SpencerEducationAdapter(),
                WonkheAdapter()
            ]

    def register_adapter(self, adapter: BaseAdapter) -> None:
        """
        Registers a new source adapter dynamically.
        """
        self.adapters.append(adapter)

    def route(self, url: str) -> Tuple[RoutingResult, Optional[BaseAdapter]]:
        """
        Validates URL and routes it to the matching adapter.

        Args:
            url: The requested URL string.

        Returns:
            Tuple[RoutingResult, Optional[BaseAdapter]]:
                Routing metadata and the instantiated matched adapter (or None if invalid/unsupported).
        """
        clean_url = normalize_url(url)

        # 1. Validate URL syntax
        if not validate_url(clean_url):
            return RoutingResult(
                url=clean_url if clean_url else str(url),
                is_valid=False,
                supported=False,
                status=CommentStatus.UNSUPPORTED,
                error_message="Invalid or malformed URL syntax"
            ), None

        # 2. Match registered adapters
        for adapter in self.adapters:
            if adapter.supports(clean_url):
                return RoutingResult(
                    url=clean_url,
                    is_valid=True,
                    supported=True,
                    adapter_name=adapter.adapter_name,
                    platform_name=adapter.platform_name,
                    status=CommentStatus.UNKNOWN,
                    error_message=None
                ), adapter

        # 3. No adapter supported
        return RoutingResult(
            url=clean_url,
            is_valid=True,
            supported=False,
            status=CommentStatus.UNSUPPORTED,
            error_message="Unsupported news website domain"
        ), None

    def route_by_html(self, url: str, html: str) -> Tuple[RoutingResult, Optional[BaseAdapter]]:
        """
        Post-fetch platform detection probe (Step 30A.1).
        Inspects fetched page HTML using supports_html() contract on registered adapters.
        """
        clean_url = normalize_url(url)
        if not html:
            return RoutingResult(
                url=clean_url,
                is_valid=True,
                supported=False,
                status=CommentStatus.UNSUPPORTED,
                error_message="No HTML content available for fallback platform detection"
            ), None

        for adapter in self.adapters:
            if hasattr(adapter, "supports_html") and adapter.supports_html(clean_url, html):
                return RoutingResult(
                    url=clean_url,
                    is_valid=True,
                    supported=True,
                    adapter_name=adapter.adapter_name,
                    platform_name=adapter.platform_name,
                    status=CommentStatus.UNKNOWN,
                    error_message=None
                ), adapter

        return RoutingResult(
            url=clean_url,
            is_valid=True,
            supported=False,
            status=CommentStatus.UNSUPPORTED,
            error_message="No registered adapter matched page HTML fingerprints"
        ), None
