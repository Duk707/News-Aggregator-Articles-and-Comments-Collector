"""
Direct Supabase Uploader & Dry-Run Analyzer (Step 29).
Executes pre-upload read-only dry runs and performs transactional uploads from previewed SupabaseStagingDataset
into public.articles and public.comments tables.
"""
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

from src.integrations.supabase.models import SupabaseStagingDataset, SupabaseArticleRow, SupabaseCommentRow
from src.integrations.supabase.client import SupabaseClient


class UploadRecordResult(BaseModel):
    """Result status for individual article or comment insertion."""
    record_type: str  # "article" or "comment"
    staging_id: int
    real_id: Optional[int] = None
    status: str  # "inserted", "linked", "failed", "blocked", "skipped", "unknown"
    notes: str = ""
    message: str = ""


class UploadDryRunResult(BaseModel):
    """Result container for read-only pre-upload dry run analysis."""
    connectivity_ok: bool = False
    api_key_valid: bool = False
    read_access_ok: bool = False
    active_role: str = "anon"
    write_access_note: str = "Write permission not yet verified by a real INSERT (manual live-write test required)"
    
    article_case_a_inserts: int = 0
    article_case_b_links: int = 0
    article_case_c_warnings: int = 0
    article_case_d_blocks: int = 0
    comment_duplicate_warnings: int = 0

    article_cases: Dict[int, str] = Field(default_factory=dict)
    article_matched_ids: Dict[int, int] = Field(default_factory=dict)
    article_conflict_messages: Dict[int, str] = Field(default_factory=dict)

    can_proceed: bool = False
    error_message: str = ""

    @property
    def read_access_verified(self) -> bool:
        """Returns True if connectivity, API key validity, and read access are all verified."""
        return self.connectivity_ok and self.api_key_valid and self.read_access_ok


class UploadExecutionSummary(BaseModel):
    """Comprehensive summary report for Supabase upload execution."""
    total_articles_staged: int = 0
    articles_inserted: int = 0
    articles_linked: int = 0
    articles_failed: int = 0
    articles_blocked: int = 0
    articles_unknown: int = 0

    total_comments_staged: int = 0
    comments_inserted: int = 0
    comments_failed: int = 0
    comments_skipped: int = 0
    comments_unknown: int = 0

    unknown_outcomes: int = 0

    article_results: List[UploadRecordResult] = Field(default_factory=list)
    comment_results: List[UploadRecordResult] = Field(default_factory=list)

    staging_article_id_map: Dict[int, int] = Field(default_factory=dict)  # staging_id -> real_id
    staging_comment_id_map: Dict[int, int] = Field(default_factory=dict)  # staging_id -> real_id

    logs: List[str] = Field(default_factory=list)

    @property
    def success(self) -> bool:
        """Returns True if zero articles/comments failed and zero unknown outcomes occurred."""
        return self.articles_failed == 0 and self.comments_failed == 0 and self.unknown_outcomes == 0 and self.articles_blocked == 0

    def format_summary_text(self) -> str:
        """Formats human-readable summary text report."""
        lines = [
            "==================================================",
            "        SUPABASE DIRECT UPLOAD SUMMARY REPORT      ",
            "==================================================",
            f"Overall Status: {'SUCCESS' if self.success else 'COMPLETED WITH ISSUES / WARNINGS'}",
            "",
            "--- Articles Summary ---",
            f"  Staged:    {self.total_articles_staged}",
            f"  Inserted:  {self.articles_inserted}",
            f"  Linked:    {self.articles_linked} (existing DB articles matched)",
            f"  Failed:    {self.articles_failed}",
            f"  Blocked:   {self.articles_blocked} (Case D title conflicts)",
            f"  Unknown:   {self.articles_unknown}",
            "",
            "--- Comments Summary ---",
            f"  Staged:    {self.total_comments_staged}",
            f"  Inserted:  {self.comments_inserted}",
            f"  Failed:    {self.comments_failed}",
            f"  Skipped:   {self.comments_skipped} (parent article failed/blocked)",
            f"  Unknown:   {self.comments_unknown}",
            "",
            f"Total Unknown Outcomes: {self.unknown_outcomes}",
            "=================================================="
        ]
        return "\n".join(lines)


class SupabaseUploader:
    """
    Handles dry-run verification and direct transactional upload to Supabase.
    """

    def __init__(self, client: SupabaseClient):
        self.client = client

    def run_dry_run(self, dataset: SupabaseStagingDataset) -> UploadDryRunResult:
        """
        Performs a strictly read-only pre-upload dry run using GET requests.
        Verifies connectivity, API key validity, read access, active role, and analyzes article conflicts.
        Does NOT execute any INSERT/UPDATE/DELETE operations.
        """
        result = UploadDryRunResult()
        result.active_role = "authenticated" if self.client.is_authenticated() else "anon"

        # 1. Connectivity & Read Access Check
        status, data = self.client.get("articles", params={"select": "id,url,title", "limit": "100"})

        if status == 200:
            result.connectivity_ok = True
            result.api_key_valid = True
            result.read_access_ok = True
            db_articles = data if isinstance(data, list) else []
        elif status in (401, 403):
            result.connectivity_ok = True
            result.api_key_valid = False
            result.read_access_ok = False
            result.error_message = f"Read access denied (HTTP {status}): Invalid API key or RLS policy restricts SELECT."
            result.can_proceed = False
            return result
        else:
            result.connectivity_ok = False
            result.error_message = f"Supabase GET request failed (HTTP {status}): {data}"
            result.can_proceed = False
            return result

        # Map existing database articles by url and title
        existing_by_url = {}
        existing_by_title = {}

        for db_art in db_articles:
            if isinstance(db_art, dict):
                art_id = db_art.get("id")
                url = (db_art.get("url") or "").strip()
                title = (db_art.get("title") or "").strip().lower()

                if url:
                    existing_by_url[url] = art_id
                if title:
                    existing_by_title[title] = art_id

        # 2. Analyze Dataset Article Conflicts (Cases A-D)
        for art in dataset.articles:
            staged_url = (art.url or "").strip()
            staged_title = (art.title or "").strip().lower()

            match_id = existing_by_url.get(staged_url)

            if not match_id:
                # Check for Case D title collision with different URL
                if staged_title in existing_by_title:
                    result.article_case_d_blocks += 1
                    result.article_cases[art.id] = "Case D"
                    result.article_conflict_messages[art.id] = f"Case D Conflict: Matching title '{art.title}' exists in DB under a different URL."
                else:
                    # Case A: New Article Insert
                    result.article_case_a_inserts += 1
                    result.article_cases[art.id] = "Case A"
            else:
                # Case B: Clean Match on URL
                result.article_case_b_links += 1
                result.article_cases[art.id] = "Case B"
                result.article_matched_ids[art.id] = match_id

        # Can proceed if read access is OK and zero Case D title conflicts block execution
        result.can_proceed = result.read_access_verified and (result.article_case_d_blocks == 0)
        return result

    def execute_upload(
        self,
        dataset: SupabaseStagingDataset,
        dry_run_result: Optional[UploadDryRunResult] = None,
        progress_callback: Optional[Any] = None
    ) -> UploadExecutionSummary:
        """
        Executes actual live upload of staged articles and comments to Supabase.
        """
        if dry_run_result is None:
            dry_run_result = self.run_dry_run(dataset)

        summary = UploadExecutionSummary(
            total_articles_staged=len(dataset.articles),
            total_comments_staged=len(dataset.comments)
        )

        if not dry_run_result.can_proceed:
            summary.logs.append(f"Upload aborted: {dry_run_result.error_message or 'Dry run failed or Case D block encountered'}")
            return summary

        # 1. Process Articles
        for art in dataset.articles:
            case = dry_run_result.article_cases.get(art.id, "Case A")

            if case in ("Case B", "Case C"):
                real_id = dry_run_result.article_matched_ids.get(art.id)
                if real_id:
                    summary.staging_article_id_map[art.id] = real_id
                    summary.articles_linked += 1
                    summary.article_results.append(UploadRecordResult(
                        record_type="article",
                        staging_id=art.id,
                        real_id=real_id,
                        status="linked",
                        notes=f"Linked to existing DB article ID {real_id} ({case})"
                    ))
            elif case == "Case D":
                summary.articles_blocked += 1
                summary.article_results.append(UploadRecordResult(
                    record_type="article",
                    staging_id=art.id,
                    status="blocked",
                    notes="Blocked due to Case D title collision with different URL"
                ))
            else:
                # Case A: Execute INSERT
                art_payload = art.model_dump(exclude={"id"}, exclude_none=True)

                status, data = self.client.post("articles", art_payload, prefer_return=True)

                if status == 201:
                    inserted_rec = data[0] if isinstance(data, list) and len(data) > 0 else (data if isinstance(data, dict) else {})
                    real_id = inserted_rec.get("id")
                    if real_id:
                        summary.staging_article_id_map[art.id] = real_id
                        summary.articles_inserted += 1
                        summary.article_results.append(UploadRecordResult(
                            record_type="article",
                            staging_id=art.id,
                            real_id=real_id,
                            status="inserted",
                            notes="Successfully inserted new article"
                        ))
                    else:
                        summary.articles_unknown += 1
                        summary.unknown_outcomes += 1
                        summary.article_results.append(UploadRecordResult(
                            record_type="article",
                            staging_id=art.id,
                            status="unknown",
                            notes="HTTP 201 received but no ID returned"
                        ))
                elif status in (401, 403):
                    summary.articles_failed += 1
                    summary.article_results.append(UploadRecordResult(
                        record_type="article",
                        staging_id=art.id,
                        status="failed",
                        message=f"RLS/Permission denied (HTTP {status}): {data}"
                    ))
                elif status == 409:
                    # Conflict during concurrent insert: attempt reconciliation
                    reconcile_status, reconcile_data = self.client.get("articles", params={"url": f"eq.{art.url}"})
                    if reconcile_status == 200 and isinstance(reconcile_data, list) and len(reconcile_data) > 0:
                        real_id = reconcile_data[0].get("id")
                        summary.staging_article_id_map[art.id] = real_id
                        summary.articles_linked += 1
                        summary.article_results.append(UploadRecordResult(
                            record_type="article",
                            staging_id=art.id,
                            real_id=real_id,
                            status="linked",
                            notes=f"Reconciled 409 conflict to existing article ID {real_id}"
                        ))
                    else:
                        summary.articles_failed += 1
                        summary.article_results.append(UploadRecordResult(
                            record_type="article",
                            staging_id=art.id,
                            status="failed",
                            message=f"HTTP 409 conflict could not be reconciled: {data}"
                        ))
                else:
                    # Unknown outcome / 500 / timeout: perform reconciliation search
                    reconcile_status, reconcile_data = self.client.get("articles", params={"url": f"eq.{art.url}"})
                    if reconcile_status == 200 and isinstance(reconcile_data, list) and len(reconcile_data) > 0:
                        real_id = reconcile_data[0].get("id")
                        summary.staging_article_id_map[art.id] = real_id
                        summary.articles_inserted += 1
                        summary.article_results.append(UploadRecordResult(
                            record_type="article",
                            staging_id=art.id,
                            real_id=real_id,
                            status="inserted",
                            notes=f"Reconciled unknown status {status} to existing article ID {real_id}"
                        ))
                    else:
                        summary.articles_unknown += 1
                        summary.unknown_outcomes += 1
                        summary.article_results.append(UploadRecordResult(
                            record_type="article",
                            staging_id=art.id,
                            status="unknown",
                            message=f"INSERT failed with status {status} and could not be reconciled: {data}"
                        ))

        # 2. Process Comments
        for cmt in dataset.comments:
            real_art_id = summary.staging_article_id_map.get(cmt.article_id)

            if not real_art_id:
                summary.comments_skipped += 1
                summary.comment_results.append(UploadRecordResult(
                    record_type="comment",
                    staging_id=cmt.id,
                    status="skipped",
                    notes=f"Skipped comment: parent staged article ID {cmt.article_id} was not inserted or linked"
                ))
                continue

            real_parent_id = None
            if cmt.parent_comment_id is not None:
                real_parent_id = summary.staging_comment_id_map.get(cmt.parent_comment_id)
                if real_parent_id is None:
                    summary.comments_skipped += 1
                    summary.comment_results.append(UploadRecordResult(
                        record_type="comment",
                        staging_id=cmt.id,
                        status="skipped",
                        notes=f"Skipped reply: parent staged comment ID {cmt.parent_comment_id} was not inserted"
                    ))
                    continue

            cmt_payload = cmt.model_dump(exclude={"id"}, exclude_none=True)
            cmt_payload["article_id"] = real_art_id
            cmt_payload["parent_comment_id"] = real_parent_id

            status, data = self.client.post("comments", cmt_payload, prefer_return=True)

            if status == 201:
                inserted_rec = data[0] if isinstance(data, list) and len(data) > 0 else (data if isinstance(data, dict) else {})
                real_c_id = inserted_rec.get("id")
                if real_c_id:
                    summary.staging_comment_id_map[cmt.id] = real_c_id
                    summary.comments_inserted += 1
                    summary.comment_results.append(UploadRecordResult(
                        record_type="comment",
                        staging_id=cmt.id,
                        real_id=real_c_id,
                        status="inserted",
                        notes="Successfully inserted comment"
                    ))
                else:
                    summary.comments_unknown += 1
                    summary.unknown_outcomes += 1
                    summary.comment_results.append(UploadRecordResult(
                        record_type="comment",
                        staging_id=cmt.id,
                        status="unknown",
                        notes="HTTP 201 received but no comment ID returned"
                    ))
            elif status in (401, 403):
                summary.comments_failed += 1
                summary.comment_results.append(UploadRecordResult(
                    record_type="comment",
                    staging_id=cmt.id,
                    status="failed",
                    message=f"RLS/Permission denied inserting comment (HTTP {status}): {data}"
                ))
            else:
                summary.comments_failed += 1
                summary.comment_results.append(UploadRecordResult(
                    record_type="comment",
                    staging_id=cmt.id,
                    status="failed",
                    message=f"Comment INSERT failed with status {status}: {data}"
                ))

        return summary
