import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field


class ExtractedMetadata(BaseModel):
    """
    Structured metadata extracted from an article HTML page.
    """
    title: Optional[str] = Field(default=None, description="Article title/headline")
    author: Optional[str] = Field(default=None, description="Article author or byline")
    publication_datetime: Optional[str] = Field(default=None, description="Original publication date/time")
    updated_datetime: Optional[str] = Field(default=None, description="Last updated date/time")
    # TODO / Diagnostic Note: original_publisher currently represents the publisher
    # reported by the page metadata (e.g. Yahoo News) and may differ from the original
    # syndicated content provider (e.g. Reuters, Associated Press, USA TODAY).
    original_publisher: Optional[str] = Field(default=None, description="Original content publisher reported by page metadata")
    canonical_url: Optional[str] = Field(default=None, description="Canonical URL of article")
    language: Optional[str] = Field(default=None, description="Language code")
    field_methods: Dict[str, str] = Field(default_factory=dict, description="Extraction strategy used for each field")
    extraction_summary: str = Field(default="None", description="Summary of extraction strategies applied")


class MetadataExtractor:
    """
    Fallback metadata extractor adhering to extraction order:
    1. JSON-LD (application/ld+json)
    2. OpenGraph & standard <meta> tags
    3. Semantic HTML tags (article, h1, time, etc.)
    4. Source-specific CSS selectors
    """

    @classmethod
    def extract(cls, html: str, fallback_canonical_url: Optional[str] = None) -> ExtractedMetadata:
        """
        Parses HTML and extracts article metadata using ordered fallbacks.

        Args:
            html: Raw or rendered HTML content string.
            fallback_canonical_url: Optional fallback URL if canonical tag is absent.

        Returns:
            ExtractedMetadata: Normalized extracted metadata object.
        """
        if not html or not html.strip():
            return ExtractedMetadata(extraction_summary="Empty HTML")

        soup = BeautifulSoup(html, "html.parser")
        field_methods: Dict[str, str] = {}

        # Initialize targets
        title: Optional[str] = None
        author: Optional[str] = None
        publication_datetime: Optional[str] = None
        updated_datetime: Optional[str] = None
        original_publisher: Optional[str] = None
        canonical_url: Optional[str] = None
        language: Optional[str] = None

        # -------------------------------------------------------------
        # Fallback Level 1: JSON-LD (application/ld+json)
        # -------------------------------------------------------------
        json_ld_data = cls._parse_json_ld(soup)
        if json_ld_data:
            if not title and json_ld_data.get("title"):
                title = json_ld_data["title"]
                field_methods["title"] = "JSON-LD"

            if not author and json_ld_data.get("author"):
                author = json_ld_data["author"]
                field_methods["author"] = "JSON-LD"

            if not publication_datetime and json_ld_data.get("publication_datetime"):
                publication_datetime = json_ld_data["publication_datetime"]
                field_methods["publication_datetime"] = "JSON-LD"

            if not updated_datetime and json_ld_data.get("updated_datetime"):
                updated_datetime = json_ld_data["updated_datetime"]
                field_methods["updated_datetime"] = "JSON-LD"

            if not original_publisher and json_ld_data.get("original_publisher"):
                original_publisher = json_ld_data["original_publisher"]
                field_methods["original_publisher"] = "JSON-LD"

            if not canonical_url and json_ld_data.get("canonical_url"):
                canonical_url = json_ld_data["canonical_url"]
                field_methods["canonical_url"] = "JSON-LD"

            if not language and json_ld_data.get("language"):
                language = json_ld_data["language"]
                field_methods["language"] = "JSON-LD"

        # -------------------------------------------------------------
        # Fallback Level 2: OpenGraph & Standard Meta Tags
        # -------------------------------------------------------------
        meta_data = cls._parse_meta_tags(soup)

        if not title and meta_data.get("title"):
            title = meta_data["title"]
            field_methods["title"] = "OpenGraph/Meta"

        if not author and meta_data.get("author"):
            author = meta_data["author"]
            field_methods["author"] = "OpenGraph/Meta"

        if not publication_datetime and meta_data.get("publication_datetime"):
            publication_datetime = meta_data["publication_datetime"]
            field_methods["publication_datetime"] = "OpenGraph/Meta"

        if not updated_datetime and meta_data.get("updated_datetime"):
            updated_datetime = meta_data["updated_datetime"]
            field_methods["updated_datetime"] = "OpenGraph/Meta"

        if not original_publisher and meta_data.get("original_publisher"):
            original_publisher = meta_data["original_publisher"]
            field_methods["original_publisher"] = "OpenGraph/Meta"

        if not canonical_url and meta_data.get("canonical_url"):
            canonical_url = meta_data["canonical_url"]
            field_methods["canonical_url"] = "OpenGraph/Meta"

        if not language and meta_data.get("language"):
            language = meta_data["language"]
            field_methods["language"] = "OpenGraph/Meta"

        # -------------------------------------------------------------
        # Fallback Level 3: Semantic HTML
        # -------------------------------------------------------------
        semantic_data = cls._parse_semantic_html(soup)

        if not title and semantic_data.get("title"):
            title = semantic_data["title"]
            field_methods["title"] = "Semantic HTML"

        if not author and semantic_data.get("author"):
            author = semantic_data["author"]
            field_methods["author"] = "Semantic HTML"

        if not publication_datetime and semantic_data.get("publication_datetime"):
            publication_datetime = semantic_data["publication_datetime"]
            field_methods["publication_datetime"] = "Semantic HTML"

        if not language and semantic_data.get("language"):
            language = semantic_data["language"]
            field_methods["language"] = "Semantic HTML"

        # -------------------------------------------------------------
        # Fallback Level 4: Yahoo-specific CSS Selectors
        # -------------------------------------------------------------
        yahoo_data = cls._parse_yahoo_specific(soup)

        if not title and yahoo_data.get("title"):
            title = yahoo_data["title"]
            field_methods["title"] = "Yahoo Selector"

        if not author and yahoo_data.get("author"):
            author = yahoo_data["author"]
            field_methods["author"] = "Yahoo Selector"

        if not publication_datetime and yahoo_data.get("publication_datetime"):
            publication_datetime = yahoo_data["publication_datetime"]
            field_methods["publication_datetime"] = "Yahoo Selector"

        if not original_publisher and yahoo_data.get("original_publisher"):
            original_publisher = yahoo_data["original_publisher"]
            field_methods["original_publisher"] = "Yahoo Selector"

        # Final canonical URL fallback if not found in page tags
        if not canonical_url and fallback_canonical_url:
            canonical_url = fallback_canonical_url
            field_methods["canonical_url"] = "Navigation Redirect"

        # Normalize epoch timestamps
        publication_datetime = cls._normalize_datetime(publication_datetime)
        updated_datetime = cls._normalize_datetime(updated_datetime)

        # Normalize original publisher attribution and clean author byline
        author, original_publisher = cls._normalize_publisher(original_publisher, author, canonical_url)

        # Build summary of extraction methods
        unique_methods = sorted(list(set(field_methods.values())))
        summary = " + ".join(unique_methods) if unique_methods else "None"

        return ExtractedMetadata(
            title=title.strip() if title else None,
            author=author.strip() if author else None,
            publication_datetime=publication_datetime,
            updated_datetime=updated_datetime,
            original_publisher=original_publisher.strip() if original_publisher else None,
            canonical_url=canonical_url.strip() if canonical_url else None,
            language=language.strip() if language else None,
            field_methods=field_methods,
            extraction_summary=summary
        )

    @classmethod
    def _normalize_datetime(cls, val: Optional[str]) -> Optional[str]:
        """Normalizes ISO or numeric epoch timestamps into standard ISO 8601 UTC representation."""
        if not val or not str(val).strip():
            return None
        val_str = str(val).strip()
        try:
            ts = float(val_str)
            if 100000000 <= ts <= 4000000000:
                dt = datetime.fromtimestamp(ts, timezone.utc)
                return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except (ValueError, OverflowError, TypeError):
            pass
        return val_str

    @classmethod
    def _normalize_publisher(
        cls,
        raw_publisher: Optional[str],
        author: Optional[str],
        canonical_url: Optional[str]
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Parses original publisher attribution and cleans author byline.
        Returns tuple of (cleaned_author, original_publisher).
        """
        cleaned_author = author.strip() if author else None
        publisher = raw_publisher.strip() if raw_publisher else None

        # Check byline comma separation: e.g. "Claire Carter, Washington Examiner"
        if cleaned_author and ", " in cleaned_author:
            parts = [p.strip() for p in cleaned_author.split(", ") if p.strip()]
            if len(parts) == 2:
                cleaned_author = parts[0]
                if not publisher or publisher.lower() in ("msn", "www.msn.com", "yahoo", "yahoo news", "unknown"):
                    publisher = parts[1]

        # Domain fallback from canonical URL if publisher is missing or generic MSN
        if (not publisher or publisher.lower() in ("msn", "www.msn.com")) and canonical_url:
            try:
                from src.utils.urls import extract_domain
                domain = extract_domain(canonical_url)
                if domain and domain not in ("msn.com", "www.msn.com", "yahoo.com", "www.yahoo.com"):
                    main_part = domain.replace("www.", "").split(".")[0]
                    if main_part:
                        publisher = main_part.replace("-", " ").title()
            except Exception:
                pass

        return cleaned_author, publisher

    @classmethod
    def _parse_json_ld(cls, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extracts metadata fields from application/ld+json script tags."""
        result: Dict[str, Any] = {}
        scripts = soup.find_all("script", type="application/ld+json")

        for script in scripts:
            if not script.string:
                continue
            try:
                data = json.loads(script.string)
            except Exception:
                continue

            # Standardize object list
            items = []
            if isinstance(data, dict):
                if "@graph" in data and isinstance(data["@graph"], list):
                    items = data["@graph"]
                else:
                    items = [data]
            elif isinstance(data, list):
                items = data

            for item in items:
                if not isinstance(item, dict):
                    continue

                item_type = str(item.get("@type", ""))

                # Title
                if not result.get("title"):
                    if item.get("headline"):
                        result["title"] = str(item["headline"])
                    elif item.get("name"):
                        result["title"] = str(item["name"])

                # Author
                if not result.get("author") and item.get("author"):
                    auth = item["author"]
                    if isinstance(auth, dict) and auth.get("name"):
                        result["author"] = str(auth["name"])
                    elif isinstance(auth, str):
                        result["author"] = auth
                    elif isinstance(auth, list) and len(auth) > 0:
                        first_auth = auth[0]
                        if isinstance(first_auth, dict) and first_auth.get("name"):
                            result["author"] = str(first_auth["name"])
                        elif isinstance(first_auth, str):
                            result["author"] = first_auth

                # Dates
                if not result.get("publication_datetime") and item.get("datePublished"):
                    result["publication_datetime"] = str(item["datePublished"])
                if not result.get("updated_datetime") and item.get("dateModified"):
                    result["updated_datetime"] = str(item["dateModified"])

                # Publisher
                if not result.get("original_publisher") and item.get("publisher"):
                    pub = item["publisher"]
                    if isinstance(pub, dict) and pub.get("name"):
                        result["original_publisher"] = str(pub["name"])
                    elif isinstance(pub, str):
                        result["original_publisher"] = pub

                # Canonical URL
                if not result.get("canonical_url"):
                    if item.get("url"):
                        result["canonical_url"] = str(item["url"])
                    elif item.get("mainEntityOfPage"):
                        main_entity = item["mainEntityOfPage"]
                        if isinstance(main_entity, str):
                            result["canonical_url"] = main_entity
                        elif isinstance(main_entity, dict) and main_entity.get("@id"):
                            result["canonical_url"] = str(main_entity["@id"])

                # Language
                if not result.get("language") and item.get("inLanguage"):
                    lang = item["inLanguage"]
                    if isinstance(lang, str):
                        result["language"] = lang
                    elif isinstance(lang, dict) and lang.get("name"):
                        result["language"] = str(lang["name"])

        return result

    @classmethod
    def _parse_meta_tags(cls, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extracts metadata from OpenGraph and standard meta tags."""
        result: Dict[str, Any] = {}

        def get_meta(*names_or_props: str) -> Optional[str]:
            for identifier in names_or_props:
                tag = soup.find("meta", attrs={"property": identifier}) or soup.find("meta", attrs={"name": identifier})
                if tag and tag.get("content"):
                    return str(tag["content"]).strip()
            return None

        # Title
        title = get_meta("og:title", "twitter:title", "title")
        if title:
            result["title"] = title
        elif soup.title and soup.title.string:
            result["title"] = soup.title.string.strip()

        # Author
        author = get_meta("article:author", "author", "twitter:creator", "parsely-author")
        if author:
            result["author"] = author

        # Dates
        pub_date = get_meta("article:published_time", "og:article:published_time", "publication_date", "pubdate", "parsely-pub-date")
        if pub_date:
            result["publication_datetime"] = pub_date

        mod_date = get_meta("article:modified_time", "og:article:modified_time", "lastmod")
        if mod_date:
            result["updated_datetime"] = mod_date

        # Publisher
        publisher = get_meta("og:site_name", "publisher", "twitter:site", "parsely-publisher")
        if publisher:
            result["original_publisher"] = publisher

        # Canonical link tag
        link_canonical = soup.find("link", rel="canonical")
        if link_canonical and link_canonical.get("href"):
            result["canonical_url"] = str(link_canonical["href"]).strip()
        else:
            og_url = get_meta("og:url")
            if og_url:
                result["canonical_url"] = og_url

        # Language tag
        og_locale = get_meta("og:locale")
        if og_locale:
            result["language"] = og_locale
        else:
            html_tag = soup.find("html") or soup.html or soup.find(attrs={"lang": True})
            if html_tag and html_tag.get("lang"):
                result["language"] = str(html_tag["lang"]).strip()

        return result

    @classmethod
    def _parse_semantic_html(cls, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extracts metadata from semantic HTML elements (article, h1, time, etc.)."""
        result: Dict[str, Any] = {}

        # Semantic Title (h1 inside article or header)
        h1 = soup.find("h1")
        if h1 and h1.get_text():
            result["title"] = h1.get_text().strip()

        # Semantic Time
        time_tag = soup.find("time")
        if time_tag:
            if time_tag.get("datetime"):
                result["publication_datetime"] = str(time_tag["datetime"]).strip()
            elif time_tag.get_text():
                result["publication_datetime"] = time_tag.get_text().strip()

        # Semantic Author (address or author class/itemprop)
        author_el = soup.find(attrs={"itemprop": "author"}) or soup.find("address")
        if author_el and author_el.get_text():
            result["author"] = author_el.get_text().strip()

        return result

    @classmethod
    def _parse_yahoo_specific(cls, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extracts metadata using Yahoo-specific DOM CSS selectors."""
        result: Dict[str, Any] = {}

        # Yahoo Headline selector
        title_el = soup.select_one(".caas-title, header h1, div[data-test-locator='article-title']")
        if title_el and title_el.get_text():
            result["title"] = title_el.get_text().strip()

        # Yahoo Author selector
        author_el = soup.select_one(".caas-author-name, .caas-attr-item-byline, div.caas-author-byline, span.caas-author-byline")
        if author_el and author_el.get_text():
            result["author"] = author_el.get_text().strip()

        # Yahoo Provider / Original Publisher selector
        provider_el = soup.select_one(".caas-attr-provider, .caas-publisher-logo img")
        if provider_el:
            if provider_el.name == "img" and provider_el.get("alt"):
                result["original_publisher"] = str(provider_el["alt"]).strip()
            elif provider_el.get_text():
                result["original_publisher"] = provider_el.get_text().strip()

        # Yahoo Date / Time selector
        time_el = soup.select_one(".caas-attr-time-style, time.caas-attr-meta-time")
        if time_el:
            if time_el.get("datetime"):
                result["publication_datetime"] = str(time_el["datetime"]).strip()
            elif time_el.get_text():
                result["publication_datetime"] = time_el.get_text().strip()

        return result
