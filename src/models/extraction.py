from typing import Optional, List
from pydantic import BaseModel, Field
from src.models.comment_status import CommentStatus
from src.models.article import Article


class ExtractionResult(BaseModel):
    """
    Standardized result wrapper returned by source adapters after collection attempt.
    """
    requested_url: str = Field(description="URL requested for collection")
    success: bool = Field(description="True if article content was successfully extracted")
    article: Optional[Article] = Field(default=None, description="Extracted Article instance if successful")
    comments_status: CommentStatus = Field(default=CommentStatus.UNKNOWN, description="Comment status summary")
    error_message: Optional[str] = Field(default=None, description="Error message if extraction failed")
    diagnostic_notes: List[str] = Field(default_factory=list, description="Collection and diagnostic notes")
    retrieved_at: str = Field(description="ISO timestamp of collection run")

    model_config = {
        "populate_by_name": True,
        "serialize_by_alias": True
    }
