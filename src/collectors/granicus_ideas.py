"""
Granicus Ideas Source Adapter (Step 30C.1).
Extracts agenda item records and publicly readable reader comments from Granicus Ideas pages (*.granicusideas.com).
"""
import re
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup

from src.collectors.base import BaseAdapter
from src.models import Article, ExtractionResult, CommentStatus, Comment
from src.utils.urls import normalize_url

TZ_OFFSETS = {
    "PDT": timezone(timedelta(hours=-7)),
    "PST": timezone(timedelta(hours=-8)),
    "EDT": timezone(timedelta(hours=-4)),
    "EST": timezone(timedelta(hours=-5)),
    "CDT": timezone(timedelta(hours=-5)),
    "CST": timezone(timedelta(hours=-6)),
    "MDT": timezone(timedelta(hours=-6)),
    "MST": timezone(timedelta(hours=-7)),
    "UTC": timezone.utc,
    "GMT": timezone.utc,
}


def parse_granicus_timestamp(raw_text: str) -> Optional[str]:
    """
    Parses Granicus Ideas timestamp strings (e.g. "October 03, 2026 at 12:38am PDT", "2026-08-12T10:00:00Z").
    Returns normalized timezone-aware ISO-8601 string or None if relative date string (e.g. "3 months ago").
    """
    if not raw_text:
        return None
    clean_str = raw_text.strip()

    # 1. Check for ISO date format (e.g. 2026-08-12T10:00:00Z or 2026-08-12)
    if re.match(r"^\d{4}-\d{2}-\d{2}", clean_str):
        return clean_str

    # 2. Check for timezone abbreviation at end of string
    tz_obj = None
    tz_match = re.search(r"\b(PDT|PST|EDT|EST|CDT|CST|MDT|MST|UTC|GMT)$", clean_str, re.IGNORECASE)
    if tz_match:
        tz_str = tz_match.group(1).upper()
        tz_obj = TZ_OFFSETS.get(tz_str)

    # 3. Clean string for strptime
    norm = re.sub(r"\s+at\s+", " ", clean_str, flags=re.IGNORECASE)
    norm = re.sub(r"\s+(PDT|PST|EDT|EST|CDT|CST|MDT|MST|UTC|GMT)$", "", norm, flags=re.IGNORECASE).strip()

    formats = [
        "%B %d, %Y %I:%M%p",
        "%B %d, %Y %I:%M %p",
        "%B %d, %Y",
        "%b %d, %Y %I:%M%p",
        "%b %d, %Y %I:%M %p",
        "%b %d, %Y"
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(norm, fmt)
            if tz_obj:
                dt = dt.replace(tzinfo=tz_obj)
            return dt.isoformat()
        except ValueError:
            pass

    return None


class GranicusIdeasAdapter(BaseAdapter):
    """
    Source adapter for Granicus Ideas / SpeakUp civic agenda platforms (*.granicusideas.com).
    """
    platform_name: str = "Granicus Ideas"
    adapter_name: str = "GranicusIdeasAdapter"

    def supports(self, url: str) -> bool:
        """
        Determines whether the URL belongs to a Granicus Ideas domain (*.granicusideas.com).
        """
        clean = normalize_url(url).lower()
        return "granicusideas.com" in clean

    def supports_html(self, url: str, html: str) -> bool:
        """
        Post-fetch detection probe checking for Granicus Ideas characteristics.
        """
        if self.supports(url):
            return True
        if not html:
            return False
        html_lower = html.lower()
        return "granicusideas" in html_lower or "granicus" in html_lower

    def extract(
        self,
        url: str,
        html: Optional[str] = None,
        fetch_page_func: Optional[Callable[[str], str]] = None,
        max_comments: int = 500,
        **kwargs
    ) -> ExtractionResult:
        """
        Extracts item metadata and public comments from a Granicus Ideas agenda item page.
        Supports multi-page comment pagination via fetch_page_func.
        """
        retrieved_at = datetime.now(timezone.utc).isoformat()
        clean_url = normalize_url(url)

        if not html:
            if fetch_page_func:
                html = fetch_page_func(clean_url)
            else:
                fetch_res = self.load(clean_url)
                if not fetch_res.success or not fetch_res.html:
                    return ExtractionResult(
                        requested_url=clean_url,
                        success=False,
                        comments_status=CommentStatus.UNSUPPORTED,
                        error_message=fetch_res.error_message or "Failed to load Granicus Ideas page content",
                        retrieved_at=retrieved_at
                    )
                html = fetch_res.html

        soup = BeautifulSoup(html, "html.parser")
        diagnostic_notes: List[str] = []

        # 1. Canonical URL
        canonical_link = soup.find("link", rel="canonical")
        if canonical_link and canonical_link.get("href"):
            canonical_url = canonical_link["href"].strip()
        else:
            canonical_url = clean_url

        # 2. Publisher Determination
        host = clean_url.split("//")[-1].split("/")[0].lower()
        if "ousd" in host:
            publisher = "Oakland Unified School District"
        elif "broward" in host:
            publisher = "Broward County Public Schools"
        else:
            publisher = host.split(".")[0].upper()

        # 3. Title
        title_elem = (
            soup.find("h1", class_=lambda c: c and ("title" in c or "page-title" in c))
            or soup.find("h1")
            or soup.find(".agenda-item-title")
        )
        if title_elem:
            title = title_elem.get_text(strip=True)
        else:
            og_title = soup.find("meta", property="og:title")
            title = og_title["content"].strip() if og_title and og_title.get("content") else None

        # 4. Item Text / Description
        content_elem = (
            soup.find("div", class_=lambda c: c and ("description" in c or "content" in c or "body" in c))
            or soup.find("article")
            or soup.find("main")
        )
        if content_elem:
            content_clone = BeautifulSoup(str(content_elem), "html.parser")
            # Decompose comments container if present inside body container
            for c_sec in content_clone.find_all("div", id=lambda i: i and "comment" in i):
                c_sec.decompose()
            article_text = content_clone.get_text(separator="\n\n", strip=True)
        else:
            article_text = None

        # 5. Comment Count Reported
        reported_count = None
        count_elem = soup.find(lambda t: t.name in ["h2", "h3", "span", "div"] and "Comment" in t.get_text())
        if count_elem:
            match = re.search(r"(\d+)\s+Comments?", count_elem.get_text(), re.IGNORECASE)
            if match:
                reported_count = int(match.group(1))

        # 6. Multi-page Comment Extraction Loop
        comments: List[Comment] = []
        seen_comment_ids = set()
        visited_urls = {clean_url}
        current_soup = soup
        page_num = 1

        while True:
            # Locate comment container or comment blocks on current page
            comment_blocks = current_soup.find_all("div", class_=lambda c: c and ("comment-item" in c or "comment" in c))
            if not comment_blocks:
                comment_blocks = current_soup.find_all("li", class_=lambda c: c and "comment" in c)

            page_extracted_count = 0
            for block in comment_blocks:
                # Check data-id attribute on block or container
                data_id = block.get("data-id") or block.get("id")
                
                # Exclude container elements or form wrappers with data-id=None or form IDs
                if not data_id or "new_comment" in str(data_id) or "form" in str(data_id):
                    continue

                clean_id = str(data_id).strip()
                if clean_id in seen_comment_ids:
                    continue

                # Author
                author_el = (
                    block.find("span", class_=lambda c: c and ("author" in c or "user" in c or "name" in c))
                    or block.find("strong")
                    or block.find("a", class_=lambda c: c and "user" in c)
                )
                author_name = author_el.get_text(strip=True) if author_el else "Anonymous"

                # Text
                text_el = (
                    block.find("div", class_=lambda c: c and ("body" in c or "text" in c or "content" in c))
                    or block.find("p")
                )
                comment_body = text_el.get_text(strip=True) if text_el else ""

                if not comment_body:
                    continue

                # Timestamp parsing
                time_el = block.find("time")
                published_dt = None
                if time_el:
                    raw_dt = time_el.get("datetime") or time_el.get_text(strip=True)
                    published_dt = parse_granicus_timestamp(raw_dt)
                
                comment_obj = Comment(
                    comment_id=clean_id,
                    article_url=canonical_url,
                    parent_comment_id=None,
                    author_display_name=author_name,
                    comment_text=comment_body,
                    published_datetime=published_dt,
                    reactions={},
                    reply_count=0,
                    depth=0,
                    retrieved_at=retrieved_at
                )
                comments.append(comment_obj)
                seen_comment_ids.add(clean_id)
                page_extracted_count += 1

                if len(comments) >= max_comments:
                    diagnostic_notes.append(f"Reached max_comments limit of {max_comments}")
                    break

            if len(comments) >= max_comments:
                break

            # Check for next page link
            next_link = (
                current_soup.find("a", rel="next")
                or current_soup.find("a", class_=lambda c: c and "next" in c)
            )
            if not next_link or not next_link.get("href") or not fetch_page_func:
                break

            next_href = next_link["href"].strip()
            if next_href.startswith("/"):
                base_domain = clean_url.split("//")[0] + "//" + clean_url.split("//")[1].split("/")[0]
                next_url = base_domain + next_href
            elif not next_href.startswith("http"):
                next_url = clean_url.split("?")[0] + next_href
            else:
                next_url = next_href

            if next_url in visited_urls:
                break

            visited_urls.add(next_url)
            page_num += 1

            next_html = fetch_page_func(next_url)
            if not next_html:
                break
            current_soup = BeautifulSoup(next_html, "html.parser")

        # 7. Unexplained Count Mismatch Diagnostic Note
        if reported_count is not None and len(comments) != reported_count:
            if not any("max_comments" in note for note in diagnostic_notes):
                diagnostic_notes.append(
                    f"Unexplained count mismatch: reported {reported_count}, extracted {len(comments)} unique public comments."
                )

        # 8. Comment Status Determination
        if len(comments) > 0:
            status = CommentStatus.AVAILABLE
        elif soup.find(text=lambda t: t and ("closed" in t.lower() or "no comments" in t.lower())):
            status = CommentStatus.NONE_PRESENT
        else:
            status = CommentStatus.NONE_PRESENT

        article = Article(
            platform=self.platform_name,
            source_adapter=self.adapter_name,
            requested_url=clean_url,
            canonical_url=canonical_url,
            original_publisher=publisher,
            title=title,
            author=None,
            publication_datetime=None,
            updated_datetime=None,
            article_text=article_text,
            language="en",
            topic_query=kwargs.get("topic_query"),
            retrieved_at=retrieved_at,
            comments_status=status,
            comment_count_reported=reported_count,
            comments_collected=len(comments),
            extraction_method="bs4_granicus_ideas_html",
            diagnostic_notes=diagnostic_notes,
            comments=comments
        )

        return ExtractionResult(
            requested_url=clean_url,
            success=True,
            article=article,
            comments_status=status,
            error_message=None,
            diagnostic_notes=diagnostic_notes,
            retrieved_at=retrieved_at
        )
