from typing import Optional, List
from pydantic import BaseModel, Field
from src.models.comment_status import CommentStatus
from src.models.comment import Comment


class Article(BaseModel):
    """
    Normalized data model for a collected news article and associated comments.
    """
    platform: str = Field(description="Name of the news platform (e.g., Yahoo News, MSN)")
    source_adapter: str = Field(description="Class name of the adapter handling this platform")
    requested_url: str = Field(description="Initial URL requested for collection")
    canonical_url: Optional[str] = Field(default=None, description="Canonical URL resolved from HTML/meta")
    original_publisher: Optional[str] = Field(default=None, description="Original content publisher (e.g., Reuters, AP)")
    title: Optional[str] = Field(default=None, description="Article title/headline")
    author: Optional[str] = Field(default=None, description="Article author or byline")
    publication_datetime: Optional[str] = Field(default=None, description="Original publication timestamp")
    updated_datetime: Optional[str] = Field(default=None, description="Last updated timestamp if available")
    article_text: Optional[str] = Field(default=None, description="Cleaned main body text of the article")
    language: Optional[str] = Field(default=None, description="Language code (e.g., en-US)")
    topic_query: Optional[str] = Field(
        default=None,
        alias="topic/query",
        description="Associated topic or search term (e.g., AI in Education)"
    )
    retrieved_at: str = Field(description="ISO timestamp when the article was collected")
    comments_status: CommentStatus = Field(
        default=CommentStatus.UNKNOWN,
        description="Categorized accessibility status of public comments"
    )
    comment_count_reported: Optional[int] = Field(default=None, description="Comment count reported by site metadata/UI")
    comments_collected: int = Field(default=0, description="Total number of comments successfully extracted")
    extraction_method: Optional[str] = Field(default=None, description="Primary method used to extract article content")
    diagnostic_notes: List[str] = Field(default_factory=list, description="Diagnostic logs and extraction notes")
    comments: List[Comment] = Field(default_factory=list, description="List of collected Comment objects")

    model_config = {
        "populate_by_name": True,
        "serialize_by_alias": True
    }
