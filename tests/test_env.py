import sys
from playwright.sync_api import sync_playwright

def test_python_version():
    """Verify that Python 3.11+ is active."""
    assert sys.version_info >= (3, 11)

def test_playwright_chromium_launch():
    """Verify Playwright can launch Chromium and render HTML."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content("<h1>Environment Verification</h1>")
        heading = page.query_selector("h1").inner_text()
        browser.close()
        assert heading == "Environment Verification"
