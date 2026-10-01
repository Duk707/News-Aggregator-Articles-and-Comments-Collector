"""
Unit and Integration Tests for Supabase Preview & Export GUI Components (Step 28).
Verifies preview row formatting (14 article columns, 5 comment columns), detail text rendering,
export button state gating (disabled on errors/empty, enabled on warnings/valid), additive
isolation on staging failures, custom directory export, state reset, and zero live DB access.
"""
import os
import unittest
from unittest.mock import MagicMock, patch
import tkinter as tk
from datetime import datetime, timezone

from src.models.article import Article
from src.models.comment import Comment, CommentStatus
from src.models.extraction import ExtractionResult
from src.integrations.supabase.models import (
    SupabaseArticleRow,
    SupabaseCommentRow,
    SupabaseStagingDataset
)
from src.integrations.supabase.mapper import SupabaseMapper
from src.gui.supabase_preview import (
    SUPABASE_ARTICLE_COLUMNS,
    SUPABASE_COMMENT_COLUMNS,
    truncate_text,
    format_supabase_article_tree_row,
    format_supabase_comment_tree_row,
    format_supabase_article_detail,
    format_supabase_comment_detail
)
from src.gui.app import CollectionApp


class TestSupabasePreviewFormatters(unittest.TestCase):
    """Tests Treeview row formatting and detail inspection rendering helpers."""

    def test_truncate_text(self):
        self.assertEqual(truncate_text(None), "")
        self.assertEqual(truncate_text("Short text"), "Short text")
        long_str = "A" * 100
        truncated = truncate_text(long_str, max_len=50)
        self.assertEqual(len(truncated), 53)  # 50 chars + "..."
        self.assertTrue(truncated.endswith("..."))

    def test_format_supabase_article_tree_row(self):
        row = SupabaseArticleRow(
            id=-1,
            title="A Very Long Article Title That Will Exceed Normal Cell Width Bounds",
            content="Full raw content text that goes on and on with extra details...",
            source="Yahoo News",
            created_at="2026-03-31T12:00:00Z",
            url="https://news.yahoo.com/test-article-url-that-is-quite-long.html",
            author="John Doe",
            published_date="2026-03-31",
            content_hash="abc123hash456789extra",
            clean_content="Clean content text extracted...",
            processing_status=None,
            processing_note=None,
            processed_at=None,
            is_relevant=True
        )

        formatted = format_supabase_article_tree_row(row)
        self.assertEqual(len(formatted), 14)
        self.assertEqual(formatted[0], "-1")  # id
        self.assertTrue(formatted[1].endswith("..."))  # truncated title
        self.assertEqual(formatted[3], "Yahoo News")  # source
        self.assertEqual(formatted[4], "2026-03-31T12:00:00Z")  # created_at
        self.assertEqual(formatted[6], "John Doe")  # author
        self.assertEqual(formatted[7], "2026-03-31")  # published_date
        self.assertEqual(formatted[10], "(NULL)")  # processing_status
        self.assertEqual(formatted[13], "True")  # is_relevant

    def test_format_supabase_comment_tree_row(self):
        row = SupabaseCommentRow(
            id=-101,
            article_id=-1,
            text="This is a test public comment on the article.",
            created_at="2026-03-31T12:05:00Z",
            parent_comment_id=None
        )

        formatted = format_supabase_comment_tree_row(row)
        self.assertEqual(len(formatted), 5)
        self.assertEqual(formatted[0], "-101")  # id
        self.assertEqual(formatted[1], "-1")  # article_id
        self.assertEqual(formatted[2], "This is a test public comment on the article.")  # text
        self.assertEqual(formatted[3], "2026-03-31T12:05:00Z")  # created_at
        self.assertEqual(formatted[4], "(Root)")  # parent_comment_id

    def test_format_supabase_article_detail(self):
        row = SupabaseArticleRow(
            id=-1,
            title="Sample Article",
            content="Raw content body",
            source="MSN",
            created_at="2026-03-31T12:00:00Z",
            url="https://www.msn.com/article",
            author="Jane Smith",
            published_date="2026-03-31",
            content_hash="hash123",
            clean_content="Clean body",
            is_relevant=True
        )

        detail_str = format_supabase_article_detail(row)
        self.assertIn("=== SUPABASE ARTICLE ROW INSPECTION (Staging ID: -1) ===", detail_str)
        self.assertIn("Sample Article", detail_str)
        self.assertIn("Jane Smith", detail_str)
        self.assertIn("--- Full Un-truncated Clean Content Body ---", detail_str)
        self.assertIn("Clean body", detail_str)

    def test_format_supabase_comment_detail(self):
        row = SupabaseCommentRow(
            id=-101,
            article_id=-1,
            text="Un-truncated detailed comment text.",
            created_at="2026-03-31T12:05:00Z",
            parent_comment_id=-100
        )

        detail_str = format_supabase_comment_detail(row)
        self.assertIn("=== SUPABASE COMMENT ROW INSPECTION (Staging ID: -101) ===", detail_str)
        self.assertIn("Article Staging ID: -1", detail_str)
        self.assertIn("Parent Comment ID:  -100", detail_str)
        self.assertIn("Un-truncated detailed comment text.", detail_str)


class TestSupabaseAppIntegration(unittest.TestCase):
    """Tests CollectionApp integration for Supabase staging preview, export gating, and state reset."""

    def setUp(self):
        try:
            self.root = tk.Tk()
            self.root.withdraw()  # Hide GUI window during automated tests
            self.app = CollectionApp(self.root)
        except tk.TclError:
            self.skipTest("Tkinter GUI display unavailable in headless test environment.")

    def tearDown(self):
        if hasattr(self, "root") and self.root:
            self.root.destroy()

    def test_preview_tabs_and_columns_exist(self):
        """Verifies Supabase staging tabs and treeview columns exist in the app."""
        tab_names = [self.app.notebook.tab(i, "text").strip() for i in range(self.app.notebook.index("end"))]
        self.assertIn("Supabase Articles Staging", tab_names)
        self.assertIn("Supabase Comments Staging", tab_names)

        art_cols = self.app.supabase_articles_tree["columns"]
        self.assertEqual(list(art_cols), list(SUPABASE_ARTICLE_COLUMNS))

        cm_cols = self.app.supabase_comments_tree["columns"]
        self.assertEqual(list(cm_cols), list(SUPABASE_COMMENT_COLUMNS))

    def test_export_button_gating_disabled_on_error(self):
        """Verifies btn_export_supabase is disabled when dataset has validation errors."""
        art_row = SupabaseArticleRow(
            id=-1,
            title="",  # Missing required title -> causes validation error
            content="Content",
            source="Yahoo",
            created_at="2026-03-31T12:00:00Z",
            url="https://news.yahoo.com/test",
            author="Author",
            published_date="2026-03-31",
            content_hash="hash",
            clean_content="Content"
        )
        dataset = SupabaseStagingDataset(
            articles=[art_row],
            comments=[],
            validation_errors=["Article -1 is missing a title"],
            validation_warnings=[]
        )

        self.app._handle_supabase_staging_complete(dataset, staging_error=None)
        self.assertEqual(str(self.app.btn_export_supabase["state"]), "disabled")
        self.assertIn("Invalid", self.app.lbl_supabase_status["text"])

    def test_export_button_gating_enabled_on_valid_or_warnings(self):
        """Verifies btn_export_supabase is enabled when dataset is valid or has warnings only."""
        art_row = SupabaseArticleRow(
            id=-1,
            title="Valid Title",
            content="Content",
            source="Yahoo",
            created_at="2026-03-31T12:00:00Z",
            url="https://news.yahoo.com/test",
            author="Author",
            published_date="2026-03-31",
            content_hash="hash",
            clean_content="Content"
        )
        dataset = SupabaseStagingDataset(
            articles=[art_row],
            comments=[],
            validation_errors=[],
            validation_warnings=["Warning: missing publication date on comment"]
        )

        self.app._handle_supabase_staging_complete(dataset, staging_error=None)
        self.assertEqual(str(self.app.btn_export_supabase["state"]), "normal")
        self.assertIn("Ready", self.app.lbl_supabase_status["text"])

    def test_additive_staging_failure_isolation(self):
        """
        Verifies that if SupabaseMapper raises an exception, the main thread handles it gracefully,
        logs the warning, disables Supabase export, but leaves the rest of the application intact.
        """
        self.app._handle_supabase_staging_complete(None, staging_error="Simulated Mapper Failure")
        self.assertIsNone(self.app.current_staging_dataset)
        self.assertEqual(str(self.app.btn_export_supabase["state"]), "disabled")
        self.assertIn("Simulated Mapper Failure", self.app.lbl_supabase_status["text"])

    @patch("src.gui.app.filedialog.askdirectory")
    @patch("src.gui.app.SupabaseCSVExporter.export")
    @patch("src.gui.app.messagebox.showinfo")
    def test_export_supabase_clicked_custom_dir(self, mock_showinfo, mock_export, mock_askdir):
        """Verifies custom directory selection and CSV export trigger."""
        mock_askdir.return_value = "C:/tmp/custom_export"
        mock_export.return_value = {
            "articles_csv": "C:/tmp/custom_export/articles_supabase.csv",
            "comments_csv": "C:/tmp/custom_export/comments_supabase.csv"
        }

        art_row = SupabaseArticleRow(
            id=-1,
            title="Title",
            content="Body",
            source="MSN",
            created_at="2026-03-31T12:00:00Z",
            url="https://www.msn.com/article",
            author="Author",
            published_date="2026-03-31",
            content_hash="hash",
            clean_content="Body"
        )
        dataset = SupabaseStagingDataset(
            articles=[art_row],
            comments=[],
            validation_errors=[],
            validation_warnings=[]
        )
        self.app.current_staging_dataset = dataset
        self.app.btn_export_supabase.config(state=tk.NORMAL)

        self.app._on_export_supabase_clicked()

        mock_askdir.assert_called_once()
        mock_export.assert_called_once_with(dataset, output_dir="C:/tmp/custom_export")
        mock_showinfo.assert_called_once()

    def test_start_clicked_resets_supabase_state(self):
        """Verifies that starting a new collection resets Supabase staging state and preview UI."""
        art_row = SupabaseArticleRow(
            id=-1,
            title="Old Article",
            content="Old Body",
            source="MSN",
            created_at="2026-03-31T12:00:00Z",
            url="https://www.msn.com/article",
            author="Author",
            published_date="2026-03-31",
            content_hash="hash",
            clean_content="Old Body"
        )
        dataset = SupabaseStagingDataset(articles=[art_row], comments=[], validation_errors=[], validation_warnings=[])
        self.app._handle_supabase_staging_complete(dataset, staging_error=None)
        self.assertIsNotNone(self.app.current_staging_dataset)

        # Set valid URL and delay so on_start_clicked proceeds past input validation
        self.app.url_text.delete("1.0", tk.END)
        self.app.url_text.insert(tk.END, "https://news.yahoo.com/test.html\n")

        with patch("threading.Thread") as mock_thread_cls:
            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread
            self.app.on_start_clicked()

        self.assertIsNone(self.app.current_staging_dataset)
        self.assertEqual(len(self.app.supabase_articles_tree.get_children()), 0)
        self.assertEqual(str(self.app.btn_export_supabase["state"]), "disabled")
        self.assertIn("in progress", self.app.lbl_supabase_status["text"])


if __name__ == "__main__":
    unittest.main()
