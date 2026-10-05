"""
Unit & Integration Tests for Supabase Direct Uploader (Step 29).
100% Mocked network calls — zero live network or database requests.
"""
import unittest
from unittest.mock import patch, MagicMock

from src.integrations.supabase.config import SupabaseClientConfig
from src.integrations.supabase.client import SupabaseClient
from src.integrations.supabase.uploader import SupabaseUploader
from src.integrations.supabase.models import SupabaseStagingDataset, SupabaseArticleRow, SupabaseCommentRow


class TestSupabaseUploader(unittest.TestCase):

    def setUp(self):
        self.config = SupabaseClientConfig(
            supabase_url="https://testproject.supabase.co",
            supabase_anon_key="test_anon_key_123"
        )
        self.client = SupabaseClient(config=self.config)
        self.uploader = SupabaseUploader(client=self.client)

        self.sample_dataset = SupabaseStagingDataset(
            articles=[
                SupabaseArticleRow(
                    id=-1,
                    source="Yahoo News",
                    url="https://news.yahoo.com/test-article-1",
                    title="Test Article Title",
                    content="Clean article text content."
                )
            ],
            comments=[
                SupabaseCommentRow(
                    id=-10,
                    article_id=-1,
                    parent_comment_id=None,
                    text="First top level comment"
                ),
                SupabaseCommentRow(
                    id=-11,
                    article_id=-1,
                    parent_comment_id=-10,
                    text="Reply to first comment"
                )
            ]
        )

    def test_client_config_and_urls(self):
        self.assertEqual(self.config.url, "https://testproject.supabase.co")
        self.assertEqual(self.config.anon_key, "test_anon_key_123")
        self.assertEqual(self.config.get_rest_url(), "https://testproject.supabase.co/rest/v1")
        self.assertEqual(self.config.get_auth_url(), "https://testproject.supabase.co/auth/v1")

    def test_client_headers_and_auth(self):
        headers = self.client._build_headers(prefer_return=True, prefer_resolution="merge-duplicates")
        self.assertEqual(headers["apikey"], "test_anon_key_123")
        self.assertEqual(headers["Authorization"], "Bearer test_anon_key_123")
        self.assertIn("return=representation", headers["Prefer"])
        self.assertIn("resolution=merge-duplicates", headers["Prefer"])

        self.client.auth_token = "jwt_user_token_999"
        headers_auth = self.client._build_headers()
        self.assertEqual(headers_auth["Authorization"], "Bearer jwt_user_token_999")

    @patch("src.integrations.supabase.client.requests.get")
    def test_dry_run_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_get.return_value = mock_resp

        result = self.uploader.run_dry_run(self.sample_dataset)

        self.assertTrue(result.connectivity_ok)
        self.assertTrue(result.api_key_valid)
        self.assertTrue(result.read_access_ok)
        self.assertTrue(result.can_proceed)
        self.assertEqual(result.article_case_a_inserts, 1)

    @patch("src.integrations.supabase.client.requests.get")
    def test_dry_run_auth_denied(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"
        mock_resp.json.side_effect = Exception("Not JSON")
        mock_get.return_value = mock_resp

        result = self.uploader.run_dry_run(self.sample_dataset)

        self.assertTrue(result.connectivity_ok)
        self.assertFalse(result.api_key_valid)
        self.assertFalse(result.read_access_ok)
        self.assertFalse(result.can_proceed)

    @patch("src.integrations.supabase.client.requests.post")
    @patch("src.integrations.supabase.client.requests.get")
    def test_upload_case_a_article_and_comment_success(self, mock_get, mock_post):
        # Dry run GET
        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = []
        mock_get.return_value = mock_get_resp

        # POST responses
        mock_post_art_resp = MagicMock()
        mock_post_art_resp.status_code = 201
        mock_post_art_resp.json.return_value = [{"id": 101, "title": "Test Article Title"}]

        mock_post_cmt1_resp = MagicMock()
        mock_post_cmt1_resp.status_code = 201
        mock_post_cmt1_resp.json.return_value = [{"id": 201, "text": "First top level comment"}]

        mock_post_cmt2_resp = MagicMock()
        mock_post_cmt2_resp.status_code = 201
        mock_post_cmt2_resp.json.return_value = [{"id": 202, "text": "Reply to first comment"}]

        mock_post.side_effect = [mock_post_art_resp, mock_post_cmt1_resp, mock_post_cmt2_resp]

        dry_run = self.uploader.run_dry_run(self.sample_dataset)
        summary = self.uploader.execute_upload(self.sample_dataset, dry_run_result=dry_run)

        self.assertTrue(summary.success)
        self.assertEqual(summary.articles_inserted, 1)
        self.assertEqual(summary.comments_inserted, 2)
        self.assertEqual(summary.staging_article_id_map[-1], 101)
        self.assertEqual(summary.staging_comment_id_map[-10], 201)
        self.assertEqual(summary.staging_comment_id_map[-11], 202)

    @patch("src.integrations.supabase.client.requests.post")
    @patch("src.integrations.supabase.client.requests.get")
    def test_upload_case_b_existing_article_link(self, mock_get, mock_post):
        # Dry run GET returns existing article matching URL
        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = [{
            "id": 999,
            "url": "https://news.yahoo.com/test-article-1",
            "title": "Test Article Title"
        }]
        mock_get.return_value = mock_get_resp

        # Comments POST responses
        mock_post_cmt1 = MagicMock()
        mock_post_cmt1.status_code = 201
        mock_post_cmt1.json.return_value = [{"id": 301}]

        mock_post_cmt2 = MagicMock()
        mock_post_cmt2.status_code = 201
        mock_post_cmt2.json.return_value = [{"id": 302}]

        mock_post.side_effect = [mock_post_cmt1, mock_post_cmt2]

        dry_run = self.uploader.run_dry_run(self.sample_dataset)
        self.assertEqual(dry_run.article_case_b_links, 1)

        summary = self.uploader.execute_upload(self.sample_dataset, dry_run_result=dry_run)

        self.assertTrue(summary.success)
        self.assertEqual(summary.articles_inserted, 0)
        self.assertEqual(summary.articles_linked, 1)
        self.assertEqual(summary.comments_inserted, 2)
        self.assertEqual(summary.staging_article_id_map[-1], 999)

    @patch("src.integrations.supabase.client.requests.get")
    def test_upload_case_d_title_conflict_block(self, mock_get):
        # Dry run GET returns existing article matching title under DIFFERENT url
        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = [{
            "id": 888,
            "url": "https://different.domain.com/other-url",
            "title": "Test Article Title"
        }]
        mock_get.return_value = mock_get_resp

        dry_run = self.uploader.run_dry_run(self.sample_dataset)
        self.assertEqual(dry_run.article_case_d_blocks, 1)
        self.assertFalse(dry_run.can_proceed)

    @patch("src.integrations.supabase.client.requests.post")
    @patch("src.integrations.supabase.client.requests.get")
    def test_upload_permission_denied_403(self, mock_get, mock_post):
        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = []
        mock_get.return_value = mock_get_resp

        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 403
        mock_post_resp.text = "RLS policy restricts INSERT on table articles"
        mock_post_resp.json.side_effect = Exception("Not JSON")
        mock_post.return_value = mock_post_resp

        dry_run = self.uploader.run_dry_run(self.sample_dataset)
        summary = self.uploader.execute_upload(self.sample_dataset, dry_run_result=dry_run)

        self.assertFalse(summary.success)
        self.assertEqual(summary.articles_failed, 1)
        self.assertEqual(summary.comments_skipped, 2)

    @patch("src.integrations.supabase.client.requests.post")
    @patch("src.integrations.supabase.client.requests.get")
    def test_upload_comment_created_at_omission_and_published_date(self, mock_get, mock_post):
        """
        Verifies that 'created_at' is omitted from comment POST payloads so PostgreSQL DEFAULT now() applies.
        Verifies that 'published_date' is included in POST payload when known and omitted when None.
        """
        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = []
        mock_get.return_value = mock_get_resp

        mock_post_art = MagicMock()
        mock_post_art.status_code = 201
        mock_post_art.json.return_value = [{"id": 100}]

        mock_post_cmt1 = MagicMock()
        mock_post_cmt1.status_code = 201
        mock_post_cmt1.json.return_value = [{"id": 501}]

        mock_post_cmt2 = MagicMock()
        mock_post_cmt2.status_code = 201
        mock_post_cmt2.json.return_value = [{"id": 502}]

        mock_post.side_effect = [mock_post_art, mock_post_cmt1, mock_post_cmt2]

        dataset = SupabaseStagingDataset(
            articles=[
                SupabaseArticleRow(id=-1, source="Granicus", url="https://ousd.granicusideas.com/item/1", title="Item 1", published_date="2026-08-12")
            ],
            comments=[
                SupabaseCommentRow(id=-10, article_id=-1, text="Comment missing date", created_at=None, published_date=None),
                SupabaseCommentRow(id=-11, article_id=-1, text="Comment with date", created_at=None, published_date="2026-10-03")
            ]
        )

        dry_run = self.uploader.run_dry_run(dataset)
        summary = self.uploader.execute_upload(dataset, dry_run_result=dry_run)

        self.assertTrue(summary.success)
        self.assertEqual(mock_post.call_count, 3)

        # Inspect POST payloads for comments (calls 1 and 2 after article call 0)
        cmt1_call_args = mock_post.call_args_list[1]
        cmt1_payload = cmt1_call_args[1]["json"] if "json" in cmt1_call_args[1] else cmt1_call_args[0][1]
        self.assertNotIn("created_at", cmt1_payload)
        self.assertNotIn("published_date", cmt1_payload)

        cmt2_call_args = mock_post.call_args_list[2]
        cmt2_payload = cmt2_call_args[1]["json"] if "json" in cmt2_call_args[1] else cmt2_call_args[0][1]
        self.assertNotIn("created_at", cmt2_payload)
        self.assertIn("published_date", cmt2_payload)
        self.assertEqual(cmt2_payload["published_date"], "2026-10-03")



if __name__ == "__main__":
    unittest.main()
