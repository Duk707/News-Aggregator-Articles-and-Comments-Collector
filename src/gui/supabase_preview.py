"""
GUI presentation and preview helper module for Supabase staging data.
Isolates Treeview formatting, column definitions, text truncation, detail inspection rendering,
and preview tab layout logic from application models and core validation routines.
"""
import tkinter as tk
from tkinter import ttk, scrolledtext
from typing import Tuple, Optional, List, Dict, Any, Union

from src.integrations.supabase.models import (
    SupabaseArticleRow,
    SupabaseCommentRow,
    SupabaseStagingDataset
)


# Column tuple definition for Articles (14 columns in exact schema contract order)
SUPABASE_ARTICLE_COLUMNS = (
    "id",
    "title",
    "content",
    "source",
    "created_at",
    "url",
    "author",
    "published_date",
    "content_hash",
    "clean_content",
    "processing_status",
    "processing_note",
    "processed_at",
    "is_relevant"
)

# Column tuple definition for Comments (5 columns in exact schema contract order)
SUPABASE_COMMENT_COLUMNS = (
    "id",
    "article_id",
    "text",
    "created_at",
    "parent_comment_id"
)


def truncate_text(text: Optional[str], max_len: int = 55) -> str:
    """
    Truncates a string value for table cell display if it exceeds max_len.
    Returns empty string for None values.
    """
    if text is None:
        return ""
    clean = text.replace("\n", " ").replace("\r", " ").strip()
    if len(clean) > max_len:
        return clean[:max_len] + "..."
    return clean


def format_supabase_article_tree_row(row: SupabaseArticleRow) -> Tuple:
    """
    Formats all 14 SupabaseArticleRow fields into a tuple for Treeview cell display,
    applying text truncation to long strings for clean table presentation.
    """
    return (
        str(row.id),
        truncate_text(row.title, 45),
        truncate_text(row.content, 45),
        row.source or "",
        row.created_at or "(DB Default)",
        truncate_text(row.url, 45),
        row.author or "",
        row.published_date or "",
        truncate_text(row.content_hash, 16),
        truncate_text(row.clean_content, 45),
        row.processing_status or "(NULL)",
        row.processing_note or "(NULL)",
        row.processed_at or "(NULL)",
        str(row.is_relevant) if row.is_relevant is not None else "(DB Default)"
    )


def format_supabase_comment_tree_row(row: SupabaseCommentRow) -> Tuple:
    """
    Formats all 5 SupabaseCommentRow fields into a tuple for Treeview cell display,
    applying text truncation to long comment text for clean table presentation.
    """
    return (
        str(row.id),
        str(row.article_id),
        truncate_text(row.text, 65),
        row.created_at or "(DB Default)",
        str(row.parent_comment_id) if row.parent_comment_id is not None else "(Root)"
    )


def format_supabase_article_detail(row: SupabaseArticleRow) -> str:
    """
    Renders complete, un-truncated article details for the Inspection ScrolledText area.
    """
    lines = [
        f"=== SUPABASE ARTICLE ROW INSPECTION (Staging ID: {row.id}) ===",
        f"Database Table: public.articles",
        f"Staging ID:     {row.id} (Temporary negative bigint)",
        f"Title:          {row.title or '(None)'}",
        f"Canonical URL:  {row.url or '(None)'}",
        f"Original Source:{row.source or '(None)'}",
        f"Author:         {row.author or '(None)'}",
        f"Pub Date:       {row.published_date or '(None)'}",
        f"Created At:     {row.created_at or '(Omitted - Database Default now() will apply)'}",
        f"Is Relevant:    {row.is_relevant if row.is_relevant is not None else '(Omitted - Database Default true will apply)'}",
        f"Content Hash:   {row.content_hash or '(None - Body empty)'}",
        f"Proc Status:    {row.processing_status or '(NULL - No AI processing)'}",
        f"Proc Note:      {row.processing_note or '(NULL)'}",
        f"Processed At:   {row.processed_at or '(NULL)'}",
        "",
        "--- Full Un-truncated Clean Content Body ---",
        row.clean_content or "(No content body text extracted)",
        "",
        "--- Full Un-truncated Content Text ---",
        row.content or "(No content body text extracted)"
    ]
    return "\n".join(lines)


def format_supabase_comment_detail(row: SupabaseCommentRow) -> str:
    """
    Renders complete, un-truncated comment details for the Inspection ScrolledText area.
    """
    lines = [
        f"=== SUPABASE COMMENT ROW INSPECTION (Staging ID: {row.id}) ===",
        f"Database Table:   public.comments",
        f"Staging ID:       {row.id} (Temporary negative bigint - globally unique)",
        f"Article Staging ID: {row.article_id}",
        f"Parent Comment ID:  {row.parent_comment_id if row.parent_comment_id is not None else '(Root Comment / Top-Level)'}",
        f"Created At:       {row.created_at or '(Omitted - Database Default now() will apply)'}",
        "",
        "--- Full Un-truncated Comment Text ---",
        row.text or "(Empty comment text)"
    ]
    return "\n".join(lines)

