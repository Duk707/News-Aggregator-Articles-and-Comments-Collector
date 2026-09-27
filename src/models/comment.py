from typing import Optional, Union, Dict, Any
from pydantic import BaseModel, Field


class Comment(BaseModel):
    """
    Normalized data model for a single public comment or reply.
    """
    comment_id: str = Field(description="Unique identifier for the comment within the platform")
    article_url: str = Field(description="URL of the associated article")
    parent_comment_id: Optional[str] = Field(default=None, description="Parent comment ID if this is a reply")
    author_display_name: Optional[str] = Field(default=None, description="Public display name of the comment author")
    comment_text: str = Field(description="Raw text content of the comment")
    published_datetime: Optional[str] = Field(default=None, description="Publication timestamp of the comment")
    reactions: Union[int, Dict[str, Any], None] = Field(default=None, description="Public reaction count or reaction breakdown")
    reply_count: int = Field(default=0, description="Number of direct replies to this comment")
    depth: int = Field(default=0, description="Nesting depth (0 for top-level comment)")
    retrieved_at: str = Field(description="ISO timestamp when the comment was retrieved")

    model_config = {
        "populate_by_name": True,
        "serialize_by_alias": True
    }
