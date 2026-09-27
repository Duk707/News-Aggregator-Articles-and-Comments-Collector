import math
import os
import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import List, Optional, Set, Tuple, Dict, Any

import requests

from src.collectors.router import SourceRouter
from src.discovery.models import CandidateArticle
from src.utils.urls import normalize_url


KNOWN_TRACKING_PARAMS: Set[str] = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "ncid", "gclid", "fbclid", "ref_", "guccounter", "guce_referrer",
    "guce_referrer_sig", "src", "soc_src", "soc_trk"
}


def clean_tracking_params(url_str: str) -> str:
    """
    Cleans known analytics and tracking parameters from a URL while preserving
    functional query parameters required for article resolution.
    Unwraps search click redirect wrappers (e.g. Bing News RSS apiclick.aspx?url=...).
    """
    if not url_str:
        return ""

    parsed = urllib.parse.urlparse(url_str)
    # Unwrap Bing News apiclick.aspx wrapper links safely
    if "apiclick.aspx" in parsed.path or "bing.com" in parsed.netloc:
        query_params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        if "url" in query_params and query_params["url"]:
            unwrapped = urllib.parse.unquote(query_params["url"][0])
            parsed = urllib.parse.urlparse(unwrapped)

    if not parsed.query:
        return urllib.parse.urlunparse(parsed)

    query_params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    cleaned_params = {}
    for key, values in query_params.items():
        if key.lower() not in KNOWN_TRACKING_PARAMS:
            cleaned_params[key] = values

    cleaned_query = urllib.parse.urlencode(cleaned_params, doseq=True)
    cleaned_url = urllib.parse.urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        cleaned_query,
        parsed.fragment
    ))
    return cleaned_url


def parse_rfc822_date(date_str: Optional[str]) -> Optional[datetime]:
    """
    Parses an RFC-822 or ISO date string (e.g. from RSS <pubDate>) into a UTC datetime.
    Returns None if date_str is missing or unparseable.
    """
    if not date_str or not date_str.strip():
        return None

    try:
        dt = parsedate_to_datetime(date_str.strip())
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt
    except Exception:
        pass

    # Fallback ISO format parsing
    try:
        dt = datetime.fromisoformat(date_str.strip().replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt
    except Exception:
        return None


def parse_date_filter_boundary(date_str: Optional[str], end_of_day: bool = False) -> Optional[datetime]:
    """
    Parses a YYYY-MM-DD user input string into a UTC datetime boundary.
    """
    if not date_str or not date_str.strip():
        return None
    try:
        parts = date_str.strip().split("-")
        if len(parts) == 3:
            year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
            if end_of_day:
                return datetime(year, month, day, 23, 59, 59, tzinfo=timezone.utc)
            else:
                return datetime(year, month, day, 0, 0, 0, tzinfo=timezone.utc)
    except Exception:
        pass
    return None


class CandidateDiscoverer:
    """
    Decoupled Candidate Discovery Engine.
    Executes public news RSS discovery queries for Yahoo and MSN articles,
    applying URL link validation via SourceRouter, tracking parameter cleaning,
    deduplication, keyword filtering, and conservative date filtering.
    """

    BING_NEWS_RSS_URL = "https://www.bing.com/news/search"

    def __init__(self, router: Optional[SourceRouter] = None):
        self.router = router or SourceRouter()

    def discover(
        self,
        query: str,
        include_yahoo: bool = True,
        include_msn: bool = True,
        max_candidates: int = 20,
        include_keywords: Optional[List[str]] = None,
        include_keyword_mode: str = "ANY",
        exclude_keywords: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        timeout_sec: int = 15
    ) -> List[CandidateArticle]:
        """
        Executes news discovery over public RSS feed using source-specific sub-queries,
        adaptive bounded pagination depth, and balanced round-robin merging.

        Args:
            query: Optional main topic or discovery search query string.
            include_yahoo: If True, include Yahoo News candidates.
            include_msn: If True, include MSN candidates.
            max_candidates: Max candidate records to return (upper bound).
            include_keywords: Optional list of required keywords in candidate title/snippet.
            include_keyword_mode: Match mode for include keywords: 'ANY' (default) or 'ALL'.
            exclude_keywords: Optional list of forbidden keywords in candidate title/snippet.
            start_date: Optional start date filter string ('YYYY-MM-DD').
            end_date: Optional end date filter string ('YYYY-MM-DD').
            timeout_sec: HTTP request timeout in seconds.

        Returns:
            List[CandidateArticle]: Filtered, validated, deduplicated, and source-balanced candidate articles.
        """
        clean_query = query.strip() if query else ""
        clean_includes = [k.strip() for k in (include_keywords or []) if k.strip()]
        mode_upper = (include_keyword_mode or "ANY").strip().upper()

        if not clean_query and not clean_includes:
            return []

        if not include_yahoo and not include_msn:
            return []

        # Formulate source terms
        sources = []
        if include_yahoo:
            sources.append("site:yahoo.com")
        if include_msn:
            sources.append("site:msn.com")

        # Formulate base discovery terms
        if clean_query:
            base_query_terms = [clean_query]
        else:
            if mode_upper == "ALL":
                base_query_terms = [" ".join(clean_includes)]
            else:
                base_query_terms = clean_includes

        display_query = clean_query if clean_query else ", ".join(clean_includes)

        # Adaptive page calculation: target pages per source scales with max_candidates
        target_pages_per_source = min(5, max(2, math.ceil(max_candidates / 8)))
        offsets = [1 + 10 * i for i in range(target_pages_per_source)]

        total_requests = 0
        MAX_TOTAL_REQUESTS = max(6, target_pages_per_source * len(sources) * len(base_query_terms))
        seen_urls: Set[str] = set()

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        source_pools: Dict[str, List[CandidateArticle]] = {site: [] for site in sources}

        # Populate per-source candidate pools independently
        for site_term in sources:
            pool = source_pools[site_term]
            for offset in offsets:
                if len(pool) >= max_candidates or total_requests >= MAX_TOTAL_REQUESTS:
                    break
                new_candidates_on_offset = 0
                for bt in base_query_terms:
                    if len(pool) >= max_candidates or total_requests >= MAX_TOTAL_REQUESTS:
                        break
                    full_query = f"{bt} {site_term}"
                    params = {
                        "q": full_query,
                        "format": "rss",
                        "first": offset
                    }
                    total_requests += 1

                    try:
                        resp = requests.get(self.BING_NEWS_RSS_URL, params=params, headers=headers, timeout=timeout_sec)
                        if resp.status_code == 200 and resp.text:
                            batch = self.parse_xml_candidates(
                                xml_content=resp.text,
                                query=display_query,
                                include_yahoo=include_yahoo,
                                include_msn=include_msn,
                                max_candidates=max_candidates - len(pool),
                                include_keywords=include_keywords,
                                include_keyword_mode=include_keyword_mode,
                                exclude_keywords=exclude_keywords,
                                start_date=start_date,
                                end_date=end_date,
                                seen_urls=seen_urls
                            )
                            for c in batch:
                                pool.append(c)
                                new_candidates_on_offset += 1
                                if len(pool) >= max_candidates:
                                    break
                    except Exception:
                        continue

                # Early stop for this source if no new unique candidates were returned on this offset page
                if new_candidates_on_offset == 0:
                    break

        # Balanced round-robin merging across source pools
        merged_candidates: List[CandidateArticle] = []
        while len(merged_candidates) < max_candidates and any(source_pools.values()):
            for site_term in sources:
                if source_pools[site_term]:
                    cand = source_pools[site_term].pop(0)
                    merged_candidates.append(cand)
                    if len(merged_candidates) >= max_candidates:
                        break

        return merged_candidates

    def parse_xml_candidates(
        self,
        xml_content: str,
        query: str,
        include_yahoo: bool = True,
        include_msn: bool = True,
        max_candidates: int = 20,
        include_keywords: Optional[List[str]] = None,
        include_keyword_mode: str = "ANY",
        exclude_keywords: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        seen_urls: Optional[Set[str]] = None
    ) -> List[CandidateArticle]:
        """
        Parses candidate articles from an RSS XML string fixture or live HTTP response,
        enforcing SourceRouter validation, tracking param cleaning, keyword filtering,
        and conservative date range filtering.
        """
        if not xml_content or not xml_content.strip():
            return []

        try:
            root = ET.fromstring(xml_content.strip())
        except Exception:
            return []

        # Parse date filter boundaries
        start_dt = parse_date_filter_boundary(start_date, end_of_day=False)
        end_dt = parse_date_filter_boundary(end_date, end_of_day=True)
        has_date_filter = (start_dt is not None) or (end_dt is not None)

        # Normalize keyword filters
        clean_includes = [k.strip().lower() for k in (include_keywords or []) if k.strip()]
        clean_excludes = [k.strip().lower() for k in (exclude_keywords or []) if k.strip()]
        mode_upper = (include_keyword_mode or "ANY").strip().upper()

        candidates: List[CandidateArticle] = []
        if seen_urls is None:
            seen_urls = set()
        timestamp = datetime.now(timezone.utc).isoformat()

        items = root.findall(".//item")
        for item in items:
            title_elem = item.find("title")
            link_elem = item.find("link")
            desc_elem = item.find("description")
            pub_date_elem = item.find("pubDate")

            raw_title = title_elem.text.strip() if (title_elem is not None and title_elem.text) else "Untitled Candidate"
            raw_link = link_elem.text.strip() if (link_elem is not None and link_elem.text) else ""
            raw_snippet = desc_elem.text.strip() if (desc_elem is not None and desc_elem.text) else None
            raw_pub_date = pub_date_elem.text.strip() if (pub_date_elem is not None and pub_date_elem.text) else None

            if not raw_link:
                continue

            # 1. Clean tracking parameters safely
            cleaned_link = clean_tracking_params(raw_link)
            normalized_link = normalize_url(cleaned_link)

            if not normalized_link or normalized_link in seen_urls:
                continue

            # 2. Link Parsing & SourceRouter Validation
            # Admit candidate ONLY if SourceRouter validates it as a supported Yahoo/MSN URL
            routing_result, adapter = self.router.route(normalized_link)
            if not routing_result.is_valid or not routing_result.supported or not adapter:
                continue

            # 3. Date Parsing & Conservative Date Range Filtering
            dt_item = parse_rfc822_date(raw_pub_date)
            iso_pub_date = dt_item.isoformat() if dt_item else None

            if has_date_filter:
                # Rule 1 Requirement: When user explicitly supplies start/end date,
                # do NOT silently treat unknown/unparseable date as satisfying the filter.
                # Exclude candidate conservatively if date is missing or outside range.
                if dt_item is None:
                    continue
                if start_dt and dt_item < start_dt:
                    continue
                if end_dt and dt_item > end_dt:
                    continue

            # 4. Include & Exclude Keyword Filtering
            searchable_text = f"{raw_title} {raw_snippet or ''}".lower()

            if clean_includes:
                if mode_upper == "ALL":
                    # Candidate text must contain ALL include keywords
                    if not all(inc in searchable_text for inc in clean_includes):
                        continue
                else:
                    # Candidate text must contain AT LEAST ONE include keyword (default ANY)
                    if not any(inc in searchable_text for inc in clean_includes):
                        continue

            if clean_excludes:
                # Candidate text must NOT contain any exclude keyword
                if any(exc in searchable_text for exc in clean_excludes):
                    continue

            seen_urls.add(normalized_link)
            parsed_domain = urllib.parse.urlparse(normalized_link).netloc

            candidate = CandidateArticle(
                title=raw_title,
                url=normalized_link,
                platform=routing_result.platform_name or "Unknown",
                source_domain=parsed_domain,
                snippet=raw_snippet,
                publication_date=iso_pub_date,
                discovery_query=query,
                discovery_provider="Bing News RSS",
                discovery_method="public_rss_feed",
                discovered_at=timestamp
            )
            candidates.append(candidate)

            if len(candidates) >= max_candidates:
                break

        return candidates
