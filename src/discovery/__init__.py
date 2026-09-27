"""
Candidate Article Discovery Package.
Provides public news RSS discovery, URL link validation via SourceRouter,
keyword filtering, date range filtering, and structured provenance metadata.
"""
from src.discovery.models import CandidateArticle
from src.discovery.search import CandidateDiscoverer

__all__ = ["CandidateArticle", "CandidateDiscoverer"]
