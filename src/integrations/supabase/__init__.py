"""
Supabase compatibility, staging, validation, and export module.
"""

from src.integrations.supabase.models import (
    SupabaseArticleRow,
    SupabaseCommentRow,
    SupabaseStagingDataset
)
from src.integrations.supabase.mapper import SupabaseMapper
from src.integrations.supabase.validation import SupabaseValidator
from src.integrations.supabase.exporter import SupabaseCSVExporter
from src.integrations.supabase.config import (
    SupabaseClientConfig,
    load_supabase_config,
    save_supabase_client_config
)
from src.integrations.supabase.client import SupabaseClient
from src.integrations.supabase.uploader import (
    SupabaseUploader,
    UploadDryRunResult,
    UploadExecutionSummary,
    UploadRecordResult
)

__all__ = [
    "SupabaseArticleRow",
    "SupabaseCommentRow",
    "SupabaseStagingDataset",
    "SupabaseMapper",
    "SupabaseValidator",
    "SupabaseCSVExporter",
    "SupabaseClientConfig",
    "load_supabase_config",
    "save_supabase_client_config",
    "SupabaseClient",
    "SupabaseUploader",
    "UploadDryRunResult",
    "UploadExecutionSummary",
    "UploadRecordResult"
]
