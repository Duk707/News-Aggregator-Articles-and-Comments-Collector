#!/usr/bin/env python3
"""
scripts/probe_bing_rss_pagination.py

Diagnostic experiment utility to measure Bing News RSS pagination capacity beyond page 5.
Evaluates offsets first=1, 11, 21, ..., 91 (up to 10 pages per source) for Yahoo News and MSN.
Directly compares unique candidate yield of Pages 1–5 against Pages 6–10.

SAFETY GUARANTEES:
- Offline / dry-run by default.
- Requires explicit --live flag to make live HTTP requests.
- Rate-limited with minimum 2.0s sequential delay between requests.
- Hard maximum budget of 20 total requests per execution.
- Immediately stops on HTTP 403, 429, or network errors with GLOBAL abort.
- Validates XML responses to reject malformed XML and unexpected HTML bodies.
- Does not modify any production code, database, or configuration.
"""

import argparse
import os
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import requests

from src.discovery.models import CandidateArticle, SourceDiscoveryDiagnostics
from src.discovery.search import CandidateDiscoverer


BING_NEWS_RSS_URL = "https://www.bing.com/news/search"
MAX_REQUEST_BUDGET = 20
PAGE_OFFSETS = [1, 11, 21, 31, 41, 51, 61, 71, 81, 91]


@dataclass
class PageProbeResult:
    page_num: int
    offset: int
    status_code: Optional[int] = None
    raw_items: int = 0
    new_unique: int = 0
    repeats: int = 0
    rejected_unsupported: int = 0
    rejected_keywords: int = 0
    cumulative_unique: int = 0
    platform_breakdown: Dict[str, int] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class PhaseProbeSummary:
    phase_name: str
    page_range: str
    requests_attempted: int = 0
    successful_requests: int = 0
    raw_items: int = 0
    new_unique: int = 0
    repeats: int = 0
    rejected_unsupported: int = 0
    rejected_keywords: int = 0
    cumulative_unique_end: int = 0
    platform_breakdown: Dict[str, int] = field(default_factory=dict)


@dataclass
class SourceProbeResult:
    source_name: str
    site_query: str
    pages: List[PageProbeResult] = field(default_factory=list)
    phase1: Optional[PhaseProbeSummary] = None  # Pages 1-5
    phase2: Optional[PhaseProbeSummary] = None  # Pages 6-10
    total_unique: int = 0
    termination_reason: str = "completed"
    error: Optional[str] = None


@dataclass
class ProbeRunState:
    total_requests: int = 0
    global_aborted: bool = False
    abort_reason: Optional[str] = None
    abort_message: Optional[str] = None


@dataclass
class ProbeConfig:
    live: bool = False
    delay_sec: float = 2.0
    max_pages: int = 10
    keywords: List[str] = field(default_factory=lambda: ["AI", "education"])
    keyword_mode: str = "ALL"
    query: str = ""
    sources: List[str] = field(default_factory=lambda: ["yahoo", "msn"])
    stop_on_zero_items: bool = False
    fixture_dir: Optional[str] = None


def build_probe_query(
    query: str,
    site_query: str,
    keywords: Optional[List[str]] = None,
    keyword_mode: str = "ALL"
) -> str:
    """
    Formulates the outbound Bing News search query following production conventions:
    - If base query is provided, uses: "<base_query> <site_query>".
    - If base query is blank:
      - If mode is 'ALL', joins include keywords with spaces: "<kw1> <kw2> <site_query>".
      - If mode is 'ANY', rejects unsupported configuration explicitly to prevent
        exceeding the strict 20-request probe budget.
    """
    clean_q = (query or "").strip()
    clean_kws = [k.strip() for k in (keywords or []) if k.strip()]
    mode_upper = (keyword_mode or "ALL").strip().upper()

    if clean_q:
        base_term = clean_q
    elif clean_kws:
        if mode_upper == "ALL":
            base_term = " ".join(clean_kws)
        else:
            raise ValueError(
                f"Unsupported configuration: Blank search query with keyword mode '{mode_upper}' "
                "requires multiple keyword subqueries per offset, which is not supported in the "
                "single-query pagination probe to guarantee strict budget isolation. "
                "Please provide a search query or use mode 'ALL'."
            )
    else:
        raise ValueError("Cannot formulate query: Both search query and include keywords are empty.")

    return f"{base_term} {site_query}".strip()


def default_live_fetcher(url: str, params: dict, timeout: float = 10.0) -> Tuple[int, str]:
    """Live HTTP fetcher with standard browser User-Agent header."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    resp = requests.get(url, params=params, headers=headers, timeout=timeout)
    return resp.status_code, resp.text


def build_phase_summary(phase_name: str, page_range: str, pages: List[PageProbeResult]) -> PhaseProbeSummary:
    summary = PhaseProbeSummary(phase_name=phase_name, page_range=page_range)
    cumul_end = 0
    for p in pages:
        summary.requests_attempted += 1
        if p.status_code == 200 and not p.error:
            summary.successful_requests += 1
        summary.raw_items += p.raw_items
        summary.new_unique += p.new_unique
        summary.repeats += p.repeats
        summary.rejected_unsupported += p.rejected_unsupported
        summary.rejected_keywords += p.rejected_keywords
        cumul_end = p.cumulative_unique
        for plat, count in p.platform_breakdown.items():
            summary.platform_breakdown[plat] = summary.platform_breakdown.get(plat, 0) + count
    summary.cumulative_unique_end = cumul_end
    return summary


def probe_source(
    source_key: str,
    site_query: str,
    config: ProbeConfig,
    fetcher: Optional[Callable[[str, dict], Tuple[int, str]]],
    seen_urls: Set[str],
    discovery_service: CandidateDiscoverer,
    run_state: ProbeRunState
) -> SourceProbeResult:
    result = SourceProbeResult(
        source_name="Yahoo News" if source_key == "yahoo" else "MSN",
        site_query=site_query
    )

    include_yahoo = (source_key == "yahoo")
    include_msn = (source_key == "msn")

    try:
        full_q = build_probe_query(
            query=config.query,
            site_query=site_query,
            keywords=config.keywords,
            keyword_mode=config.keyword_mode
        )
    except ValueError as val_err:
        result.termination_reason = "invalid_query_configuration"
        result.error = str(val_err)
        run_state.global_aborted = True
        run_state.abort_reason = "invalid_query_configuration"
        run_state.abort_message = str(val_err)
        return result

    offsets_to_test = PAGE_OFFSETS[:min(config.max_pages, len(PAGE_OFFSETS))]

    for idx, offset in enumerate(offsets_to_test):
        page_num = idx + 1

        if run_state.global_aborted:
            result.termination_reason = f"aborted_{run_state.abort_reason}"
            break

        # Check total request budget limit
        if run_state.total_requests >= MAX_REQUEST_BUDGET:
            result.termination_reason = "max_request_budget_reached"
            break

        page_result = PageProbeResult(page_num=page_num, offset=offset)

        # Enforce rate-limiting delay between live requests
        if config.live and run_state.total_requests > 0:
            effective_delay = max(config.delay_sec, 2.0)
            time.sleep(effective_delay)

        params = {
            "q": full_q,
            "format": "rss",
            "first": offset
        }

        status_code = None
        xml_text = ""
        error_msg = None

        if fetcher:
            try:
                run_state.total_requests += 1
                status_code, xml_text = fetcher(BING_NEWS_RSS_URL, params)
                page_result.status_code = status_code
            except Exception as exc:
                error_msg = f"Network exception: {exc}"
                page_result.error = error_msg
                result.pages.append(page_result)
                result.termination_reason = "network_error"
                run_state.global_aborted = True
                run_state.abort_reason = "network_error"
                run_state.abort_message = error_msg
                break
        elif config.fixture_dir:
            # Offline fixture mode for testing
            fix_path = Path(config.fixture_dir) / f"{source_key}_page_{page_num}.xml"
            if fix_path.exists():
                status_code = 200
                xml_text = fix_path.read_text(encoding="utf-8")
                page_result.status_code = 200
            else:
                error_msg = f"Fixture not found: {fix_path}"
                page_result.error = error_msg
                result.pages.append(page_result)
                break
        else:
            # Dry-run: no fetcher provided and not live
            page_result.error = "Dry-run mode (no HTTP request made)"
            result.pages.append(page_result)
            continue

        # Immediate GLOBAL abort on safety-critical status codes
        if status_code in (403, 429):
            result.termination_reason = f"http_{status_code}_blocked"
            page_result.error = f"HTTP {status_code} Access Denied / Rate Limited"
            result.pages.append(page_result)
            run_state.global_aborted = True
            run_state.abort_reason = f"http_{status_code}_blocked"
            run_state.abort_message = f"HTTP {status_code}"
            break

        if status_code != 200:
            page_result.error = f"HTTP {status_code}"
            result.pages.append(page_result)
            result.termination_reason = f"http_{status_code}_error"
            run_state.global_aborted = True
            run_state.abort_reason = f"http_{status_code}_error"
            run_state.abort_message = f"HTTP {status_code}"
            break

        # Validate XML/RSS response structure
        if not xml_text or not xml_text.strip():
            page_result.error = "Empty response body received"
            result.pages.append(page_result)
            result.termination_reason = "empty_response"
            run_state.global_aborted = True
            run_state.abort_reason = "empty_response"
            run_state.abort_message = "Empty response body"
            break

        is_html_text = ("<html" in xml_text.lower()) or ("<!doctype html" in xml_text.lower())

        try:
            root = ET.fromstring(xml_text.strip())
            is_html_root = root.tag.lower().endswith("html")
            has_channel = (root.find(".//channel") is not None) or (root.tag.lower() == "rss")

            if is_html_text or is_html_root or not has_channel:
                err_desc = (
                    "Unexpected HTML response received instead of RSS feed"
                    if (is_html_text or is_html_root)
                    else f"Unexpected XML structure without RSS <channel> (root tag: <{root.tag}>)"
                )
                page_result.error = err_desc
                result.pages.append(page_result)
                result.termination_reason = "unexpected_html_response" if (is_html_text or is_html_root) else "missing_rss_channel"
                run_state.global_aborted = True
                run_state.abort_reason = result.termination_reason
                run_state.abort_message = err_desc
                break
        except Exception as parse_err:
            if is_html_text:
                err_desc = f"Unexpected HTML response received instead of RSS: {parse_err}"
                term_reason = "unexpected_html_response"
            else:
                err_desc = f"Malformed XML response: {parse_err}"
                term_reason = "malformed_xml"
            page_result.error = err_desc
            result.pages.append(page_result)
            result.termination_reason = term_reason
            run_state.global_aborted = True
            run_state.abort_reason = term_reason
            run_state.abort_message = err_desc
            break

        # Parse valid RSS XML response using existing production parser
        page_diag = SourceDiscoveryDiagnostics(source_name=result.source_name)
        candidates = discovery_service.parse_xml_candidates(
            xml_content=xml_text,
            query=config.query,
            include_yahoo=include_yahoo,
            include_msn=include_msn,
            max_candidates=9999,
            include_keywords=config.keywords,
            include_keyword_mode=config.keyword_mode,
            seen_urls=seen_urls,
            source_diagnostics=page_diag
        )

        page_result.raw_items = page_diag.raw_items_in_responses
        page_result.new_unique = len(candidates)
        page_result.repeats = page_diag.repeated_urls_in_search
        page_result.rejected_unsupported = page_diag.rejected_unsupported_urls
        page_result.rejected_keywords = page_diag.rejected_keywords
        page_result.platform_breakdown = dict(page_diag.platform_breakdown)
        page_result.cumulative_unique = len(seen_urls)

        result.pages.append(page_result)

        # Stop if Bing returned 0 raw items (end of results)
        if config.stop_on_zero_items and page_result.raw_items == 0:
            result.termination_reason = "zero_raw_items"
            break

    result.total_unique = len(seen_urls)

    # Compute Phase 1 (pages 1-5) and Phase 2 (pages 6-10) summaries
    p1_pages = [p for p in result.pages if p.page_num <= 5]
    p2_pages = [p for p in result.pages if p.page_num > 5]

    if p1_pages:
        result.phase1 = build_phase_summary("Phase 1", "Pages 1–5 (Offsets 1–41)", p1_pages)
    if p2_pages:
        result.phase2 = build_phase_summary("Phase 2", "Pages 6–10 (Offsets 51–91)", p2_pages)

    return result


def format_page_table(source_result: SourceProbeResult) -> str:
    lines = []
    lines.append(f"Source: {source_result.source_name} ({source_result.site_query})")
    lines.append("Page | Offset | Status | Raw Items | New Unique | Repeats | Rej Unsupp | Rej Keyw | Cumul Unique")
    lines.append("-----+--------+--------+-----------+------------+---------+------------+----------+-------------")
    if not source_result.pages:
        lines.append(f"  [No pages attempted - {source_result.termination_reason}]")
    for p in source_result.pages:
        if p.error:
            if p.status_code in (403, 429):
                status_str = f"{p.status_code}!"
            elif p.status_code == 200:
                status_str = "ERR200"
            elif p.status_code:
                status_str = f"E{p.status_code}"
            else:
                status_str = "ERR"
        else:
            status_str = str(p.status_code) if p.status_code is not None else "OK"

        lines.append(
            f"{p.page_num:4d} | {p.offset:6d} | {status_str:>6s} | "
            f"{p.raw_items:9d} | {p.new_unique:10d} | {p.repeats:7d} | "
            f"{p.rejected_unsupported:10d} | {p.rejected_keywords:8d} | "
            f"{p.cumulative_unique:12d}"
        )
    if source_result.error:
        lines.append(f"Source Error: {source_result.error}")
    err_pages = [p for p in source_result.pages if p.error]
    if err_pages:
        lines.append("Page Diagnostic Errors:")
        for p in err_pages:
            lines.append(f"  - Page {p.page_num} (offset {p.offset}): {p.error}")
    return "\n".join(lines)


def format_phase_comparison(source_result: SourceProbeResult) -> str:
    p1 = source_result.phase1
    p2 = source_result.phase2

    lines = []
    lines.append("=" * 82)
    lines.append(f"PHASE COMPARISON: {source_result.source_name} ({source_result.site_query})")
    lines.append("=" * 82)
    lines.append(f"{'Metric':<30} | {'Phase 1 (Pages 1–5)':<22} | {'Phase 2 (Pages 6–10)':<22} | {'Total'}")
    lines.append("-" * 30 + "-+-" + "-" * 22 + "-+-" + "-" * 22 + "-+-" + "-" * 10)

    p1_req = p1.requests_attempted if p1 else 0
    p2_req = p2.requests_attempted if p2 else 0
    lines.append(f"{'Requests Attempted':<30} | {p1_req:<22d} | {p2_req:<22d} | {p1_req + p2_req}")

    p1_raw = p1.raw_items if p1 else 0
    p2_raw = p2.raw_items if p2 else 0
    lines.append(f"{'Raw RSS Items':<30} | {p1_raw:<22d} | {p2_raw:<22d} | {p1_raw + p2_raw}")

    p1_uniq = p1.new_unique if p1 else 0
    p2_uniq = p2.new_unique if p2 else 0
    lines.append(f"{'New Unique Candidates':<30} | {p1_uniq:<22d} | {p2_uniq:<22d} | {p1_uniq + p2_uniq}")

    p1_rep = p1.repeats if p1 else 0
    p2_rep = p2.repeats if p2 else 0
    lines.append(f"{'Repeated URLs':<30} | {p1_rep:<22d} | {p2_rep:<22d} | {p1_rep + p2_rep}")

    p1_uns = p1.rejected_unsupported if p1 else 0
    p2_uns = p2.rejected_unsupported if p2 else 0
    lines.append(f"{'Rejected Unsupported URLs':<30} | {p1_uns:<22d} | {p2_uns:<22d} | {p1_uns + p2_uns}")

    p1_key = p1.rejected_keywords if p1 else 0
    p2_key = p2.rejected_keywords if p2 else 0
    lines.append(f"{'Rejected Keywords':<30} | {p1_key:<22d} | {p2_key:<22d} | {p1_key + p2_key}")

    p1_end = p1.cumulative_unique_end if p1 else 0
    p2_end = p2.cumulative_unique_end if p2 else p1_end
    lines.append(f"{'Cumulative Unique at End':<30} | {p1_end:<22d} | {p2_end:<22d} | {p2_end}")

    # Platform breakdowns
    p1_plat = ", ".join(f"{k}: {v}" for k, v in p1.platform_breakdown.items()) if p1 else "None"
    p2_plat = ", ".join(f"{k}: {v}" for k, v in p2.platform_breakdown.items()) if p2 else "None"
    lines.append(f"{'Platform Attribution':<30} | {p1_plat:<22} | {p2_plat:<22} | -")

    lines.append("-" * 82)
    diff = p2_uniq
    pct = (p2_uniq / p1_uniq * 100.0) if p1_uniq > 0 else 0.0
    lines.append(f"Capacity Assessment: Phase 2 yielded +{diff} additional unique candidates ({pct:.1f}% of Phase 1).")
    lines.append(f"Termination Reason: {source_result.termination_reason}")
    lines.append("=" * 82)
    return "\n".join(lines)


def run_probe(
    config: ProbeConfig,
    fetcher: Optional[Callable[[str, dict], Tuple[int, str]]] = None
) -> Dict[str, SourceProbeResult]:
    """
    Executes the pagination capacity probe across requested sources.
    Uses provided fetcher or live fetcher if config.live is True.
    """
    if config.live and fetcher is None:
        fetcher = default_live_fetcher

    discovery_service = CandidateDiscoverer()
    results: Dict[str, SourceProbeResult] = {}
    run_state = ProbeRunState()

    sources_to_probe = []
    if "yahoo" in config.sources:
        sources_to_probe.append(("yahoo", "site:yahoo.com"))
    if "msn" in config.sources:
        sources_to_probe.append(("msn", "site:msn.com"))

    for src_key, site_query in sources_to_probe:
        source_name = "Yahoo News" if src_key == "yahoo" else "MSN"

        if run_state.global_aborted:
            # Source skipped due to prior global abort
            skipped_result = SourceProbeResult(
                source_name=source_name,
                site_query=site_query,
                termination_reason=f"global_abort_{run_state.abort_reason}",
                error=f"Run aborted globally: {run_state.abort_message}"
            )
            results[src_key] = skipped_result
            continue

        source_seen_urls: Set[str] = set()
        src_res = probe_source(
            source_key=src_key,
            site_query=site_query,
            config=config,
            fetcher=fetcher,
            seen_urls=source_seen_urls,
            discovery_service=discovery_service,
            run_state=run_state
        )
        results[src_key] = src_res

    return results


def print_full_report(results: Dict[str, SourceProbeResult], config: ProbeConfig) -> None:
    print("\n" + "=" * 82)
    print("BING NEWS RSS PAGINATION CAPACITY EXPERIMENT REPORT")
    print("=" * 82)
    print(f"Mode: {'LIVE NETWORK' if config.live else 'DRY RUN / MOCKED'}")
    print(f"Keywords: {config.keywords} (Mode: {config.keyword_mode})")
    print(f"Discovery Query: '{config.query}'")
    print(f"Max Pages Tested: {config.max_pages}")
    print("=" * 82 + "\n")

    for src_key, res in results.items():
        print(format_page_table(res))
        print()
        print(format_phase_comparison(res))
        print()

    # Grand total summary
    tot_p1_uniq = sum(r.phase1.new_unique for r in results.values() if r.phase1)
    tot_p2_uniq = sum(r.phase2.new_unique for r in results.values() if r.phase2)
    tot_uniq = tot_p1_uniq + tot_p2_uniq

    print("=" * 82)
    print("OVERALL EXPERIMENT SUMMARY")
    print("=" * 82)
    print(f"Total Unique Candidates Discovered: {tot_uniq}")
    print(f"  - Phase 1 (Pages 1–5):   {tot_p1_uniq} candidates")
    print(f"  - Phase 2 (Pages 6–10):  {tot_p2_uniq} candidates")
    if tot_p1_uniq > 0:
        increase_pct = (tot_p2_uniq / tot_p1_uniq) * 100.0
        print(f"  - Yield Increase from Pages 6–10: +{tot_p2_uniq} (+{increase_pct:.1f}%)")
    print("=" * 82 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Probe Bing News RSS pagination capacity for Yahoo News and MSN (Gate 3A)."
    )
    parser.add_argument(
        "--live",
        action="store_true",
        default=False,
        help="Actually send HTTP requests to Bing News RSS. (Default: False, safe dry-run)"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=2.0,
        help="Sequential delay in seconds between requests (enforces >= 2.0s when live, default: 2.0)"
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=10,
        help="Maximum pages to probe per source, up to 10 (default: 10)"
    )
    parser.add_argument(
        "--keywords",
        type=str,
        default="AI, education",
        help="Comma-separated include keywords (default: 'AI, education')"
    )
    parser.add_argument(
        "--mode",
        choices=["ALL", "ANY"],
        default="ALL",
        help="Include keyword match mode (default: ALL)"
    )
    parser.add_argument(
        "--query",
        type=str,
        default="",
        help="Base search query topic (default: empty)"
    )
    parser.add_argument(
        "--sources",
        choices=["yahoo", "msn", "both"],
        default="both",
        help="Which sources to probe (default: both)"
    )
    parser.add_argument(
        "--stop-on-zero-items",
        action="store_true",
        default=False,
        help="Stop pagination early for a source if Bing returns 0 raw items on a page."
    )
    parser.add_argument(
        "--fixture-dir",
        type=str,
        default=None,
        help="Directory with offline XML fixtures for testing (e.g. yahoo_page_1.xml)"
    )

    args = parser.parse_args()

    clean_kw = [k.strip() for k in args.keywords.split(",") if k.strip()]
    src_list = ["yahoo", "msn"] if args.sources == "both" else [args.sources]

    config = ProbeConfig(
        live=args.live,
        delay_sec=max(args.delay, 2.0) if args.live else args.delay,
        max_pages=min(max(1, args.max_pages), 10),
        keywords=clean_kw,
        keyword_mode=args.mode,
        query=args.query,
        sources=src_list,
        stop_on_zero_items=args.stop_on_zero_items,
        fixture_dir=args.fixture_dir
    )

    if not config.live and not config.fixture_dir:
        print("\n" + "=" * 82)
        print("DRY-RUN SAFETY CHECK: --live flag was NOT specified.")
        print("No live HTTP network calls will be made.")
        print("To run the live diagnostic probe against Bing News RSS, run:")
        print("    python scripts/probe_bing_rss_pagination.py --live")
        print("=" * 82 + "\n")
        sys.exit(0)

    try:
        results = run_probe(config)
    except ValueError as val_err:
        print(f"\nConfiguration Error: {val_err}\n", file=sys.stderr)
        sys.exit(1)

    print_full_report(results, config)


if __name__ == "__main__":
    main()
