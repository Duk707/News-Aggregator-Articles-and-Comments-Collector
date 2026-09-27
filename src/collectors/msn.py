import re
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from bs4 import BeautifulSoup

from src.collectors.base import BaseAdapter
from src.utils.urls import extract_domain
from src.browser import BrowserManager, BrowserFetchResult
from src.extraction.metadata import MetadataExtractor, ExtractedMetadata
from src.extraction.article_text import ArticleTextExtractor, ExtractedArticleText
from src.models import CommentStatus
from src.extraction.comments import CommentExtractionResult, MSNCommentExtractor


class MSNAdapter(BaseAdapter):
    """
    Source adapter for MSN News article platform.
    """
    platform_name: str = "MSN"
    adapter_name: str = "MSNAdapter"

    def supports(self, url: str) -> bool:
        """
        Returns True if the URL belongs to MSN News.
        """
        domain = extract_domain(url)
        if not domain:
            return False

        # Matches msn.com, www.msn.com, etc.
        return domain == "msn.com" or domain.endswith(".msn.com")

    def load_article(self, url: str, browser_manager: Optional[BrowserManager] = None) -> BrowserFetchResult:
        """
        Loads an MSN article using Playwright and compiles Shadow DOM paragraph tags
        into the rendered HTML content shell so downstream body extraction works reliably.
        """
        if not self.supports(url):
            return BrowserFetchResult(
                requested_url=url,
                success=False,
                error_type="UNSUPPORTED",
                error_message=f"URL '{url}' is not supported by {self.adapter_name}",
                retrieved_at=datetime.now(timezone.utc).isoformat()
            )

        def _custom_fetch(bm: BrowserManager) -> BrowserFetchResult:
            context = bm.create_context()
            page = context.new_page()
            response = None
            try:
                response = page.goto(url, timeout=bm.navigation_timeout_ms, wait_until="load")
            except Exception:
                pass

            time.sleep(5)  # Allow client-side JS hydration

            try:
                page.evaluate("window.scrollBy(0, 1000)")
            except Exception:
                pass
            time.sleep(3)

            final_url = page.url
            status_code = response.status if response else 200

            # Deep shadow DOM paragraph compilation
            shadow_p = page.evaluate(r"""() => {
                const paragraphs = [];
                const seenTexts = new Set();

                function isUnwanted(node) {
                    if (!node || node.nodeType !== 1) return false;
                    const tag = node.tagName.toLowerCase();
                    if (['script', 'style', 'noscript', 'iframe', 'svg', 'button', 'form', 'nav', 'header', 'footer', 'aside'].includes(tag)) return true;

                    const cls = (typeof node.className === 'string') 
                        ? node.className.toLowerCase() 
                        : (node.getAttribute ? (node.getAttribute('class') || '').toLowerCase() : '');
                    const id = (typeof node.id === 'string') 
                        ? node.id.toLowerCase() 
                        : (node.getAttribute ? (node.getAttribute('id') || '').toLowerCase() : '');
                    const role = node.getAttribute ? (node.getAttribute('role') || '').toLowerCase() : '';
                    const ariaModal = node.getAttribute ? (node.getAttribute('aria-modal') || '').toLowerCase() : '';
                    const dataTest = node.getAttribute ? (node.getAttribute('data-test-locator') || '').toLowerCase() : '';
                    const dataComp = node.getAttribute ? (node.getAttribute('data-component') || '').toLowerCase() : '';
                    const dataSubComp = node.getAttribute ? (node.getAttribute('data-sub-component') || '').toLowerCase() : '';

                    // Exclude modal dialogs and video overlay containers
                    if (role === 'dialog' || role === 'alertdialog' || ariaModal === 'true') {
                        return true;
                    }
                    if (cls.includes('vjs-modal-dialog') || cls.includes('modal-dialog') || cls.includes('vjs-modal') ||
                        cls.includes('vjs-control-text') || cls.includes('vjs-error-display') || cls.includes('vjs-text-track-settings')) {
                        return true;
                    }

                    if (cls.includes('ad-') || cls.includes('advertisement') || cls.includes('recommend') ||
                        cls.includes('related') || cls.includes('carousel') || cls.includes('outbrain') ||
                        cls.includes('taboola') || cls.includes('feed') || cls.includes('source-link') ||
                        cls.includes('provider-link') || cls.includes('article-tags') || cls.includes('syndication-footer') ||
                        id.includes('ad-') || dataTest.includes('recommended') || dataTest.includes('taboola') ||
                        dataComp.includes('recommend') || dataSubComp.includes('recommend') ||
                        dataComp.includes('source-link') || dataComp.includes('provider-link')) {
                        return true;
                    }
                    return false;
                }

                function walk(node) {
                    if (!node) return;
                    if (isUnwanted(node)) return;

                    if (node.nodeType === 1 && node.tagName.toLowerCase() === 'p') {
                        const txt = (node.textContent || '').trim().replace(/\\s+/g, ' ');
                        const lower = txt.toLowerCase();

                        // Narrowly anchored boilerplate text guardrails
                        const isBoilerplate = 
                            /^original article source:/i.test(txt) ||
                            (/^source:\s+[a-z0-9]/i.test(txt) && txt.length < 120) ||
                            /^(?:read|Read) on the \w+ app/i.test(txt) ||
                            txt === "READ ON THE FOX BUSINESS APP" ||
                            /^provided by \w+ media/i.test(txt) ||
                            /^distributed by \w+/i.test(txt);

                        if (!isBoilerplate && txt.length > 20 && !seenTexts.has(txt)) {
                            seenTexts.add(txt);
                            paragraphs.push(txt);
                        }
                        return; // Do not recurse inside <p> tag
                    }

                    if (node.shadowRoot) {
                        walk(node.shadowRoot);
                    }

                    const children = node.children || node.childNodes || [];
                    for (let c of children) {
                        walk(c);
                    }
                }

                // Prefer walking main article container if present
                const articleRoot = document.querySelector('article, msn-article, [data-component="article"], main');
                if (articleRoot) {
                    walk(articleRoot);
                }

                // Fall back to document.body if articleRoot yielded no paragraphs
                if (paragraphs.length === 0) {
                    walk(document.body);
                }

                return paragraphs;
            }""")

            html = page.content()

            # Append shadow paragraphs inside an article shell tag if shadow DOM text was found
            if shadow_p:
                p_html = "".join(f"<p>{p}</p>" for p in shadow_p)
                html = html + f"\n<article class='msn-hydrated-body'>{p_html}</article>"

            return BrowserFetchResult(
                requested_url=url,
                final_url=final_url,
                status_code=status_code,
                html=html,
                success=True,
                retrieved_at=datetime.now(timezone.utc).isoformat()
            )

        if browser_manager:
            return _custom_fetch(browser_manager)
        else:
            with BrowserManager(headless=True) as bm:
                return _custom_fetch(bm)

    def extract_metadata(self, html: str, fallback_url: Optional[str] = None) -> ExtractedMetadata:
        """
        Extracts structured metadata from MSN article HTML using ordered fallbacks.
        """
        return MetadataExtractor.extract(html, fallback_canonical_url=fallback_url)

    def extract_article_body(self, html: str) -> ExtractedArticleText:
        """
        Extracts article body text from MSN HTML, supporting hydrated Shadow DOM containers
        as well as standard <article> / paragraph elements.
        """
        if not html or not html.strip():
            return ExtractedArticleText(success=False, extraction_method="None")

        soup = BeautifulSoup(html, "html.parser")

        # Check hydrated Shadow DOM container first if present
        hydrated_article = soup.find("article", class_="msn-hydrated-body")
        if hydrated_article:
            # Decompose unwanted modal dialogs, Video.js containers, and ads inside hydrated body
            unwanted_selectors = [
                "[role='dialog']",
                "[role='alertdialog']",
                "[aria-modal='true']",
                ".vjs-modal-dialog",
                ".vjs-control-text",
                ".vjs-error-display",
                ".vjs-text-track-settings",
                ".modal-dialog",
                ".source-link",
                ".provider-link",
                ".article-tags",
                ".syndication-footer",
                ".caas-readmore",
                ".caas-sponsored",
                ".caas-related-articles",
                ".caas-carousel",
                ".caas-share-buttons",
                ".caas-footer",
                "#comments",
                ".comments-container"
            ]
            for sel in unwanted_selectors:
                for el in hydrated_article.select(sel):
                    el.decompose()

            paragraphs = []
            seen_texts = set()
            for p in hydrated_article.find_all("p"):
                txt = p.get_text(strip=True)
                txt_cleaned = re.sub(r'\s+', ' ', txt)
                if len(txt_cleaned) > 20 and txt_cleaned not in seen_texts:
                    if ArticleTextExtractor._is_valid_paragraph(txt_cleaned):
                        seen_texts.add(txt_cleaned)
                        paragraphs.append(txt_cleaned)
            if paragraphs:
                body_text = "\n\n".join(paragraphs)
                return ExtractedArticleText(
                    text=body_text,
                    paragraph_count=len(paragraphs),
                    char_count=len(body_text),
                    success=True,
                    extraction_method="MSN Shadow DOM Hydration"
                )

        # Fallback to standard ArticleTextExtractor
        return ArticleTextExtractor.extract(html)

    def extract_comments(
        self,
        url: str,
        html: Optional[str] = None,
        browser_manager: Optional[BrowserManager] = None,
        max_comments: int = 50
    ) -> CommentExtractionResult:
        """
        Extracts public comments from MSN article HTML or via MSN Peregrine Community API metadata.
        """
        return MSNCommentExtractor.extract(
            url=url,
            html=html,
            browser_manager=browser_manager,
            max_comments=max_comments
        )

    def get_loading_diagnostics(self, fetch_result: BrowserFetchResult) -> Dict[str, Any]:
        """
        Generates a diagnostic summary dictionary of the page loading attempt.
        """
        return {
            "platform": self.platform_name,
            "adapter": self.adapter_name,
            "requested_url": fetch_result.requested_url,
            "final_url": fetch_result.final_url,
            "status_code": fetch_result.status_code,
            "success": fetch_result.success,
            "error_type": fetch_result.error_type,
            "error_message": fetch_result.error_message,
            "retrieved_at": fetch_result.retrieved_at,
            "html_bytes": len(fetch_result.html.encode('utf-8')) if fetch_result.html else 0
        }
