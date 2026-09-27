from typing import Optional
from pydantic import BaseModel, Field


class CollectorConfig(BaseModel):
    """
    Central operational safety configuration for rate limits, run limits, and timeouts.
    """
    inter_article_delay: float = Field(
        default=2.0,
        description="Delay in seconds applied between successive supported article collection attempts in batch mode."
    )
    max_articles: Optional[int] = Field(
        default=50,
        description="Maximum number of supported articles allowed to be collected in a single batch run (None for unlimited)."
    )
    max_comments_per_article: int = Field(
        default=50,
        description="Maximum number of comments to extract per article."
    )
    navigation_timeout_ms: int = Field(
        default=30000,
        description="Navigation timeout in milliseconds for Playwright browser operations."
    )
    request_delay_ms: int = Field(
        default=0,
        description="Low-level page request delay in milliseconds enforced inside BrowserManager."
    )
    topic_query: Optional[str] = Field(
        default=None,
        description="Optional topic or search phrase associated with this collection run (e.g., AI in Education)."
    )

    model_config = {
        "populate_by_name": True,
        "serialize_by_alias": True
    }
