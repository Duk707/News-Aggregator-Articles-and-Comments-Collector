import os
import json
from typing import Dict, Any

FIXTURES_DIR = os.path.dirname(os.path.abspath(__file__))


def load_fixture(filename: str) -> str:
    """
    Loads raw text content from a fixture file in tests/fixtures/.
    
    Args:
        filename: Name of fixture file (e.g. 'yahoo_article_observed.html').

    Returns:
        str: Raw text content of the fixture.
    """
    filepath = os.path.join(FIXTURES_DIR, filename)
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Fixture file not found: {filepath}")
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def load_json_fixture(filename: str) -> Dict[str, Any]:
    """
    Loads and parses JSON content from a fixture file in tests/fixtures/.

    Args:
        filename: Name of JSON fixture file (e.g. 'msn_peregrine_community_observed.json').

    Returns:
        dict: Parsed JSON data.
    """
    content = load_fixture(filename)
    return json.loads(content)
