"""
Shared WordPress comment and reply tree extraction module (Step 30A).
Parses standard WordPress comment HTML containers (ol.comment-list, ul.commentlist, etc.),
reconstructs parent-child reply trees, preserves comment depth and author names,
and filters out automated trackbacks / pingbacks.
"""
import re
from typing import List, Tuple, Optional
from bs4 import BeautifulSoup
from src.models import Comment


def parse_wordpress_comments(
    soup: BeautifulSoup,
    article_url: str,
    retrieved_at: str
) -> Tuple[List[Comment], int]:
    """
    Parses public WordPress comments from a BeautifulSoup page DOM.

    Returns:
        Tuple[List[Comment], int]: (Extracted comment list, Count of filtered trackbacks/pingbacks)
    """
    comments: List[Comment] = []
    trackback_count: int = 0

    comment_container = (
        soup.find("ol", class_="comment-list") or
        soup.find("ul", class_="comment-list") or
        soup.find("ol", class_="commentlist") or
        soup.find("ul", class_="commentlist") or
        soup.find("div", class_="comment-list")
    )

    if not comment_container:
        return comments, trackback_count

    # Top-level comment elements (direct children or top-level li)
    top_items = comment_container.find_all("li", recursive=False)
    if not top_items:
        top_items = comment_container.find_all("li", class_=lambda c: c and "comment" in c)

    for item in top_items:
        _extract_comment_node(
            node=item,
            parent_id=None,
            depth=0,
            article_url=article_url,
            retrieved_at=retrieved_at,
            comments_out=comments,
            trackback_count_out=trackback_count
        )

    # Calculate trackbacks filtered
    pingbacks = comment_container.find_all("li", class_=lambda c: c and ("pingback" in c or "trackback" in c))
    trackback_count = len(pingbacks)

    return comments, trackback_count


def _extract_comment_node(
    node,
    parent_id: Optional[str],
    depth: int,
    article_url: str,
    retrieved_at: str,
    comments_out: List[Comment],
    trackback_count_out: int
) -> None:
    """
    Recursively extracts a single WordPress comment item and its child replies.
    """
    classes = node.get("class", [])
    if isinstance(classes, list):
        class_str = " ".join(classes)
    else:
        class_str = str(classes)

    # Filter trackbacks / pingbacks
    if "pingback" in class_str or "trackback" in class_str:
        return

    # Extract comment ID
    raw_id = node.get("id")
    if raw_id and raw_id.startswith("comment-"):
        comment_id = raw_id
    elif raw_id and raw_id.startswith("li-comment-"):
        comment_id = raw_id.replace("li-comment-", "comment-")
    else:
        comment_id = f"comment-depth-{depth}-{len(comments_out) + 1}"

    # Extract Author Name
    author_elem = (
        node.find("cite", class_="fn") or
        node.find("span", class_="comment-author") or
        node.find("b", class_="fn") or
        node.find("div", class_="comment-author")
    )
    if author_elem:
        author = author_elem.get_text(strip=True)
        # Remove common "says:" suffixes if present
        author = re.sub(r"\s+says:$", "", author, flags=re.IGNORECASE)
    else:
        author = "Anonymous"

    # Extract Published Datetime
    time_elem = node.find("time")
    if time_elem and time_elem.get("datetime"):
        published_at = time_elem["datetime"].strip()
    elif time_elem:
        published_at = time_elem.get_text(strip=True)
    else:
        meta_date = node.find("a", class_=lambda c: c and ("comment-date" in c or "comment-time" in c))
        published_at = meta_date.get_text(strip=True) if meta_date else None

    # Extract Comment Body Text
    body_elem = (
        node.find("div", class_="comment-content") or
        node.find("div", class_="comment-body") or
        node.find("section", class_="comment-content")
    )

    if body_elem:
        # Clone body to avoid mutating DOM when parsing children
        body_clone = BeautifulSoup(str(body_elem), "html.parser")
        # Remove nested reply lists if they were accidentally captured inside body div
        for child_list in body_clone.find_all(["ol", "ul"], class_=lambda c: c and ("children" in c or "comment-list" in c)):
            child_list.decompose()
        comment_text = body_clone.get_text(separator="\n\n", strip=True)
    else:
        # Fallback: direct paragraphs in node before child list
        p_elems = node.find_all("p", recursive=False)
        comment_text = "\n\n".join(p.get_text(strip=True) for p in p_elems if p.get_text(strip=True))

    if not comment_text:
        return

    # Children / Nested Replies
    child_container = node.find(["ul", "ol"], class_=lambda c: c and "children" in c)
    child_items = child_container.find_all("li", recursive=False) if child_container else []

    comment_obj = Comment(
        comment_id=comment_id,
        article_url=article_url,
        parent_comment_id=parent_id,
        author_display_name=author,
        comment_text=comment_text,
        published_datetime=published_at,
        reactions=None,
        reply_count=len(child_items),
        depth=depth,
        retrieved_at=retrieved_at
    )
    comments_out.append(comment_obj)

    # Process child replies recursively
    for child in child_items:
        _extract_comment_node(
            node=child,
            parent_id=comment_id,
            depth=depth + 1,
            article_url=article_url,
            retrieved_at=retrieved_at,
            comments_out=comments_out,
            trackback_count_out=trackback_count_out
        )

