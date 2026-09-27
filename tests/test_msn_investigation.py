import os
import json
import pytest
from src.collectors.msn import MSNAdapter

def test_msn_adapter_url_recognition():
    """Verify MSNAdapter URL recognition for MSN domains."""
    adapter = MSNAdapter()
    assert adapter.supports("https://www.msn.com/en-us/news/politics/article/ar-AA1WCoGY") is True
    assert adapter.supports("https://msn.com/en-us/news") is True
    assert adapter.supports("https://news.yahoo.com/article.html") is False
    assert adapter.supports("https://example.com/msn") is False


def test_msn_diagnostic_artifacts_exist_and_valid():
    """Verify that Step 17 MSN diagnostic artifacts exist and contain valid evidence."""
    json_path = "data/diagnostics/msn_structure_investigation.json"
    html_path = "data/diagnostics/msn_article_rendered.html"
    
    assert os.path.exists(json_path), "JSON diagnostic artifact must exist"
    assert os.path.exists(html_path), "HTML rendered artifact must exist"
    
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    assert data["requested_url"].startswith("https://www.msn.com")
    assert data["http_success"] is True
    assert data["status_code"] == 200
    assert data["title"] is not None
    assert data["article_body_found"] is True
    assert data["paragraph_count"] > 0
    assert data["character_count"] > 1000
    assert data["comments_feature_present"] is True
    assert data["comment_control_found"] is True
    assert data["observed_comment_delivery_mechanism"] == "MSN_COMMUNITY_API_ENDPOINT"
    assert len(data["verified_comment_network_activity"]) > 0
    assert len(data["unrelated_network_activity_sample"]) > 0
