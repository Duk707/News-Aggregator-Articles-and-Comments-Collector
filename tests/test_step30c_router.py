"""
Integration unit tests for SourceRouter registration of Step 30C civic platform adapters.
"""
import pytest
from src.collectors.router import SourceRouter
from src.collectors.granicus_ideas import GranicusIdeasAdapter
from src.collectors.legistar import LegistarAdapter


def test_router_supports_granicus_ideas_and_legistar():
    router = SourceRouter()

    # 1. Granicus Ideas routing
    granicus_url = "https://ousd.granicusideas.com/meetings/2989/agenda_items/6a7902467d79659707005b5d"
    res, adapter = router.route(granicus_url)
    assert res.supported is True
    assert res.adapter_name == "GranicusIdeasAdapter"
    assert res.platform_name == "Granicus Ideas"
    assert isinstance(adapter, GranicusIdeasAdapter)

    # 2. Legistar routing
    legistar_url = "https://ousd.legistar.com/LegislationDetail.aspx?ID=100&GUID=ABC"
    res, adapter = router.route(legistar_url)
    assert res.supported is True
    assert res.adapter_name == "LegistarAdapter"
    assert res.platform_name == "Legistar"
    assert isinstance(adapter, LegistarAdapter)


def test_router_post_fetch_probe_granicus_ideas():
    router = SourceRouter()

    url = "https://civicportal.org/item/123"
    html = '<html><head><meta name="generator" content="GranicusIdeas v2.0"></head><body>Item</body></html>'

    res, adapter = router.route_by_html(url, html)
    assert res.supported is True
    assert res.adapter_name == "GranicusIdeasAdapter"
    assert isinstance(adapter, GranicusIdeasAdapter)
