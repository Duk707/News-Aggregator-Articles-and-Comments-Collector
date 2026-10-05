"""
Unit tests for LegistarAdapter and LegistarDiscovery (Step 30C).
"""
import os
import json
import pytest
from unittest.mock import MagicMock
from src.collectors.legistar import LegistarAdapter
from src.collectors.granicus_ideas import GranicusIdeasAdapter
from src.discovery.legistar import LegistarDiscovery
from src.models import CommentStatus

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def load_fixture(filename: str) -> str:
    path = os.path.join(FIXTURES_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def test_legistar_supports():
    adapter = LegistarAdapter()
    assert adapter.supports("https://ousd.legistar.com/LegislationDetail.aspx?ID=123") is True
    assert adapter.supports("https://houstonisd.legistar.com/LegislationDetail.aspx?ID=456") is True
    assert adapter.supports("https://example.com/article") is False


def test_legistar_extract_item_standalone():
    adapter = LegistarAdapter()
    html = load_fixture("legistar_item.html")

    url = "https://ousd.legistar.com/LegislationDetail.aspx?ID=100&GUID=ABC"
    result = adapter.extract(url, html=html)

    assert result.success is True
    assert result.article is not None
    assert "[25-3060]" in result.article.title
    assert "Board Policy 0441" in result.article.title
    assert result.article.original_publisher == "OUSD"
    # Standalone Legistar item without active cross-link defaults to UNKNOWN
    assert result.comments_status == CommentStatus.UNKNOWN
    assert result.article.comments_collected == 0
    assert any("Public comment surface was not resolved" in note for note in result.diagnostic_notes)


def test_legistar_extract_item_cross_linked():
    leg_adapter = LegistarAdapter()
    gran_adapter = GranicusIdeasAdapter()

    leg_html = load_fixture("legistar_item.html")
    p1_html = load_fixture("granicus_ideas_ousd_p1.html")

    gran_url = "https://ousd.granicusideas.com/meetings/2989/agenda_items/6a7902467d79659707005b5d"
    leg_url = "https://ousd.legistar.com/LegislationDetail.aspx?ID=100"

    result = leg_adapter.extract(
        leg_url,
        html=leg_html,
        granicus_adapter=gran_adapter,
        cross_link_url=gran_url,
        html_override=p1_html
    )

    assert result.success is True
    assert result.article is not None
    # GranicusIdeasAdapter extracts comments and sets AVAILABLE
    assert result.comments_status == CommentStatus.AVAILABLE
    assert result.article.comments_collected > 0


def test_legistar_discovery_odata_escaping():
    discovery = LegistarDiscovery()
    raw_kw = "AI's impact on education & 'ethics'"
    escaped = discovery.escape_odata_string(raw_kw)
    assert escaped == "AI''s impact on education & ''ethics''"


def test_legistar_discovery_search_matters_offline():
    discovery = LegistarDiscovery()

    # Mock HTTP session for offline zero-network test
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = json.loads(load_fixture("legistar_api_matters.json"))
    mock_session.get.return_value = mock_resp

    matters = discovery.search_matters("ousd", "Artificial Intelligence", http_session=mock_session)
    assert len(matters) == 2
    assert matters[0]["MatterFile"] == "25-3060"
    assert matters[0]["MatterTitle"] == "Board Policy 0441 — Artificial Intelligence"


def test_legistar_discovery_composite_cross_linking_unique():
    discovery = LegistarDiscovery()

    matter = {
        "MatterFile": "25-3060",
        "MatterTitle": "Board Policy 0441 — Artificial Intelligence",
        "MatterDate": "2026-08-12T00:00:00Z"
    }

    candidates = [
        {
            "url": "https://ousd.granicusideas.com/meetings/2989/agenda_items/6a7902467d79659707005b5d",
            "file_number": "25-3060",
            "title": "Board Policy 0441 — Artificial Intelligence",
            "date": "2026-08-12"
        }
    ]

    matched_url, status = discovery.cross_link_granicus_ideas(matter, candidates)
    assert matched_url == "https://ousd.granicusideas.com/meetings/2989/agenda_items/6a7902467d79659707005b5d"
    # Resolution finds candidate URL, but status remains UNKNOWN until extraction
    assert status == CommentStatus.UNKNOWN


def test_legistar_discovery_composite_cross_linking_ambiguous():
    discovery = LegistarDiscovery()

    matter = {
        "MatterFile": "25-3060",
        "MatterTitle": "Board Policy 0441 — Artificial Intelligence",
        "MatterDate": "2026-08-12T00:00:00Z"
    }

    # Two candidate URLs matching the same matter
    candidates = [
        {
            "url": "https://ousd.granicusideas.com/item/1",
            "file_number": "25-3060",
            "title": "Board Policy 0441 — Artificial Intelligence",
            "date": "2026-08-12"
        },
        {
            "url": "https://ousd.granicusideas.com/item/2",
            "file_number": "25-3060",
            "title": "Board Policy 0441 — Artificial Intelligence",
            "date": "2026-08-12"
        }
    ]

    matched_url, status = discovery.cross_link_granicus_ideas(matter, candidates)
    assert matched_url is None
    assert status == CommentStatus.UNKNOWN


def test_legistar_discovery_composite_cross_linking_zero_match():
    discovery = LegistarDiscovery()

    matter = {
        "MatterFile": "25-3060",
        "MatterTitle": "Board Policy 0441 — Artificial Intelligence",
        "MatterDate": "2026-08-12T00:00:00Z"
    }

    candidates = [
        {
            "url": "https://ousd.granicusideas.com/item/99",
            "file_number": "99-9999",
            "title": "Unrelated Park Maintenance",
            "date": "2020-01-01"
        }
    ]

    matched_url, status = discovery.cross_link_granicus_ideas(matter, candidates)
    assert matched_url is None
    assert status == CommentStatus.UNKNOWN
