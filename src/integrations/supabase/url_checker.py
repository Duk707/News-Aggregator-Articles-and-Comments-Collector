"""
src/integrations/supabase/url_checker.py

Read-only Supabase article URL duplicate checking component (Gate 3B.1).
Retrieves all accessible article URLs from `public.articles` using keyset pagination
and provides efficient in-memory duplicate lookup against discovered candidate URLs.

RLS VISIBILITY NOTICE:
Row-Level Security (RLS) policies in PostgreSQL/Supabase restrict row visibility
based on the active client role (e.g. anon vs authenticated). Keyset pagination
reliably retrieves all records VISIBLE to the active client role. It cannot guarantee
the absence of records hidden by RLS policies.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple
import urllib.parse

from src.discovery.search import clean_tracking_params
from src.integrations.supabase.client import SupabaseClient
from src.utils.urls import normalize_url


def canonicalize_url_key(url_str: Optional[str]) -> str:
    """
    Constructs a deterministic canonical lookup key for URL comparison:
    1. Unwraps search click redirect wrappers (e.g. Bing News apiclick.aspx).
    2. Cleans known analytics/tracking parameters (utm_*, ncid, gclid, etc.).
    3. Validates that the URL has an absolute http/https scheme and non-empty hostname.
       Returns empty string for invalid, missing, malformed, or non-http/https URLs.
    4. Normalizes scheme and network location (hostname) to lowercase.
    5. Strips default HTTP/HTTPS ports (:80, :443) from netloc if present.
    6. Preserves case-sensitive URL path and meaningful trailing slashes.
    7. Sorts functional query parameters deterministically by key and value.
    8. Discards client-side fragments (#...).
    
    Returns an empty string if url_str is missing, invalid, or unparseable.
    """
    if not url_str or not isinstance(url_str, str) or not url_str.strip():
        return ""

    # 1 & 2: Clean tracking parameters and unwrap Bing redirect wrappers safely
    cleaned = clean_tracking_params(url_str.strip())
    if not cleaned:
        return ""

    try:
        parsed = urllib.parse.urlparse(cleaned)
    except Exception:
        return ""

    scheme = parsed.scheme.lower() if parsed.scheme else ""
    if scheme not in ("http", "https"):
        return ""

    # Require valid non-empty hostname
    hostname = parsed.hostname
    if not hostname or not hostname.strip():
        return ""

    netloc = parsed.netloc.lower()

    # Normalize default ports
    if scheme == "http" and netloc.endswith(":80"):
        netloc = netloc[:-3]
    elif scheme == "https" and netloc.endswith(":443"):
        netloc = netloc[:-4]

    # Correction 2: Preserve meaningful trailing slashes in path
    path = parsed.path

    # Deterministically sort functional query parameters
    query = ""
    if parsed.query:
        query_pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        if query_pairs:
            # Sort by param name, then value (case-sensitive)
            sorted_pairs = sorted(query_pairs, key=lambda kv: (kv[0], kv[1]))
            query = urllib.parse.urlencode(sorted_pairs, doseq=True)

    # Fragment is intentionally discarded for article deduplication
    canonical = urllib.parse.urlunparse((
        scheme,
        netloc,
        path,
        parsed.params,
        query,
        ""
    ))
    return canonical


@dataclass
class StoredUrlRecord:
    """Metadata representing an existing article URL retrieved from public.articles."""
    id: int
    original_url: str
    normalized_key: str


class UrlRetrievalStatus(str, Enum):
    """Categorized status for Supabase URL snapshot retrieval."""
    COMPLETE = "complete"                       # All RLS-accessible records retrieved
    EMPTY = "empty"                             # Table is empty (0 accessible records)
    AUTH_ERROR = "auth_error"                   # HTTP 401 or 403 access denied
    HTTP_ERROR = "http_error"                   # Other HTTP error (e.g. 500)
    NETWORK_ERROR = "network_error"             # Connection error, timeout, or DNS failure
    MALFORMED_RESPONSE = "malformed_response"   # Response was not valid JSON list of dicts
    INCOMPLETE_PAGINATION = "incomplete_pagination"  # Safety limit hit or cursor non-advancing


@dataclass
class UrlCheckerSnapshot:
    """
    Immutable in-memory snapshot of accessible article URLs and retrieval diagnostics.
    """
    status: UrlRetrievalStatus
    total_records_read: int = 0
    valid_urls_loaded: int = 0
    null_or_empty_urls_skipped: int = 0
    pages_fetched: int = 0
    error_message: Optional[str] = None
    rls_limitation_notice: str = (
        "Comparison is verified against all RLS-visible records accessible to the current database role. "
        "It cannot guarantee absence of records hidden by Row-Level Security policies."
    )
    records_by_key: Dict[str, StoredUrlRecord] = field(default_factory=dict)

    @property
    def is_verified_accessible(self) -> bool:
        """True if and only if retrieval succeeded completely across all accessible records."""
        return self.status in (UrlRetrievalStatus.COMPLETE, UrlRetrievalStatus.EMPTY)

    def is_duplicate(self, candidate_url: str) -> bool:
        """
        Returns True if candidate_url matches any existing URL in this accessible snapshot.
        Returns False if candidate_url is empty, invalid, or absent from the snapshot.
        """
        key = canonicalize_url_key(candidate_url)
        if not key:
            return False
        return key in self.records_by_key

    def get_match(self, candidate_url: str) -> Optional[StoredUrlRecord]:
        """
        Returns the StoredUrlRecord matching candidate_url, or None if no match found.
        """
        key = canonicalize_url_key(candidate_url)
        if not key:
            return None
        return self.records_by_key.get(key)


class SupabaseUrlChecker:
    """
    Read-only service for retrieving existing article URLs from Supabase public.articles.
    Uses keyset pagination (id > last_seen_id) to efficiently and deterministically stream
    all accessible records without offset instability or local disk caching.
    """

    TABLE_NAME = "articles"
    DEFAULT_PAGE_SIZE = 1000
    DEFAULT_MAX_PAGES = 100  # Defensive safety cap (allows up to 100,000 records)

    def __init__(
        self,
        client: SupabaseClient,
        page_size: int = DEFAULT_PAGE_SIZE,
        max_pages: int = DEFAULT_MAX_PAGES
    ):
        self.client = client
        self.page_size = max(1, page_size)
        self.max_pages = max(1, max_pages)

    def fetch_accessible_snapshot(self) -> UrlCheckerSnapshot:
        """
        Streams all RLS-accessible article records from Supabase public.articles
        using keyset pagination (id > last_seen_id ordered by id.asc).
        
        Returns a UrlCheckerSnapshot containing the in-memory lookup set and diagnostic status.
        Never executes write operations (INSERT, UPDATE, DELETE).
        """
        last_seen_id: Optional[int] = None
        pages_fetched = 0
        total_records_read = 0
        null_or_empty_urls_skipped = 0
        records_by_key: Dict[str, StoredUrlRecord] = {}

        while True:
            # Defensive check against infinite pagination
            if pages_fetched >= self.max_pages:
                return UrlCheckerSnapshot(
                    status=UrlRetrievalStatus.INCOMPLETE_PAGINATION,
                    total_records_read=total_records_read,
                    valid_urls_loaded=len(records_by_key),
                    null_or_empty_urls_skipped=null_or_empty_urls_skipped,
                    pages_fetched=pages_fetched,
                    error_message=f"Pagination halted: Reached safety limit of {self.max_pages} pages ({total_records_read} records read).",
                    records_by_key=records_by_key
                )

            params: Dict[str, str] = {
                "select": "id,url",
                "order": "id.asc",
                "limit": str(self.page_size)
            }
            if last_seen_id is not None:
                params["id"] = f"gt.{last_seen_id}"

            try:
                status_code, data = self.client.get(self.TABLE_NAME, params=params)
            except Exception as exc:
                return UrlCheckerSnapshot(
                    status=UrlRetrievalStatus.NETWORK_ERROR,
                    total_records_read=total_records_read,
                    valid_urls_loaded=len(records_by_key),
                    null_or_empty_urls_skipped=null_or_empty_urls_skipped,
                    pages_fetched=pages_fetched,
                    error_message=f"Network exception communicating with Supabase: {exc}",
                    records_by_key=records_by_key
                )

            if status_code in (401, 403):
                return UrlCheckerSnapshot(
                    status=UrlRetrievalStatus.AUTH_ERROR,
                    total_records_read=total_records_read,
                    valid_urls_loaded=len(records_by_key),
                    null_or_empty_urls_skipped=null_or_empty_urls_skipped,
                    pages_fetched=pages_fetched,
                    error_message=f"Access denied (HTTP {status_code}): Invalid client key or RLS policy restricts SELECT.",
                    records_by_key=records_by_key
                )

            if status_code != 200:
                return UrlCheckerSnapshot(
                    status=UrlRetrievalStatus.HTTP_ERROR,
                    total_records_read=total_records_read,
                    valid_urls_loaded=len(records_by_key),
                    null_or_empty_urls_skipped=null_or_empty_urls_skipped,
                    pages_fetched=pages_fetched,
                    error_message=f"Supabase GET request failed with HTTP {status_code}: {data}",
                    records_by_key=records_by_key
                )

            # Validate response payload structure
            if not isinstance(data, list):
                return UrlCheckerSnapshot(
                    status=UrlRetrievalStatus.MALFORMED_RESPONSE,
                    total_records_read=total_records_read,
                    valid_urls_loaded=len(records_by_key),
                    null_or_empty_urls_skipped=null_or_empty_urls_skipped,
                    pages_fetched=pages_fetched,
                    error_message=f"Malformed API response: Expected JSON list, received {type(data).__name__}.",
                    records_by_key=records_by_key
                )

            # End of table reached
            if len(data) == 0:
                final_status = UrlRetrievalStatus.EMPTY if pages_fetched == 0 else UrlRetrievalStatus.COMPLETE
                return UrlCheckerSnapshot(
                    status=final_status,
                    total_records_read=total_records_read,
                    valid_urls_loaded=len(records_by_key),
                    null_or_empty_urls_skipped=null_or_empty_urls_skipped,
                    pages_fetched=pages_fetched,
                    records_by_key=records_by_key
                )

            # Process records in current batch
            for item in data:
                if not isinstance(item, dict) or "id" not in item:
                    return UrlCheckerSnapshot(
                        status=UrlRetrievalStatus.MALFORMED_RESPONSE,
                        total_records_read=total_records_read,
                        valid_urls_loaded=len(records_by_key),
                        null_or_empty_urls_skipped=null_or_empty_urls_skipped,
                        pages_fetched=pages_fetched,
                        error_message="Malformed API record: Expected dict containing 'id' field.",
                        records_by_key=records_by_key
                    )

                # Strengthened check: 'url' field must be present because it was explicitly requested
                if "url" not in item:
                    return UrlCheckerSnapshot(
                        status=UrlRetrievalStatus.MALFORMED_RESPONSE,
                        total_records_read=total_records_read,
                        valid_urls_loaded=len(records_by_key),
                        null_or_empty_urls_skipped=null_or_empty_urls_skipped,
                        pages_fetched=pages_fetched,
                        error_message="Malformed API record: Missing explicitly requested 'url' field.",
                        records_by_key=records_by_key
                    )

                try:
                    record_id = int(item["id"])
                except (ValueError, TypeError):
                    return UrlCheckerSnapshot(
                        status=UrlRetrievalStatus.MALFORMED_RESPONSE,
                        total_records_read=total_records_read,
                        valid_urls_loaded=len(records_by_key),
                        null_or_empty_urls_skipped=null_or_empty_urls_skipped,
                        pages_fetched=pages_fetched,
                        error_message=f"Malformed record 'id': Cannot parse {item.get('id')} as integer.",
                        records_by_key=records_by_key
                    )

                # Cursor advancement safety check
                if last_seen_id is not None and record_id <= last_seen_id:
                    return UrlCheckerSnapshot(
                        status=UrlRetrievalStatus.INCOMPLETE_PAGINATION,
                        total_records_read=total_records_read,
                        valid_urls_loaded=len(records_by_key),
                        null_or_empty_urls_skipped=null_or_empty_urls_skipped,
                        pages_fetched=pages_fetched,
                        error_message=f"Pagination cursor failed to advance (id {record_id} <= last_seen_id {last_seen_id}).",
                        records_by_key=records_by_key
                    )

                raw_url = item["url"]
                # Strengthened check: url must be string or None
                if raw_url is not None and not isinstance(raw_url, str):
                    return UrlCheckerSnapshot(
                        status=UrlRetrievalStatus.MALFORMED_RESPONSE,
                        total_records_read=total_records_read,
                        valid_urls_loaded=len(records_by_key),
                        null_or_empty_urls_skipped=null_or_empty_urls_skipped,
                        pages_fetched=pages_fetched,
                        error_message=f"Malformed API record: Expected string or null for 'url', received {type(raw_url).__name__}.",
                        records_by_key=records_by_key
                    )

                last_seen_id = record_id
                total_records_read += 1

                if raw_url is None or not raw_url.strip():
                    null_or_empty_urls_skipped += 1
                    continue

                canon_key = canonicalize_url_key(raw_url)
                if not canon_key:
                    null_or_empty_urls_skipped += 1
                    continue

                # Store first occurrence to preserve lowest id / provenance
                if canon_key not in records_by_key:
                    records_by_key[canon_key] = StoredUrlRecord(
                        id=record_id,
                        original_url=raw_url.strip(),
                        normalized_key=canon_key
                    )

            pages_fetched += 1

