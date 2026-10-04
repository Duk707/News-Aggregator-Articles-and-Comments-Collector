"""
REST API Client for Supabase Integration (Step 29).
Handles HTTP communication with Supabase PostgREST and Auth endpoints using requests.
Enforces client-safe headers and supports optional user authentication (Auth API).
"""
import requests
from typing import Optional, Dict, Any, Tuple
from src.integrations.supabase.config import SupabaseClientConfig


class SupabaseClient:
    """
    Client for interacting with Supabase PostgREST REST API and Auth service.
    Uses anon key for public access and optional JWT access token for authenticated access.
    Never uses or accepts service_role keys.
    """

    def __init__(self, config: Optional[SupabaseClientConfig] = None, url: str = "", anon_key: str = ""):
        if config is not None:
            self.config = config
        else:
            self.config = SupabaseClientConfig(supabase_url=url, supabase_anon_key=anon_key)
        
        self.auth_token: Optional[str] = self.config.auth_token

    def is_authenticated(self) -> bool:
        """Returns True if an active user JWT auth token is present."""
        return bool(self.auth_token)

    def login(self, email: str, password: str) -> Dict[str, Any]:
        """
        Authenticates a user using email/password against Supabase Auth endpoint.
        On success, stores the JWT access_token in memory.
        """
        auth_url = f"{self.config.get_auth_url()}/token?grant_type=password"
        headers = {
            "apikey": self.config.supabase_anon_key,
            "Content-Type": "application/json"
        }
        payload = {
            "email": email,
            "password": password
        }

        response = requests.post(auth_url, json=payload, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token")
            if token:
                self.auth_token = token
                self.config.auth_token = token
            return data
        else:
            err_msg = f"Authentication failed (HTTP {response.status_code}): {response.text}"
            raise ValueError(err_msg)

    def authenticate_user(self, email: str, password: str) -> Dict[str, Any]:
        """Alias for login."""
        return self.login(email, password)

    def _build_headers(self, prefer_return: bool = False, prefer_resolution: Optional[str] = None) -> Dict[str, str]:
        """
        Constructs HTTP request headers required for Supabase REST API requests.
        """
        bearer_token = self.auth_token if self.auth_token else self.config.supabase_anon_key
        headers = {
            "apikey": self.config.supabase_anon_key,
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json"
        }

        prefer_parts = []
        if prefer_return:
            prefer_parts.append("return=representation")
        if prefer_resolution:
            prefer_parts.append(f"resolution={prefer_resolution}")

        if prefer_parts:
            headers["Prefer"] = ",".join(prefer_parts)

        return headers

    def get(self, table: str, params: Optional[Dict[str, Any]] = None) -> Tuple[int, Any]:
        """
        Executes a GET query on a table.
        Returns tuple of (status_code, response_data).
        """
        rest_url = f"{self.config.get_rest_url()}/{table}"
        headers = self._build_headers()

        response = requests.get(rest_url, headers=headers, params=params, timeout=15)
        try:
            data = response.json()
        except Exception:
            data = response.text

        return response.status_code, data

    def post(
        self,
        table: str,
        payload: Any,
        prefer_return: bool = True,
        prefer_resolution: Optional[str] = None
    ) -> Tuple[int, Any]:
        """
        Executes a POST insert on a table.
        Returns tuple of (status_code, response_data).
        """
        rest_url = f"{self.config.get_rest_url()}/{table}"
        headers = self._build_headers(prefer_return=prefer_return, prefer_resolution=prefer_resolution)

        response = requests.post(rest_url, json=payload, headers=headers, timeout=15)
        try:
            data = response.json()
        except Exception:
            data = response.text

        return response.status_code, data
