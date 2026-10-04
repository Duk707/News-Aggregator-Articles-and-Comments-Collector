"""
Higher Education Policy Institute (HEPI) Source Adapter (Step 30A).
Extracts policy articles and public reader comments from hepi.ac.uk.
Preserves published_datetime = None when comment timestamps are omitted in HTML (per Christopher workbook ground truth).
"""
import re
from typing import Optional, List
from datetime import datetime, timezone
from bs4 import BeautifulSoup

from src.collectors.base import BaseAdapter
from src.models import Article, ExtractionResult, CommentStatus
from src.extraction.wordpress import parse_wordpress_comments
from src.utils.urls import normalize_url


class HEPIAdapter(BaseAdapter):
    """
    Source adapter for Higher Education Policy Institute (hepi.ac.uk).
    """
    platform_name: str = "Higher Education Policy Institute"
    adapter_name: str = "HEPIAdapter"

    def supports(self, url: str) -> bool:
        """
        Determines whether the URL belongs to hepi.ac.uk.
        """
        clean = normalize_url(url).lower()
        return "hepi.ac.uk" in clean

    def extract(self, url: str, html: Optional[str] = None, **kwargs) -> ExtractionResult:
        """
        Extracts policy article metadata, body content, and public comments from a HEPI post.
        """
        retrieved_at = datetime.now(timezone.utc).isoformat()
        clean_url = normalize_url(url)

        if not html:
            fetch_res = self.load(clean_url)
            if not fetch_res.success or not fetch_res.html:
                return ExtractionResult(
                    requested_url=clean_url,
                    success=False,
                    comments_status=CommentStatus.UNSUPPORTED,
                    error_message=fetch_res.error_message or "Failed to load page content",
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
            og_url = soup.find("meta", property="og:url")
            canonical_url = og_url["content"].strip() if og_url and og_url.get("content") else clean_url

        # 2. Title
        title_elem = (
            soup.find("h1", class_="post-title") or
            soup.find("h1", class_="entry-title") or
            soup.find("h1")
        )
        if title_elem:
            title = title_elem.get_text(strip=True)
        else:
            og_title = soup.find("meta", property="og:title")
            title = og_title["content"].strip() if og_title and og_title.get("content") else None

        # 3. Author / Byline
        author_elem = (
            soup.find("span", class_="author") or
            soup.find("div", class_="post-author") or
            soup.find("a", rel="author")
        )
        if author_elem:
            author = author_elem.get_text(strip=True)
        else:
            meta_author = soup.find("meta", name="author")
            author = meta_author["content"].strip() if meta_author and meta_author.get("content") else None

        # 4. Publication Date
        date_elem = (
            soup.find("span", class_="post-date") or
            soup.find("time", class_="entry-date") or
            soup.find("time")
        )
        if date_elem and date_elem.get("datetime"):
            pub_date = date_elem["datetime"].strip()
        elif date_elem:
            pub_date = date_elem.get_text(strip=True)
        else:
            meta_date = soup.find("meta", property="article:published_time")
            pub_date = meta_date["content"].strip() if meta_date and meta_date.get("content") else None

        # 5. Article Text
        content_elem = (
            soup.find("div", class_="pf-content") or
            soup.find("div", class_="entry-content") or
            soup.find("div", class_="post-content") or
            soup.find("article")
        )
        if content_elem:
            content_clone = BeautifulSoup(str(content_elem), "html.parser")
            for noise in content_clone.find_all("div", class_=["sharedaddy", "post-tags", "post-navigation"]):
                noise.decompose()
            article_text = content_clone.get_text(separator="\n\n", strip=True)
        else:
            article_text = None

        # 6. Comment Extraction via Shared WordPress Helper
        comments, trackbacks_filtered = parse_wordpress_comments(soup, article_url=canonical_url, retrieved_at=retrieved_at)

        if trackbacks_filtered > 0:
            diagnostic_notes.append(f"Trackbacks Filtered: {trackbacks_filtered}")

        # Check for missing comment dates (common on HEPI posts)
        missing_dates_count = sum(1 for c in comments if c.published_datetime is None)
        if missing_dates_count > 0:
            diagnostic_notes.append(f"Comments with missing timestamps (set to None): {missing_dates_count}")

        # 7. Reported Comment Count
        reported_count = None
        count_elem = soup.find("h3", id="comments-title") or soup.find("h3", class_="comments-title")
        if count_elem:
            count_text = count_elem.get_text(strip=True)
            match = re.search(r"(\d+)", count_text)
            if match:
                reported_count = int(match.group(1))

        # 8. Comment Status Determination
        if len(comments) > 0:
            status = CommentStatus.AVAILABLE
        elif soup.find(class_=lambda c: c and ("comments-closed" in c or "nocomments" in c)):
            status = CommentStatus.DISABLED
        else:
            status = CommentStatus.NONE_PRESENT

        article = Article(
            platform=self.platform_name,
            source_adapter=self.adapter_name,
            requested_url=clean_url,
            canonical_url=canonical_url,
            original_publisher="Higher Education Policy Institute",
            title=title,
            author=author,
            publication_datetime=pub_date,
            updated_datetime=None,
            article_text=article_text,
            language="en-GB",
            topic_query=kwargs.get("topic_query"),
            retrieved_at=retrieved_at,
            comments_status=status,
            comment_count_reported=reported_count,
            comments_collected=len(comments),
            extraction_method="bs4_hepi_html",
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
