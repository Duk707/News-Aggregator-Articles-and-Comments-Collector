"""
Legistar Source Adapter (Step 30C.2).
Extracts legislative item records from Legistar web pages (*.legistar.com).
Cross-links to Granicus Ideas for public comments when available.
"""
import re
from typing import Optional, List
from datetime import datetime, timezone
from bs4 import BeautifulSoup

from src.collectors.base import BaseAdapter
from src.models import Article, ExtractionResult, CommentStatus, Comment
from src.utils.urls import normalize_url


class LegistarAdapter(BaseAdapter):
    """
    Source adapter for Legistar web legislative portals (*.legistar.com).
    """
    platform_name: str = "Legistar"
    adapter_name: str = "LegistarAdapter"

    def supports(self, url: str) -> bool:
        """
        Determines whether the URL belongs to a Legistar domain (*.legistar.com).
        """
        clean = normalize_url(url).lower()
        return "legistar.com" in clean

    def supports_html(self, url: str, html: str) -> bool:
        """
        Post-fetch detection probe checking for Legistar characteristics.
        """
        if self.supports(url):
            return True
        if not html:
            return False
        html_lower = html.lower()
        return "legistar" in html_lower or "inSite" in html_lower

    def extract(self, url: str, html: Optional[str] = None, granicus_adapter=None, **kwargs) -> ExtractionResult:
        """
        Extracts legislative matter record from Legistar.
        Integrates cross-linked Granicus Ideas public comments when cross_link_url is provided.
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
                    error_message=fetch_res.error_message or "Failed to load Legistar page content",
                    retrieved_at=retrieved_at
                )
            html = fetch_res.html

        soup = BeautifulSoup(html, "html.parser")
        diagnostic_notes: List[str] = [
            "Legistar legislative portals store official meeting agenda items.",
            "Public comments require cross-linking to Granicus Ideas public comment surface."
        ]

        # 1. Title & File Number
        title_elem = soup.find("span", id=lambda i: i and "lblName" in i) or soup.find("h1") or soup.find("title")
        title = title_elem.get_text(strip=True) if title_elem else "Legistar Legislative Item"

        file_elem = soup.find("span", id=lambda i: i and "lblFile" in i)
        file_num = file_elem.get_text(strip=True) if file_elem else None
        if file_num and file_num not in title:
            title = f"[{file_num}] {title}"

        # 2. Publisher
        host = clean_url.split("//")[-1].split("/")[0].lower()
        publisher = host.split(".")[0].upper()

        # 3. Matter Text / Details
        details_elem = soup.find("td", id=lambda i: i and "ctl00_ContentPlaceHolder1_lblText" in i) or soup.find("form")
        article_text = details_elem.get_text(separator="\n\n", strip=True) if details_elem else soup.get_text(strip=True)

        # 4. Handle Cross-Linked Granicus Ideas Comments if cross_link_url provided
        cross_link_url = kwargs.get("cross_link_url")
        comments: List[Comment] = []
        status = CommentStatus.UNKNOWN
        reported_count = 0

        if cross_link_url and granicus_adapter:
            granicus_html = kwargs.get("granicus_html") or kwargs.get("html_override")
            granicus_res = granicus_adapter.extract(cross_link_url, html=granicus_html, **kwargs)
            if granicus_res.success and granicus_res.article:
                comments = granicus_res.article.comments
                status = granicus_res.comments_status
                reported_count = granicus_res.article.comment_count_reported
                diagnostic_notes.append(f"Successfully cross-linked public comments from Granicus Ideas: {cross_link_url}")
        else:
            diagnostic_notes.append("Public comment surface was not resolved for this Legistar item.")

        article = Article(
            platform=self.platform_name,
            source_adapter=self.adapter_name,
            requested_url=clean_url,
            canonical_url=clean_url,
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
            extraction_method="bs4_legistar_html",
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
