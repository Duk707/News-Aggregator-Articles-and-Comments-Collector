"""
GUI input validation, URL parsing, and formatting helpers.
Separated from Tkinter widget rendering to enable deterministic automated testing.
"""
from typing import List, Tuple, Optional, Dict, Any
from src.models.extraction import ExtractionResult
from src.models.comment_status import CommentStatus


def parse_url_input(raw_text: str) -> List[str]:
    """
    Parses a multiline string into a list of cleaned, non-empty URL strings.
    Ignores empty lines and comment lines starting with '#'.
    """
    if not raw_text:
        return []

    urls: List[str] = []
    for line in raw_text.splitlines():
        line_str = line.strip()
        if line_str and not line_str.startswith("#"):
            urls.append(line_str)
    return urls


def validate_gui_config(
    inter_article_delay_str: str,
    max_articles_str: str,
    max_comments_str: str,
    navigation_timeout_str: str,
    topic_str: Optional[str] = None
) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """
    Validates user configuration inputs for the collection pipeline.

    Rules:
    - inter_article_delay: float >= 0.0
    - max_articles: int > 0
    - max_comments_per_article: int >= 0
    - navigation_timeout (sec): float > 0.0 -> converted to ms integer
    - topic_str: optional string; trimmed once if non-empty, None if empty/blank

    Returns:
        Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        (is_valid, parsed_config_dict, error_message_if_invalid)
    """
    # 1. Validate inter_article_delay
    try:
        delay = float(inter_article_delay_str)
        if delay < 0.0:
            return False, None, "Inter-article delay must be non-negative (>= 0.0 seconds)."
    except ValueError:
        return False, None, f"Invalid inter-article delay value: '{inter_article_delay_str}'. Must be a number."

    # 2. Validate max_articles
    try:
        max_articles = int(max_articles_str)
        if max_articles <= 0:
            return False, None, "Max articles limit must be a positive integer (> 0)."
    except ValueError:
        return False, None, f"Invalid max articles limit value: '{max_articles_str}'. Must be an integer."

    # 3. Validate max_comments
    try:
        max_comments = int(max_comments_str)
        if max_comments < 0:
            return False, None, "Max comments limit must be non-negative (>= 0)."
    except ValueError:
        return False, None, f"Invalid max comments value: '{max_comments_str}'. Must be an integer."

    # 4. Validate navigation_timeout
    try:
        timeout_sec = float(navigation_timeout_str)
        if timeout_sec <= 0.0:
            return False, None, "Navigation timeout must be greater than zero (> 0 seconds)."
        timeout_ms = int(timeout_sec * 1000)
    except ValueError:
        return False, None, f"Invalid navigation timeout value: '{navigation_timeout_str}'. Must be a number."

    # 5. Parse and normalize optional topic string
    topic_query: Optional[str] = None
    if topic_str and topic_str.strip():
        topic_query = topic_str.strip()

    parsed_config = {
        "inter_article_delay": delay,
        "max_articles": max_articles,
        "max_comments_per_article": max_comments,
        "navigation_timeout_ms": timeout_ms,
        "topic_query": topic_query
    }
    return True, parsed_config, None


def format_result_log_line(result: ExtractionResult, index: int, total: int) -> str:
    """
    Formats an ExtractionResult into a concise progress log line for the GUI log display.
    """
    prefix = f"[{index}/{total}]"
    if result.success and result.article:
        art = result.article
        platform = art.platform or "Unknown"
        title_snippet = art.title[:45] + "..." if art.title and len(art.title) > 45 else (art.title or "Untitled")
        comments_info = f"{art.comments_collected} comments ({art.comments_status.value})"
        return f"{prefix} SUCCESS ({platform}): \"{title_snippet}\" - {comments_info}"
    elif result.comments_status == CommentStatus.UNSUPPORTED:
        return f"{prefix} UNSUPPORTED: {result.requested_url} ({result.error_message or 'No adapter'})"
    elif "Duplicate" in (result.error_message or ""):
        return f"{prefix} DUPLICATE: {result.requested_url} (Skipped)"
    elif "limit reached" in (result.error_message or "").lower():
        return f"{prefix} SKIPPED (LIMIT): {result.requested_url}"
    else:
        err = result.error_message or "Unknown failure"
        return f"{prefix} FAILED: {result.requested_url} ({err})"


def format_article_table_row(result: ExtractionResult) -> Tuple[str, str, str, str, str, str, str, str, str]:
    """
    Formats an ExtractionResult into a 9-tuple cell row for the Research Results Treeview table:
    (Platform, Title, Publisher, Pub Date, Article Status, Comment Status, Reported, Collected, Diagnostic / Method)
    """
    if result.article:
        art = result.article
        platform = art.platform or "Unknown"
        title = art.title or "[Untitled Article]"
        publisher = art.original_publisher or "N/A"
        pub_date = art.publication_datetime or "N/A"
        if isinstance(pub_date, str) and len(pub_date) > 19:
            pub_date = pub_date[:19].replace("T", " ")
        art_status = "SUCCESS" if result.success else "PARTIAL"
        comment_status = art.comments_status.value if art.comments_status else "UNKNOWN"
        reported = str(art.comment_count_reported) if art.comment_count_reported is not None else "N/A"
        collected = str(art.comments_collected)
        notes_str = "; ".join(result.diagnostic_notes) if result.diagnostic_notes else ""
        method_or_note = art.extraction_method or notes_str or "N/A"
    else:
        # Determine status and platform from URL/result for failure cases
        url_lower = result.requested_url.lower()
        if "yahoo.com" in url_lower:
            platform = "Yahoo"
        elif "msn.com" in url_lower:
            platform = "MSN"
        else:
            platform = "Unknown"

        publisher = "N/A"
        pub_date = "N/A"
        collected = "0"
        reported = "N/A"

        if result.comments_status == CommentStatus.UNSUPPORTED or "unsupported" in (result.error_message or "").lower():
            art_status = "UNSUPPORTED"
            title = "[Unsupported Domain]"
        elif "duplicate" in (result.error_message or "").lower():
            art_status = "DUPLICATE"
            title = "[Duplicate Skipped]"
        elif "limit reached" in (result.error_message or "").lower():
            art_status = "RUN_LIMIT"
            title = "[Max Articles Limit Reached]"
        else:
            art_status = "FETCH_FAILED"
            title = "[Article Extraction Failed]"

        comment_status = result.comments_status.value if result.comments_status else "UNKNOWN"
        notes_str = "; ".join(result.diagnostic_notes) if result.diagnostic_notes else ""
        method_or_note = result.error_message or notes_str or "N/A"

    return (
        platform,
        title,
        publisher,
        str(pub_date),
        art_status,
        comment_status,
        reported,
        collected,
        method_or_note
    )


def format_article_detail_text(result: ExtractionResult) -> str:
    """
    Formats an ExtractionResult into a detailed multi-line text string for the research inspection panel.
    """
    lines: List[str] = [
        "=" * 70,
        "ARTICLE METADATA & RESEARCH INSPECTION DETAILS",
        "=" * 70,
        f"Requested URL:      {result.requested_url}"
    ]

    if result.article:
        art = result.article
        lines.extend([
            f"Canonical URL:      {art.canonical_url or 'N/A'}",
            f"Platform:           {art.platform or 'Unknown'}",
            f"Source Adapter:     {art.source_adapter or 'N/A'}",
            f"Original Publisher: {art.original_publisher or 'N/A'}",
            f"Title:              {art.title or 'N/A'}",
            f"Author:             {art.author or 'N/A'}",
            f"Publication Time:   {art.publication_datetime or 'N/A'}",
            f"Updated Time:       {art.updated_datetime or 'N/A'}",
            f"Language:           {art.language or 'N/A'}",
            f"Topic/Query:        {getattr(art, 'topic_query', None) or 'N/A'}",
            f"Retrieved At:       {art.retrieved_at or 'N/A'}",
            "-" * 70,
            "EXTRACTION STATUS & PROVENANCE",
            "-" * 70,
            f"Article Success:    {'SUCCESS' if result.success else 'FAILED'}",
            f"Extraction Method:  {art.extraction_method or 'N/A'}",
            f"Comment Status:     {art.comments_status.value if art.comments_status else 'N/A'}",
            f"Reported Count:     {art.comment_count_reported if art.comment_count_reported is not None else 'N/A'}",
            f"Collected Count:    {art.comments_collected}",
            f"Diagnostic Notes:   {'; '.join(result.diagnostic_notes or art.diagnostic_notes) if (result.diagnostic_notes or art.diagnostic_notes) else 'None'}",
            f"Error Message:      {result.error_message or 'None'}",
            "-" * 70,
            "ARTICLE BODY TEXT PREVIEW",
            "-" * 70
        ])
        if art.article_text:
            text_preview = art.article_text[:1000]
            if len(art.article_text) > 1000:
                text_preview += f"\n... [Truncated {len(art.article_text) - 1000} additional characters]"
            lines.append(text_preview)
        else:
            lines.append("[No article body text extracted]")

        lines.extend([
            "-" * 70,
            "COMMENTS SUMMARY",
            "-" * 70
        ])
        if art.comments and len(art.comments) > 0:
            lines.append(f"Total Comments Collected: {len(art.comments)} (Status: {art.comments_status.value})")
            lines.append(f"Sample Comment 1 Author: {art.comments[0].author_display_name or 'Anonymous'}")
            comment_snippet = art.comments[0].comment_text[:200] if art.comments[0].comment_text else ""
            lines.append(f"Sample Comment 1 Text:   \"{comment_snippet}...\"")
        else:
            lines.append(f"No comments collected. (Status: {art.comments_status.value})")
    else:
        lines.extend([
            f"Article Status:     {'SUCCESS' if result.success else 'FAILED'}",
            f"Comment Status:     {result.comments_status.value if result.comments_status else 'UNKNOWN'}",
            f"Diagnostic Notes:   {result.diagnostic_notes or 'N/A'}",
            f"Error Message:      {result.error_message or 'None'}",
            "-" * 70,
            "ARTICLE BODY TEXT PREVIEW",
            "-" * 70,
            "[Article fetch/extraction was not successful; no body text available.]",
            "-" * 70,
            "COMMENTS SUMMARY",
            "-" * 70,
            f"No comments available. (Status: {result.comments_status.value if result.comments_status else 'UNKNOWN'})"
        ])

    lines.append("=" * 70)
    return "\n".join(lines)

