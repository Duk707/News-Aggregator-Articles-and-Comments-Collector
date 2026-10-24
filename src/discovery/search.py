import math
import os
import re
import threading
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import List, Optional, Set, Tuple, Dict, Any, Callable

import requests

from src.collectors.router import SourceRouter
from src.discovery.models import CandidateArticle, DiscoveryRunDiagnostics, SourceDiscoveryDiagnostics
from src.utils.urls import normalize_url


def _canonicalize_key(url_str: str) -> str:
    """
    Lazily imports and applies canonicalize_url_key to avoid circular imports.
    Returns canonical key or empty string if canonicalization fails.
    Never silently falls back to raw URL strings.
    """
    if not url_str or not isinstance(url_str, str) or not url_str.strip():
        return ""
    try:
        from src.integrations.supabase.url_checker import canonicalize_url_key
        key = canonicalize_url_key(url_str)
        return key or ""
    except Exception:
        return ""


def is_valid_rss_xml(text: str) -> Tuple[bool, Optional[ET.Element], str]:
    """
    Validates that response text is well-formed XML representing an RSS feed or Atom channel,
    and is not an HTML error/landing page or malformed document.
    Returns (is_valid, root_element, reason).
    """
    if not text or not text.strip():
        return False, None, "empty_response"
    trimmed = text.strip()
    if trimmed.lower().startswith("<!doctype html") or trimmed.lower().startswith("<html"):
        return False, None, "html_response_not_rss"
    try:
        root = ET.fromstring(trimmed)
    except Exception as exc:
        return False, None, f"xml_parse_error: {str(exc)}"

    tag_lower = root.tag.lower()
    if "html" in tag_lower:
        return False, None, "html_root_not_rss"
    if tag_lower != "rss":
        return False, None, "invalid_root_tag"
    if root.find("channel") is None:
        return False, None, "missing_rss_channel"

    return True, root, "valid"



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
        self.last_diagnostics: Optional[DiscoveryRunDiagnostics] = None

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
        timeout_sec: int = 15,
        diagnostics: Optional[DiscoveryRunDiagnostics] = None,
        target_yahoo: Optional[int] = None,
        target_msn: Optional[int] = None,
        max_pages_per_source: int = 10,
        max_total_requests: Optional[int] = None,
        max_consecutive_zero_yield: int = 2,
        rate_limit_delay_sec: float = 0.0,
        supabase_snapshot: Optional[Any] = None,
        http_fetcher: Optional[Callable[..., Any]] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> List[CandidateArticle]:
        """
        Executes news discovery over public RSS feed using source-specific sub-queries,
        adaptive bounded pagination depth, and balanced round-robin merging.

        Supports legacy bounded discovery (using max_candidates) and targeted discovery
        (using target_yahoo, target_msn, and optional SupabaseUrlChecker snapshot).
        """
        run_diag = diagnostics if diagnostics is not None else DiscoveryRunDiagnostics()
        self.last_diagnostics = run_diag

        if cancel_event is not None and cancel_event.is_set():
            run_diag.overall_termination = "cancelled"
            return []

        is_targeted_mode = (target_yahoo is not None or target_msn is not None)

        if is_targeted_mode and supabase_snapshot is not None:
            raw_status = getattr(supabase_snapshot, "status", "UNKNOWN")
            status_val = raw_status.value if hasattr(raw_status, "value") else str(raw_status)
            run_diag.db_verification_status = status_val
            run_diag.yahoo.db_verification_status = status_val
            run_diag.msn.db_verification_status = status_val

            is_verified = getattr(supabase_snapshot, "is_verified_accessible", False)
            if not is_verified:
                run_diag.overall_termination = "db_verification_failed"
                return []
        elif is_targeted_mode:
            run_diag.db_verification_status = "disabled"
            run_diag.yahoo.db_verification_status = "disabled"
            run_diag.msn.db_verification_status = "disabled"

        clean_query = query.strip() if query else ""
        clean_includes = [k.strip() for k in (include_keywords or []) if k.strip()]
        mode_upper = (include_keyword_mode or "ANY").strip().upper()

        if not clean_query and not clean_includes:
            run_diag.overall_termination = "empty_query"
            return []

        if not include_yahoo and not include_msn:
            run_diag.overall_termination = "no_sources_selected"
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

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        total_requests = 0
        last_request_time: Optional[float] = None
        abort_all = False

        if not is_targeted_mode:
            # ================= LEGACY MODE =================
            target_pages_per_source = min(5, max(2, math.ceil(max_candidates / 8)))
            offsets = [1 + 10 * i for i in range(target_pages_per_source)]
            MAX_TOTAL_REQUESTS = max_total_requests if max_total_requests is not None else max(6, target_pages_per_source * len(sources) * len(base_query_terms))
            seen_urls: Set[str] = set()
            source_pools: Dict[str, List[CandidateArticle]] = {site: [] for site in sources}

            for site_term in sources:
                pool = source_pools[site_term]
                src_diag = run_diag.yahoo if "yahoo" in site_term else run_diag.msn
                src_terminated_reason = "completed_all_pages"

                if cancel_event is not None and cancel_event.is_set():
                    src_diag.termination_reason = "cancelled"
                    break

                for offset in offsets:
                    if cancel_event is not None and cancel_event.is_set():
                        src_terminated_reason = "cancelled"
                        break
                    if len(pool) >= max_candidates:
                        src_terminated_reason = "max_candidates_reached"
                        break
                    if total_requests >= MAX_TOTAL_REQUESTS:
                        src_terminated_reason = "max_total_requests_budget"
                        break

                    src_diag.pages_attempted += 1
                    new_candidates_on_offset = 0
                    offset_had_network_error = False
                    offset_had_xml_error = False
                    offset_successful_fetch = False

                    for bt in base_query_terms:
                        if cancel_event is not None and cancel_event.is_set():
                            src_terminated_reason = "cancelled"
                            break
                        if len(pool) >= max_candidates:
                            src_terminated_reason = "max_candidates_reached"
                            break
                        if total_requests >= MAX_TOTAL_REQUESTS:
                            src_terminated_reason = "max_total_requests_budget"
                            break

                        full_query = f"{bt} {site_term}"
                        params = {
                            "q": full_query,
                            "format": "rss",
                            "first": offset
                        }

                        if rate_limit_delay_sec > 0.0 and last_request_time is not None:
                            elapsed = time.time() - last_request_time
                            if elapsed < rate_limit_delay_sec:
                                rem_delay = rate_limit_delay_sec - elapsed
                                if cancel_event is not None:
                                    if cancel_event.wait(timeout=rem_delay):
                                        src_terminated_reason = "cancelled"
                                        break
                                else:
                                    time.sleep(rem_delay)

                        if cancel_event is not None and cancel_event.is_set():
                            src_terminated_reason = "cancelled"
                            break

                        total_requests += 1
                        src_diag.requests_made += 1
                        last_request_time = time.time()

                        try:
                            if http_fetcher is not None:
                                resp = http_fetcher(self.BING_NEWS_RSS_URL, params=params, headers=headers, timeout=timeout_sec)
                            else:
                                resp = requests.get(self.BING_NEWS_RSS_URL, params=params, headers=headers, timeout=timeout_sec)

                            if resp.status_code == 200 and resp.text:
                                is_valid, root_elem, val_err = is_valid_rss_xml(resp.text)
                                if not is_valid:
                                    src_diag.xml_parse_errors += 1
                                    offset_had_xml_error = True
                                    continue
                                offset_successful_fetch = True

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
                                    seen_urls=seen_urls,
                                    source_diagnostics=src_diag,
                                    use_canonical_keys=False
                                )
                                for c in batch:
                                    pool.append(c)
                                    new_candidates_on_offset += 1
                                    if len(pool) >= max_candidates:
                                        src_terminated_reason = "max_candidates_reached"
                                        break
                            else:
                                src_diag.network_errors += 1
                                offset_had_network_error = True
                        except Exception:
                            src_diag.network_errors += 1
                            offset_had_network_error = True
                            continue

                    src_diag.unique_candidates_pooled = len(pool)

                    if cancel_event is not None and cancel_event.is_set():
                        src_terminated_reason = "cancelled"
                        break

                    if new_candidates_on_offset == 0:
                        if offset_had_network_error and not offset_successful_fetch:
                            src_terminated_reason = "network_error"
                        elif offset_had_xml_error and not offset_successful_fetch:
                            src_terminated_reason = "xml_parse_error"
                        else:
                            src_terminated_reason = "zero_yield_page"
                        break

                src_diag.termination_reason = src_terminated_reason

            merged_candidates: List[CandidateArticle] = []
            while len(merged_candidates) < max_candidates and any(source_pools.values()):
                for site_term in sources:
                    if source_pools[site_term]:
                        cand = source_pools[site_term].pop(0)
                        merged_candidates.append(cand)
                        src_diag = run_diag.yahoo if "yahoo" in site_term else run_diag.msn
                        src_diag.candidates_returned += 1
                        actual_plat = cand.platform or "Unknown"
                        src_diag.returned_platform_breakdown[actual_plat] = (
                            src_diag.returned_platform_breakdown.get(actual_plat, 0) + 1
                        )
                        if len(merged_candidates) >= max_candidates:
                            break

            run_diag.total_candidates_returned = len(merged_candidates)

            if cancel_event is not None and cancel_event.is_set():
                run_diag.overall_termination = "cancelled"
            else:
                total_net_errs = run_diag.yahoo.network_errors + run_diag.msn.network_errors
                total_xml_errs = run_diag.yahoo.xml_parse_errors + run_diag.msn.xml_parse_errors
                if total_net_errs > 0 or total_xml_errs > 0:
                    run_diag.overall_termination = "completed_with_errors"
                else:
                    run_diag.overall_termination = "completed"

            return merged_candidates

        # ================= TARGETED MODE =================
        HARD_PAGE_LIMIT = 15
        HARD_REQUEST_LIMIT = 40

        try:
            req_pages = int(max_pages_per_source) if max_pages_per_source is not None else 10
        except (ValueError, TypeError):
            req_pages = 10
        bounded_pages_per_source = max(1, min(HARD_PAGE_LIMIT, req_pages))

        if max_total_requests is not None:
            try:
                req_budget = int(max_total_requests)
            except (ValueError, TypeError):
                req_budget = HARD_REQUEST_LIMIT
            MAX_TOTAL_REQUESTS = max(1, min(HARD_REQUEST_LIMIT, req_budget))
        else:
            calc_budget = bounded_pages_per_source * len(sources) * len(base_query_terms)
            MAX_TOTAL_REQUESTS = min(HARD_REQUEST_LIMIT, max(10, calc_budget))

        # Enforce minimum 2.0-second delay for live targeted requests across sources
        effective_rate_limit = max(2.0, rate_limit_delay_sec) if http_fetcher is None else rate_limit_delay_sec

        target_y = target_yahoo if (include_yahoo and target_yahoo is not None) else 0
        target_m = target_msn if (include_msn and target_msn is not None) else 0

        if include_yahoo:
            run_diag.yahoo.target_confirmed_new = target_y
        if include_msn:
            run_diag.msn.target_confirmed_new = target_m

        offsets = [1 + 10 * i for i in range(bounded_pages_per_source)]
        seen_keys: Set[str] = set()

        yahoo_pool: List[CandidateArticle] = []
        msn_pool: List[CandidateArticle] = []

        for site_term in sources:
            is_yahoo_query = ("yahoo" in site_term)
            src_diag = run_diag.yahoo if is_yahoo_query else run_diag.msn
            src_target = target_y if is_yahoo_query else target_m
            own_pool = yahoo_pool if is_yahoo_query else msn_pool

            if cancel_event is not None and cancel_event.is_set():
                src_diag.termination_reason = "cancelled"
                run_diag.overall_termination = "cancelled"
                break

            if abort_all:
                src_diag.termination_reason = "http_blocked"
                continue

            if len(own_pool) >= src_target:
                src_diag.termination_reason = "target_reached"
                continue

            src_terminated_reason = "completed_all_pages"
            consecutive_zero_yield = 0

            for offset in offsets:
                if cancel_event is not None and cancel_event.is_set():
                    src_terminated_reason = "cancelled"
                    run_diag.overall_termination = "cancelled"
                    break
                if len(own_pool) >= src_target:
                    src_terminated_reason = "target_reached"
                    break
                if total_requests >= MAX_TOTAL_REQUESTS:
                    src_terminated_reason = "max_total_requests_budget"
                    break

                src_diag.pages_attempted += 1
                new_candidates_on_offset = 0
                offset_had_network_error = False
                offset_had_xml_error = False
                offset_successful_fetch = False

                for bt in base_query_terms:
                    if cancel_event is not None and cancel_event.is_set():
                        src_terminated_reason = "cancelled"
                        run_diag.overall_termination = "cancelled"
                        break
                    if len(own_pool) >= src_target:
                        src_terminated_reason = "target_reached"
                        break
                    if total_requests >= MAX_TOTAL_REQUESTS:
                        src_terminated_reason = "max_total_requests_budget"
                        break

                    full_query = f"{bt} {site_term}"
                    params = {
                        "q": full_query,
                        "format": "rss",
                        "first": offset
                    }
                    total_requests += 1
                    src_diag.requests_made += 1

                    if effective_rate_limit > 0.0 and last_request_time is not None:
                        elapsed = time.time() - last_request_time
                        if elapsed < effective_rate_limit:
                            rem_delay = effective_rate_limit - elapsed
                            if cancel_event is not None:
                                if cancel_event.wait(timeout=rem_delay):
                                    src_terminated_reason = "cancelled"
                                    run_diag.overall_termination = "cancelled"
                                    break
                            else:
                                time.sleep(rem_delay)
                    last_request_time = time.time()

                    if cancel_event is not None and cancel_event.is_set():
                        src_terminated_reason = "cancelled"
                        run_diag.overall_termination = "cancelled"
                        break

                    try:
                        if http_fetcher is not None:
                            resp = http_fetcher(self.BING_NEWS_RSS_URL, params=params, headers=headers, timeout=timeout_sec)
                        else:
                            resp = requests.get(self.BING_NEWS_RSS_URL, params=params, headers=headers, timeout=timeout_sec)

                        if resp.status_code in (403, 429):
                            src_diag.network_errors += 1
                            offset_had_network_error = True
                            src_terminated_reason = "http_blocked"
                            run_diag.overall_termination = "http_blocked"
                            abort_all = True
                            break
                        elif resp.status_code == 200 and resp.text:
                            is_valid, root_elem, val_err = is_valid_rss_xml(resp.text)
                            if not is_valid:
                                src_diag.xml_parse_errors += 1
                                offset_had_xml_error = True
                                continue
                            offset_successful_fetch = True

                            rem_y = max(0, target_y - len(yahoo_pool)) if include_yahoo else 0
                            rem_m = max(0, target_m - len(msn_pool)) if include_msn else 0
                            current_quotas = {"Yahoo News": rem_y, "MSN": rem_m}

                            batch = self.parse_xml_candidates(
                                xml_content=resp.text,
                                query=display_query,
                                include_yahoo=include_yahoo,
                                include_msn=include_msn,
                                max_candidates=rem_y + rem_m,
                                include_keywords=include_keywords,
                                include_keyword_mode=include_keyword_mode,
                                exclude_keywords=exclude_keywords,
                                start_date=start_date,
                                end_date=end_date,
                                seen_urls=seen_keys,
                                source_diagnostics=src_diag,
                                supabase_snapshot=supabase_snapshot,
                                use_canonical_keys=True,
                                platform_quotas=current_quotas
                            )

                            for c in batch:
                                if c.platform == "Yahoo News":
                                    if include_yahoo and len(yahoo_pool) < target_y:
                                        yahoo_pool.append(c)
                                        new_candidates_on_offset += 1
                                elif c.platform == "MSN":
                                    if include_msn and len(msn_pool) < target_m:
                                        msn_pool.append(c)
                                        new_candidates_on_offset += 1

                            if len(own_pool) >= src_target:
                                src_terminated_reason = "target_reached"
                                break
                        else:
                            src_diag.network_errors += 1
                            offset_had_network_error = True
                    except Exception:
                        src_diag.network_errors += 1
                        offset_had_network_error = True
                        continue

                if cancel_event is not None and cancel_event.is_set():
                    src_terminated_reason = "cancelled"
                    run_diag.overall_termination = "cancelled"
                    break

                if abort_all:
                    break

                if len(own_pool) >= src_target:
                    src_terminated_reason = "target_reached"
                    break

                if new_candidates_on_offset > 0:
                    consecutive_zero_yield = 0
                    src_diag.consecutive_zero_yield_pages = 0
                else:
                    if offset_had_network_error and not offset_successful_fetch:
                        pass
                    elif offset_had_xml_error and not offset_successful_fetch:
                        pass
                    else:
                        consecutive_zero_yield += 1
                        src_diag.consecutive_zero_yield_pages = consecutive_zero_yield
                        if consecutive_zero_yield >= max_consecutive_zero_yield:
                            src_terminated_reason = "consecutive_zero_yield"
                            break

            src_diag.termination_reason = src_terminated_reason

        # Post-process pools and diagnostics
        has_verified_snapshot = (supabase_snapshot is not None and getattr(supabase_snapshot, "is_verified_accessible", False))

        if include_yahoo:
            conf_y = len([c for c in yahoo_pool if c.db_status == "db_verified_new"])
            unver_y = len([c for c in yahoo_pool if c.db_status == "unverified"])
            run_diag.yahoo.unique_candidates_pooled = len(yahoo_pool)
            run_diag.yahoo.confirmed_new_candidates = conf_y
            run_diag.yahoo.unverified_candidates = unver_y
            run_diag.yahoo.candidates_returned = len(yahoo_pool)
            if has_verified_snapshot:
                run_diag.yahoo.shortfall = max(0, target_y - conf_y)
            else:
                run_diag.yahoo.shortfall = target_y
            if len(yahoo_pool) > 0:
                run_diag.yahoo.returned_platform_breakdown = {"Yahoo News": len(yahoo_pool)}

        if include_msn:
            conf_m = len([c for c in msn_pool if c.db_status == "db_verified_new"])
            unver_m = len([c for c in msn_pool if c.db_status == "unverified"])
            run_diag.msn.unique_candidates_pooled = len(msn_pool)
            run_diag.msn.confirmed_new_candidates = conf_m
            run_diag.msn.unverified_candidates = unver_m
            run_diag.msn.candidates_returned = len(msn_pool)
            if has_verified_snapshot:
                run_diag.msn.shortfall = max(0, target_m - conf_m)
            else:
                run_diag.msn.shortfall = target_m
            if len(msn_pool) > 0:
                run_diag.msn.returned_platform_breakdown = {"MSN": len(msn_pool)}

        merged_candidates = []
        y_idx, m_idx = 0, 0
        while y_idx < len(yahoo_pool) or m_idx < len(msn_pool):
            if y_idx < len(yahoo_pool):
                merged_candidates.append(yahoo_pool[y_idx])
                y_idx += 1
            if m_idx < len(msn_pool):
                merged_candidates.append(msn_pool[m_idx])
                m_idx += 1

        run_diag.total_candidates_returned = len(merged_candidates)

        if cancel_event is not None and cancel_event.is_set():
            run_diag.overall_termination = "cancelled"
        elif not abort_all:
            total_net_errs = run_diag.yahoo.network_errors + run_diag.msn.network_errors
            total_xml_errs = run_diag.yahoo.xml_parse_errors + run_diag.msn.xml_parse_errors
            if total_net_errs > 0 or total_xml_errs > 0:
                run_diag.overall_termination = "completed_with_errors"
            elif has_verified_snapshot:
                # With verified snapshot:
                is_shortfall = (include_yahoo and run_diag.yahoo.shortfall > 0) or (include_msn and run_diag.msn.shortfall > 0)
                total_conf = run_diag.yahoo.confirmed_new_candidates + run_diag.msn.confirmed_new_candidates
                if is_shortfall:
                    if total_conf > 0:
                        run_diag.overall_termination = "partial_success"
                    else:
                        run_diag.overall_termination = "target_not_met"
                else:
                    run_diag.overall_termination = "completed"
            else:
                # Unchecked mode (no snapshot provided):
                if len(merged_candidates) > 0:
                    run_diag.overall_termination = "completed_unverified"
                else:
                    run_diag.overall_termination = "target_not_met"

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
        seen_urls: Optional[Set[str]] = None,
        source_diagnostics: Optional[SourceDiscoveryDiagnostics] = None,
        supabase_snapshot: Optional[Any] = None,
        use_canonical_keys: bool = False,
        platform_quotas: Optional[Dict[str, int]] = None,
    ) -> List[CandidateArticle]:
        """
        Parses candidate articles from an RSS XML string fixture or live HTTP response,
        enforcing SourceRouter validation, tracking param cleaning, keyword filtering,
        conservative date range filtering, optional Supabase snapshot duplicate exclusion,
        and platform quota limits.
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
        if source_diagnostics:
            source_diagnostics.raw_items_in_responses += len(items)

        for item in items:
            if source_diagnostics:
                source_diagnostics.items_processed += 1

            title_elem = item.find("title")
            link_elem = item.find("link")
            desc_elem = item.find("description")
            pub_date_elem = item.find("pubDate")

            raw_title = title_elem.text.strip() if (title_elem is not None and title_elem.text) else "Untitled Candidate"
            raw_link = link_elem.text.strip() if (link_elem is not None and link_elem.text) else ""
            raw_snippet = desc_elem.text.strip() if (desc_elem is not None and desc_elem.text) else None
            raw_pub_date = pub_date_elem.text.strip() if (pub_date_elem is not None and pub_date_elem.text) else None

            if not raw_link:
                if source_diagnostics:
                    source_diagnostics.rejected_unsupported_urls += 1
                continue

            # 1. Clean tracking parameters safely
            cleaned_link = clean_tracking_params(raw_link)
            normalized_link = normalize_url(cleaned_link)

            if not normalized_link:
                if source_diagnostics:
                    source_diagnostics.rejected_unsupported_urls += 1
                continue

            # Within-run duplicate detection
            c_key = ""
            if use_canonical_keys:
                c_key = _canonicalize_key(normalized_link)
                if not c_key:
                    if source_diagnostics:
                        source_diagnostics.rejected_unsupported_urls += 1
                    continue
                if c_key in seen_urls:
                    if source_diagnostics:
                        source_diagnostics.repeated_urls_in_search += 1
                    continue
            else:
                if normalized_link in seen_urls:
                    if source_diagnostics:
                        source_diagnostics.repeated_urls_in_search += 1
                    continue

            # 2. Link Parsing & SourceRouter Validation
            # Admit candidate ONLY if SourceRouter validates it as a supported Yahoo/MSN URL
            routing_result, adapter = self.router.route(normalized_link)
            if not routing_result.is_valid or not routing_result.supported or not adapter:
                if source_diagnostics:
                    source_diagnostics.rejected_unsupported_urls += 1
                continue

            actual_platform = routing_result.platform_name or "Unknown"

            # 3. Date Parsing & Conservative Date Range Filtering
            dt_item = parse_rfc822_date(raw_pub_date)
            iso_pub_date = dt_item.isoformat() if dt_item else None

            if has_date_filter:
                if dt_item is None or (start_dt and dt_item < start_dt) or (end_dt and dt_item > end_dt):
                    if source_diagnostics:
                        source_diagnostics.rejected_dates += 1
                    continue

            # 4. Include & Exclude Keyword Filtering
            searchable_text = f"{raw_title} {raw_snippet or ''}".lower()

            if clean_includes:
                if mode_upper == "ALL":
                    if not all(inc in searchable_text for inc in clean_includes):
                        if source_diagnostics:
                            source_diagnostics.rejected_keywords += 1
                        continue
                else:
                    if not any(inc in searchable_text for inc in clean_includes):
                        if source_diagnostics:
                            source_diagnostics.rejected_keywords += 1
                        continue

            if clean_excludes:
                if any(exc in searchable_text for exc in clean_excludes):
                    if source_diagnostics:
                        source_diagnostics.rejected_keywords += 1
                    continue

            # 5. Supabase Snapshot Duplicate Exclusion
            if supabase_snapshot is not None:
                if hasattr(supabase_snapshot, "is_duplicate") and supabase_snapshot.is_duplicate(normalized_link):
                    if source_diagnostics:
                        source_diagnostics.db_duplicates_excluded += 1
                        stored_url = None
                        if hasattr(supabase_snapshot, "get_match"):
                            try:
                                match_record = supabase_snapshot.get_match(normalized_link)
                                stored_url = getattr(match_record, "original_url", None) if match_record is not None else None
                            except Exception:
                                stored_url = None
                        source_diagnostics.db_excluded_urls.append({
                            "candidate_url": normalized_link,
                            "stored_url": stored_url
                        })
                    continue
                db_status = "db_verified_new"
            else:
                db_status = "unverified"

            # Check platform quota if provided (Correction 3)
            if platform_quotas is not None:
                if platform_quotas.get(actual_platform, 0) <= 0:
                    # Platform quota is already filled or platform not enabled
                    # DO NOT add to seen_urls, DO NOT count toward batch limit
                    continue

            # Register in within-run seen set only after accepting candidate
            if use_canonical_keys:
                seen_urls.add(c_key)
            else:
                seen_urls.add(normalized_link)

            if platform_quotas is not None:
                platform_quotas[actual_platform] -= 1

            parsed_domain = urllib.parse.urlparse(normalized_link).netloc

            candidate = CandidateArticle(
                title=raw_title,
                url=normalized_link,
                platform=actual_platform,
                source_domain=parsed_domain,
                snippet=raw_snippet,
                publication_date=iso_pub_date,
                discovery_query=query,
                discovery_provider="Bing News RSS",
                discovery_method="public_rss_feed",
                discovered_at=timestamp,
                db_status=db_status
            )
            candidates.append(candidate)
            if source_diagnostics:
                source_diagnostics.platform_breakdown[actual_platform] = (
                    source_diagnostics.platform_breakdown.get(actual_platform, 0) + 1
                )

            if platform_quotas is None:
                if len(candidates) >= max_candidates:
                    break

        return candidates

