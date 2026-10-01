from typing import Optional, List
from pydantic import BaseModel, Field
from src.models.article import Article


class SupabaseArticleRow(BaseModel):
    """
    Data model representing a single row compatible with the public.articles Supabase table schema.
    """
    id: int = Field(description="Temporary negative bigint staging ID (e.g. -1, -2)")
    title: Optional[str] = Field(default=None, description="Article headline/title")
    content: Optional[str] = Field(default=None, description="Cleaned main body text of the article")
    source: Optional[str] = Field(default=None, description="Original publisher or platform fallback")
    created_at: Optional[str] = Field(default=None, description="Omitted upon insertion to use DB default now()")
    url: Optional[str] = Field(default=None, description="Canonical URL with requested URL fallback")
    author: Optional[str] = Field(default=None, description="Article author or publisher byline")
    published_date: Optional[str] = Field(default=None, description="ISO-8601 publication timestamp")
    content_hash: Optional[str] = Field(default=None, description="SHA-256 hex digest of normalized article text")
    clean_content: Optional[str] = Field(default=None, description="Cleaned article content")
    processing_status: Optional[str] = Field(default=None, description="Intentionally nullable/unset (AI pipeline reserved)")
    processing_note: Optional[str] = Field(default=None, description="Intentionally nullable/unset (AI pipeline reserved)")
    processed_at: Optional[str] = Field(default=None, description="Intentionally nullable/unset (AI pipeline reserved)")
    is_relevant: Optional[bool] = Field(default=None, description="Omitted upon insertion to use DB default true")

    model_config = {
        "populate_by_name": True,
        "serialize_by_alias": True
    }


class SupabaseCommentRow(BaseModel):
    """
    Data model representing a single row compatible with the public.comments Supabase table schema.
    """
    id: int = Field(description="Temporary negative bigint staging ID globally unique across dataset")
    article_id: int = Field(description="Temporary negative bigint staging ID of parent article")
    text: str = Field(description="Text content of comment")
    created_at: Optional[str] = Field(default=None, description="ISO-8601 creation timestamp or None for DB default now()")
    parent_comment_id: Optional[int] = Field(default=None, description="Temporary negative staging ID of parent comment")

    model_config = {
        "populate_by_name": True,
        "serialize_by_alias": True
    }


class SupabaseStagingDataset(BaseModel):
    """
    Staging container holding mapped Supabase-compatible rows, original collector models, and validation metrics.
    """
    articles: List[SupabaseArticleRow] = Field(default_factory=list, description="Staged article rows")
    comments: List[SupabaseCommentRow] = Field(default_factory=list, description="Staged comment rows")
    source_articles: List[Article] = Field(default_factory=list, description="Preserved original rich collector Article objects")
    validation_errors: List[str] = Field(default_factory=list, description="Critical validation error messages")
    validation_warnings: List[str] = Field(default_factory=list, description="Validation warning messages")

    model_config = {
        "populate_by_name": True,
        "serialize_by_alias": True
    }
