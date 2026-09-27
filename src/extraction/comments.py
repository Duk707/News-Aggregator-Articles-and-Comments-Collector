import os
import re
import json
import html
import hashlib
import urllib.request
import gzip
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field
from src.models.comment_status import CommentStatus
from src.models.comment import Comment


class CommentDiagnosticsResult(BaseModel):
    """
    Diagnostic model representing observable evidence regarding comment presence,
    controls, containers, frames, and access restrictions on a page.
    """
    url: str = Field(description="URL evaluated for comment evidence")
    has_comment_text: bool = Field(default=False, description="True if 'comment' or related keywords exist on page")
    has_view_comments_button: bool = Field(default=False, description="True if a 'View/Show comments' button/link exists")
    reported_comment_count: Optional[int] = Field(default=None, description="Reported comment count if stated in DOM/UI")
    comment_container_found: bool = Field(default=False, description="True if a designated comment DOM container exists")
    iframes_found: List[str] = Field(default_factory=list, description="List of iframe src/id attributes on page")
    access_login_messages: List[str] = Field(default_factory=list, description="Login or access restriction text found")
    disabled_messages: List[str] = Field(default_factory=list, description="Explicit comments disabled text found")
    preliminary_status: CommentStatus = Field(default=CommentStatus.UNKNOWN, description="Conservatively inferred comment status")
    diagnostic_notes: List[str] = Field(default_factory=list, description="Detailed evidence notes")
    raw_evidence: Dict[str, Any] = Field(default_factory=dict, description="Raw matching snippets and selectors")
    timestamp: str = Field(description="ISO timestamp of diagnostic evaluation")


class YahooCommentDeliveryEvidence(BaseModel):
    """
    Empirical investigation evidence documenting how Yahoo delivers public comments upon user interaction.
    """
    url: str = Field(description="Target article URL evaluated")
    button_found: bool = Field(default=False, description="True if a 'View comments' control button was found")
    button_clicked: bool = Field(default=False, description="True if the control button was successfully clicked")
    verified_comment_network_activity: List[Dict[str, Any]] = Field(default_factory=list, description="Network requests positively identified with comment delivery")
    unrelated_network_activity_count: int = Field(default=0, description="Count of advertising/analytics network requests captured around interaction")
    unrelated_network_activity_sample: List[str] = Field(default_factory=list, description="Sample of advertising/analytics domains captured")
    verified_comment_dom_changes: List[str] = Field(default_factory=list, description="DOM containers/nodes positively identified with comments")
    verified_comment_iframes: List[str] = Field(default_factory=list, description="New iframes with positive evidence connecting them to comments")
    unrelated_iframe_changes: List[str] = Field(default_factory=list, description="New advertising/analytics/safeframe iframes created after click")
    visible_comment_text_found: bool = Field(default=False, description="True if actual comment text became visible on page")
    rendered_comments_count: int = Field(default=0, description="Count of visible comment text blocks found after click")
    login_required_after_click: bool = Field(default=False, description="True if clicking triggered an authentication modal/login prompt")
    observed_delivery_mechanism: str = Field(default="UNKNOWN", description="Observed technical mechanism supported strictly by positive evidence")
    findings_summary: str = Field(default="", description="Detailed summary of empirical findings")
    timestamp: str = Field(description="ISO timestamp of investigation")


class CommentDiagnosticInspector:
    """
    Investigative inspector that analyzes rendered HTML / DOM for public comment evidence
    BEFORE attempting extraction, applying conservative status classification.
    """

    # Specific comment control regexes
    COMMENT_KEYWORDS = [r"\bcomments?\b", r"\bview comments\b", r"\bshow comments\b", r"\bjoin the conversation\b"]
    BUTTON_KEYWORDS = [
        r"\bview\s+(?:all\s+)?comments?\b",
        r"\bshow\s+(?:all\s+)?comments?\b",
        r"\bread\s+(?:all\s+)?comments?\b",
        r"\bload\s+(?:all\s+)?comments?\b",
        r"\bjoin\s+the\s+conversation\b",
        r"^\s*comments?\s*(?:\(\d+\))?\s*$",
        r"^\s*\d+\s+comments?\s*$"
    ]
    LOGIN_KEYWORDS = [
        r"sign in to comment",
        r"log in to comment",
        r"login to comment",
        r"sign in to view comments",
        r"log in to view comments"
    ]
    DISABLED_KEYWORDS = [
        r"comments are disabled",
        r"comments have been disabled",
        r"comments are closed",
        r"commenting is turned off"
    ]

    # Selectors for potential comment containers
    COMMENT_CONTAINER_SELECTORS = [
        "#comments",
        ".comments-container",
        ".caas-comments",
        "[data-test-locator='comments']",
        "[data-test-locator='comments-count']",
        "div[class*='comment-container']",
        "section[class*='comment']"
    ]

    @classmethod
    def inspect(cls, url: str, html: str) -> CommentDiagnosticsResult:
        """
        Inspects page HTML for comment evidence and returns a diagnostic result.

        Args:
            url: Evaluated URL string.
            html: Rendered page HTML.

        Returns:
            CommentDiagnosticsResult: Detailed diagnostic findings and conservative status.
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        notes: List[str] = []
        raw_evidence: Dict[str, Any] = {}

        if not html or not html.strip():
            return CommentDiagnosticsResult(
                url=url,
                preliminary_status=CommentStatus.EXTRACTION_ERROR,
                diagnostic_notes=["Empty HTML payload provided for diagnostic inspection"],
                timestamp=timestamp
            )

        soup = BeautifulSoup(html, "html.parser")
        page_text = soup.get_text()
        page_text_lower = page_text.lower()

        # 1. Check for general comment keywords
        has_comment_text = any(re.search(pat, page_text_lower) for pat in cls.COMMENT_KEYWORDS)
        if has_comment_text:
            notes.append("Found general 'comment/comments' text in page DOM")

        # 2. Check for interactive comment controls (buttons/links)
        has_view_button = False
        button_matches = []
        # Target interactive elements or small elements (avoid large container divs)
        candidate_elements = soup.find_all(["button", "a"]) + soup.find_all(attrs={"role": "button"}) + soup.find_all(class_=re.compile(r"comment", re.I))

        for btn in candidate_elements:
            btn_text = btn.get_text().strip()
            # Ignore giant container elements (only evaluate discrete control elements)
            if not btn_text or len(btn_text) > 150:
                continue

            btn_text_lower = btn_text.lower()
            if any(re.search(pat, btn_text_lower) for pat in cls.BUTTON_KEYWORDS):
                has_view_button = True
                if btn_text not in button_matches:
                    button_matches.append(btn_text)

        if has_view_button:
            notes.append(f"Found verified comment interactive control(s): {button_matches[:3]}")
            raw_evidence["button_matches"] = button_matches[:3]

        # 3. Check for reported comment count
        reported_count: Optional[int] = None
        count_patterns = [
            r"comments?\s*\(\s*(\d+)\s*\)",
            r"(\d+)\s+comments?",
            r"(\d+)\s+replies"
        ]
        for pat in count_patterns:
            match = re.search(pat, page_text_lower)
            if match:
                try:
                    reported_count = int(match.group(1))
                    notes.append(f"Found reported comment count in text: {reported_count}")
                    raw_evidence["count_match_text"] = match.group(0)
                    break
                except ValueError:
                    pass

        if reported_count is None:
            ylk_match = re.search(r'cmmt_count[:=](\d+)', html, re.IGNORECASE) or re.search(r'comment_count[:=](\d+)', html, re.IGNORECASE)
            if ylk_match:
                try:
                    reported_count = int(ylk_match.group(1))
                    notes.append(f"Found reported comment count in metadata attribute: {reported_count}")
                except ValueError:
                    pass

        # 4. Check for designated comment containers
        container_found = False
        matched_selectors = []
        for selector in cls.COMMENT_CONTAINER_SELECTORS:
            elements = soup.select(selector)
            if elements:
                container_found = True
                matched_selectors.append(selector)
        if container_found:
            notes.append(f"Found comment DOM container selector(s): {matched_selectors}")
            raw_evidence["matched_container_selectors"] = matched_selectors

        # 5. Check for iframes
        iframes_found = []
        comment_iframes = []
        for iframe in soup.find_all("iframe"):
            src = str(iframe.get("src") or iframe.get("id") or iframe.get("name") or "unnamed_iframe")
            iframes_found.append(src)
            src_lower = src.lower()
            if "spot" in src_lower or "comment" in src_lower or "viafoura" in src_lower:
                comment_iframes.append(src)

        if iframes_found:
            notes.append(f"Found {len(iframes_found)} iframe(s) on page")
            raw_evidence["iframes_count"] = len(iframes_found)
        if comment_iframes:
            notes.append(f"Found comment-specific iframe(s): {comment_iframes}")
            raw_evidence["comment_iframes"] = comment_iframes

        # 6. Check for login / access restriction messages
        login_messages = []
        for pat in cls.LOGIN_KEYWORDS:
            match = re.search(pat, page_text_lower)
            if match:
                login_messages.append(match.group(0))
        if login_messages:
            notes.append(f"Found authentication/login requirement text: {login_messages}")

        # 7. Check for disabled comments messages
        disabled_messages = []
        for pat in cls.DISABLED_KEYWORDS:
            match = re.search(pat, page_text_lower)
            if match:
                disabled_messages.append(match.group(0))
        if disabled_messages:
            notes.append(f"Found comments disabled text: {disabled_messages}")

        # 8. Infer conservative preliminary CommentStatus
        status = cls._infer_conservative_status(
            container_found=container_found,
            has_view_button=has_view_button,
            reported_count=reported_count,
            has_comment_text=has_comment_text,
            login_messages=login_messages,
            disabled_messages=disabled_messages,
            comment_iframes=comment_iframes
        )

        notes.append(f"Conservatively inferred status: {status.value}")

        return CommentDiagnosticsResult(
            url=url,
            has_comment_text=has_comment_text,
            has_view_comments_button=has_view_button,
            reported_comment_count=reported_count,
            comment_container_found=container_found,
            iframes_found=iframes_found[:10],
            access_login_messages=login_messages,
            disabled_messages=disabled_messages,
            preliminary_status=status,
            diagnostic_notes=notes,
            raw_evidence=raw_evidence,
            timestamp=timestamp
        )

    @staticmethod
    def _infer_conservative_status(
        container_found: bool,
        has_view_button: bool,
        reported_count: Optional[int],
        has_comment_text: bool,
        login_messages: List[str],
        disabled_messages: List[str],
        comment_iframes: List[str]
    ) -> CommentStatus:
        """
        Conservatively assigns preliminary CommentStatus strictly according to evidence:
        - LOGIN_REQUIRED if login restriction text is found.
        - DISABLED if explicit comments disabled text is found.
        - NONE_PRESENT if reported count is explicitly 0 AND (container or button exists).
        - NOT_LOADED if positive evidence of a comment feature exists (verified control, count > 0, container, or comment iframe) but comments are not loaded in rendered DOM.
        - UNKNOWN if no verified comment control, count, container, iframe, or restriction evidence exists.
        """
        if login_messages:
            return CommentStatus.LOGIN_REQUIRED

        if disabled_messages:
            return CommentStatus.DISABLED

        if reported_count == 0 and (container_found or has_view_button):
            return CommentStatus.NONE_PRESENT

        # Positive evidence that comment feature exists
        if (reported_count is not None and reported_count > 0) or has_view_button or container_found or len(comment_iframes) > 0:
            return CommentStatus.NOT_LOADED

        # No concrete positive comment feature evidence found -> UNKNOWN
        return CommentStatus.UNKNOWN

    @classmethod
    def save_diagnostic_artifact(
        cls,
        diagnostics: CommentDiagnosticsResult,
        html: Optional[str] = None,
        output_dir: str = "data/diagnostics"
    ) -> Dict[str, str]:
        """
        Saves a structured JSON diagnostic summary and optional HTML snapshot to output_dir.

        Returns:
            Dict[str, str]: Paths of created diagnostic artifacts.
        """
        os.makedirs(output_dir, exist_ok=True)
        # Create safe filename base from URL
        safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", diagnostics.url)[:80].strip("_")
        if not safe_name:
            safe_name = "diagnostic_artifact"

        json_path = os.path.join(output_dir, f"{safe_name}_diag.json")
        saved_paths = {"json_report": json_path}

        with open(json_path, "w", encoding="utf-8") as f:
            f.write(diagnostics.model_dump_json(indent=2))

        if html:
            html_path = os.path.join(output_dir, f"{safe_name}_page.html")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html)
            saved_paths["html_snapshot"] = html_path

        return saved_paths

    @classmethod
    def investigate_comment_delivery_mechanism(
        cls,
        url: str,
        browser_manager: Any
    ) -> YahooCommentDeliveryEvidence:
        """
        Interactively clicks the verified 'View comments' button on a live Yahoo article,
        broadly capturing network activity, DOM mutations, iframe insertions, and login prompts,
        and strictly categorizing comment-related vs unrelated advertising/analytics traffic.

        Args:
            url: Target live article URL.
            browser_manager: BrowserManager instance.

        Returns:
            YahooCommentDeliveryEvidence: Empirical evidence documenting comment delivery.
        """
        from urllib.parse import urlparse

        timestamp = datetime.now(timezone.utc).isoformat()
        pre_click_requests: List[Dict[str, Any]] = []
        post_click_requests: List[Dict[str, Any]] = []

        # Current phase state flag
        phase = {"current": "PRE_CLICK"}

        context = browser_manager.create_context()
        page = context.new_page()

        # Listen broadly to all network responses
        def on_response(response):
            try:
                res_url = response.url
                domain = urlparse(res_url).hostname or "unknown"
                req = response.request
                entry = {
                    "url": res_url,
                    "domain": domain,
                    "method": req.method,
                    "resource_type": req.resource_type,
                    "status": response.status
                }
                if phase["current"] == "PRE_CLICK":
                    pre_click_requests.append(entry)
                else:
                    post_click_requests.append(entry)
            except Exception:
                pass

        page.on("response", on_response)

        # 1. Load initial page (pre-click baseline)
        page.goto(url, wait_until="domcontentloaded")
        initial_html = page.content()
        initial_soup = BeautifulSoup(initial_html, "html.parser")
        initial_iframes = [str(f.get("src") or f.get("id") or f.get("name") or "") for f in initial_soup.find_all("iframe")]

        # Switch phase to POST_CLICK right before interaction
        phase["current"] = "POST_CLICK"

        # 2. Locate 'View comments' button
        button_found = False
        button_clicked = False
        login_required = False

        button_selectors = [
            "button:has-text('View comments')",
            "a:has-text('View comments')",
            "[role='button']:has-text('View comments')",
            "button:has-text('Comments')",
            ".caas-button:has-text('comments')"
        ]

        target_btn = None
        for sel in button_selectors:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    target_btn = el
                    button_found = True
                    break
            except Exception:
                pass

        if not target_btn:
            try:
                buttons = page.query_selector_all("button, a, [role='button']")
                for btn in buttons:
                    txt = (btn.inner_text() or "").strip().lower()
                    if "view comments" in txt or "show comments" in txt or "read comments" in txt:
                        target_btn = btn
                        button_found = True
                        break
            except Exception:
                pass

        # 3. Click button if found, scroll into view if needed, wait for rendering
        if target_btn and button_found:
            try:
                target_btn.scroll_into_view_if_needed()
                target_btn.click(timeout=5000)
                button_clicked = True
            except Exception:
                try:
                    target_btn.click(force=True, timeout=5000)
                    button_clicked = True
                except Exception:
                    button_clicked = False

            # Allow time for dynamic JS execution & network payloads
            page.wait_for_timeout(4000)

        # 4. Analyze post-click DOM & diff iframes
        post_html = page.content()
        post_soup = BeautifulSoup(post_html, "html.parser")
        post_text_lower = post_soup.get_text().lower()

        post_iframes = [str(f.get("src") or f.get("id") or f.get("name") or "") for f in post_soup.find_all("iframe")]
        new_iframes = [f for f in post_iframes if f not in initial_iframes]

        # Categorize new iframes based strictly on POSITIVE comment evidence
        verified_comment_iframes = []
        unrelated_iframe_changes = []

        comment_iframe_keywords = ["spot.im", "spotim", "openweb", "viafoura", "comments-iframe", "caas-comment"]
        for iframe_src in new_iframes:
            src_lower = iframe_src.lower()
            if any(k in src_lower for k in comment_iframe_keywords):
                verified_comment_iframes.append(iframe_src)
            else:
                unrelated_iframe_changes.append(iframe_src)

        # Categorize network activity
        verified_comment_network = []
        unrelated_network_domains = set()

        comment_net_keywords = ["spot.im", "openweb", "viafoura", "comments-api", "/api/v1/comments", "caas/comments", "get_comments", "comment_box"]
        for req in post_click_requests:
            req_url_lower = req["url"].lower()
            if any(k in req_url_lower for k in comment_net_keywords):
                verified_comment_network.append(req)
            else:
                unrelated_network_domains.add(req["domain"])

        # Check for verified comment DOM containers
        verified_dom_changes = []
        for sel in [".caas-comments", "#comments", ".comments-container", "div[class*='spot-im']", "[data-spot-im-module]"]:
            if post_soup.select(sel):
                verified_dom_changes.append(sel)

        # Check for rendered comment nodes / visible text
        rendered_comment_nodes = post_soup.select("[class*='comment-body'], [class*='comment-text'], [data-spot-im-module]")
        rendered_comments_count = len(rendered_comment_nodes)
        visible_comment_text = rendered_comments_count > 0

        # Check for authentication prompt
        if any(msg in post_text_lower for msg in ["sign in to comment", "log in to comment", "login to view comments"]):
            login_required = True

        # 5. Determine technical mechanism STRICTLY from positive evidence
        mechanism = "UNDETERMINED"
        summary_parts = []

        all_verified_iframes_str = " ".join(verified_comment_iframes).lower()
        all_verified_net_str = " ".join([r["url"] for r in verified_comment_network]).lower()

        if login_required:
            mechanism = "LOGIN_RESTRICTED"
            summary_parts.append("Clicking 'View comments' opened authentication/login prompt.")
        elif "spot.im" in all_verified_iframes_str or "spot.im" in all_verified_net_str:
            mechanism = "SPOT_IM_IFRAME"
            summary_parts.append("Verified Spot.IM third-party comment iframe/API activity.")
        elif "openweb" in all_verified_iframes_str or "openweb" in all_verified_net_str:
            mechanism = "OPENWEB_IFRAME"
            summary_parts.append("Verified OpenWeb third-party comment iframe widget.")
        elif "viafoura" in all_verified_iframes_str or "viafoura" in all_verified_net_str:
            mechanism = "VIAFOURA_IFRAME"
            summary_parts.append("Verified Viafoura third-party comment iframe widget.")
        elif verified_comment_iframes:
            mechanism = "VERIFIED_COMMENT_IFRAME"
            summary_parts.append(f"Verified comment iframe(s) inserted into DOM: {verified_comment_iframes[:2]}")
        elif verified_dom_changes or visible_comment_text:
            mechanism = "DYNAMIC_DOM_COMPONENT"
            summary_parts.append("Observed verified dynamic comment DOM component insertion.")
        elif verified_comment_network:
            mechanism = "PUBLIC_API_ENDPOINT"
            summary_parts.append("Observed verified public comment API network activity.")
        elif button_clicked:
            mechanism = "UNDETERMINED"
            summary_parts.append(
                f"Button clicked successfully. Captured {len(post_click_requests)} post-click network requests "
                f"and {len(new_iframes)} new iframes, but NO positive comment-delivery evidence was identified "
                f"(new iframes belong to ad safe-frames / analytics). Classified as UNDETERMINED."
            )
        else:
            mechanism = "CONTROL_NOT_FOUND"
            summary_parts.append("No active 'View comments' button could be clicked on the page.")

        findings_summary = " ".join(summary_parts)

        context.close()

        evidence = YahooCommentDeliveryEvidence(
            url=url,
            button_found=button_found,
            button_clicked=button_clicked,
            verified_comment_network_activity=verified_comment_network[:15],
            unrelated_network_activity_count=len(post_click_requests) - len(verified_comment_network),
            unrelated_network_activity_sample=list(unrelated_network_domains)[:10],
            verified_comment_dom_changes=verified_dom_changes,
            verified_comment_iframes=verified_comment_iframes,
            unrelated_iframe_changes=unrelated_iframe_changes[:10],
            visible_comment_text_found=visible_comment_text,
            rendered_comments_count=rendered_comments_count,
            login_required_after_click=login_required,
            observed_delivery_mechanism=mechanism,
            findings_summary=findings_summary,
            timestamp=timestamp
        )

        # Save investigation diagnostic report
        os.makedirs("data/diagnostics", exist_ok=True)
        report_path = "data/diagnostics/yahoo_comment_delivery_investigation.json"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(evidence.model_dump_json(indent=2))

        return evidence


class CommentExtractionResult(BaseModel):
    """
    Normalized result model for public comment extraction containing extracted comments,
    final classified comment status, reported/extracted counts, and detailed diagnostic logs.
    """
    url: str = Field(description="URL of the associated article")
    comments: List[Comment] = Field(default_factory=list, description="List of normalized extracted comments")
    status: CommentStatus = Field(description="Final classified comment status")
    reported_count: Optional[int] = Field(default=None, description="Reported comment count if stated in DOM/UI")
    extracted_count: int = Field(default=0, description="Total number of comments extracted")
    extraction_method: str = Field(default="HTML_DOM_PARSER", description="Method or strategy used for comment extraction")
    diagnostic_notes: List[str] = Field(default_factory=list, description="Detailed diagnostic log notes")
    timestamp: str = Field(description="ISO timestamp when extraction was completed")


class YahooCommentExtractor:
    """
    Evidence-driven public comment extractor for Yahoo News and related platforms.
    Attempts interactive 'View comments' button activation using Playwright (if browser_manager is provided)
    and extracts normalized comments from publicly rendered DOM structures.
    """

    # Primary selectors for comment items across various Yahoo/Spot.IM/OpenWeb DOM versions
    COMMENT_ITEM_SELECTORS = [
        ".caas-comment-item",
        ".caas-comment",
        "[data-spot-im-module='comments'] .spot-im-comment-post",
        ".spot-im-comment-post",
        "li.comment-item",
        "div.comment-item",
        ".vf-comment",
        "div[data-comment-id]",
        "li[data-comment-id]",
        "div[class*='comment-card']",
        "div[class*='CommentCard']",
        "div[class*='comment-item']",
        "div[class*='CommentItem']"
    ]

    # Child text selectors
    TEXT_SELECTORS = [
        ".comment-text",
        ".comment-body",
        "[class*='comment-text']",
        "[class*='comment-body']",
        "[class*='comment-content']",
        "[class*='CommentContent']",
        "[class*='message']",
        "p.text",
        "p"
    ]

    # Child author selectors
    AUTHOR_SELECTORS = [
        ".comment-author",
        ".author-name",
        "[class*='author']",
        "[class*='username']",
        "[class*='displayName']",
        ".caas-author-byline",
        "strong",
        "b"
    ]

    # Child timestamp selectors
    TIMESTAMP_SELECTORS = [
        "time",
        "[class*='timestamp']",
        "[class*='time']",
        "[class*='date']",
        ".comment-date"
    ]

    # Child reaction selectors
    REACTION_SELECTORS = [
        "[class*='like-count']",
        "[class*='upvote-count']",
        "[class*='reaction-count']",
        "[data-test='like-count']",
        "[class*='reactions']",
        "[class*='likes']"
    ]

    # Reply container selectors inside a parent comment
    REPLY_CONTAINER_SELECTORS = [
        ".caas-comment-replies",
        ".comment-replies",
        "ul.replies",
        "div.replies",
        "[class*='replies']",
        "[class*='Replies']",
        "[class*='sub-comments']"
    ]

    @classmethod
    def extract(
        cls,
        url: str,
        html: Optional[str] = None,
        browser_manager: Optional[Any] = None,
        max_comments: int = 50
    ) -> CommentExtractionResult:
        """
        Extracts public comments from Yahoo article using the unauthenticated Nexus GraphQL endpoint,
        falling back to rendered DOM parsing if necessary.
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        notes: List[str] = []

        final_html = html
        if browser_manager and not final_html:
            notes.append("Using Playwright browser manager to load Yahoo article HTML")
            try:
                res = browser_manager.fetch_url(url)
                if res and res.html:
                    final_html = res.html
            except Exception as e:
                notes.append(f"Browser loading warning: {str(e)}")

        # 1. Attempt unauthenticated Nexus GraphQL extraction first
        content_id = cls._extract_content_id(url, final_html or "")
        if content_id:
            notes.append(f"Extracted Yahoo article content UUID: '{content_id}'")
            graphql_comments, reported_cnt, status, gql_notes, net_reqs = cls._fetch_nexus_graphql_comments(
                url=url,
                content_id=content_id,
                max_comments=max_comments
            )
            notes.extend(gql_notes)
            notes.append(f"Made {net_reqs} GraphQL network request(s)")

            if graphql_comments:
                notes.append(f"Successfully extracted {len(graphql_comments)} normalized comment(s) via Yahoo Nexus GraphQL API")
                return CommentExtractionResult(
                    url=url,
                    comments=graphql_comments[:max_comments],
                    status=CommentStatus.AVAILABLE,
                    reported_count=reported_cnt,
                    extracted_count=len(graphql_comments[:max_comments]),
                    extraction_method="YAHOO_NEXUS_GRAPHQL",
                    diagnostic_notes=notes,
                    timestamp=timestamp
                )
            elif status == CommentStatus.NONE_PRESENT:
                notes.append("Yahoo Nexus GraphQL confirmed 0 public comments present for this article")
                return CommentExtractionResult(
                    url=url,
                    comments=[],
                    status=CommentStatus.NONE_PRESENT,
                    reported_count=0,
                    extracted_count=0,
                    extraction_method="YAHOO_NEXUS_GRAPHQL",
                    diagnostic_notes=notes,
                    timestamp=timestamp
                )
            elif status == CommentStatus.NOT_LOADED and reported_cnt and reported_cnt > 0:
                notes.append(f"Yahoo Nexus GraphQL reported {reported_cnt} comments exist, but body nodes were not delivered")
                return CommentExtractionResult(
                    url=url,
                    comments=[],
                    status=CommentStatus.NOT_LOADED,
                    reported_count=reported_cnt,
                    extracted_count=0,
                    extraction_method="YAHOO_NEXUS_GRAPHQL",
                    diagnostic_notes=notes,
                    timestamp=timestamp
                )
        else:
            notes.append("Could not resolve Yahoo article content UUID from URL/HTML")

        # 2. Fallback: Parse rendered HTML DOM
        if not final_html or not final_html.strip():
            return CommentExtractionResult(
                url=url,
                status=CommentStatus.NOT_LOADED if content_id else CommentStatus.UNKNOWN,
                diagnostic_notes=notes + ["No HTML available for DOM comment extraction fallback"],
                timestamp=timestamp
            )

        diagnostics = CommentDiagnosticInspector.inspect(url, final_html)
        notes.extend(diagnostics.diagnostic_notes)

        comments = cls.parse_html_comments(final_html, url, max_comments=max_comments)

        if comments:
            notes.append(f"Successfully extracted {len(comments)} normalized comment(s) from rendered HTML DOM")
            return CommentExtractionResult(
                url=url,
                comments=comments,
                status=CommentStatus.AVAILABLE,
                reported_count=diagnostics.reported_comment_count,
                extracted_count=len(comments),
                extraction_method="RENDERED_HTML_DOM",
                diagnostic_notes=notes,
                timestamp=timestamp
            )

        final_status = diagnostics.preliminary_status
        if final_status == CommentStatus.AVAILABLE:
            final_status = CommentStatus.NOT_LOADED
            notes.append("Comment container/button was present, but zero comment elements were extracted from DOM")

        notes.append(f"No publicly rendered comment elements found. Final assigned status: {final_status.value}")

        return CommentExtractionResult(
            url=url,
            comments=[],
            status=final_status,
            reported_count=diagnostics.reported_comment_count,
            extracted_count=0,
            extraction_method="HTML_DOM_PARSER",
            diagnostic_notes=notes,
            timestamp=timestamp
        )

    @classmethod
    def _extract_content_id(cls, url: str, html: str) -> Optional[str]:
        """
        Extracts the article-specific Yahoo content UUID (e.g. 3bb64183-23f6-31cd-a492-620f51edd400)
        using a strict precedence hierarchy of authoritative article metadata sources.
        """
        uuid_pattern = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
        
        if not html and not url:
            return None

        # 1. Deep-link App Meta Tags (Highest Precedence - Empirically Verified)
        # e.g. <meta property="al:ios:url" content="yahoo://article/view?uuid=3bb64183-23f6-31cd-a492-620f51edd400&src=web">
        meta_deep_link = re.search(
            r'<meta\s+[^>]*?(?:property|name)=["\']?(?:al:(?:ios|android):url|twitter:app:url:(?:iphone|googleplay))["\']?\s+[^>]*?content=["\']?[^"\']*?uuid=(' + uuid_pattern + r')',
            html or "",
            re.I
        )
        if meta_deep_link:
            return meta_deep_link.group(1)

        meta_deep_link_rev = re.search(
            r'<meta\s+[^>]*?content=["\']?[^"\']*?uuid=(' + uuid_pattern + r')[^"\']*?["\']?\s+[^>]*?(?:property|name)=["\']?(?:al:(?:ios|android):url|twitter:app:url:(?:iphone|googleplay))["\']?',
            html or "",
            re.I
        )
        if meta_deep_link_rev:
            return meta_deep_link_rev.group(1)

        # 2. Verified Article Meta Tags
        # e.g. <meta name="caas-content-id" content="..."> or <meta name="contentId" content="...">
        meta_caas = re.search(
            r'<meta\s+[^>]*?(?:name|property)=["\']?(?:caas-content-id|contentId|content-id)["\']?\s+[^>]*?content=["\']?(' + uuid_pattern + r')',
            html or "",
            re.I
        )
        if meta_caas:
            return meta_caas.group(1)

        meta_caas_rev = re.search(
            r'<meta\s+[^>]*?content=["\']?(' + uuid_pattern + r')["\']?\s+[^>]*?(?:name|property)=["\']?(?:caas-content-id|contentId|content-id)["\']?',
            html or "",
            re.I
        )
        if meta_caas_rev:
            return meta_caas_rev.group(1)

        # 3. Article-Scoped DOM Extraction (Decomposes global header/nav elements to prevent telemetry UUID capture)
        if html:
            try:
                soup = BeautifulSoup(html, "html.parser")
                
                # Check data-caas-content-id attribute on container elements
                caas_elem = soup.find(attrs={"data-caas-content-id": True})
                if caas_elem and caas_elem.get("data-caas-content-id"):
                    val = caas_elem["data-caas-content-id"]
                    m = re.search(uuid_pattern, val, re.I)
                    if m:
                        return m.group(0)

                # Prefer <article> or article-body container; fallback to body with header/nav decomposed
                article_container = soup.find("article") or soup.find(class_=re.compile(r"caas-body|caas-container|article-body", re.I))
                search_root = article_container or soup.find("body") or soup
                
                if not article_container:
                    search_root = BeautifulSoup(str(search_root), "html.parser")
                    for header_tag in search_root.find_all(["header", "nav"]):
                        header_tag.decompose()
                    # Also remove any element with sec:topic-subnav or topic-subnav
                    for nav_elem in search_root.find_all(attrs={"data-ylk": re.compile(r"sec:topic-subnav|topic-subnav", re.I)}):
                        nav_elem.decompose()

                art_html = str(search_root)
                g_match = re.search(r'g["\']?\s*[:=]\s*["\']?(' + uuid_pattern + r')', art_html, re.I)
                if g_match:
                    return g_match.group(1)

                art_uuid = re.search(uuid_pattern, art_html, re.I)
                if art_uuid:
                    return art_uuid.group(0)
            except Exception:
                pass

        # 4. Explicit URL Fallback (only if an actual UUID is explicitly encoded in the URL string)
        if url:
            url_uuid = re.search(uuid_pattern, url, re.I)
            if url_uuid:
                return url_uuid.group(0)

        return None

    @classmethod
    def _fetch_nexus_graphql_comments(
        cls,
        url: str,
        content_id: str,
        max_comments: int = 50
    ) -> Tuple[List[Comment], Optional[int], CommentStatus, List[str], int]:
        """
        Executes unauthenticated Yahoo Nexus GraphQL queries for top-level comments and replies,
        supporting cursor pagination and normalized Comment object mapping.
        """
        graphql_url = "https://nexus-gateway-prod.media.yahoo.com/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Content-Type": "application/json",
            "Accept": "application/graphql-response+json,application/json;q=0.9",
            "x-yahoo-cg-client-name": "news",
            "Origin": "https://www.yahoo.com",
            "Referer": url
        }

        comments: List[Comment] = []
        seen_ids = set()
        reported_count: Optional[int] = None
        notes: List[str] = []
        net_requests = 0
        retrieved_at = datetime.now(timezone.utc).isoformat()
        after_cursor: Optional[str] = None
        has_next = True

        while has_next and len(comments) < max_comments and net_requests < 10:
            payload = {
                "extensions": {
                    "persistedQuery": {
                        "sha256Hash": "ycp_GetConversationWithMultipleContents_v1.2.0",
                        "version": 1
                    }
                },
                "variables": {
                    "clientId": "us-news-article_comments",
                    "contentId": content_id,
                    "after": after_cursor,
                    "count": min(max_comments - len(comments), 25),
                    "reactionContext": {
                        "clientId": "us-news-article_comments",
                        "contentId": content_id
                    },
                    "isLoggedOut": True,
                    "rankBy": ["TOP_COMMENTS", "NEWEST"]
                },
                "nullableFields": ["ycpUser", "userFeeling"]
            }

            net_requests += 1
            try:
                json_bytes = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(graphql_url, data=json_bytes, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=10) as resp:
                    resp_data = resp.read()
                    if resp.headers.get("Content-Encoding") == "gzip":
                        resp_data = gzip.decompress(resp_data)
                    body = json.loads(resp_data.decode("utf-8"))

                conv_data = body.get("data", {}).get("getContentConversation", {})
                conv_items = conv_data.get("items", {}) if isinstance(conv_data, dict) else {}

                if reported_count is None and isinstance(conv_data, dict):
                    reported_count = conv_data.get("commentsCount") or conv_items.get("totalCount")

                page_info = conv_items.get("pageInfo", {}) if isinstance(conv_items, dict) else {}
                has_next = bool(page_info.get("hasNextPage"))
                after_cursor = page_info.get("endCursor")

                edges = conv_items.get("edges", []) if isinstance(conv_items, dict) else []
                if not edges:
                    break

                for edge in edges:
                    if len(comments) >= max_comments:
                        break

                    node = edge.get("node", {})
                    c_id = node.get("id")
                    if not c_id or c_id in seen_ids:
                        continue
                    seen_ids.add(c_id)

                    raw_text = node.get("content", {}).get("body")
                    if not raw_text:
                        continue
                    text = html.unescape(raw_text).strip()

                    author = node.get("author", {}).get("profile", {}).get("nickname") or node.get("author", {}).get("profile", {}).get("handle") or "Anonymous"
                    created_at = node.get("createdAt")
                    reactions = node.get("feelingCount", {}).get("thumbup", 0)
                    replies_meta = node.get("replies", {})
                    r_count = replies_meta.get("totalCount", 0) if isinstance(replies_meta, dict) else 0

                    top_comment = Comment(
                        comment_id=str(c_id),
                        article_url=url,
                        parent_comment_id=None,
                        author_display_name=author,
                        comment_text=text,
                        published_datetime=created_at,
                        reactions={"upvotes": reactions} if isinstance(reactions, int) else reactions,
                        reply_count=r_count,
                        depth=0,
                        retrieved_at=retrieved_at
                    )
                    comments.append(top_comment)

                    # Fetch public replies if available and within max_comments
                    if r_count > 0 and len(comments) < max_comments:
                        reply_payload = {
                            "extensions": {
                                "persistedQuery": {
                                    "sha256Hash": "ycp_GetCommentReplies_v1.4.16",
                                    "version": 1
                                }
                            },
                            "variables": {
                                "clientId": "us-news-article_comments",
                                "contentId": content_id,
                                "commentId": str(c_id),
                                "after": None,
                                "count": min(max_comments - len(comments), 10),
                                "reactionContext": {
                                    "clientId": "us-news-article_comments",
                                    "contentId": content_id
                                },
                                "isLoggedOut": True
                            },
                            "nullableFields": ["ycpUser", "userFeeling"]
                        }

                        net_requests += 1
                        try:
                            r_json_bytes = json.dumps(reply_payload).encode("utf-8")
                            r_req = urllib.request.Request(graphql_url, data=r_json_bytes, headers=headers, method="POST")
                            with urllib.request.urlopen(r_req, timeout=10) as r_resp:
                                r_resp_data = r_resp.read()
                                if r_resp.headers.get("Content-Encoding") == "gzip":
                                    r_resp_data = gzip.decompress(r_resp_data)
                                r_body = json.loads(r_resp_data.decode("utf-8"))

                            r_edges = r_body.get("data", {}).get("getContentComment", {}).get("replies", {}).get("edges", [])
                            for r_edge in r_edges:
                                if len(comments) >= max_comments:
                                    break
                                r_node = r_edge.get("node", {})
                                r_id = r_node.get("id")
                                if not r_id or r_id in seen_ids:
                                    continue
                                seen_ids.add(r_id)

                                raw_r_text = r_node.get("content", {}).get("body")
                                if not raw_r_text:
                                    continue
                                r_text = html.unescape(raw_r_text).strip()

                                r_author = r_node.get("author", {}).get("profile", {}).get("nickname") or r_node.get("author", {}).get("profile", {}).get("handle") or "Anonymous"
                                r_created = r_node.get("createdAt")
                                r_react = r_node.get("feelingCount", {}).get("thumbup", 0)

                                reply_comment = Comment(
                                    comment_id=str(r_id),
                                    article_url=url,
                                    parent_comment_id=str(c_id),
                                    author_display_name=r_author,
                                    comment_text=r_text,
                                    published_datetime=r_created,
                                    reactions={"upvotes": r_react} if isinstance(r_react, int) else r_react,
                                    reply_count=0,
                                    depth=1,
                                    retrieved_at=retrieved_at
                                )
                                comments.append(reply_comment)
                        except Exception as e:
                            notes.append(f"Failed fetching replies for comment '{c_id}': {str(e)}")

            except Exception as e:
                notes.append(f"Yahoo Nexus GraphQL query failed on page request {net_requests}: {str(e)}")
                break

        if comments:
            status = CommentStatus.AVAILABLE
        elif reported_count == 0:
            status = CommentStatus.NONE_PRESENT
        elif reported_count is not None and reported_count > 0:
            status = CommentStatus.NOT_LOADED
        else:
            status = CommentStatus.UNKNOWN

        return comments, reported_count, status, notes, net_requests


    @classmethod
    def _load_and_interact(cls, url: str, browser_manager: Any, notes: List[str]) -> str:
        """
        Loads URL in Playwright, attempts 'View comments' button click, waits for dynamic DOM updates,
        and returns updated HTML string.
        """
        try:
            context = browser_manager.create_context()
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded")

            button_selectors = [
                "button:has-text('View comments')",
                "a:has-text('View comments')",
                "[role='button']:has-text('View comments')",
                "button:has-text('Comments')",
                ".caas-button:has-text('comments')"
            ]

            target_btn = None
            for sel in button_selectors:
                try:
                    el = page.query_selector(sel)
                    if el and el.is_visible():
                        target_btn = el
                        break
                except Exception:
                    pass

            if target_btn:
                notes.append("Found interactive 'View comments' button; attempting click")
                try:
                    target_btn.scroll_into_view_if_needed()
                    target_btn.click(timeout=5000)
                    page.wait_for_timeout(3000)
                    notes.append("Successfully clicked 'View comments' button and waited for dynamic rendering")
                except Exception as e:
                    notes.append(f"Attempted to click 'View comments' button but encountered error: {str(e)}")
            else:
                notes.append("No active 'View comments' button found during live browser session")

            content = page.content()
            context.close()
            return content
        except Exception as e:
            notes.append(f"Browser interaction error during comment extraction: {str(e)}")
            return ""

    @classmethod
    def parse_html_comments(cls, html: str, article_url: str, max_comments: int = 50) -> List[Comment]:
        """
        Parses HTML string for structured public comment items, supporting top-level comments,
        nested reply structures, deduplication, and max_comments limits.
        """
        if not html or not html.strip():
            return []

        soup = BeautifulSoup(html, "html.parser")
        retrieved_at = datetime.now(timezone.utc).isoformat()
        comments: List[Comment] = []
        seen_ids = set()

        top_level_nodes = cls._find_comment_nodes(soup)

        for node in top_level_nodes:
            if len(comments) >= max_comments:
                break

            comment_obj = cls._parse_single_node(node, article_url, retrieved_at, parent_id=None, depth=0)
            if comment_obj and comment_obj.comment_id not in seen_ids:
                seen_ids.add(comment_obj.comment_id)
                comments.append(comment_obj)

                # Check for replies nested inside this node
                replies = cls._parse_nested_replies(
                    node,
                    article_url,
                    retrieved_at,
                    parent_id=comment_obj.comment_id,
                    depth=1,
                    seen_ids=seen_ids,
                    max_comments=max_comments - len(comments)
                )
                comment_obj.reply_count = len(replies)
                comments.extend(replies)

        return comments[:max_comments]

    @classmethod
    def _find_comment_nodes(cls, soup: BeautifulSoup) -> List[Any]:
        """
        Searches soup for comment item nodes, preferring top-level items outside of nested reply containers.
        """
        for selector in cls.COMMENT_ITEM_SELECTORS:
            items = soup.select(selector)
            if items:
                top_level = []
                for item in items:
                    is_reply = False
                    for reply_sel in cls.REPLY_CONTAINER_SELECTORS:
                        if item.find_parent(class_=re.compile(reply_sel.strip(".#[]="), re.I)) or item.find_parent(select=reply_sel if reply_sel.startswith(".") or reply_sel.startswith("#") else None):
                            is_reply = True
                            break
                    if not is_reply:
                        top_level.append(item)
                return top_level if top_level else items
        return []

    @classmethod
    def _parse_single_node(
        cls,
        node: BeautifulSoup,
        article_url: str,
        retrieved_at: str,
        parent_id: Optional[str] = None,
        depth: int = 0
    ) -> Optional[Comment]:
        """
        Parses a single HTML comment node into a normalized Comment object.
        """
        # Make a copy of node to decompose child comment items / reply containers before text extraction
        node_copy = BeautifulSoup(str(node), "html.parser")
        for reply_sel in cls.REPLY_CONTAINER_SELECTORS:
            for child in node_copy.select(reply_sel):
                child.decompose()

        # Extract comment text first from node_copy
        text = None
        for sel in cls.TEXT_SELECTORS:
            elem = node_copy.select_one(sel)
            if elem:
                text_content = elem.get_text().strip()
                if text_content:
                    text = text_content
                    break

        if not text:
            text_content = node_copy.get_text().strip()
            if text_content and len(text_content) < 2000:
                text = text_content

        if not text:
            return None

        # Extract comment ID
        comment_id = node.get("data-comment-id") or node.get("data-id") or node.get("id")
        if not comment_id:
            author_elem = node_copy.select_one(cls.AUTHOR_SELECTORS[0]) if cls.AUTHOR_SELECTORS else None
            author_peek = author_elem.get_text().strip() if author_elem else ""
            raw_hash_input = f"{author_peek}_{text}"
            comment_id = f"comment_{hashlib.md5(raw_hash_input.encode('utf-8')).hexdigest()[:12]}"

        # Extract author name
        author_name = None
        for sel in cls.AUTHOR_SELECTORS:
            elem = node_copy.select_one(sel)
            if elem and elem.get_text().strip():
                author_name = elem.get_text().strip()
                break

        # Extract timestamp
        timestamp_str = None
        for sel in cls.TIMESTAMP_SELECTORS:
            elem = node_copy.select_one(sel)
            if elem:
                timestamp_str = elem.get("datetime") or elem.get_text().strip()
                if timestamp_str:
                    break

        # Extract reactions count
        reactions_count = None
        for sel in cls.REACTION_SELECTORS:
            elem = node_copy.select_one(sel)
            if elem:
                r_text = elem.get_text().strip()
                m = re.search(r"\d+", r_text)
                if m:
                    reactions_count = int(m.group(0))
                    break

        return Comment(
            comment_id=str(comment_id),
            article_url=article_url,
            parent_comment_id=parent_id,
            author_display_name=author_name,
            comment_text=text,
            published_datetime=timestamp_str,
            reactions=reactions_count,
            reply_count=0,
            depth=depth,
            retrieved_at=retrieved_at
        )

    @classmethod
    def _parse_nested_replies(
        cls,
        parent_node: BeautifulSoup,
        article_url: str,
        retrieved_at: str,
        parent_id: str,
        depth: int,
        seen_ids: set,
        max_comments: int
    ) -> List[Comment]:
        """
        Finds and parses nested replies inside a parent comment node.
        """
        replies: List[Comment] = []
        if max_comments <= 0:
            return replies

        reply_items = []
        for reply_sel in cls.REPLY_CONTAINER_SELECTORS:
            container = parent_node.select_one(reply_sel)
            if container:
                for item_sel in cls.COMMENT_ITEM_SELECTORS:
                    found = container.select(item_sel)
                    if found:
                        reply_items = found
                        break
                if reply_items:
                    break

        for r_node in reply_items:
            if len(replies) >= max_comments:
                break
            r_obj = cls._parse_single_node(r_node, article_url, retrieved_at, parent_id=parent_id, depth=depth)
            if r_obj and r_obj.comment_id not in seen_ids:
                seen_ids.add(r_obj.comment_id)
                replies.append(r_obj)

        return replies


class MSNCommentExtractor:
    """
    Evidence-driven public comment extractor for MSN News articles using the unauthenticated
    MSN Peregrine Community REST API, with fallback to HTML/Shadow DOM parser.
    """

    @classmethod
    def extract(
        cls,
        url: str,
        html: Optional[str] = None,
        browser_manager: Optional[Any] = None,
        max_comments: int = 50
    ) -> CommentExtractionResult:
        timestamp = datetime.now(timezone.utc).isoformat()
        diagnostic_notes = []

        # 1. Resolve CMSID and locale
        cmsid, locale = cls._extract_cmsid_and_locale(url, html or "")
        if cmsid:
            diagnostic_notes.append(f"MSN CMSID resolved: '{cmsid}', locale: '{locale}'")
        else:
            diagnostic_notes.append("MSN CMSID could not be resolved from URL/HTML")

        reported_count: Optional[int] = None
        comment_status = CommentStatus.UNKNOWN
        community_meta = None

        # 2. Query MSN Peregrine Community metadata first if CMSID available
        if cmsid:
            community_meta = cls._fetch_community_metadata(cmsid, html=html)
            if community_meta:
                diagnostic_notes.append(f"Fetched public MSN Community metadata ({community_meta.get('source', 'api')})")
                allow_comments = community_meta.get("allowComments")
                raw_status = str(community_meta.get("commentStatus", "")).lower()
                disabled_msg = str(community_meta.get("disableMessage", "")).strip()

                if "commentCount" in community_meta:
                    try:
                        reported_count = int(community_meta["commentCount"])
                    except (ValueError, TypeError):
                        pass

                # Check explicit disabled / zero statuses
                if allow_comments is False or disabled_msg or raw_status in ("off", "disabled", "closed"):
                    return CommentExtractionResult(
                        url=url,
                        comments=[],
                        status=CommentStatus.DISABLED,
                        reported_count=reported_count or 0,
                        extracted_count=0,
                        extraction_method="MSN_COMMUNITY_API",
                        diagnostic_notes=diagnostic_notes + [f"Comments explicitly disabled on MSN (allowComments={allow_comments})"],
                        timestamp=timestamp
                    )
                elif allow_comments is True and reported_count == 0:
                    return CommentExtractionResult(
                        url=url,
                        comments=[],
                        status=CommentStatus.NONE_PRESENT,
                        reported_count=0,
                        extracted_count=0,
                        extraction_method="MSN_COMMUNITY_API",
                        diagnostic_notes=diagnostic_notes + ["MSN Community API reported allowComments=True and commentCount=0"],
                        timestamp=timestamp
                    )

            # 3. Query MSN Community API for comment objects
            api_comments, api_reported, api_status, api_notes, req_count = cls._fetch_community_comments(
                url=url,
                cmsid=cmsid,
                locale=locale,
                max_comments=max_comments
            )
            diagnostic_notes.extend(api_notes)
            diagnostic_notes.append(f"Made {req_count} MSN Community API request(s)")

            if api_reported is not None and reported_count is None:
                reported_count = api_reported

            if api_comments:
                diagnostic_notes.append(f"Successfully extracted {len(api_comments)} public comment(s) via MSN Community API")
                return CommentExtractionResult(
                    url=url,
                    comments=api_comments[:max_comments],
                    status=CommentStatus.AVAILABLE,
                    reported_count=reported_count or len(api_comments),
                    extracted_count=len(api_comments[:max_comments]),
                    extraction_method="MSN_COMMUNITY_API",
                    diagnostic_notes=diagnostic_notes,
                    timestamp=timestamp
                )
            elif api_status == CommentStatus.NONE_PRESENT:
                return CommentExtractionResult(
                    url=url,
                    comments=[],
                    status=CommentStatus.NONE_PRESENT,
                    reported_count=0,
                    extracted_count=0,
                    extraction_method="MSN_COMMUNITY_API",
                    diagnostic_notes=diagnostic_notes,
                    timestamp=timestamp
                )
            elif api_status == CommentStatus.NOT_LOADED and reported_count and reported_count > 0:
                return CommentExtractionResult(
                    url=url,
                    comments=[],
                    status=CommentStatus.NOT_LOADED,
                    reported_count=reported_count,
                    extracted_count=0,
                    extraction_method="MSN_COMMUNITY_API",
                    diagnostic_notes=diagnostic_notes + [f"MSN reported {reported_count} comments exist but API body fetch yielded 0"],
                    timestamp=timestamp
                )

        # 4. Fallback: Parse Rendered HTML DOM / Shadow DOM
        if html:
            extracted_comments, parse_notes = cls._parse_rendered_comments(url, html, max_comments=max_comments)
            diagnostic_notes.extend(parse_notes)

            if extracted_comments:
                return CommentExtractionResult(
                    url=url,
                    comments=extracted_comments[:max_comments],
                    status=CommentStatus.AVAILABLE,
                    reported_count=reported_count or len(extracted_comments),
                    extracted_count=len(extracted_comments[:max_comments]),
                    extraction_method="RENDERED_HTML_DOM",
                    diagnostic_notes=diagnostic_notes,
                    timestamp=timestamp
                )

        final_status = CommentStatus.NOT_LOADED if (reported_count and reported_count > 0) else CommentStatus.UNKNOWN

        return CommentExtractionResult(
            url=url,
            comments=[],
            status=final_status,
            reported_count=reported_count,
            extracted_count=0,
            extraction_method="MSN_COMMUNITY_PARSER",
            diagnostic_notes=diagnostic_notes,
            timestamp=timestamp
        )

    @classmethod
    def _extract_cmsid(cls, url: str, html: str = "") -> Optional[str]:
        """Extracts MSN CMSID from URL or HTML (backward compatibility helper)."""
        return cls._extract_cmsid_and_locale(url, html)[0]

    @classmethod
    def _extract_cmsid_and_locale(cls, url: str, html: str) -> Tuple[Optional[str], str]:
        """Extracts MSN CMSID (e.g. AA1WCoGY) and locale (e.g. en-us) from URL or HTML metadata."""
        locale = "en-us"
        locale_match = re.search(r'/([a-z]{2}-[a-z]{2})/', url, re.I)
        if locale_match:
            locale = locale_match.group(1).lower()

        cmsid = None
        match = re.search(r'/(?:ar|vi|ss)-([A-Za-z0-9]+)', url)
        if match:
            cmsid = match.group(1)

        if not cmsid:
            match = re.search(r'cmsid=([A-Za-z0-9]+)', url, re.IGNORECASE)
            if match:
                cmsid = match.group(1)

        if not cmsid and html:
            match = re.search(r'cmsid=([A-Za-z0-9]+)', html, re.IGNORECASE)
            if match:
                cmsid = match.group(1)
            else:
                match = re.search(r'/(?:ar|vi|ss)-([A-Za-z0-9]+)', html)
                if match:
                    cmsid = match.group(1)

        return cmsid, locale

    @classmethod
    def _fetch_community_metadata(cls, cmsid: str, html: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Fetches public community metadata from MSN Peregrine API without credentials."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json"
        }

        # 1. Attempt Peregrine community activity endpoint first
        activity_url = f"https://assets.msn.com/service/MSN/Peregrine/community/v1/contents/{urllib.parse.quote(cmsid)}/activity?user=m-anon"
        try:
            req = urllib.request.Request(activity_url, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                if isinstance(data, dict) and "allowComments" in data:
                    return {
                        "allowComments": bool(data.get("allowComments")),
                        "commentCount": int(data.get("commentCount", 0)),
                        "source": "peregrine_activity"
                    }
        except Exception:
            pass

        # 2. Fall back to legacy community URLs endpoint
        urls_endpoint = f"https://assets.msn.com/service/community/urls/?cmsid={urllib.parse.quote(cmsid)}&market=en-us&version=1.1"
        if html:
            key_match = re.search(r'apikey["\']?\s*[:=]\s*["\']?([a-zA-Z0-9_\-]+)["\']?', html, re.IGNORECASE)
            if key_match and len(key_match.group(1)) > 5:
                urls_endpoint += f"&apikey={key_match.group(1)}"

        try:
            req = urllib.request.Request(urls_endpoint, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                if isinstance(data, dict) and "value" in data and len(data["value"]) > 0:
                    val = data["value"][0]
                    summary = val.get("commentSummary", {})
                    cnt = summary.get("totalCount", 0) if isinstance(summary, dict) else 0
                    disabled = val.get("commentStatus", "").lower() in ("off", "disabled", "closed") or bool(val.get("disableMessage"))
                    return {
                        "allowComments": not disabled,
                        "commentCount": cnt,
                        "commentStatus": val.get("commentStatus"),
                        "disableMessage": val.get("disableMessage"),
                        "source": "community_urls"
                    }
        except Exception:
            pass
        return None

    @classmethod
    def _fetch_community_comments(
        cls,
        url: str,
        cmsid: str,
        locale: str = "en-us",
        max_comments: int = 50
    ) -> Tuple[List[Comment], Optional[int], CommentStatus, List[str], int]:
        """
        Fetches public comments from MSN Community API using $top and $skip pagination,
        mapping returned items into normalized Comment objects.
        """
        base_api = "https://assets.msn.com/service/community/comments/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json"
        }

        comments: List[Comment] = []
        seen_ids = set()
        notes: List[str] = []
        req_count = 0
        retrieved_at = datetime.now(timezone.utc).isoformat()
        skip = 0
        batch_size = max(max_comments, 50)
        reported_count: Optional[int] = None

        while len(comments) < max_comments and req_count < 10:
            content_id_param = f"{cmsid}_{locale}"
            api_url = f"{base_api}?contentId={urllib.parse.quote(content_id_param)}&$top={batch_size}&$skip={skip}&$orderby=Rating"
            req_count += 1

            try:
                req = urllib.request.Request(api_url, headers=headers)
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))

                # Extract reported totalCount if present at top level or container level
                if reported_count is None and isinstance(data, dict):
                    if "totalCount" in data:
                        try:
                            reported_count = int(data["totalCount"])
                        except (ValueError, TypeError):
                            pass

                # Unwrap raw items across supported MSN response formats
                items = []
                val = data.get("value") if isinstance(data, dict) else None
                if isinstance(val, list) and len(val) > 0:
                    first_val = val[0]
                    if isinstance(first_val, dict) and "items" in first_val:
                        items = first_val.get("items", [])
                        if reported_count is None and "totalCount" in first_val:
                            try:
                                reported_count = int(first_val["totalCount"])
                            except (ValueError, TypeError):
                                pass
                    elif isinstance(first_val, dict) and ("body" in first_val or "content" in first_val or "id" in first_val):
                        items = val
                elif isinstance(data, dict) and isinstance(data.get("items"), list):
                    items = data.get("items", [])

                if not items:
                    break

                for item in items:
                    if len(comments) >= max_comments:
                        break

                    c_id = item.get("id")
                    if not c_id or c_id in seen_ids:
                        continue
                    seen_ids.add(c_id)

                    raw_body = item.get("body") or item.get("content")
                    if not raw_body or not str(raw_body).strip():
                        continue
                    body_text = html.unescape(str(raw_body)).strip()

                    parent_id = item.get("parentId")
                    if not parent_id or not str(parent_id).strip():  # Empty string or None -> top-level
                        parent_id = None

                    # Extract author name from user links if present
                    author_name = None
                    links = item.get("links", [])
                    if isinstance(links, list):
                        for link in links:
                            if isinstance(link, dict) and link.get("type") == "User":
                                u_item = link.get("item", {})
                                author_name = u_item.get("primaryName") or u_item.get("firstName")
                                break
                    if not author_name:
                        author_name = item.get("createdBy") or "Anonymous"

                    created_time = item.get("createdTime")

                    # Extract upvotes / reactions
                    reactions = None
                    react_summary = item.get("reactionSummary", {})
                    if isinstance(react_summary, dict):
                        upvotes = react_summary.get("totalCount", 0)
                        if upvotes:
                            reactions = {"upvotes": int(upvotes)}

                    # Extract reply count
                    reply_count = 0
                    cmmt_summary = item.get("commentSummary", {})
                    if isinstance(cmmt_summary, dict):
                        reply_count = int(cmmt_summary.get("totalCount", 0))

                    depth = 0 if parent_id is None else 1

                    c_obj = Comment(
                        comment_id=str(c_id),
                        article_url=url,
                        parent_comment_id=parent_id,
                        author_display_name=author_name,
                        comment_text=body_text,
                        published_datetime=created_time,
                        reactions=reactions,
                        reply_count=reply_count,
                        depth=depth,
                        retrieved_at=retrieved_at
                    )
                    comments.append(c_obj)

                skip += len(items)
                if len(items) < batch_size:
                    break
            except Exception as e:
                notes.append(f"MSN Community API request {req_count} failed: {str(e)}")
                break

        if comments:
            status = CommentStatus.AVAILABLE
        elif reported_count == 0:
            status = CommentStatus.NONE_PRESENT
        elif reported_count is not None and reported_count > 0:
            status = CommentStatus.NOT_LOADED
        else:
            status = CommentStatus.UNKNOWN

        return comments, reported_count, status, notes, req_count

    @classmethod
    def _parse_rendered_comments(
        cls,
        article_url: str,
        html: str,
        max_comments: int = 50
    ) -> tuple[List[Comment], List[str]]:
        """Parses HTML for rendered MSN comment items and nested replies."""
        comments: List[Comment] = []
        notes: List[str] = []
        retrieved_at = datetime.now(timezone.utc).isoformat()
        soup = BeautifulSoup(html, "html.parser")
        seen_ids = set()

        comment_selectors = [
            ".msn-comment-item",
            ".social-comment-card",
            "div[data-comment-id]",
            "div[class*='comment-card']",
            "div[class*='social-comment']"
        ]

        found_nodes = []
        for sel in comment_selectors:
            nodes = soup.select(sel)
            if nodes:
                found_nodes = nodes
                notes.append(f"Found {len(nodes)} comment elements using selector '{sel}'")
                break

        for node in found_nodes:
            if len(comments) >= max_comments:
                break

            text_el = node.select_one(".comment-text, .comment-content, p, .body")
            comment_text = text_el.get_text(strip=True) if text_el else node.get_text(strip=True)
            if not comment_text or len(comment_text) < 2:
                continue

            comment_id = node.get("data-comment-id") or node.get("id")
            if not comment_id:
                comment_id = "msn_" + hashlib.md5(comment_text.encode('utf-8')).hexdigest()[:12]

            if comment_id in seen_ids:
                continue
            seen_ids.add(comment_id)

            author_el = node.select_one(".comment-author, .user-name, .author, [itemprop='author']")
            author_name = author_el.get_text(strip=True) if author_el else None

            time_el = node.select_one("time, .comment-date, .timestamp")
            pub_date = time_el.get("datetime") if time_el and time_el.get("datetime") else (time_el.get_text(strip=True) if time_el else None)

            parent_id = node.get("data-parent-id")
            try:
                depth = int(node.get("data-depth", 0))
            except (ValueError, TypeError):
                depth = 0 if not parent_id else 1

            try:
                reply_count = int(node.get("data-reply-count", 0))
            except (ValueError, TypeError):
                reply_count = 0

            reactions = None
            react_el = node.select_one(".upvote-count, .reactions-count, .like-count")
            if react_el and react_el.get_text(strip=True).isdigit():
                reactions = {"upvotes": int(react_el.get_text(strip=True))}

            comment_obj = Comment(
                comment_id=comment_id,
                article_url=article_url,
                parent_comment_id=parent_id,
                author_display_name=author_name,
                comment_text=comment_text,
                published_datetime=pub_date,
                reactions=reactions,
                reply_count=reply_count,
                depth=depth,
                retrieved_at=retrieved_at
            )
            comments.append(comment_obj)

        return comments, notes




