import re
from typing import Optional, List
from bs4 import BeautifulSoup, Tag
from pydantic import BaseModel, Field


class ExtractedArticleText(BaseModel):
    """
    Data model representing extracted main article body text and extraction metadata.
    """
    text: Optional[str] = Field(default=None, description="Normalized main article body text")
    paragraph_count: int = Field(default=0, description="Total number of article paragraphs extracted")
    char_count: int = Field(default=0, description="Total character length of extracted text")
    extraction_method: str = Field(default="Unknown", description="DOM selector or strategy used for body extraction")
    success: bool = Field(default=False, description="True if non-empty article text was extracted")
    warning: Optional[str] = Field(default=None, description="Warning message if text is empty or suspicious")


class ArticleTextExtractor:
    """
    Extractor for article body text.
    Isolates article body paragraphs while removing navigation, advertisements,
    recommendations, footers, and comment sections.
    """

    # Unwanted HTML tags to decompose completely
    UNWANTED_TAGS: List[str] = [
        "script", "style", "noscript", "iframe", "svg", "button", "form",
        "nav", "header", "footer", "aside"
    ]

    # Unwanted CSS selectors (ads, recommendations, social share, comments, footers, modal dialogs)
    UNWANTED_SELECTORS: List[str] = [
        "[class*='ad-']",
        "[class*='advertisement']",
        "[id*='ad-']",
        "[role='dialog']",
        "[role='alertdialog']",
        "[aria-modal='true']",
        ".vjs-modal-dialog",
        ".modal-dialog",
        ".caas-readmore",
        ".caas-sponsored",
        ".caas-related-articles",
        ".caas-carousel",
        ".caas-share-buttons",
        ".caas-footer",
        ".col-footer",
        "[data-component='RelatedContent']",
        "[data-component='RelatedArticles']",
        "[data-component='SubscribeBanner']",
        "[data-component='Footer']",
        ".caas-byline-collapse",
        ".caas-copyright",
        ".article-tags",
        ".source-link",
        ".provider-link",
        "#comments",
        ".comments-container",
        "[data-test-locator='comments']",
        "[data-test-locator='recommended-articles']",
        "[data-test-locator='taboola']",
        ".outbrain"
    ]

    # Target article container selectors in priority order
    ARTICLE_CONTAINER_SELECTORS: List[str] = [
        ".caas-body",
        "div[data-component='caas-body']",
        "[itemprop='articleBody']",
        "article",
        "main"
    ]

    @classmethod
    def extract(cls, html: str) -> ExtractedArticleText:
        """
        Parses HTML and extracts clean main article body text.

        Args:
            html: Raw or rendered HTML content string.

        Returns:
            ExtractedArticleText: Structured extraction result with body text and metrics.
        """
        if not html or not html.strip():
            return ExtractedArticleText(
                success=False,
                warning="Empty HTML input provided"
            )

        soup = BeautifulSoup(html, "html.parser")

        # 1. Decompose unwanted HTML tags
        for tag_name in cls.UNWANTED_TAGS:
            for tag in soup.find_all(tag_name):
                tag.decompose()

        # 2. Decompose unwanted CSS elements (ads, footers, comments, recommendations, modal dialogs)
        for selector in cls.UNWANTED_SELECTORS:
            for el in soup.select(selector):
                el.decompose()

        # 3. Locate target article container
        container: Optional[Tag] = None
        used_method = "Fallback Paragraph Collector"

        for selector in cls.ARTICLE_CONTAINER_SELECTORS:
            match = soup.select_one(selector)
            if match:
                container = match
                used_method = f"Selector '{selector}'"
                break

        if not container:
            container = soup.body if soup.body else soup

        # 4. Extract paragraph texts
        paragraphs: List[str] = []
        p_tags = container.find_all("p")

        if p_tags:
            seen_texts = set()
            for p in p_tags:
                text = p.get_text().strip()
                # Normalize internal whitespace
                cleaned_text = re.sub(r'\s+', ' ', text)
                if cleaned_text and cls._is_valid_paragraph(cleaned_text, p_element=p):
                    if cleaned_text not in seen_texts:
                        seen_texts.add(cleaned_text)
                        paragraphs.append(cleaned_text)
        else:
            # Fallback if no <p> tags exist: extract text blocks from container
            raw_text = container.get_text(separator="\n")
            for line in raw_text.splitlines():
                cleaned = line.strip()
                if cleaned and cls._is_valid_paragraph(cleaned):
                    paragraphs.append(cleaned)

        if not paragraphs:
            return ExtractedArticleText(
                success=False,
                extraction_method=used_method,
                warning="No article text paragraphs could be extracted from page HTML"
            )

        full_text = "\n\n".join(paragraphs)
        char_count = len(full_text)

        return ExtractedArticleText(
            text=full_text,
            paragraph_count=len(paragraphs),
            char_count=char_count,
            extraction_method=used_method,
            success=True,
            warning=None if char_count >= 100 else "Short article body extracted (<100 chars)"
        )

    @classmethod
    def _is_valid_paragraph(cls, text: str, p_element: Optional[Tag] = None) -> bool:
        """
        Filters out obvious non-article text snippets (e.g. cookie notices, short share text,
        UI dialog boilerplate, link-only related story blocks, and trailing provider disclaimers).
        Preserves substantive prose, quotations, headings, lists, and author bio sentences.
        """
        if not text or len(text) < 5:
            return False

        lower = text.lower().strip()
        if lower in ("read more", "share", "follow us", "advertisement", "copyright", "related articles"):
            return False

        # Link-only paragraph check: if <p> contains only a single <a> link tag pointing to a related story
        if p_element and isinstance(p_element, Tag):
            a_children = p_element.find_all("a", recursive=False)
            if len(a_children) == 1:
                a_text = a_children[0].get_text().strip()
                a_cleaned = re.sub(r'\s+', ' ', a_text)
                if a_cleaned == text:
                    # If anchor tag contains Yahoo context_link or related story link data attributes
                    ylk = (a_children[0].get("data-ylk") or "").lower()
                    if "elm:context_link" in ylk or "sec:content-canvas" in ylk or "article_link" in (a_children[0].get("data-yga") or "").lower():
                        return False
                    # Or if anchor is a trial/subscription CTA
                    if re.search(r'start your (?:unlimited|free) \w+ trial', lower):
                        return False

        # Conservative UI / modal accessibility boilerplate phrase filter
        unwanted_ui_phrases = [
            "this is a modal window",
            "beginning of dialog window",
            "end of dialog window",
            "escape will cancel and close",
            "close modal dialog"
        ]
        if any(phrase in lower for phrase in unwanted_ui_phrases):
            return False

        # Narrowly anchored boilerplate text guardrails
        # 1. Copyright / legal redistribution disclaimers
        if re.search(r'^(?:copyright|©)\s+\d{4}', lower):
            return False
        if "all rights reserved." in lower and ("this material may not be published" in lower or "redistributed" in lower):
            return False

        # 2. App / channel streaming download CTAs
        if re.search(r'download our (?:free )?(?:news|weather|app)', lower) or "stream channel " in lower:
            return False
        if re.search(r'^(?:read|Read) on the \w+ app$', text.strip()) or text.strip() == "READ ON THE FOX BUSINESS APP":
            return False

        # 3. Subscription trial prompts
        if re.search(r'^start your (?:unlimited|free) \w+ trial$', lower):
            return False

        # 4. Syndication source and wire distributor headers
        if re.match(r'^original article source:', lower):
            return False
        if re.match(r'^source:\s+[a-z0-9]', lower) and len(text) < 120:
            return False
        if re.match(r'^provided by \w+ media', lower) or re.match(r'^distributed by \w+', lower):
            return False

        return True
