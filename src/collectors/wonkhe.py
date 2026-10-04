"""
Wonkhe Source Adapter (Step 30B.2).
Extracts articles and publicly readable reader comments from wonkhe.com.
Uses Next.js SSR JSON-LD metadata and static comment section extraction.
"""
import re
import json
from typing import Optional, List
from datetime import datetime, timezone
from bs4 import BeautifulSoup

from src.collectors.base import BaseAdapter
from src.models import Article, ExtractionResult, CommentStatus, Comment
from src.utils.urls import normalize_url


class WonkheAdapter(BaseAdapter):
    """
    Source adapter for Wonkhe (wonkhe.com).
    """
    platform_name: str = "Wonkhe"
    adapter_name: str = "WonkheAdapter"

    def supports(self, url: str) -> bool:
        """
        Determines whether the URL belongs to wonkhe.com.
        """
        clean = normalize_url(url).lower()
        return "wonkhe.com" in clean

    def extract(self, url: str, html: Optional[str] = None, **kwargs) -> ExtractionResult:
        """
        Extracts article metadata, main body content, and public comments from a Wonkhe article.
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

        # 2. JSON-LD Fallback Metadata
        json_ld_data = {}
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "{}")
                if isinstance(data, dict) and data.get("@type") in ["NewsArticle", "Article", "BlogPosting"]:
                    json_ld_data = data
                    break
            except Exception:
                pass

        # 3. Title
        title_elem = soup.find("h1")
        if title_elem:
            title = title_elem.get_text(strip=True)
        elif json_ld_data.get("headline"):
            title = json_ld_data["headline"]
        else:
            og_title = soup.find("meta", property="og:title")
            title = og_title["content"].strip() if og_title and og_title.get("content") else None

        # 4. Author
        author = None
        if json_ld_data.get("author"):
            author_val = json_ld_data["author"]
            if isinstance(author_val, dict):
                author = author_val.get("name")
            elif isinstance(author_val, list) and len(author_val) > 0:
                author = author_val[0].get("name") if isinstance(author_val[0], dict) else str(author_val[0])
            elif isinstance(author_val, str):
                author = author_val
        
        if not author:
            meta_author = soup.find("meta", name="author")
            author = meta_author["content"].strip() if meta_author and meta_author.get("content") else None

        # 5. Publication Date
        pub_date = json_ld_data.get("datePublished")
        if not pub_date:
            meta_date = soup.find("meta", property="article:published_time")
            pub_date = meta_date["content"].strip() if meta_date and meta_date.get("content") else None

        # 6. Article Text
        content_elem = soup.find("article") or soup.find("main") or soup.find("div", class_=lambda c: c and "post" in c)
        if content_elem:
            content_clone = BeautifulSoup(str(content_elem), "html.parser")
            # Decompose comments section from article text clone if present inside article
            for sec in content_clone.find_all("section", {"aria-label": "Comments"}):
                sec.decompose()
            article_text = content_clone.get_text(separator="\n\n", strip=True)
        else:
            article_text = None

        # 7. Comment Extraction (Static Next.js SSR Comment Container)
        comments: List[Comment] = []
        comment_sec = soup.find("section", {"aria-label": "Comments"}) or soup.find(id="comments")
        
        reported_count = None
        if comment_sec:
            h2_heading = comment_sec.find(lambda t: t.name in ["h2", "h3"] and "Comments" in t.get_text())
            if h2_heading:
                match = re.search(r"(\d+)", h2_heading.get_text())
                if match:
                    reported_count = int(match.group(1))

            comment_divs = comment_sec.find_all("div", class_="mt-5")
            for idx, c_div in enumerate(comment_divs, 1):
                author_el = c_div.find("strong")
                date_el = c_div.find("span", class_="text-muted")
                text_el = c_div.find("p", class_="font-tisa") or c_div.find("p")
                
                author_name = author_el.get_text(strip=True) if author_el else "Anonymous"
                
                date_str = None
                if date_el:
                    raw_date = date_el.get_text(strip=True).lstrip("·").strip()
                    if raw_date:
                        date_str = raw_date
                
                comment_body = text_el.get_text(strip=True) if text_el else ""
                
                if comment_body:
                    comment_obj = Comment(
                        comment_id=f"wonkhe-comment-{idx}",
                        article_url=canonical_url,
                        parent_comment_id=None,
                        author_display_name=author_name,
                        comment_text=comment_body,
                        published_datetime=date_str,
                        reactions={},
                        reply_count=0,
                        depth=0,
                        retrieved_at=retrieved_at
                    )
                    comments.append(comment_obj)

        # 8. Comment Status Determination
        if len(comments) > 0:
            status = CommentStatus.AVAILABLE
        elif comment_sec and ("sign-in" in comment_sec.get_text().lower() or "log in" in comment_sec.get_text().lower()):
            status = CommentStatus.DISABLED
        else:
            status = CommentStatus.NONE_PRESENT

        article = Article(
            platform=self.platform_name,
            source_adapter=self.adapter_name,
            requested_url=clean_url,
            canonical_url=canonical_url,
            original_publisher="Wonkhe",
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
            extraction_method="bs4_nextjs_ssr_html",
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
