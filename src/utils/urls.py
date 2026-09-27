from typing import Optional
from urllib.parse import urlparse


def validate_url(url: str) -> bool:
    """
    Validates whether a given string is a syntactically valid HTTP/HTTPS URL.

    Args:
        url: The string URL to validate.

    Returns:
        bool: True if the URL has a valid scheme (http/https) and network location domain.
    """
    if not isinstance(url, str) or not url.strip():
        return False

    try:
        parsed = urlparse(url.strip())
        # Must have http/https scheme and a non-empty domain/netloc
        if parsed.scheme.lower() not in ("http", "https"):
            return False
        if not parsed.netloc:
            return False
        # Basic check for period in hostname (e.g., domain.tld) unless localhost
        hostname = parsed.hostname
        if not hostname or ("." not in hostname and hostname != "localhost"):
            return False
        return True
    except Exception:
        return False


def normalize_url(url: str) -> str:
    """
    Normalizes a URL by stripping leading/trailing whitespace.

    Args:
        url: The input URL.

    Returns:
        str: Cleaned URL string.
    """
    return url.strip() if isinstance(url, str) else ""


def extract_domain(url: str) -> Optional[str]:
    """
    Extracts the lowercase hostname/domain from a URL.

    Args:
        url: The input URL.

    Returns:
        Optional[str]: Hostname if valid URL, else None.
    """
    if not validate_url(url):
        return None
    try:
        parsed = urlparse(url.strip())
        return parsed.hostname.lower() if parsed.hostname else None
    except Exception:
        return None
