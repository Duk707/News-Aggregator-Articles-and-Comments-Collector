"""
Client-Safe Configuration Loader for Supabase Integration (Step 29).
Loads Supabase URL and Publishable/Anon Key from environment variables or untracked local config.
Enforces strict security rules: zero service_role keys, zero persistent user passwords or tokens on disk.
"""
import os
import json
from typing import Optional
from pydantic import BaseModel, Field


def sanitize_client_key(key: str) -> str:
    """
    Sanitizes and validates a client-safe key string.
    Rejects keys beginning with 'sb_secret_' or containing 'service_role'.
    Returns empty string if key is invalid, empty, or prohibited.
    """
    if not key or not str(key).strip():
        return ""
    cleaned = str(key).strip()
    if cleaned.lower().startswith("sb_secret_") or "service_role" in cleaned.lower():
        return ""
    return cleaned


class SupabaseClientConfig(BaseModel):
    """
    Client-safe configuration model storing only public project URL and Publishable/Anon Key.
    """
    supabase_url: str = Field(default="", description="Base Supabase project REST URL (e.g. https://xyz.supabase.co)")
    supabase_anon_key: str = Field(default="", description="Client-safe publishable/anon key")
    auth_token: Optional[str] = Field(default=None, description="Optional in-memory JWT token")

    def __init__(self, url: str = "", anon_key: str = "", publishable_key: str = "", **data):
        if url and "supabase_url" not in data:
            data["supabase_url"] = url
        resolved_key = publishable_key or anon_key
        if resolved_key and "supabase_anon_key" not in data:
            data["supabase_anon_key"] = resolved_key
        if "supabase_anon_key" in data:
            data["supabase_anon_key"] = sanitize_client_key(data["supabase_anon_key"])
        super().__init__(**data)

    @property
    def url(self) -> str:
        return self.supabase_url

    @property
    def anon_key(self) -> str:
        return self.supabase_anon_key

    @property
    def publishable_key(self) -> str:
        return self.supabase_anon_key

    def is_configured(self) -> bool:
        """Returns True if both URL and valid Publishable/Anon Key are non-empty."""
        return bool(self.supabase_url.strip() and self.supabase_anon_key.strip())

    def get_rest_url(self) -> str:
        """Returns normalized PostgREST base endpoint URL."""
        base = self.supabase_url.strip().rstrip('/')
        if not base.endswith('/rest/v1'):
            base = f"{base}/rest/v1"
        return base

    def get_auth_url(self) -> str:
        """Returns normalized Supabase Auth base endpoint URL."""
        base = self.supabase_url.strip().rstrip('/')
        if base.endswith('/rest/v1'):
            base = base[:-8]
        return f"{base}/auth/v1"


def load_supabase_config(config_dir: str = "data/config", config_path: Optional[str] = None) -> SupabaseClientConfig:
    """
    Loads SupabaseClientConfig from environment variables first, falling back to local JSON config file.
    Accepted environment variables (in strict priority order):
      1. SUPABASE_PUBLISHABLE_KEY (Preferred current client key)
      2. SUPABASE_ANON_KEY (Backward-compatible fallback)
    Does NOT accept generic SUPABASE_KEY, SUPABASE_SECRET_KEY, or sb_secret_ keys.
    """
    # 1. Environment Variable Precedence (SUPABASE_PUBLISHABLE_KEY -> SUPABASE_ANON_KEY)
    url_env = os.getenv("SUPABASE_URL", "").strip()
    raw_key_env = (
        os.getenv("SUPABASE_PUBLISHABLE_KEY", "").strip()
        or os.getenv("SUPABASE_ANON_KEY", "").strip()
    )
    key_env = sanitize_client_key(raw_key_env)

    if url_env and key_env and not config_path:
        return SupabaseClientConfig(supabase_url=url_env, supabase_anon_key=key_env)

    # 2. Local File Fallback
    target_paths = []
    if config_path:
        target_paths.append(config_path)
    target_paths.extend([
        os.path.join(config_dir, "supabase_client_config.json"),
        os.path.join(config_dir, "supabase.json")
    ])

    for json_path in target_paths:
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                url_file = data.get("supabase_url", "").strip() or data.get("url", "").strip() or url_env
                raw_key_file = (
                    data.get("publishable_key", "").strip()
                    or data.get("supabase_publishable_key", "").strip()
                    or data.get("anon_key", "").strip()
                    or data.get("supabase_anon_key", "").strip()
                    or key_env
                )
                key_file = sanitize_client_key(raw_key_file)
                return SupabaseClientConfig(supabase_url=url_file, supabase_anon_key=key_file)
            except Exception:
                pass

    return SupabaseClientConfig(supabase_url=url_env, supabase_anon_key=key_env)


def save_supabase_client_config(config: SupabaseClientConfig, config_dir: str = "data/config", config_path: Optional[str] = None) -> str:
    """
    Saves ONLY client-safe public URL and Publishable/Anon Key to local config file.
    Does NOT save secret keys, passwords, access tokens, refresh tokens, or service_role keys.
    """
    if config_path:
        json_path = config_path
        os.makedirs(os.path.dirname(os.path.abspath(config_path)), exist_ok=True)
    else:
        os.makedirs(config_dir, exist_ok=True)
        json_path = os.path.join(config_dir, "supabase_client_config.json")

    safe_data = {
        "supabase_url": config.supabase_url.strip(),
        "publishable_key": config.supabase_anon_key.strip(),
        "anon_key": config.supabase_anon_key.strip()
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(safe_data, f, indent=2)
    return json_path
