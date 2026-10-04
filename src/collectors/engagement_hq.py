"""
EngagementHQ Civic Platform Source Adapter (Step 30A / Step 30A.1).
Extracts public consultation prompts, civic project topics, and resident submissions from EngagementHQ / Engage portals.
Uses multi-fingerprint detection (meta tags, script paths, DOM markers) to recognize platform instances across custom government domains.
"""
from typing import Optional, List
from datetime import datetime, timezone
from bs4 import BeautifulSoup

from src.collectors.base import BaseAdapter
from src.models import Article, Comment, ExtractionResult, CommentStatus
from src.utils.urls import normalize_url


class EngagementHQAdapter(BaseAdapter):
    """
    Platform-centric source adapter for EngagementHQ / Engage civic portals (Granicus / Bang the Table).
    """
    platform_name: str = "EngagementHQ Civic Portal"
    adapter_name: str = "EngagementHQAdapter"

    KNOWN_DOMAINS = [
        "engagementhq.com",
        "bangthetable.com",
        "engage.vic.gov.au",
        "connect.austintexas.gov"
    ]

    def supports(self, url: str) -> bool:
        """
        Fast-path pre-fetch URL check. Returns True for known EngagementHQ domain hostnames.
        """
        clean = normalize_url(url).lower()
        return any(domain in clean for domain in self.KNOWN_DOMAINS)

    def supports_html(self, url: str, html: str) -> bool:
        """
        Post-fetch platform detection probe.
        Requires at least TWO independent indicators, with at least ONE being a strong vendor indicator.
        Strong 1: Meta generator / og:site_name containing "EngagementHQ".
        Strong 2: CDN script/stylesheet path matching cdn.engagementhq.com, bangthetable.com, or assets/engagement_hq.
        Supporting: Specific DOM containers (.ehq-widget, .forum-tool, #engagement-tools, .submission-card).
        """
        if not html:
            return False

        soup = BeautifulSoup(html, "html.parser")
        strong_vendor_count = 0
        supporting_count = 0

        # Strong Indicator 1: Meta generator tag or og:site_name
        meta_gen = soup.find("meta", attrs={"name": "generator"})
        if meta_gen and "engagementhq" in str(meta_gen.get("content", "")).lower():
            strong_vendor_count += 1
        else:
            meta_site = soup.find("meta", property="og:site_name")
            if meta_site and "engagementhq" in str(meta_site.get("content", "")).lower():
                strong_vendor_count += 1

        # Strong Indicator 2: Asset CDN script or stylesheet URL
        cdn_found = False
        for script in soup.find_all("script", src=True):
            src = script["src"].lower()
            if "cdn.engagementhq.com" in src or "bangthetable.com" in src or "assets/engagement_hq" in src:
                cdn_found = True
                break
        if not cdn_found:
            for link in soup.find_all("link", href=True):
                href = link["href"].lower()
                if "cdn.engagementhq.com" in href or "bangthetable.com" in href or "assets/engagement_hq" in href:
                    cdn_found = True
                    break
        if cdn_found:
            strong_vendor_count += 1

        # Supporting Indicator: Characteristic DOM container
        if soup.find(class_=lambda c: c and ("ehq-widget" in c or "forum-tool" in c or "survey-tool" in c or "engagement-tools" in c or "submission-card" in c)):
            supporting_count += 1

        # Claim rule: At least 2 independent indicators total, AND at least 1 must be a strong vendor indicator.
        total_indicators = strong_vendor_count + supporting_count
        return (strong_vendor_count >= 1) and (total_indicators >= 2)

    def extract(self, url: str, html: Optional[str] = None, **kwargs) -> ExtractionResult:
        """
        Extracts civic consultation topic/prompt and public resident responses from an EngagementHQ portal page.
        Honors supplied `html` directly to guarantee zero duplicate network fetches.
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
        diagnostic_notes: List[str] = ["Platform Provider: EngagementHQ"]

        # 1. Canonical URL
        canonical_link = soup.find("link", rel="canonical")
        if canonical_link and canonical_link.get("href"):
            canonical_url = canonical_link["href"].strip()
        else:
            og_url = soup.find("meta", property="og:url")
            canonical_url = og_url["content"].strip() if og_url and og_url.get("content") else clean_url

        # 2. Project Title / Civic Prompt Title
        title_elem = (
            soup.find("h1", class_=lambda c: c and ("project-title" in c or "ehq-title" in c)) or
            soup.find("h1")
        )
        if title_elem:
            title = title_elem.get_text(strip=True)
        else:
            og_title = soup.find("meta", property="og:title")
            title = og_title["content"].strip() if og_title and og_title.get("content") else None

        # 3. Content Owner / Publisher (Municipality Name)
        meta_site = soup.find("meta", property="og:site_name")
        if meta_site and meta_site.get("content"):
            publisher = meta_site["content"].strip()
        else:
            header_logo = soup.find(class_=lambda c: c and "header-logo" in c)
            publisher = header_logo.get_text(strip=True) if header_logo else "Public Institution / Municipality"

        # 4. Article Text / Consultation Project Description
        desc_elem = (
            soup.find("div", class_=lambda c: c and ("project-description" in c or "ehq-description" in c or "project-body" in c)) or
            soup.find("main")
        )
        if desc_elem:
            article_text = desc_elem.get_text(separator="\n\n", strip=True)
        else:
            article_text = None

        # 5. Extract Public Submissions / Comments
        comments: List[Comment] = []
        submission_cards = soup.find_all(class_=lambda c: c and ("submission-card" in c or "forum-post" in c or "comment-item" in c or "idea-card" in c))

        for idx, card in enumerate(submission_cards):
            post_id = card.get("data-post-id") or card.get("id") or f"submission-{idx + 1}"

            # Author
            author_elem = card.find(class_=lambda c: c and ("author-name" in c or "user-name" in c or "submitter-title" in c))
            author_name = author_elem.get_text(strip=True) if author_elem else "Public Resident"

            # Text
            text_elem = card.find(class_=lambda c: c and ("post-content" in c or "submission-body" in c or "idea-text" in c))
            text = text_elem.get_text(strip=True) if text_elem else card.get_text(strip=True)

            # Date
            time_elem = card.find("time")
            pub_date = time_elem["datetime"].strip() if time_elem and time_elem.get("datetime") else None

            # Optional Stance Metadata
            reactions = None
            stance_elem = card.find(class_=lambda c: c and ("stance-tag" in c or "badge-position" in c))
            if stance_elem:
                reactions = {"stance": stance_elem.get_text(strip=True)}

            if text:
                comments.append(Comment(
                    comment_id=str(post_id),
                    article_url=canonical_url,
                    parent_comment_id=None,
                    author_display_name=author_name,
                    comment_text=text,
                    published_datetime=pub_date,
                    reactions=reactions,
                    reply_count=0,
                    depth=0,
                    retrieved_at=retrieved_at
                ))

        # 6. Status Determination
        if len(comments) > 0:
            status = CommentStatus.AVAILABLE
        elif soup.find(class_=lambda c: c and ("tool-closed" in c or "consultation-closed" in c)):
            status = CommentStatus.DISABLED
        else:
            status = CommentStatus.NONE_PRESENT

        article = Article(
            platform=self.platform_name,
            source_adapter=self.adapter_name,
            requested_url=clean_url,
            canonical_url=canonical_url,
            original_publisher=publisher,
            title=title,
            author=publisher,
            publication_datetime=None,
            updated_datetime=None,
            article_text=article_text,
            language="en",
            topic_query=kwargs.get("topic_query"),
            retrieved_at=retrieved_at,
            comments_status=status,
            comment_count_reported=len(comments),
            comments_collected=len(comments),
            extraction_method="bs4_engagement_hq_html",
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
