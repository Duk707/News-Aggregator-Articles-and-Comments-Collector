from typing import Optional, Dict, List
from pydantic import BaseModel, Field


class CandidateArticle(BaseModel):
    """
    Data model representing a candidate news article discovered via public news discovery.
    Retains structured provenance describing the discovery provider, method, and search query.
    """
    title: str = Field(description="Headline title of candidate article")
    url: str = Field(description="Cleaned, validated candidate article URL")
    platform: str = Field(description="Platform name (e.g., Yahoo News, MSN)")
    source_domain: str = Field(description="Domain name (e.g., news.yahoo.com, www.msn.com)")
    snippet: Optional[str] = Field(default=None, description="Summary snippet from discovery RSS/metadata")
    publication_date: Optional[str] = Field(default=None, description="ISO publication timestamp parsed from RSS pubDate")
    discovery_query: str = Field(description="Main search query string used for discovery")
    discovery_provider: str = Field(default="Bing News RSS", description="Name of public discovery provider")
    discovery_method: str = Field(default="public_rss_feed", description="Mechanism used to locate candidate")
    discovered_at: str = Field(description="ISO timestamp when candidate was discovered")
    db_status: str = Field(default="unverified", description="Database verification status: 'db_verified_new', 'db_duplicate', or 'unverified'")


class SourceDiscoveryDiagnostics(BaseModel):
    """
    Accounting diagnostics for a single discovery source query (e.g. site:yahoo.com or site:msn.com).
    """
    source_name: str = Field(description="Name of the discovery query source (e.g. Yahoo News, MSN)")
    requests_made: int = Field(default=0, description="Total HTTP requests dispatched for this query")
    pages_attempted: int = Field(default=0, description="Total RSS offset pages attempted")
    raw_items_in_responses: int = Field(default=0, description="Total raw <item> elements found across all valid XML responses")
    items_processed: int = Field(default=0, description="Total items processed before candidate limit was reached")
    unique_candidates_pooled: int = Field(default=0, description="Unique validated candidates added to this source's pool")
    candidates_returned: int = Field(default=0, description="Candidates from this source included in final merged output")
    repeated_urls_in_search: int = Field(default=0, description="Items skipped because URL was already seen in this search run")
    rejected_unsupported_urls: int = Field(default=0, description="Items rejected because URL is invalid syntax or not supported by router")
    rejected_keywords: int = Field(default=0, description="Items rejected due to include/exclude keyword mismatch")
    rejected_dates: int = Field(default=0, description="Items rejected due to date filter mismatch or missing date")
    target_confirmed_new: Optional[int] = Field(default=None, description="Requested target for confirmed new URLs")
    confirmed_new_candidates: int = Field(default=0, description="Confirmed new candidates accepted into pool (snapshot verified)")
    unverified_candidates: int = Field(default=0, description="Eligible candidates accepted without database verification")
    shortfall: int = Field(default=0, description="Shortfall from target (target - confirmed_new) if target specified")
    db_duplicates_excluded: int = Field(default=0, description="Candidates rejected because they already exist in Supabase snapshot")
    db_excluded_urls: List[Dict[str, Optional[str]]] = Field(default_factory=list, description="List of candidate URLs excluded because they matched accessible Supabase records, along with their matching stored URL if available")
    db_verification_status: str = Field(default="disabled", description="Supabase verification state: 'complete', 'empty', 'failed', 'incomplete', 'disabled'")
    consecutive_zero_yield_pages: int = Field(default=0, description="Consecutive pages that yielded zero new candidates")
    platform_breakdown: Dict[str, int] = Field(default_factory=dict, description="Counts of pooled candidates by actual adapter platform")
    returned_platform_breakdown: Dict[str, int] = Field(default_factory=dict, description="Counts of returned candidates by actual adapter platform")
    network_errors: int = Field(default=0, description="Number of HTTP/network request errors or timeouts")
    xml_parse_errors: int = Field(default=0, description="Number of malformed XML response errors")
    termination_reason: str = Field(default="not_started", description="Why pagination terminated for this source")

    @property
    def raw_items_returned(self) -> int:
        """Backward compatibility alias for raw_items_in_responses."""
        return self.raw_items_in_responses

    @property
    def unique_eligible_urls(self) -> int:
        """Backward compatibility alias for unique_candidates_pooled."""
        return self.unique_candidates_pooled


class DiscoveryRunDiagnostics(BaseModel):
    """
    Aggregate diagnostics container for an entire discovery run.
    """
    yahoo: SourceDiscoveryDiagnostics = Field(default_factory=lambda: SourceDiscoveryDiagnostics(source_name="Yahoo News"))
    msn: SourceDiscoveryDiagnostics = Field(default_factory=lambda: SourceDiscoveryDiagnostics(source_name="MSN"))
    total_candidates_returned: int = Field(default=0, description="Total candidates returned after merging")
    overall_termination: str = Field(default="completed", description="Overall summary termination status")
    db_verification_status: str = Field(default="disabled", description="Overall Supabase verification state")

    def format_summary_line(self) -> str:
        """Returns a concise single-line summary of per-source diagnostics."""
        parts = []
        for src in (self.yahoo, self.msn):
            if src.pages_attempted > 0 or src.requests_made > 0:
                parts.append(
                    f"{src.source_name}: {src.candidates_returned} ret / {src.unique_candidates_pooled} pooled "
                    f"({src.pages_attempted} pgs, {src.raw_items_in_responses} items, "
                    f"{src.repeated_urls_in_search} dups, {src.rejected_keywords} kw-rej, "
                    f"{src.rejected_unsupported_urls} unsupp, term: {src.termination_reason})"
                )
        return " | ".join(parts) if parts else "No sources searched"

    def format_multiline_report(self) -> str:
        """Returns a readable multiline formatted diagnostic report."""
        lines = [
            f"Discovery Run Summary (Total Returned to GUI: {self.total_candidates_returned}, Status: {self.overall_termination})"
        ]
        if self.db_verification_status != "disabled":
            lines.append(f"• Database Verification: Status [{self.db_verification_status}]")
        else:
            lines.append("• Database Verification: Disabled (No database snapshot provided; candidates are unverified)")
        for src in (self.yahoo, self.msn):
            if src.pages_attempted == 0 and src.requests_made == 0:
                continue
            lines.append(f"• {src.source_name} Query (Terminated: {src.termination_reason}):")
            if src.target_confirmed_new is not None:
                if self.db_verification_status != "disabled":
                    lines.append(
                        f"    - Target & Yield: Target {src.target_confirmed_new} -> {src.confirmed_new_candidates} confirmed new "
                        f"(Shortfall: {src.shortfall}, DB Dups Excluded: {src.db_duplicates_excluded})"
                    )

                else:
                    lines.append(
                        f"    - Target & Yield: Target {src.target_confirmed_new} -> {src.unverified_candidates} eligible/unverified "
                        f"(DB Verification: Disabled, 0 confirmed new)"
                    )

            if src.db_excluded_urls:
                lines.append(
                    f"    - Excluded Supabase Duplicates ({len(src.db_excluded_urls)} item(s) matched accessible database records):"
                )
                for item in src.db_excluded_urls:
                    cand_u = item.get("candidate_url", "")
                    stored_u = item.get("stored_url")
                    lines.append(f"        * Candidate URL: {cand_u}")
                    if stored_u:
                        lines.append(f"          Stored URL:    {stored_u}")
                    else:
                        lines.append(f"          Stored URL:    [Could not retrieve matching stored record]")

            lines.append(
                f"    - Network: {src.requests_made} requests across {src.pages_attempted} page(s) "
                f"({src.network_errors} net errs, {src.xml_parse_errors} xml errs)"
            )
            lines.append(
                f"    - RSS Feed: {src.raw_items_in_responses} total item(s) in responses ({src.items_processed} processed)"
            )
            lines.append(
                f"    - Exclusions: {src.repeated_urls_in_search} duplicates, "
                f"{src.rejected_keywords} keyword mismatch, "
                f"{src.rejected_unsupported_urls} unsupported/invalid, "
                f"{src.rejected_dates} date mismatch"
            )
            pooled_plat_str = ", ".join(f"{k}: {v}" for k, v in src.platform_breakdown.items()) if src.platform_breakdown else "none"
            ret_plat_str = ", ".join(f"{k}: {v}" for k, v in src.returned_platform_breakdown.items()) if src.returned_platform_breakdown else "none"
            lines.append(
                f"    - Yield: {src.unique_candidates_pooled} pooled -> {src.candidates_returned} returned to GUI"
            )
            lines.append(
                f"    - Platforms: Pooled [{pooled_plat_str}] -> Returned [{ret_plat_str}]"
            )
        return "\n".join(lines)
