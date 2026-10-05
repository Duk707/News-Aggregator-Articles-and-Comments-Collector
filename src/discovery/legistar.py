"""
Legistar Discovery and Cross-Linking Service (Step 30C).
Provides keyword-based search over Legistar REST OData APIs and composite field cross-linking
to Granicus Ideas public comment surfaces.
"""
import re
import urllib.parse
from typing import List, Dict, Any, Optional, Tuple
import requests

from src.models import CommentStatus


class LegistarDiscovery:
    """
    Discovery engine for searching Legistar legislative records and cross-linking to Granicus Ideas.
    """
    def __init__(self, base_api_url: str = "https://webapi.legistar.com/v1"):
        self.base_api_url = base_api_url.rstrip("/")

    @staticmethod
    def escape_odata_string(value: str) -> str:
        """
        Escapes single quotes for OData string filter expressions by doubling them (' -> '').
        """
        return value.replace("'", "''")

    def search_matters(
        self,
        client: str,
        keyword: str,
        http_session: Optional[requests.Session] = None
    ) -> List[Dict[str, Any]]:
        """
        Searches Legistar API matters endpoint using OData substringof filter.
        
        Args:
            client: Legistar client identifier (e.g. 'ousd', 'houstonisd').
            keyword: Topic search phrase or keyword.
            http_session: Optional custom or mocked HTTP session.

        Returns:
            List of raw matter JSON dictionary records.
        """
        escaped_kw = self.escape_odata_string(keyword)
        encoded_filter = urllib.parse.quote(f"substringof('{escaped_kw}', MatterTitle) eq true")
        url = f"{self.base_api_url}/{client}/matters?$filter={encoded_filter}"

        session = http_session or requests.Session()
        try:
            resp = session.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    return data
            return []
        except Exception:
            return []

    def cross_link_granicus_ideas(
        self,
        legistar_matter: Dict[str, Any],
        candidate_granicus_items: List[Dict[str, Any]]
    ) -> Tuple[Optional[str], CommentStatus]:
        """
        Cross-links a Legistar matter record to a Granicus Ideas agenda item using COMPOSITE_FIELD_MATCH.
        Composite fields: File Number + Meeting Date + Title similarity.

        Returns:
            Tuple[Optional[str], CommentStatus]: (matched_url, status)
            - Unique match: (url, AVAILABLE)
            - Ambiguous multiple matches: (None, UNKNOWN)
            - Zero matches: (None, NONE_PRESENT)
        """
        matter_file = str(legistar_matter.get("MatterFile", "")).strip().lower()
        matter_title = str(legistar_matter.get("MatterTitle", "")).strip().lower()
        matter_date = str(legistar_matter.get("MatterDate", "")).split("T")[0]

        matches = []
        for candidate in candidate_granicus_items:
            c_url = candidate.get("url", "")
            c_title = str(candidate.get("title", "")).strip().lower()
            c_file = str(candidate.get("file_number", "")).strip().lower()
            c_date = str(candidate.get("date", "")).split("T")[0]

            file_match = matter_file and (matter_file in c_file or matter_file in c_url.lower())
            title_match = matter_title and (matter_title in c_title or c_title in matter_title)
            date_match = matter_date and (matter_date == c_date)

            if file_match or (title_match and date_match):
                matches.append(c_url)

        if len(matches) == 1:
            return matches[0], CommentStatus.UNKNOWN
        elif len(matches) > 1:
            return None, CommentStatus.UNKNOWN
        else:
            return None, CommentStatus.UNKNOWN
