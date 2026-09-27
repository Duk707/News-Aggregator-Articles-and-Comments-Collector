from typing import Optional
from pydantic import BaseModel, Field


class CandidateArticle(BaseModel):
    """
    Data model representing a candidate news article discovered via public news discovery.
    Retains structured provenance describing the discovery provider, method, and search query.
    """
    title: str = Field(description="Headline title of candidate article")
    url: str = Field(description="Cleaned, validated candidate article URL")
    platform: str = Field(description="Platform name (e.g., Yahoo News, MSN)")
    source_domain: str = Field(description="Domain name (e.g., news.yahoo.com, www.msn.com)")
    snippet: Optional[str] = Field(default=None, description="Summary snippet from discovery RSS/metadata")
    publication_date: Optional[str] = Field(default=None, description="ISO publication timestamp parsed from RSS pubDate")
    discovery_query: str = Field(description="Main search query string used for discovery")
    discovery_provider: str = Field(default="Bing News RSS", description="Name of public discovery provider")
    discovery_method: str = Field(default="public_rss_feed", description="Mechanism used to locate candidate")
    discovered_at: str = Field(description="ISO timestamp when candidate was discovered")
