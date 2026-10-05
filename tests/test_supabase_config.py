"""
Unit tests for SupabaseClientConfig and load_supabase_config resolution order.
Verifies SUPABASE_PUBLISHABLE_KEY precedence, SUPABASE_ANON_KEY fallback,
prohibition of SUPABASE_KEY and SUPABASE_SECRET_KEY, and sb_secret_ prefix rejection.
"""
import os
import json
import pytest

from src.integrations.supabase.config import (
    SupabaseClientConfig,
    load_supabase_config,
    save_supabase_client_config,
    sanitize_client_key
)


def test_publishable_key_accepted(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://publishable-test.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_pub_key_12345")
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)

    config = load_supabase_config()

    assert config.is_configured()
    assert config.url == "https://publishable-test.supabase.co"
    assert config.publishable_key == "sb_pub_key_12345"
    assert config.anon_key == "sb_pub_key_12345"


def test_publishable_key_precedence_over_anon_key(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://precedence-test.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "primary_pub_key")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "secondary_anon_key")

    config = load_supabase_config()

    assert config.is_configured()
    assert config.publishable_key == "primary_pub_key"
    assert config.anon_key == "primary_pub_key"


def test_anon_key_backward_compatible_fallback(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://fallback-test.supabase.co")
    monkeypatch.delenv("SUPABASE_PUBLISHABLE_KEY", raising=False)
    monkeypatch.setenv("SUPABASE_ANON_KEY", "legacy_anon_key_999")

    config = load_supabase_config()

    assert config.is_configured()
    assert config.publishable_key == "legacy_anon_key_999"
    assert config.anon_key == "legacy_anon_key_999"


def test_generic_supabase_key_ignored(monkeypatch):
    """
    Verifies that generic SUPABASE_KEY is ignored and does NOT configure the client.
    """
    monkeypatch.setenv("SUPABASE_URL", "https://generic-key-test.supabase.co")
    monkeypatch.delenv("SUPABASE_PUBLISHABLE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    monkeypatch.setenv("SUPABASE_KEY", "generic_key_should_be_ignored")

    config = load_supabase_config()

    assert not config.is_configured()
    assert config.publishable_key == ""
    assert config.anon_key == ""


def test_missing_client_keys_unconfigured(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://unconfigured-test.supabase.co")
    monkeypatch.delenv("SUPABASE_PUBLISHABLE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)

    config = load_supabase_config()

    assert not config.is_configured()
    assert config.publishable_key == ""
    assert config.anon_key == ""


def test_secret_key_prohibited_and_never_used_as_fallback(monkeypatch):
    """
    Verifies that SUPABASE_SECRET_KEY is ignored and never used as a key fallback.
    """
    monkeypatch.setenv("SUPABASE_URL", "https://secret-test.supabase.co")
    monkeypatch.delenv("SUPABASE_PUBLISHABLE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_key_do_not_use")

    config = load_supabase_config()

    # Must NOT be configured and must NOT load secret key
    assert not config.is_configured()
    assert config.publishable_key == ""
    assert config.anon_key == ""
    assert "sb_secret_key_do_not_use" not in config.model_dump_json()


def test_sb_secret_prefix_rejected_on_client_safe_fields(monkeypatch):
    """
    Verifies that any key beginning with 'sb_secret_' or containing 'service_role'
    is rejected even if passed via SUPABASE_PUBLISHABLE_KEY or SUPABASE_ANON_KEY.
    """
    monkeypatch.setenv("SUPABASE_URL", "https://secret-prefix-test.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_secret_fake_service_role_key_123")
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)

    config = load_supabase_config()

    assert not config.is_configured()
    assert config.publishable_key == ""
    assert config.anon_key == ""

    # Test direct model instantiation with secret key
    direct_cfg = SupabaseClientConfig(
        url="https://secret-prefix-test.supabase.co",
        publishable_key="sb_secret_prohibited"
    )
    assert not direct_cfg.is_configured()
    assert direct_cfg.publishable_key == ""


def test_local_json_loading_and_saving_publishable_key(tmp_path):
    config_dir = str(tmp_path)
    json_path = os.path.join(config_dir, "supabase_client_config.json")

    # Save initial config
    initial_config = SupabaseClientConfig(
        url="https://local-file-test.supabase.co",
        publishable_key="local_pub_key_888"
    )
    save_supabase_client_config(initial_config, config_dir=config_dir)

    assert os.path.exists(json_path)
    with open(json_path, "r", encoding="utf-8") as f:
        saved_data = json.load(f)

    assert saved_data["publishable_key"] == "local_pub_key_888"
    assert saved_data["anon_key"] == "local_pub_key_888"
    assert "secret_key" not in saved_data

    # Load back using load_supabase_config
    loaded = load_supabase_config(config_dir=config_dir, config_path=json_path)
    assert loaded.is_configured()
    assert loaded.url == "https://local-file-test.supabase.co"
    assert loaded.publishable_key == "local_pub_key_888"
